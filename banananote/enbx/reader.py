"""Reader for Seewo EasiNote .enbx packages.

An .enbx file is a ZIP (OPC-like) package. Confirmed structure (verified
against EasiNote 5.2.4.11582 output):

    Board.xml                     slide size + ordered list of slide GUIDs
    Slides/Slide_{n}.xml          per-slide XML, <Id> GUID matches Board order
    Document.xml                  metadata
    thumbnail.png                 first-slide thumbnail
    SlideThumbnails/Slide_{n}.png per-slide thumbnails
    [Content_Types].xml           content type map
    (Resources/... | Media/...)   objects embed resources by file name

Element markup inside Slide XML is not publicly documented, so parsing is
tolerant/heuristic: known nodes are converted, unknown ones are reported via
`warnings` list on the returned doc so the UI can show a compatibility note.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET

from ..core.model import (
    DEFAULT_SLIDE_W,
    DEFAULT_SLIDE_H,
    Doc,
    ImageElement,
    InkElement,
    Page,
    ShapeElement,
    TextElement,
    b64encode,
)

REG_BY_ID = re.compile(r'^[0-9a-fA-F-]{32,36}$')


def _texts(node: ET.Element) -> str:
    return "".join(node.itertext()).strip()


def _first_child_text(node: ET.Element, tag: str) -> str:
    child = node.find(tag)
    return _texts(child) if child is not None else ""


def _float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        s = str(v).strip().rstrip("px")
        if not s:
            return default
        return float(s)
    except (TypeError, ValueError):
        return default


_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6})$")


def normalize_color(raw: str | None, default: str = "#FFFFFFFF") -> str:
    """Accepts #AARRGGBB / #RRGGBB, returns Qt-compatible #AARRGGBB."""
    if not raw:
        return default
    raw = raw.strip()
    m = re.search(r"^\s*#?([0-9a-fA-F]{8}|[0-9a-fA-F]{6})\s*$", raw)
    if not m:
        return default
    hexv = m.group(1)
    if len(hexv) == 6:
        hexv = "FF" + hexv
    return "#" + hexv


def _iter_resource_names(zf: zipfile.ZipFile) -> list[str]:
    out = []
    for name in zf.namelist():
        low = name.lower()
        if low.endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")):
            out.append(name)
    return out


def _decode_ink_points(raw: str) -> list[list[float]]:
    """Ink point lists come in 'x1,y1,x2,y2...' or 'x;y' style variants."""
    pts: list[list[float]] = []
    if not raw:
        return pts
    for pair in re.split(r"[|;]|(?<!^) (?= )", raw.replace("\n", "")):
        nums = re.findall(r"-?\d+(?:\.\d+)?", pair)
        if len(nums) >= 2:
            pts.append([float(nums[0]), float(nums[1])]
                       + ([float(nums[2])] if len(nums) >= 3 else []))
    return pts


def _collect_text_payload(node: ET.Element) -> str:
    """Gather human-visible text from a text-ish node."""
    chunks: list[str] = []
    for sub in node.iter():
        if sub.tag.endswith(("Text", "TextContent", "Content", "String")):
            t = _texts(sub)
            if t:
                chunks.append(t)
    return "\n".join(chunks)


def _try_parse_image(node: ET.Element, zf: zipfile.ZipFile,
                     resources: dict[str, str]) -> ImageElement | None:
    name = node.get("Name") or node.get("FileName") or node.get("ResourceName") or ""
    refs = [name] if name else []
    # any attribute / child text that looks like a resource path
    for v in [node.get(a) for a in node.attrib.keys()]:
        if isinstance(v, str) and ("Resources/" in v or "Media/" in v):
            refs.append(v.split("/")[-1])
    data: bytes | None = None
    for ref in refs:
        key = ref.strip().split("/")[-1]
        if key in resources:
            data = zf.read(resources[key])
            break
    if data is None:
        return None
    # size/radius/dim children often enclose geometry
    w = _float(node.get("Width")) or _float(_first_child_text(node, "Width"), 100)
    h = _float(node.get("Height")) or _float(_first_child_text(node, "Height"), 80)
    x = _float(node.get("Left")) or _float(_first_child_text(node, "Left") or node.get("X"), 0)
    y = _float(node.get("Top")) or _float(_first_child_text(node, "Top") or node.get("Y"), 0)
    return ImageElement(x=x, y=y, width=w, height=h, data_b64=b64encode(data))


