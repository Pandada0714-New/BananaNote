"""Fullscreen presentation mode: keeps only pen / highlighter / eraser /
shapes / text plus page flipping, runs the shared document fullscreen."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (QColorDialog, QLabel, QMainWindow, QSpinBox,
                               QToolBar, QToolButton)

from .. import i18n
from ..core.model import Doc
from .canvas import BoardScene, BoardView, CanvasSignals, TextItem

COLORS = ["#FF202020", "#FFD32F2F", "#FF2E7D32", "#FF1565C0",
          "#FFF9A825", "#FFFFFFFF"]
PRESENT_MODES = ["pen", "highlighter", "eraser", "text", "rect", "ellipse",
                 "line"]


class PresentView(BoardView):
    """BoardView that reports resize (for refit) and wheel page steps."""

    fit_requested = Signal()
    wheel_step = Signal(int)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.fit_requested.emit()

    def wheelEvent(self, event) -> None:  # noqa: N802
        if event.buttons() == Qt.MouseButton.NoButton:
            dy = event.angleDelta().y()
            if dy and not self._text_editing():
                self.wheel_step.emit(1 if dy < 0 else -1)
                event.accept()
                return
        super().wheelEvent(event)

    def _text_editing(self) -> bool:
        scene = self.scene()
        focus = scene.focusItem() if scene else None
        return isinstance(focus, TextItem) and focus._editing

    def fit_in(self, width: float, height: float) -> None:
        margin = 60
        self.setSceneRect(-margin, -margin, width + 2 * margin,
                          height + 2 * margin)
        vp = self.viewport().size()
        scale = min((vp.width() - 20) / (width + 2 * margin),
                    (vp.height() - 20) / (height + 2 * margin))
        scale = max(0.05, min(scale, 8.0))
        self.setTransform(self.transform().fromScale(scale, scale))


class PresentWindow(QMainWindow):
    """Everything is drawn onto the shared Doc; edits sync back on close."""

    finished_present = Signal(bool)

    def __init__(self, doc: Doc, start_page: int) -> None:
        super().__init__()
        self.doc = doc
        self.current_page = max(0, min(start_page, len(doc.pages) - 1))
        self.signals = CanvasSignals()
        self.changed = False
        self.setWindowTitle(i18n.tr("present_title"))

        self.view = PresentView(self.signals)
        self.view.setBackgroundBrush(QBrush(QColor("#14161a")))
        self.setCentralWidget(self.view)
        self._build_toolbar()
        self._build_shortcuts()
        self.signals.content_changed.connect(self._on_content_changed)
        self.view.fit_requested.connect(self._refit)
        self.view.wheel_step.connect(self.flip_page)
        self.load_page(self.current_page)
        self.set_mode("pen")

    # ---------------------------------------------------------------- toolbar
    def _build_toolbar(self) -> None:
        bar = QToolBar("present")
        bar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.BottomToolBarArea, bar)
        self.toolbar = bar

        self._mode_buttons: dict[str, QToolButton] = {}
        for mode in PRESENT_MODES:
            btn = QToolButton()
            btn.setText(i18n.tr(f"tool_{mode}"))
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, m=mode: self.set_mode(m))
            bar.addWidget(btn)
            self._mode_buttons[mode] = btn
        self._mode_buttons["pen"].setChecked(True)

        bar.addSeparator()
        for hexcolor in COLORS:
            btn = QToolButton()
            btn.setFixedSize(26, 26)
            btn.setStyleSheet(
                f"background: {hexcolor}; border: 2px solid #909090;"
                f" border-radius: 4px;")
            btn.clicked.connect(lambda _=False, c=hexcolor: self.set_color(c))
            bar.addWidget(btn)
        pick = QToolButton()
        pick.setText(i18n.tr("custom_color"))
        pick.clicked.connect(self._pick_color)
        bar.addWidget(pick)

        bar.addSeparator()
        bar.addWidget(QLabel(i18n.tr("width_label") + " "))
        spin = QSpinBox()
        spin.setRange(1, 40)
        spin.setValue(3)
        spin.valueChanged.connect(self.set_width)
        bar.addWidget(spin)

        bar.addSeparator()
        for key, handler in [("undo", self.undo), ("redo", self.redo),
                             ("clear_page", self.clear_page)]:
            bar.addAction(i18n.tr(key), handler)

        bar.addSeparator()
        bar.addAction(i18n.tr("present_prev"), self.prev_page)
        self.page_label = QLabel()
        bar.addWidget(self.page_label)
        bar.addAction(i18n.tr("present_next"), self.next_page)

        bar.addSeparator()
        bar.addAction(i18n.tr("present_exit"), self.close)

    def _build_shortcuts(self) -> None:
        for key, handler in [
                ("Escape", self.close),
                ("PgUp", self.prev_page), ("PgDown", self.next_page),
                ("Left", self.prev_page), ("Right", self.next_page),
                ("Space", self.next_page),
                ("Ctrl+Z", self.undo), ("Ctrl+Y", self.redo)]:
            sc = QShortcut(QKeySequence(key), self)
            sc.activated.connect(handler)

    # ------------------------------------------------------------------ modes
    def set_mode(self, mode: str) -> None:
        self.view.set_mode(mode)
        for key, btn in self._mode_buttons.items():
            btn.setChecked(key == mode)

    def set_color(self, c: str) -> None:
        self.view.color = c

    def _pick_color(self) -> None:
        c = QColorDialog.getColor(parent=self)
        if c.isValid():
            self.view.color = c.name(QColor.NameFormat.HexArgb)

    def set_width(self, w: int) -> None:
        self.view.width = float(w)

    # ------------------------------------------------------------------- pages
    def load_page(self, index: int) -> None:
        self._sync_model()
        self.current_page = index
        page = self.doc.pages[index]
        scene = BoardScene(page.w, page.h, page.background,
                           page.background_image)
        old_scene = self.view.scene()
        self.view.setScene(scene)
        del old_scene
        self.view.load_elements(page.elements, page.w, page.h,
                                page.background, page.background_image)
        self.view.set_mode(self.view.mode)
        self._update_label()

    def next_page(self) -> None:
        if not self._text_editing() and \
                self.current_page < len(self.doc.pages) - 1:
            self.load_page(self.current_page + 1)

    def prev_page(self) -> None:
        if not self._text_editing() and self.current_page > 0:
            self.load_page(self.current_page - 1)

    def flip_page(self, step: int) -> None:
        self.next_page() if step > 0 else self.prev_page()

    def _update_label(self) -> None:
        self.page_label.setText(i18n.tr(
            "present_page_label", i=self.current_page + 1,
            n=len(self.doc.pages)))

    # ------------------------------------------------------------- edit utils
    def _text_editing(self) -> bool:
        scene = self.view.scene()
        focus = scene.focusItem() if scene else None
        return isinstance(focus, TextItem) and focus._editing

    def undo(self) -> None:
        if not self._text_editing():
            self.view.hist_undo()
            self._sync_model()

    def redo(self) -> None:
        if not self._text_editing():
            self.view.hist_redo()
            self._sync_model()

    def clear_page(self) -> None:
        scene = self.view.scene()
        for it in list(scene.items()):
            scene.removeItem(it)
        self._sync_model()

    # ---------------------------------------------------------------- syncing
    def _on_content_changed(self) -> None:
        self._sync_model()
        self.changed = True

    def _sync_model(self) -> None:
        scene = self.view.scene()
        if scene is None:
            return
        self.doc.pages[self.current_page].elements = scene.build_model()

    def _refit(self) -> None:
        page = self.doc.pages[self.current_page]
        self.view.fit_in(page.w, page.h)

    # --------------------------------------------------------------- lifecycle
    def closeEvent(self, event) -> None:  # noqa: N802
        if self._text_editing():
            scene = self.view.scene()
            focus = scene.focusItem()
            if isinstance(focus, TextItem):
                focus.finish_editing()
            event.ignore()
            return
        self._sync_model()
        self.finished_present.emit(self.changed)
        event.accept()
