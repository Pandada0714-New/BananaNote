"""Reader for Seewo EasiNote .enbx packages.

An .enbx file is a ZIP (OPC-like) package. Confirmed structure (verified
against EasiNote 5.x output):

    Board.xml                     slide size + ordered list of slide GUIDs
    Slides/Slide_{n}.xml          per-slide XML, <Id> GUID matches Board order
    Document.xml                  metadata
    thumbnail.png                 first-slide thumbnail
    SlideThumbnails/Slide_{n}.png per-slide thumbnails
    [Content_Types].xml           content type map
    Resources/...                 media payloads named "<uuid>[.ext]"

Since 26.1-prerelease-2 the slide parser is structural instead of
heuristic: it walks only the real element containers
(`Slide/Elements`, `Group/Elements`, widget subtrees) and converts each
known element type directly:

    Picture                -> ImageElement (+ crop / rotation)
    Shape/Ellipse/...      -> ShapeElement (rect/ellipse) or ink polyline
                              parsed from the Path data
    Text / RichText        -> TextElement (text, font, size, color)
    Group                  -> recursed with accumulated offsets
    Video / Audio          -> ImageElement (thumbnail / icon) + label
    Table                  -> cell rects + centered cell text
    Topic (mind map)       -> title + node texts at their locations
    ClassicalWorkElement   -> stacked title / author / body texts

Background: `ColorBrush` color or `ImageBrush` bitmap stretched to fill
(page.background_image). Animations and interactive behaviors are
ignored (they carry no static content) and reported in `doc.warnings`.
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
    b64decode,
    b64encode,
)

# Square "audio" placeholder icon for audio objects (no preview bitmap
# exists for sound in the package).
AUDIO_ICON_B64 = (
    "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"
    "QgghhGgE/wPoFXBhRpvGkAAAAABJRU5ErkJggg=="
)
_ELLIPSE_GEO = ("circle", "ellipse")
_RECT_GEO = ("rectangle", "roundrectangle", "square", "trapezoid",
             "parallelogram", "diamond", "cube")
_OPEN_GEO = ("freeline", "connector", "line", "arrow", "brace", "wave")

_PAIR = re.compile(r"-?\d+(?:\.\d+(?:[eE]-?\d+)?)?")


def normalize_color(raw: str | None, default: str = "#FFE8E8E8") -> str:
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


def _texts(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return "".join(node.itertext()).strip()


def _first_child_text(node: ET.Element | None, tag: str) -> str:
    if node is None:
        return ""
    return _texts(node.find(tag))


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


def _norm_guid(s: str) -> str:
    return re.sub(r"[\s{}-]", "", s or "").lower()


def _image_dims(data: bytes) -> tuple[int, int] | None:
    """Best-effort natural (w, h) of an image payload from its header."""
    import struct
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", data[16:24])
        return w, h
    if data[:3] == b"\xff\xd8\xff":  # jpeg
        i = 2
        while i < len(data) - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            ln = struct.unpack(">H", data[i + 2:i + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h
            i += 2 + ln
        return None
    if data[:2] == b"BM":
        w, h = struct.unpack("<ii", data[18:26])
        return abs(w), abs(h)
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        tag = data[12:16]
        if tag == b"VP8X":
            w = 1 + int.from_bytes(data[24:27], "little")
            h = 1 + int.from_bytes(data[27:30], "little")
            return w, h
        if tag == b"VP8L":
            bits = int.from_bytes(data[21:26], "little")
            return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
        if tag == b"VP8 ":
            return (int.from_bytes(data[26:28], "little") & 0x3FFF,
                    int.from_bytes(data[28:30], "little") & 0x3FFF)
    return None


class _Pkg:
    """Resource/lookup helpers bound to one open .enbx archive."""

    def __init__(self, zf: zipfile.ZipFile) -> None:
        self.zf = zf
        self._by_stem: dict[str, str] = {}
        self._by_name: dict[str, str] = {}
        self._cache: dict[str, bytes] = {}
        for name in zf.namelist():
            low = name.lower()
            if "/__!" in low or "thumbnail" in low:
                continue
            if low.endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp",
                             ".mp3", ".mp4", ".wav", ".avi")):
                self._by_name[PurePosixPath(name).name.lower()] = name
                base = PurePosixPath(name).name
                self._by_stem[PurePosixPath(base).stem.lower()] = name
            elif not PurePosixPath(name).suffix:  # extensionless hashed payloads
                base = PurePosixPath(name).name
                self._by_name[base.lower()] = name
                self._by_stem[base.lower()] = name

    def resolve(self, source: str | None) -> bytes | None:
        """Fetch payload bytes for an `id://<uuid>` or bare-name reference."""
        if not source:
            return None
        key = str(source).strip()
        if key.startswith("id:"):
            key = key.split("id:", 1)[1].lstrip("/")
        key = PurePosixPath(key.split("/")[0].split("?")[0].strip()).name.lower()
        if not key or len(key) != 32:
            return None
        real = self._by_stem.get(key) or self._by_name.get(key) \
            or self._by_stem.get(PurePosixPath(key).stem)
        if real is None:
            return None
        if real not in self._cache:
            try:
                self._cache[real] = self.zf.read(real)
            except (KeyError, zipfile.BadZipFile):
                self._cache[real] = b""
        return self._cache[real] or None


def _path_to_points(raw: str, step: int = 6) -> list[list[float]]:
    """Parse `M x,y L x,y C ... z` path data into an approximate polyline."""
    pts: list[list[float]] = []
    if not raw:
        return pts
    cmd = "M"
    cur: list[float] = []
    for tok in re.findall(r"[A-Za-z]|-?\d+(?:\.\d+)?(?:[eE]-?\d+)?", raw):
        if re.fullmatch(r"[A-Za-z]", tok):
            cmd = tok.upper()
            if cmd == "Z":
                if len(pts) >= 2:
                    pts.append(list(pts[0]))
                cur = []
            continue
        try:
            v = float(tok)
        except ValueError:
            continue
        cur.append(v)
        if cmd in "ML" and len(cur) >= 2:
            pts.append([cur[-2], cur[-1]])
            cur = []
        elif cmd == "C" and len(cur) == 6:
            x0, y0 = (pts[-1] if pts else [0.0, 0.0])
            cx1, cy1, cx2, cy2, x1, y1 = cur
            cur = []
            if cx1 == cx2 == x0 == x1:  # degenerate vertical curve
                pts.append([x1, y1])
                continue
            for i in range(1, step + 1):
                t = i / step
                mt = 1 - t
                bx = (mt ** 3 * x0 + 3 * mt * mt * t * cx1 +
                      3 * mt * t * t * cx2 + t ** 3 * x1)
                by = (mt ** 3 * y0 + 3 * mt * mt * t * cy1 +
                      3 * mt * t * t * cy2 + t ** 3 * y1)
                pts.append([bx, by])
    return pts


def _point_at(origin: tuple[float, float], pts: list[list[float]]) -> None:
    """Shift a path polyline by its element origin offset."""
    for p in pts:
        p[0] += origin[0]
        p[1] += origin[1]


# --------------------------------------------------------------------- text

def _rich_text(rich: ET.Element | None) -> tuple[str, float, str, str, bool]:
    """(text, font_size, font_family, color, bold) from a RichText-ish node."""
    if rich is None:
        return "", 0.0, "", "", False
    lines: list[str] = []
    size = 0.0
    font = ""
    color = ""
    bold = False
    for line in rich.iter("TextLine"):
        line_text = ""
        for run in line.iter("TextRun"):
            t = _first_child_text(run, "Text")
            if not t:
                continue
            line_text += t
            if not size:
                size = _float(_first_child_text(run, "FontSize"), 0) or \
                    _float(_first_child_text(rich, "FontSize"), 0)
            if not font:
                font = _first_child_text(run.find("FontFamily"), "Source") or \
                    _first_child_text(
                        run.find("DefaultRunProperty/FontFamily"), "Source")
            c = _first_child_text(run.find("Foreground"), "ColorBrush")
            if (not color or color.startswith("#00")) and c and \
                    not c.startswith("#00"):
                color = c
            if not bold:
                bold = _first_child_text(run, "FontWeight").lower() == "bold"
        if line_text:
            lines.append(line_text)
    if not size:  # lines with runs w/o Text but a DefaultRunProperty
        size = _float(_first_child_text(rich, "FontSize"), 0)
    if not color:
        color = _first_child_text(rich.find("Foreground"), "ColorBrush")
    return "\n".join(lines), size, font, color, bold


def _add_text(page: Page, node: ET.Element | None, x: float, y: float,
              text: str | None = None, size: float = 0.0, font: str = "",
              color: str = "", bold: bool = False,
              rotation: float = 0.0, width: float = 0.0) -> None:
    if node is not None:
        rich = node if node.tag == "RichText" else node.find("RichText")
        if rich is None and node.tag == "Text":
            rich = node.find("RichText")
        t, s, f, c, b = _rich_text(rich)
        text = t if text is None else text
        size = size or s
        font = font or f
        color = color or c
        bold = bold or b
    if not (text or "").strip():
        return
    page.elements.append(TextElement(
        x=x, y=y, text=text, font_size=size or 24.0, font=font,
        color=normalize_color(color) if color else "#FF464646",
        bold=bold, rotation=rotation, width=width))


# ------------------------------------------------------------------- images

def _parse_picture(el: ET.Element, pkg: _Pkg, page: Page,
                   dx: float, dy: float) -> None:
    data = pkg.resolve(_first_child_text(el, "Source"))
    if not data:
        return
    x = _float(_first_child_text(el, "X")) + dx
    y = _float(_first_child_text(el, "Y")) + dy
    w = _float(_first_child_text(el, "Width"), 100)
    h = _float(_first_child_text(el, "Height"), 80)
    rotation = _float(_first_child_text(el, "Rotation"), 0)
    crop = ""
    region = _first_child_text(el, "Rectangle")
    if region:
        # DisplayRegion is given in post-rotation coordinates; treat it as
        # x, y, width, height and drop it when it covers the whole payload.
        nums = _PAIR.findall(region)
        if len(nums) >= 4:
            cx, cy, cw, ch = (float(v) for v in nums[:4])
            natural = _image_dims(data)
            if natural:
                nw, nh = natural
                if round((rotation % 360) / 90) % 2 == 1:
                    nw, nh = nh, nw
                if cw < nw - 2 or ch < nh - 2:
                    crop = f"{cx:.2f},{cy:.2f},{cw:.2f},{ch:.2f}"
    page.elements.append(ImageElement(x=x, y=y, width=w, height=h,
                                      data_b64=b64encode(data),
                                      rotation=rotation,
                                      crop=crop))


def _parse_media(el: ET.Element, pkg: _Pkg, page: Page,
                 dx: float, dy: float, media: dict[str, list[str]]) -> None:
    """Video -> its thumbnail picture; Audio -> icon + name label."""
    name = _first_child_text(el, "MediaName")
    kind = el.tag.lower()
    x = _float(_first_child_text(el, "X")) + dx
    y = _float(_first_child_text(el, "Y")) + dy
    w = _float(_first_child_text(el, "Width"), 120)
    h = _float(_first_child_text(el, "Height"), 80)
    if kind == "video":
        data = pkg.resolve(_first_child_text(el, "Thumbnail")) or \
            pkg.resolve(_first_child_text(el, "Source"))
        if data and _image_dims(data):
            page.elements.append(ImageElement(x=x, y=y, width=w, height=h,
                                              data_b64=b64encode(data)))
            media.setdefault("video", []).append(name)
            return
    elif kind == "audio":
        icon_bytes = b64decode(AUDIO_ICON_B64)
        s = 48  # square icon centred in the object box
        page.elements.append(ImageElement(
            x=x + max(0, (w - s) / 2), y=y + max(0, (h - s) / 2),
            width=s, height=s, data_b64=AUDIO_ICON_B64))
        if name:
            page.elements.append(TextElement(
                x=x + w + 6, y=y + h / 2 - 14,
                text=name, font_size=18, color="#FF5A5F5A"))
        media.setdefault("audio", []).append(name)
        return
    media.setdefault("other", []).append(name or el.tag)


# ------------------------------------------------------------------- shapes

def _parse_shape(el: ET.Element, page: Page, dx: float, dy: float) -> None:
    x = _float(_first_child_text(el, "X")) + dx
    y = _float(_first_child_text(el, "Y")) + dy
    w = _float(_first_child_text(el, "Width"), 120)
    h = _float(_first_child_text(el, "Height"), 80)
    rotation = _float(_first_child_text(el, "Rotation"), 0)
    fill = normalize_color(_first_child_text(el, "Background/ColorBrush"))
    stroke = normalize_color(_first_child_text(el, "Foreground/ColorBrush"))
    thickness = _float(_first_child_text(el, "Thickness"), 2.0)

    geometry = el.find("Geometry")
    gtype = ""
    if geometry is not None:
        gtype = _first_child_text(geometry, "PresetGeometry/GeometryType") or \
            _first_child_text(geometry, "GeometryType")
    gtype = gtype.strip().lower() or "rectangle"

    if any(k in gtype for k in _ELLIPSE_GEO):
        if w <= 0 or h <= 0:
            return
        page.elements.append(ShapeElement(
            x=x, y=y, width=max(w, 1), height=max(h, 1), shape="ellipse",
            stroke_color=stroke, fill_color=fill,
            stroke_width=thickness, rotation=rotation))
        return
    if not any(k in gtype for k in _RECT_GEO):
        # open / custom path: draw as stroked polyline (keeps arrows,
        # braces, connectors and hand-drawn freeform shapes recognizable)
        pts = _path_to_points(_first_child_text(el, "Path"))
        if len(pts) >= 2:
            _point_at((x, y), pts)
            page.elements.append(InkElement(strokes=[{
                "color": stroke, "width": max(thickness, 0.5),
                "points": [[round(p[0], 2), round(p[1], 2)] for p in pts]}]))
            return
        if w <= 0 or h <= 0:
            return
    page.elements.append(ShapeElement(
        x=x, y=y, width=max(w, 1), height=max(h, 1), shape="rect",
        stroke_color=stroke, fill_color=fill,
        stroke_width=thickness, rotation=rotation))
    # shapes may carry an embedded caption (InlineText / Text)
    text_node = el.find("InlineText") if el.find("InlineText") is not None \
        else el.find("Text")
    if text_node is not None:
        margin_txt = _first_child_text(el, "TextMargin")
        margin = _float(margin_txt.split(",")[0]) if margin_txt else 0.0
        _add_text(page, text_node, x + 8 + margin, y + 4,
                  width=max(w - 16 - 2 * margin, 40.0))


# -------------------------------------------------------------------- group

def _parse_elements(container: ET.Element | None, page: Page, pkg: _Pkg,
                    dx: float, dy: float, media: dict[str, list[str]],
                    skip: dict[str, int]) -> None:
    if container is None:
        return
    for el in list(container):
        tag = el.tag
        if tag in ("Picture",):
            _parse_picture(el, pkg, page, dx, dy)
        elif tag == "Text":
            rot = _float(_first_child_text(el, "Rotation"), 0.0)
            _add_text(page, el,
                      _float(_first_child_text(el, "X")) + dx,
                      _float(_first_child_text(el, "Y")) + dy,
                      rotation=rot,
                      width=_float(_first_child_text(el, "Width")))
        elif tag in ("Shape", "Ellipse", "Rectangle", "CustomGeometry"):
            geometry = el.find("Geometry")
            if geometry is None and tag != "Shape":
                geometry = el
            if el.tag == "Shape" and el.find("Geometry") is None:
                # DrawingBoard strokes are plain Path-d shapes
                pts = _path_to_points(_first_child_text(el, "Path"))
                if len(pts) >= 2:
                    _point_at((dx + _float(_first_child_text(el, "X")),
                               dy + _float(_first_child_text(el, "Y"))), pts)
                    stroke = normalize_color(
                        _first_child_text(el, "Foreground/ColorBrush"))
                    page.elements.append(InkElement(strokes=[{
                        "color": stroke,
                        "width": max(_float(
                            _first_child_text(el, "Thickness"), 2.0), 0.5),
                        "points": [[round(p[0], 2), round(p[1], 2)]
                                   for p in pts]}]))
                    continue
            _parse_shape(el, page, dx, dy)
        elif tag == "Group":
            _parse_elements(el.find("Elements"), page, pkg,
                            dx + _float(_first_child_text(el, "X")),
                            dy + _float(_first_child_text(el, "Y")),
                            media, skip)
        elif tag == "Video":
            _parse_media(el, pkg, page, dx, dy, media)
        elif tag == "Audio":
            _parse_media(el, pkg, page, dx, dy, media)
        elif tag == "Table":
            _parse_table(el, page, dx, dy)
        elif tag == "Topic":
            _parse_topic(el, page, dx, dy)
        elif tag == "ClassicalWorkElement":
            _parse_classical(el, page, dx, dy)
        else:
            skip[tag] = skip.get(tag, 0) + 1


# ------------------------------------------------------------------- table

def _parse_table(el: ET.Element, page: Page, dx: float, dy: float) -> None:
    """Grid table: cell rectangles with centered cell text."""
    x = _float(_first_child_text(el, "X")) + dx
    y = _float(_first_child_text(el, "Y")) + dy
    stroke = normalize_color(_first_child_text(el, "Skin/Stroke/ColorBrush"))
    thickness = max(_float(_first_child_text(el, "Skin/StrokeThickness"), 1),
                    0.5)
    header_size = _float(_first_child_text(el, "Skin/HeaderFontSize"), 0)
    header_color = normalize_color(
        _first_child_text(el, "Skin/HeaderForeground/ColorBrush"),
        "#FF464646")
    cols_node = el.find("ColumnWidths")
    cols = [float(_texts(c)) for c in list(cols_node)] \
        if cols_node is not None else []
    rows = el.find("Rows")
    cy = y
    header_first = True
    for row in list(rows) if rows is not None else []:
        h = _float(_first_child_text(row, "Height"), 60)
        cells = row.find("Cells")
        cx = x
        col_idx = 0
        for cell in list(cells) if cells is not None else []:
            colspan = max(int(_float(_first_child_text(cell, "ColumnSpan"), 1)), 1)
            cw = sum(cols[col_idx:col_idx + colspan]) if cols else 200.0
            page.elements.append(ShapeElement(
                x=cx, y=cy, width=max(cw, 1), height=max(h, 1), shape="rect",
                stroke_color=stroke, fill_color="#00000000",
                stroke_width=thickness))
            text_node = cell.find("Text")
            if text_node is not None:
                rich = text_node if text_node.tag == "RichText" \
                    else text_node.find("RichText")
                t, s, f, c, b = _rich_text(rich)
                if t:
                    run_size = s or (header_size if header_first and
                                     header_size > 0 else 0.0)
                    run_color = header_color if header_first else \
                        (c or "#FF464646")
                    page.elements.append(TextElement(
                        x=cx + 8, y=cy + max(0, (h - (run_size or 24)) / 2),
                        text=t, font_size=run_size or 24.0, font=f,
                        color=run_color, bold=b, width=max(cw - 16, 40.0)))
            cx += cw
            col_idx += colspan
        cy += h
        header_first = False

def _parse_topic(el: ET.Element, page: Page, dx: float, dy: float) -> None:
    """Mind-map widget: keep the title and every node text bubble."""
    tx = _float(_first_child_text(el, "X")) + dx
    ty = _float(_first_child_text(el, "Y")) + dy
    _add_text(page, el.find("Title"), tx, ty)
    for node in el.iter("Node"):
        loc = _first_child_text(node, "Location")
        nums = _PAIR.findall(loc)
        contents = node.find("Contents")
        if not contents:
            continue
        text: list[str] = []
        size = 0.0
        font = ""
        color = ""
        bold = False
        for content in list(contents):
            t, s, f, c, b = _rich_text(
                content if content.tag == "RichText"
                else content.find("RichText") or content.find("Text"))
            if t:
                text.append(t)
                size = size or s
                font = font or f
                color = color or c
                bold = bold or b
        if not text:
            continue
        nx = tx + (_float(nums[0]) if len(nums) > 0 else 0.0)
        ny = ty + (_float(nums[1]) if len(nums) > 1 else 0.0)
        page.elements.append(TextElement(
            x=nx, y=ny, text="\n".join(text), font_size=size or 24.0,
            font=font, color=normalize_color(color), bold=bold))
    for link in el.iter("NodeLink"):
        pass  # connectors are decorative; node text preserves the content


# ------------------------------------------------------ classical work panel

def _parse_classical(el: ET.Element, page: Page, dx: float, dy: float) -> None:
    """Classical-text panel: title / author+dynasty / paragraph editors."""
    x = _float(_first_child_text(el, "X")) + dx
    y = _float(_first_child_text(el, "Y")) + dy
    theme = normalize_color(_first_child_text(el, "ThemeBrush/ColorBrush"),
                            "#FF781222")
    title = _first_child_text(el, "Title")
    author_name = _first_child_text(el, "Author")
    dynasty = _first_child_text(el, "Dynasty")
    if title:
        page.elements.append(TextElement(x=x + 24, y=y + 8, text=title,
                                         font_size=46, color=theme))
    author = f"{dynasty}　{author_name}".strip()
    if author_name:
        page.elements.append(TextElement(x=x + 24, y=y + 70, text=author,
                                         font_size=26, color="#FF9B8A8A"))
    editors = el.find("Editors")
    paragraphs: list[str] = []
    body_size, body_font, body_color = 0.0, "", ""
    for editor in list(editors) if editors is not None else []:
        t, s, f, c, b = _rich_text(
            editor if editor.tag == "RichText" else editor.find("RichText"))
        if t:
            paragraphs.append(t)
            body_size = body_size or s
            body_font = body_font or f
            body_color = body_color or c
    if not paragraphs:
        body = _first_child_text(el, "Content").replace("\r", "")
        if body.strip():
            paragraphs = [ln for ln in body.split("\n") if ln.strip()]
        body_size, body_font, body_color = body_size or 32.0, "KaiTi", "#FF464646"
    if paragraphs:
        page.elements.append(TextElement(
            x=x + 24, y=y + 120, text="\n".join(paragraphs),
            font_size=body_size or 32.0, font=body_font, color=body_color,
            width=1000.0))


# -------------------------------------------------------------------- slide

def parse_slide(root: ET.Element, zf: zipfile.ZipFile, pkg: _Pkg,
                doc: Doc) -> Page:
    page = Page()
    page.w = _float(_first_child_text(root, "Width"), doc.width)
    page.h = _float(_first_child_text(root, "Height"), doc.height)
    page.background = "#FFFFFFFF"

    bg = root.find("Background")
    if bg is not None:
        color_brush = bg.find("ColorBrush")
        image_brush = bg.find("ImageBrush")
        if color_brush is not None:
            page.background = normalize_color(_texts(color_brush))
        elif image_brush is not None:
            data = pkg.resolve(_first_child_text(image_brush, "Source"))
            if data:
                page.background = "#FFFFFFFF"
                page.background_image = b64encode(data)

    media: dict[str, list[str]] = {}
    skip: dict[str, int] = {}
    _parse_elements(root.find("Elements"), page, pkg, 0.0, 0.0, media, skip)

    if skip:
        doc.warnings.append(
            "slide has unsupported element tags (ignored): " +
            ", ".join(sorted(skip)[:8]))
    flat = [n for sub in media.values() for n in sub]
    if flat:
        doc.warnings.append("interactive media kept as pictures/comments: "
                            + ", ".join(flat[:6]))
    return page


def read_enbx(path: str) -> Doc:
    """Load an .enbx package into a Doc. Raises ValueError on junk input."""
    zf = zipfile.ZipFile(path)
    names = set(zf.namelist())
    if "Board.xml" not in names:
        raise ValueError("not an enbx package: missing Board.xml")

    doc = Doc()
    pkg = _Pkg(zf)

    board = ET.fromstring(zf.read("Board.xml"))
    doc.width = _float(_first_child_text(board, "SlideWidth"), DEFAULT_SLIDE_W)
    doc.height = _float(_first_child_text(board, "SlideHeight"), DEFAULT_SLIDE_H)

    try:
        docmeta = ET.fromstring(zf.read("Document.xml"))
        doc.name = _first_child_text(docmeta, "Name") or doc.name
    except (KeyError, ET.ParseError):
        pass

    ordered_ids = [_norm_guid(t) for t in
                   (_texts(it) for it in board.findall("Slides/Item")) if t]

    slides_by_id: dict[str, ET.Element] = {}
    slide_files = sorted((n for n in names
                          if n.startswith("Slides/") and n.endswith(".xml")),
                         key=lambda n: (len(n), n))
    for fn in slide_files:
        try:
            root = ET.fromstring(zf.read(fn))
        except ET.ParseError:
            continue
        sid = _norm_guid(_first_child_text(root, "Id"))
        slides_by_id[sid or fn] = root

    used: set[str] = set()
    ordered: list[str] = []
    for sid in ordered_ids:
        if sid in slides_by_id and sid not in used:
            ordered.append(sid)
            used.add(sid)

    ordered = ordered or list(slides_by_id.keys())
    for sid in ordered:
        doc.pages.append(parse_slide(slides_by_id[sid], zf, pkg, doc))

    if not doc.pages:
        doc.pages.append(Page(w=doc.width, h=doc.height))
    for p in doc.pages:
        p.w = doc.width
        p.h = doc.height
    return doc
