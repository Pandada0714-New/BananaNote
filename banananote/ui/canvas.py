"""Board canvas: QGraphicsScene/View based page renderer + editing modes."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, Signal, QObject
from PySide6.QtGui import (QBrush, QColor, QFontDatabase, QImage, QPainter,
                           QPainterPath, QPen, QPixmap, QTransform)
from PySide6.QtWidgets import (QFileDialog, QGraphicsEllipseItem,
                               QGraphicsItem, QGraphicsLineItem,
                               QGraphicsPathItem, QGraphicsPixmapItem,
                               QGraphicsRectItem, QGraphicsScene,
                               QGraphicsTextItem, QGraphicsView)

from ..core.model import (ImageElement, InkElement, ShapeElement, TextElement,
                          b64decode, b64encode)


def qcolor(argb: str) -> QColor:
    c = QColor()
    c.setNamedColor(argb)
    return c


def _make_pic(el: ImageElement) -> "PicItem":
    """Build a pixmap item honouring optional crop + rotation.

    The EasiNote DisplayRegion is expressed in post-rotation coordinates,
    so cropping happens after rotating the image.
    """
    img = QImage.fromData(b64decode(el.data_b64))
    want_transform = bool(el.crop or el.rotation)
    if not img.isNull() and want_transform:
        if el.crop:
            nums = [n for n in el.crop.replace(" ", "").split(",") if n]
            if len(nums) >= 4:
                try:
                    cx, cy, cw, ch = (float(v) for v in nums[:4])
                except ValueError:
                    cx, cy, cw, ch = 0.0, 0.0, 0.0, 0.0
                r = QRectF(cx, cy, cw, ch).toRect()
                if r.isValid() and QRectF(img.rect()).toRect().contains(r):
                    img = img.copy(r)
        if el.rotation:
            img = img.transformed(QTransform().rotate(el.rotation))
    pic = PicItem(b64decode(el.data_b64), img if want_transform else None)
    pic.crop = el.crop
    pic.item_rotation = el.rotation
    pic.setPos(el.x, el.y)
    pw, ph = pic._pix.width(), pic._pix.height()
    if pw > 0 and ph > 0:
        pic.setScale(max(0.01, min(el.width / pw, el.height / ph)))
    return pic


class CanvasSignals(QObject):
    content_changed = Signal()
    mode_hint = Signal(str)


class InkItem(QGraphicsPathItem):
    """One ink element = one or more strokes drawn into a single item."""

    def __init__(self) -> None:
        super().__init__()
        self.strokes: list[dict[str, Any]] = []

    def rebuild(self) -> None:
        path = QPainterPath()
        for s in self.strokes:
            pts = s["points"]
            if len(pts) >= 2:
                poly = QPainterPath()
                poly.moveTo(pts[0][0], pts[0][1])
                for p in pts[1:]:
                    poly.lineTo(p[0], p[1])
                path.addPath(poly)
        self.setPath(path)
        self.update()

    def paint(self, painter: QPainter, *_args) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for s in self.strokes:
            pts = s["points"]
            w = s.get("width", 3.0)
            pen = QPen(qcolor(s["color"]), max(w, 0.1))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            if len(pts) < 2:
                if pts:
                    painter.drawPoint(QPointF(pts[0][0], pts[0][1]))
                continue
            poly = QPainterPath()
            poly.moveTo(pts[0][0], pts[0][1])
            for p in pts[1:]:
                poly.lineTo(p[0], p[1])
            painter.drawPath(poly)

    def element(self) -> InkElement:
        return InkElement(strokes=[dict(s) for s in self.strokes])


class TextItem(QGraphicsTextItem):
    _known_families: set[str] | None = None

    def __init__(self, x: float, y: float, text: str = "",
                 font_size: float = 24.0, color: str = "#FF202020",
                 font: str = "", rotation: float = 0.0,
                 bold: bool = False, width: float = 0.0) -> None:
        super().__init__(text)
        self.setPos(x, y)
        self.setDefaultTextColor(qcolor(color))
        f = self.font()
        if font:
            if TextItem._known_families is None:
                TextItem._known_families = set(QFontDatabase.families())
            if font in TextItem._known_families:
                f.setFamily(font)  # else keep default -> CJK fallback
        f.setPixelSize(max(2, round(font_size)))
        f.setBold(bold)
        self.setFont(f)
        self.font_size = font_size
        self.color = color
        self.font_name = font
        self._editing = True
        if width > 0:
            self.setTextWidth(width)
        if rotation:
            self.setRotation(rotation)
        self.setFlags(self.flags()
                      | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                      | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFocus()

    def finish_editing(self) -> None:
        self._editing = False
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.clearFocus()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFocus()
        super().mouseDoubleClickEvent(event)

    def element(self) -> TextElement:
        if self._editing:
            self.finish_editing()
        f = self.font()
        px = f.pixelSize() if f.pixelSize() > 1 else 24
        tw = self.textWidth()
        return TextElement(x=self.pos().x(), y=self.pos().y(),
                           text=self.toPlainText(),
                           font_size=float(px), color=self.color,
                           font=self.font_name, bold=f.bold(),
                           width=tw if tw > 0 else 0.0)


class ShapeLikeItem:
    stroke_color: str
    fill_color: str
    stroke_width: float

    def apply_style(self, stroke_color: str, fill_color: str, width: float) -> None:
        pen = QPen(qcolor(stroke_color), width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(pen)
        fill = qcolor(fill_color)
        self.setBrush(QBrush(fill) if fill.alpha() else Qt.BrushStyle.NoBrush)
        self.stroke_color = stroke_color
        self.fill_color = fill_color
        self.stroke_width = width


class RectItem(ShapeLikeItem, QGraphicsRectItem):
    def element(self) -> ShapeElement:
        r = self.rect()
        return ShapeElement(x=r.left(), y=r.top(), width=r.width(),
                            height=r.height(), shape="rect",
                            stroke_color=self.stroke_color,
                            fill_color=self.fill_color,
                            stroke_width=self.stroke_width)


class EllipseItem(ShapeLikeItem, QGraphicsEllipseItem):
    def element(self) -> ShapeElement:
        r = self.rect()
        return ShapeElement(x=r.left(), y=r.top(), width=r.width(),
                            height=r.height(), shape="ellipse",
                            stroke_color=self.stroke_color,
                            fill_color=self.fill_color,
                            stroke_width=self.stroke_width)


class LineItem(QGraphicsLineItem):
    def __init__(self, x1, y1, x2, y2, stroke_color: str, width: float):
        super().__init__(QLineF(x1, y1, x2, y2))
        self.stroke_color = stroke_color
        self.stroke_width = width
        pen = QPen(qcolor(stroke_color), width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(pen)

    def element(self) -> ShapeElement:
        ln = self.line()
        return ShapeElement(x=min(ln.x1(), ln.x2()), y=min(ln.y1(), ln.y2()),
                            width=abs(ln.x2() - ln.x1()),
                            height=abs(ln.y2() - ln.y1()), shape="line",
                            stroke_color=self.stroke_color,
                            stroke_width=self.stroke_width)


class PicItem(QGraphicsPixmapItem):
    def __init__(self, data: bytes, image: QImage | None = None) -> None:
        super().__init__()
        self._data = data
        if image is not None and not image.isNull():
            self._pix = QPixmap.fromImage(image)
        else:
            self._pix = QPixmap()
            self._pix.loadFromData(data)
        self.setPixmap(self._pix)
        self.crop = ""          # preserved through edit round-trips
        self.item_rotation = 0.0
        self.setFlags(self.flags()
                      | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                      | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)

    def fit_to(self, width: float, height: float | None = None) -> None:
        pw, ph = self._pix.width(), self._pix.height()
        if pw <= 0 or ph <= 0:
            return
        scale = width / pw if height is None else min(width / pw, height / ph)
        self.setScale(max(0.01, scale))

    def element(self) -> ImageElement:
        r = self.boundingRect()
        w = r.width() * self.scale()
        h = r.height() * self.scale()
        return ImageElement(x=self.pos().x(), y=self.pos().y(),
                            width=w, height=h,
                            data_b64=b64encode(self._data),
                            rotation=self.item_rotation, crop=self.crop)


class BoardScene(QGraphicsScene):
    def __init__(self, w: float, h: float, background: str = "#FFFFFFFF",
                 background_image: str = "") -> None:
        super().__init__(0, 0, w, h)
        self._bg = background
        self._bg_image = background_image
        self._bg_pix: QPixmap | None = None
        self._undo_stack: list[dict[str, Any]] = []
        self._redo_stack: list[dict[str, Any]] = []
        self.setBackgroundBrush(QBrush(qcolor(background)))

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        """Slide color + stretched background bitmap behind every item."""
        painter.fillRect(rect, qcolor(self._bg))
        if not self._bg_image:
            return
        if self._bg_pix is None:
            pix = QPixmap()
            pix.loadFromData(b64decode(self._bg_image))
            self._bg_pix = pix.scaled(
                int(self.width()), int(self.height()),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
        painter.drawPixmap(0, 0, self._bg_pix)

    def build_model(self):
        els = []
        for it in self.items():
            getter = getattr(it, "element", None)
            if callable(getter):
                try:
                    els.append(getter())
                except Exception:  # noqa: BLE001 - keep canvas alive
                    pass
        return els


class BoardView(QGraphicsView):
    def __init__(self, signals: CanvasSignals, parent=None) -> None:
        super().__init__(parent)
        self.signals = signals
        self.mode = "select"
        self.color = "#FF202020"
        self.width = 3.0
        self._temp_item: Any = None
        self._temp_ink: InkItem | None = None
        self._start = QPointF(0, 0)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        editable = mode == "select"
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag if editable
                         else QGraphicsView.DragMode.NoDrag)
        for it in self.scene().items():
            if isinstance(it, TextItem) and it._editing:
                it.finish_editing()
            it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, editable)

    # ---------------------------------------------------------------- history
    def _hist_push(self) -> None:
        """Snapshot the scene right before it mutates (call at press-time)."""
        scene = self.scene()
        scene._undo_stack.append({"bg": scene._bg, "bgi": scene._bg_image,
                                  "els": scene.build_model()})
        scene._redo_stack.clear()

    def hist_undo(self) -> None:
        scene = self.scene()
        if not scene._undo_stack:
            return
        self._hist_now_push_to_redo()
        st = scene._undo_stack.pop()
        self.load_elements(st["els"], scene.width(), scene.height(),
                           st["bg"], st.get("bgi", ""))

    def hist_redo(self) -> None:
        scene = self.scene()
        if not scene._redo_stack:
            return
        scene._undo_stack.append({"bg": scene._bg, "bgi": scene._bg_image,
                                  "els": scene.build_model()})
        st = scene._redo_stack.pop()
        self.load_elements(st["els"], scene.width(), scene.height(),
                           st["bg"], st.get("bgi", ""))

    def _hist_now_push_to_redo(self) -> None:
        scene = self.scene()
        scene._redo_stack.append({"bg": scene._bg, "els": scene.build_model()})

    # ------------------------------------------------------------------ mouse
    def mousePressEvent(self, event) -> None:  # noqa: N802
        sp = self.mapToScene(event.position().toPoint())
        self._start = sp
        scene = self.scene()
        if event.button() == Qt.MouseButton.LeftButton:
            if self.mode in ("pen", "highlighter"):
                self._hist_push()
                color = QColor(self.color)
                if self.mode == "highlighter":
                    color.setAlpha(70)
                self._temp_ink = InkItem()
                self._temp_ink.strokes.append({
                    "color": "#%02X%02X%02X%02X" % (color.alpha(), color.red(),
                                                    color.green(), color.blue()),
                    "width": self.width if self.mode == "pen" else self.width * 5,
                    "points": []})
                scene.addItem(self._temp_ink)
                return
            if self.mode == "eraser":
                self._hist_push()
                self._erase_at(sp)
                return
            if self.mode == "text":
                self._hist_push()
                it = TextItem(sp.x(), sp.y(), "", font_size=24, color=self.color)
                scene.addItem(it)
                self.signals.content_changed.emit()
                return
            if self.mode in ("rect", "ellipse", "line"):
                self._hist_push()
            if self.mode in ("rect", "ellipse"):
                cls = RectItem if self.mode == "rect" else EllipseItem
                it = cls(QRectF(sp, sp))
                it.apply_style(self.color, "#00000000", self.width)
                scene.addItem(it)
                self._temp_item = it
                return
            if self.mode == "line":
                it = LineItem(sp.x(), sp.y(), sp.x(), sp.y(), self.color, self.width)
                scene.addItem(it)
                self._temp_item = it
                return
            if self.mode == "image":
                fn, _ = QFileDialog.getOpenFileName(
                    self, "Insert Image", "",
                    "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
                if fn:
                    self._hist_push()
                    with open(fn, "rb") as fh:
                        data = fh.read()
                    pic = PicItem(data)
                    pic.fit_to(400)
                    pic.setPos(sp)
                    scene.addItem(pic)
                    self.signals.content_changed.emit()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        sp = self.mapToScene(event.position().toPoint())
        if self._temp_ink is not None:
            self._temp_ink.strokes[0]["points"].append([sp.x(), sp.y()])
            self._temp_ink.rebuild()
            self.signals.content_changed.emit()
            return
        if self.mode == "eraser" and event.buttons() & Qt.MouseButton.LeftButton:
            self._erase_at(sp)
            return
        if self._temp_item is not None and event.buttons() & Qt.MouseButton.LeftButton:
            if isinstance(self._temp_item, LineItem):
                self._temp_item.setLine(QLineF(self._start, sp))
            else:
                self._temp_item.setRect(QRectF(self._start, sp).normalized())
            self.signals.content_changed.emit()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._temp_ink is not None:
            pts = self._temp_ink.strokes[0]["points"]
            if len(pts) == 1:
                pts.append([pts[0][0] + 0.4, pts[0][1] + 0.4])
            self._temp_ink.rebuild()
            self._temp_ink = None
        if self.mode == "eraser":
            self._erase_at(self.mapToScene(event.position().toPoint()))
        if self._temp_item is not None:
            r = QRectF(self._start, self.mapToScene(
                event.position().toPoint()))
            if isinstance(self._temp_item, LineItem):
                self._temp_item.setLine(QLineF(self._start,
                                               self.mapToScene(
                                                   event.position().toPoint())))
            else:
                self._temp_item.setRect(r.normalized())
            self.signals.content_changed.emit()
        self._temp_item = None
        super().mouseReleaseEvent(event)

    def _erase_at(self, sp: QPointF) -> None:
        scene = self.scene()
        hits = scene.items(sp, Qt.ItemSelectionMode.ContainsItemShape,
                           Qt.SortOrder.AscendingOrder)
        removed = False
        for it in hits:
            if isinstance(it, TextItem) and it.textInteractionFlags() & \
                    Qt.TextInteractionFlag.TextEditorInteraction:
                continue
            scene.removeItem(it)
            removed = True
        if removed:
            self.signals.content_changed.emit()

    # ----------------------------------------------------------------- import
    def load_elements(self, elements, width: float, height: float,
                      background: str, background_image: str = "") -> None:
        scene = self.scene()
        for it in list(scene.items()):
            scene.removeItem(it)
        scene.setSceneRect(0, 0, width, height)
        scene._bg = background
        scene._bg_image = background_image
        scene._bg_pix = None
        self.fit_in(width, height)
        for el in elements:
            if isinstance(el, InkElement):
                ink = InkItem()
                ink.strokes = el.strokes
                ink.rebuild()
                scene.addItem(ink)
            elif isinstance(el, TextElement):
                it = TextItem(el.x, el.y, el.text, el.font_size, el.color,
                              getattr(el, "font", ""),
                              getattr(el, "rotation", 0.0),
                              getattr(el, "bold", False),
                              getattr(el, "width", 0.0))
                scene.addItem(it)
            elif isinstance(el, ShapeElement):
                if el.shape == "rect":
                    it = RectItem(QRectF(el.x, el.y, el.width, el.height))
                elif el.shape == "ellipse":
                    it = EllipseItem(QRectF(el.x, el.y, el.width, el.height))
                else:
                    it = LineItem(el.x, el.y, el.x + el.width, el.y + el.height,
                                  el.stroke_color, el.stroke_width)
                if not isinstance(it, LineItem):
                    it.apply_style(el.stroke_color, el.fill_color, el.stroke_width)
                if getattr(el, "rotation", 0.0):
                    it.setTransformOriginPoint(
                        el.x + el.width / 2, el.y + el.height / 2)
                    it.setRotation(el.rotation)
                scene.addItem(it)
            elif isinstance(el, ImageElement):
                pic = _make_pic(el)
                scene.addItem(pic)

    def fit_in(self, width: float, height: float) -> None:
        margin = 60
        self.setSceneRect(-margin, -margin, width + 2 * margin, height + 2 * margin)
        vp = self.viewport().size()
        scale = min((vp.width() - 20) / (width + 2 * margin),
                    (vp.height() - 20) / (height + 2 * margin))
        scale = max(0.05, min(scale, 3.0))
        self.setTransform(self.transform().fromScale(scale, scale))
