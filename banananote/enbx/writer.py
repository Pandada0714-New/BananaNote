"""BananaNote native project format (.bnx) reader/writer.

.bnx = ZIP containing:
    bnx.json            document JSON (see core.model.Doc.to_dict)
    Resources/img_N.*   image payloads, referenced from JSON as "ref:<name>"

Oversized base64 blobs are streamed into separate zip entries so the JSON
stays small and diffs friendly.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import PurePosixPath

from ..core.model import (
    Doc, Page, ImageElement, element_from_dict, b64decode, b64encode,
)

_REF_PREFIX = "ref:"


def read_bnx(path: str) -> Doc:
    with zipfile.ZipFile(path) as zf:
        data = json.loads(zf.read("bnx.json").decode("utf-8"))
    doc = Doc(
        name=data.get("name", "Untitled"),
        width=data.get("width", 1280),
        height=data.get("height", 720),
    )
    for p in data.get("pages", []):
        elements: list = []
        for el in p.get("elements", []):
            e = element_from_dict(el)
            if isinstance(e, ImageElement) and e.data_b64.startswith(_REF_PREFIX):
                key = e.data_b64[len(_REF_PREFIX):]
                try:
                    with zipfile.ZipFile(path) as zf:  # keep fresh handle
                        e.data_b64 = b64encode(zf.read(key))
                except (KeyError, zipfile.BadZipFile):
                    continue
            elements.append(e)
        for ink in p.get("ink", []):
            e = element_from_dict(ink)
            if e is not None:
                elements.append(e)
        doc.pages.append(Page(
            background=p.get("background", "#FFFFFFFF"),
            w=p.get("w", doc.width), h=p.get("h", doc.height),
            elements=elements,
        ))
    if not doc.pages:
        doc.pages.append(Page())
    return doc


def write_bnx(doc: Doc, path: str) -> None:
    # build dict payload, hoisting any non-ref images into zip entries
    pages_json = []
    resources: dict[str, bytes] = {}
    idx = 0
    for page in doc.pages:
        els, inks = [], []
        for el in page.elements:
            if el.kind == "ink":
                inks.append(_clean(el.__dict__))
            elif isinstance(el, ImageElement) and el.data_b64 and \
                    not el.data_b64.startswith(_REF_PREFIX):
                ext = _guess_ext(el)
                name = f"Resources/img_{idx}{ext}"
                idx += 1
                resources[name] = b64decode(el.data_b64)
                d = _clean(el.__dict__)
                d["data_b64"] = _REF_PREFIX + name
                els.append(d)
            else:
                els.append(_clean(el.__dict__))
        pages_json.append({
            "background": page.background, "w": page.w, "h": page.h,
            "elements": els, "ink": inks,
        })

    payload = {
        "app": "BananaNote", "version": 1,
        "name": doc.name, "width": doc.width, "height": doc.height,
        "pages": pages_json,
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("bnx.json", json.dumps(payload, ensure_ascii=False, indent=1))
        for name, blob in resources.items():
            zf.writestr(name, blob)


def _clean(d: dict) -> dict:
    """Round floats for tidy diffs and drop internal keys."""
    out = {}
    for k, v in d.items():
        if isinstance(v, float):
            out[k] = round(v, 2)
        elif isinstance(v, list) and all(isinstance(x, list) for x in v):
            out[k] = [[round(c, 2) for c in pt] for pt in v]
        else:
            out[k] = v
    return out


def _guess_ext(el: ImageElement) -> str:
    return ".png"