def parse_slide(root: ET.Element, zf: zipfile.ZipFile,
                resources: dict[str, str],
                doc: Doc) -> Page:
    page = Page()
    page.w = _float(_first_child_text(root, "Width"), doc.width)
    page.h = _float(_first_child_text(root, "Height"), doc.height)
    page.background = normalize_color(_first_child_text(root, "ColorBrush"))

    for bg in root.iter():
        if bg.tag.endswith("Background"):
            page.background = normalize_color(
                _first_child_text(bg, "ColorBrush"), page.background)

    unknown_tags: list[str] = []
    for node in root.iter():
        tag = node.tag
        low = tag.lower()
        if low in ("slide", "width", "height", "keepindependentsize",
                   "background", "duration", "themeforslide", "themeid",
                   "colorbrush", "id"):
            continue

        if "text" in low and not node.get("_consumed"):
            payload = _collect_text_payload(node)
            if payload:
                page.elements.append(TextElement(
                    x=_float(node.get("X") or node.get("Left")),
                    y=_float(node.get("Y") or node.get("Top")),
                    text=payload,
                    font_size=_float(node.get("FontSize"), 24),
                    color=normalize_color(node.get("Color") or
                                          node.get("FontColor") or "#FF202020"),
                ))
                continue

        if "ink" in low or "stroke" in low:
            pts = _decode_ink_points(
                node.get("Points") or node.get("PointList") or
                _texts(node.find("Points") if node.find("Points") is not None else node))
            if not pts:
                continue
            stroke = {
                "color": normalize_color(node.get("Color") or
                                         _first_child_text(node, "ColorBrush") or
                                         "#FF000000"),
                "width": _float(node.get("Width") or
                                _first_child_text(node, "Width"), 3.0),
                "points": pts,
            }
            # merge strokes of the same ink element into one InkElement
            if not (page.elements and isinstance(page.elements[-1], InkElement)):
                page.elements.append(InkElement())
            page.elements[-1].strokes.append(stroke)
            continue

        if "image" in low or "picture" in low or "photo" in low:
            img = _try_parse_image(node, zf, resources)
            if img is not None:
                page.elements.append(img)
                continue

        if any(k in low for k in ("shape", "rect", "ellipse", "polygon", "line")):
            page.elements.append(ShapeElement(
                x=_float(node.get("X") or node.get("Left"), 80),
                y=_float(node.get("Y") or node.get("Top"), 80),
                width=_float(node.get("Width"), 120),
                height=_float(node.get("Height"), 80),
                shape="ellipse" if "ellipse" in low else
                      "line" if "line" in low else "rect",
                stroke_color=normalize_color(
                    node.get("StrokeColor") or _first_child_text(node, "ColorBrush"),
                    "#FF303030")))
            continue

        if low not in unknown_tags and REG_BY_ID.match(_texts(node) or "") is None:
            unknown_tags.append(tag)

    if unknown_tags:
        doc.warnings.append(
            f"slide has unsupported element tags (ignored): "
            f"{', '.join(sorted(set(unknown_tags))[:8])}")

    return page


def read_enbx(path: str) -> Doc:
    """Main entry: load an .enbx package into a Doc. Raises ValueError/KeyError on junk input."""
    from xml.etree import ElementTree as _ET  # noqa: F401 (import guard for pystubs)

    zf = zipfile.ZipFile(path)
    names = set(zf.namelist())
    if "Board.xml" not in names:
        raise ValueError("not an enbx package: missing Board.xml")

    doc = Doc()
    doc.warnings = []  # type: ignore[attr-defined]

    board = ET.fromstring(zf.read("Board.xml"))
    doc.width = _float(_first_child_text(board, "SlideWidth"), DEFAULT_SLIDE_W)
    doc.height = _float(_first_child_text(board, "SlideHeight"), DEFAULT_SLIDE_H)

    try:
        docmeta = ET.fromstring(zf.read("Document.xml"))
        doc.name = _first_child_text(docmeta, "Name") or doc.name
    except (KeyError, ET.ParseError):
        pass

    # Board.xml may list GUID order; Slides/*.xml hold the real page data.
    ordered_ids = [s.strip() for s in
                   (_texts(it) for it in board.findall("Slides/Item")) if s.strip()]

    slide_files = sorted(
        (n for n in names if n.startswith("Slides/") and n.endswith(".xml")),
        key=lambda n: len(n))
    slides_by_id: dict[str, ET.Element] = {}
    slide_files_in_order: list[str] = []
    for fn in slide_files:
        try:
            root = ET.fromstring(zf.read(fn))
        except ET.ParseError:
            continue
        sid = _first_child_text(root, "Id")
        slides_by_id[sid] = root

    used: set[str] = set()
    ordered: list[str] = []
    for sid in ordered_ids:
        if sid in slides_by_id and sid not in used:
            ordered.append(sid)
            used.add(sid)

    # fallback: filename index order for docs whose GUID mapping is absent
    ordered = ordered if ordered else list(slides_by_id.keys())

    resources = {PurePosixPath(n).name: n for n in _iter_resource_names(zf)}
    for sid in ordered:
        root = slides_by_id[sid]
        doc.pages.append(parse_slide(root, zf, resources, doc))

    if not doc.pages:
        doc.pages.append(Page(w=doc.width, h=doc.height))
    for p in doc.pages:
        p.w = doc.width
        p.h = doc.height
    return doc
