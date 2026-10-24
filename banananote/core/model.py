"""Document model shared by the enbx reader, the .bnx writer and the UI."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field, asdict
from typing import Any

DEFAULT_SLIDE_W = 1280
DEFAULT_SLIDE_H = 720


@dataclass
class TextElement:
    x: float
    y: float
    text: str = ""
    font: str = ""
    font_size: float = 24.0
    color: str = "#FF202020"
    bold: bool = False
    italic: bool = False
    rotation: float = 0.0
    kind: str = "text"


@dataclass
class ImageElement:
    x: float
    y: float
    width: float
    height: float
    data_b64: str = ""  # base64 of the image bytes
    rotation: float = 0.0
    kind: str = "image"


@dataclass
class InkElement:
    x: float = 0.0
    y: float = 0.0
    strokes: list[dict[str, Any]] = field(default_factory=list)
    kind: str = "ink"
    # stroke = {"color": "#AARRGGBB", "width": float, "points": [[x, y, (w?)], ...]}


@dataclass
class ShapeElement:
    x: float
    y: float
    width: float
    height: float
    shape: str = "rect"  # rect | ellipse | line
    stroke_color: str = "#FF303030"
    fill_color: str = "#00000000"
    stroke_width: float = 2.0
    rotation: float = 0.0
    kind: str = "shape"


@dataclass
class Page:
    background: str = "#FFFFFFFF"
    w: float = DEFAULT_SLIDE_W
    h: float = DEFAULT_SLIDE_H
    elements: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "background": self.background,
            "w": self.w,
            "h": self.h,
            "elements": [asdict(e) for e in self.elements if e.kind != "ink"],
            "ink": [asdict(e) for e in self.elements if e.kind == "ink"],
        }


@dataclass
class Doc:
    name: str = "Untitled"
    pages: list[Page] = field(default_factory=list)
    width: float = DEFAULT_SLIDE_W
    height: float = DEFAULT_SLIDE_H

    @classmethod
    def blank(cls, name: str = "Untitled") -> "Doc":
        return cls(name=name, pages=[Page()])

    def to_dict(self) -> dict[str, Any]:
        return {
            "app": "BananaNote",
            "version": 1,
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "pages": [p.to_dict() for p in self.pages],
        }


def element_from_dict(d: dict[str, Any]) -> Any:
    """Rebuild an element object from its dict (for .bnx loading)."""
    kind = d.get("kind", "")
    data = dict(d)
    if kind == "ink":
        return InkElement(x=data.get("x", 0.0), y=data.get("y", 0.0),
                          strokes=data.get("strokes", []))
    cls = {"text": TextElement, "image": ImageElement, "shape": ShapeElement}.get(kind)
    if cls is None:
        return None
    allowed = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    return cls(**{k: v for k, v in data.items() if k in allowed})


def b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def b64decode(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))
