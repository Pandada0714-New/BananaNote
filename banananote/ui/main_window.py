"""BananaNote main window: toolbar, page sidebar, board view, i18n menu."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QSettings, QEvent
from PySide6.QtGui import (QAction, QActionGroup, QImage, QKeySequence,
                           QPainter, QColor, QPixmap, QShortcut)
from PySide6.QtWidgets import (QColorDialog, QDialog, QFileDialog, QHBoxLayout,
                               QLabel, QListWidget, QListWidgetItem, QMainWindow,
                               QMessageBox, QPushButton, QSpinBox, QToolBar,
                               QVBoxLayout, QWidget, QToolButton)

from ..core.model import DEFAULT_SLIDE_H, DEFAULT_SLIDE_W, Doc, Page
from ..enbx.reader import read_enbx
from ..enbx.writer import read_bnx, write_bnx
from .. import i18n
from .canvas import BoardScene, BoardView, CanvasSignals, qcolor
from .present import PresentWindow

COLORS = ["#FF202020", "#FFD32F2F", "#FF2E7D32", "#FF1565C0",
          "#FFF9A825", "#FFFFFFFF"]
MODE_KEYS = ["select", "pen", "highlighter", "eraser", "text",
             "rect", "ellipse", "line", "image"]
PAGE_BUTTONS = ["new_page", "delete_page", "duplicate"]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.doc: Doc = Doc.blank()
        self.current_page = 0
        self.signals = CanvasSignals()
        self.dirty = False
        self._scene_doc_id = None
        self._scene_page = None

        cfg = QSettings()
        i18n.set_language(cfg.value("ui/language", i18n.detect_default()))
        self._present: PresentWindow | None = None

        self.setWindowTitle(i18n.tr("app_title"))
        self.resize(1280, 800)
        self._build_menus()
        self._build_toolbar()
        self._build_central()
        self._build_statusbar()
        self._egg_clicks = 0
        self._egg_last = 0.0
        self._statusbar.installEventFilter(self)
        self._egg_shortcut = QShortcut(QKeySequence("Ctrl+Alt+U"), self)
        self._egg_shortcut.activated.connect(self.show_upgrade_easter_egg)
        self.load_page(0)

    # ----------------------------------------------------------------- menus
    def _build_menus(self) -> None:
        mb = self.menuBar()
        mb.clear()
        self._menu_settings = mb.addMenu(i18n.tr("menu_settings"))
        lang_menu = self._menu_settings.addMenu(i18n.tr("menu_language"))
        self._lang_actions: dict[str, QAction] = {}
        group = QActionGroup(self)
        for code in i18n.LANGS:
            act = QAction(i18n.tr(f"lang_{code}"), self)
            act.setCheckable(True)
            act.setChecked(i18n.get_language() == code)
            act.triggered.connect(lambda _=False, c=code: self.switch_language(c))
            group.addAction(act)
            lang_menu.addAction(act)
            self._lang_actions[code] = act
        act = QAction(i18n.tr("menu_upgrade_memory"), self)
        act.triggered.connect(self.show_upgrade_easter_egg)
        self._menu_settings.addAction(act)

    def switch_language(self, code: str) -> None:
        if code == i18n.get_language():
            return
        i18n.set_language(code)
        QSettings().setValue("ui/language", code)
        self.setUpdatesEnabled(False)
        try:
            self.removeToolBar(self.toolbar)
            self.toolbar = None
            self._build_menus()
            self._build_toolbar()
            for key, btn in self._page_buttons.items():
                btn.setText(i18n.tr(key))
            self._statusbar.showMessage(i18n.tr("ready"))
        finally:
            self.setUpdatesEnabled(True)
        self.refresh_page_list()
        self.load_page(self.current_page)  # refresh title/status texts
        self.statusBar().showMessage(i18n.tr("ready"))

    # ------------------------------------------------------------- scaffolding
    def _build_central(self) -> None:
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)

        self.page_list = QListWidget()
        self.page_list.setFixedWidth(150)
        self.page_list.currentRowChanged.connect(self._page_row_changed)
        layout.addWidget(self.page_list)

        side = QVBoxLayout()
        self._page_buttons: dict[str, QPushButton] = {}
        handlers = {"new_page": self.add_page,
                    "delete_page": self.delete_page,
                    "duplicate": self.duplicate_page}
        for key in PAGE_BUTTONS:
            btn = QPushButton(i18n.tr(key))
            btn.clicked.connect(handlers[key])
            side.addWidget(btn)
            self._page_buttons[key] = btn
        side.addStretch(1)
        layout.addLayout(side)

        self.view = BoardView(self.signals)
        self.view.setScene(BoardScene(DEFAULT_SLIDE_W, DEFAULT_SLIDE_H))
        self.view.set_mode("pen")
        layout.addWidget(self.view, stretch=1)
        self.setCentralWidget(central)

        self.signals.content_changed.connect(self._sync_page_model)
        self.refresh_page_list()

    def _build_toolbar(self) -> None:
        bar = QToolBar("tools")
        bar.setMovable(False)
        self.addToolBar(bar)
        self.toolbar = bar

        self._mode_buttons: dict[str, QToolButton] = {}
        for mode in MODE_KEYS:
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
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 40)
        self.width_spin.setValue(3)
        self.width_spin.valueChanged.connect(self.set_width)
        bar.addWidget(self.width_spin)

        bar.addSeparator()
        for key, handler, shortcut in [
                ("undo", self.undo, "Ctrl+Z"),
                ("redo", self.redo, "Ctrl+Y"),
                ("clear_page", self.clear_page, None),
                ("export_png", self.export_png, None)]:
            act = bar.addAction(i18n.tr(key), handler)
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))

        bar.addSeparator()
        bar.addAction(i18n.tr("open"), self.open_file)
        bar.addAction(i18n.tr("save"), self.save_file)

        bar.addSeparator()
        pres = bar.addAction(i18n.tr("present"), self.open_present)
        pres.setShortcut(QKeySequence("F5"))

    def _build_statusbar(self) -> None:
        self._statusbar = self.statusBar()
        self._statusbar.showMessage(i18n.tr("ready"))

    # ------------------------------------------------------------------ modes
    def set_mode(self, mode: str) -> None:
        self.view.set_mode(mode)
        for key, btn in self._mode_buttons.items():
            btn.setChecked(key == mode)
        self.statusBar().showMessage(
            i18n.tr("status_mode", mode=i18n.tr(f"tool_{mode}")))

    def set_color(self, c: str) -> None:
        self.view.color = c

    def _pick_color(self) -> None:
        c = QColorDialog.getColor(parent=self)
        if c.isValid():
            self.view.color = c.name(QColor.NameFormat.HexArgb)

    def set_width(self, w: int) -> None:
        self.view.width = float(w)

    # ------------------------------------------------------------------- pages
    def refresh_page_list(self) -> None:
        selected = self.current_page
        self.page_list.blockSignals(True)
        self.page_list.clear()
        for i in range(len(self.doc.pages)):
            self.page_list.addItem(QListWidgetItem(i18n.tr("page_item", n=i + 1)))
        self.page_list.setCurrentRow(selected)
        self.page_list.blockSignals(False)

    def _page_row_changed(self, row: int) -> None:
        if row >= 0:
            self.load_page(row)

    def load_page(self, index: int) -> None:
        self._sync_page_model()
        self.current_page = index
        page = self.doc.pages[index]
        scene = BoardScene(page.w, page.h, page.background,
                           page.background_image)
        old_view_scene = self.view.scene()
        self.view.setScene(scene)
        del old_view_scene
        self.view.load_elements(page.elements, page.w, page.h,
                                page.background, page.background_image)
        self.view.set_mode(self.view.mode)
        self._scene_doc_id = id(self.doc)
        self._scene_page = index
        self.setWindowTitle(i18n.tr(
            "window_title", name=self.doc.name,
            i=index + 1, n=len(self.doc.pages)))
        self.dirty = False

    def _detach_scene(self) -> None:
        """Scene contents no longer map to the model (doc swapped / page gone)."""
        self._scene_doc_id = None
        self._scene_page = None

    def _sync_page_model(self) -> None:
        scene = self.view.scene()
        if scene is None:
            return
        if id(self.doc) != self._scene_doc_id or self.current_page != self._scene_page:
            return  # scene belongs to another doc/page; never back-write
        page = self.doc.pages[self.current_page]
        page.elements = scene.build_model()
        self.dirty = True
        self.statusBar().showMessage(
            i18n.tr("status_page", i=self.current_page + 1, n=len(page.elements)))

    def add_page(self) -> None:
        self._sync_page_model()
        self.doc.pages.insert(self.current_page + 1,
                              Page(w=self.doc.width, h=self.doc.height))
        self.current_page += 1
        self.refresh_page_list()
        self.load_page(self.current_page)

    def delete_page(self) -> None:
        if len(self.doc.pages) <= 1:
            self._detach_scene()
            self.doc.pages = [Page()]
            self.refresh_page_list()
            self.load_page(0)
            return
        del self.doc.pages[self.current_page]
        self.current_page = max(0, self.current_page - 1)
        self.refresh_page_list()
        self.load_page(self.current_page)

    def duplicate_page(self) -> None:
        self._sync_page_model()
        import copy
        src = self.doc.pages[self.current_page]
        new = Page(background=src.background, background_image=src.background_image,
                   w=src.w, h=src.h,
                   elements=copy.deepcopy(src.elements))
        self.doc.pages.insert(self.current_page + 1, new)
        self.current_page += 1
        self.refresh_page_list()
        self.load_page(self.current_page)

    # ------------------------------------------------------------- edit utils
    def undo(self) -> None:
        self.view.hist_undo()
        self._sync_page_model()

    def redo(self) -> None:
        self.view.hist_redo()
        self._sync_page_model()

    def clear_page(self) -> None:
        scene = self.view.scene()
        for it in list(scene.items()):
            scene.removeItem(it)
        self._sync_page_model()
        self.statusBar().showMessage(i18n.tr("status_cleared"))

    # -------------------------------------------------------------- file I/O
    def open_file(self) -> None:
        fn, _ = QFileDialog.getOpenFileName(
            self, i18n.tr("dlg_open_title"), "", i18n.tr("file_dialog_filter"))
        if not fn:
            return
        try:
            if fn.lower().endswith(".bnx"):
                doc = read_bnx(fn)
            else:
                doc = read_enbx(fn)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, i18n.tr("msg_open_failed"), str(e))
            return
        self._apply_doc(doc)
        note = "; ".join(doc.warnings[:4]) if doc.warnings else "ok"
        self.statusBar().showMessage(i18n.tr(
            "status_opened", file=Path(fn).name,
            n=len(doc.pages), note=note))

    def _apply_doc(self, doc: Doc) -> None:
        """Swap in a fresh document read from disk without stale back-writes."""
        self._detach_scene()
        self.doc = doc
        self.current_page = 0
        self.refresh_page_list()
        self.load_page(0)

    def save_file(self) -> None:
        self._sync_page_model()
        fn, _ = QFileDialog.getSaveFileName(
            self, i18n.tr("dlg_save_title"), i18n.tr("save_default_name"),
            "BananaNote (*.bnx)")
        if not fn:
            return
        if not fn.lower().endswith(".bnx"):
            fn += ".bnx"
        write_bnx(self.doc, fn)
        self.dirty = False
        self.statusBar().showMessage(i18n.tr("status_saved", file=fn))

    def export_png(self) -> None:
        self._sync_page_model()
        fn, _ = QFileDialog.getSaveFileName(
            self, i18n.tr("dlg_export_title"), "page_1.png",
            "PNG image (*.png)")
        if not fn:
            return
        page = self.doc.pages[self.current_page]
        img = QImage(int(page.w), int(page.h), QImage.Format.Format_ARGB32)
        img.fill(qcolor(page.background))
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.scene().render(painter, self.view.sceneRect())
        painter.end()
        img.save(fn)
        self.statusBar().showMessage(i18n.tr("status_exported", file=fn))

    # -------------------------------------------------------------- presenter
    def open_present(self) -> None:
        present = self._present
        if present is not None and present.isVisible():
            present.raise_()
            present.activateWindow()
            return
        self._sync_page_model()
        self._present = PresentWindow(self.doc, self.current_page)
        self._present.finished_present.connect(self._present_finished)
        self._present.showFullScreen()

    def _present_finished(self, changed: bool) -> None:
        present = self._present
        if present is None:
            return
        if changed:
            self._detach_scene()  # scene is stale; never back-write it
            self.current_page = present.current_page
            self.refresh_page_list()
            self.load_page(self.current_page)
            self.dirty = True
        self.statusBar().showMessage(i18n.tr("status_present_ended"))

    # -------------------------------------------------------------- easter egg
    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self._statusbar and \
                event.type() == QEvent.Type.MouseButtonPress and \
                event.button() == Qt.MouseButton.LeftButton:
            self._egg_bump()
        return super().eventFilter(obj, event)

    def _egg_bump(self) -> None:
        """5 clicks on the status bar within a short time unlock the surprise."""
        import time
        now = time.monotonic()
        if now - self._egg_last > 3.0:
            self._egg_clicks = 0
        self._egg_last = now
        self._egg_clicks += 1
        if self._egg_clicks >= 5:
            self._egg_clicks = 0
            self.show_upgrade_easter_egg()

    def show_upgrade_easter_egg(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(i18n.tr("easter_title"))
        lay = QVBoxLayout(dlg)
        pic = QLabel()
        pix = QPixmap(str(Path(__file__).parent / "res" / "upgrade_memory.png"))
        if not pix.isNull():
            pic.setPixmap(pix.scaled(
                320, 520, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        else:
            pic.setText(i18n.tr("easter_title"))
        pic.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(pic)
        cap = QLabel(i18n.tr("easter_caption"), dlg)
        cap.setWordWrap(True)
        cap.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(cap)
        dlg.exec()

    # -------------------------------------------------------------- lifecycle
    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        page = self.doc.pages[self.current_page]
        self.view.fit_in(page.w, page.h)

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self.dirty:
            event.accept()
            return
        box = QMessageBox(self)
        box.setWindowTitle(i18n.tr("msg_unsaved_title"))
        box.setText(i18n.tr("msg_unsaved"))
        buttons = {}
        for key, role in [("msg_discard", QMessageBox.ButtonRole.DestructiveRole),
                          ("msg_cancel", QMessageBox.ButtonRole.RejectRole),
                          ("msg_save", QMessageBox.ButtonRole.AcceptRole)]:
            btn = box.addButton(i18n.tr(key), role)
            buttons[key] = btn
        box.exec()
        clicked = box.clickedButton()
        if clicked is buttons["msg_save"]:
            self.save_file()
            event.accept()
        elif clicked is buttons["msg_discard"]:
            event.accept()
        else:
            event.ignore()
