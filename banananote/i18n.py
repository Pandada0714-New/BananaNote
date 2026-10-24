"""Minimal i18n: tr(key, **kw) with en / zh string tables."""

from __future__ import annotations

LANGS = ["en", "zh"]

TABLES: dict[str, dict[str, str]] = {
    "en": {
        "app_title": "BananaNote",
        "ready": "Ready — BananaNote 26.1-prerelease-2",
        "menu_settings": "&Settings",
        "menu_language": "&Language",
        "lang_en": "English",
        "lang_zh": "简体中文",
        # tools
        "tool_select": "Select",
        "tool_pen": "Pen",
        "tool_highlighter": "Highlighter",
        "tool_eraser": "Eraser",
        "tool_text": "Text",
        "tool_rect": "Rectangle",
        "tool_ellipse": "Ellipse",
        "tool_line": "Line",
        "tool_image": "Image",
        "status_mode": "Mode: {mode}",
        "custom_color": "Custom...",
        "width_label": "Width",
        "undo": "Undo",
        "redo": "Redo",
        "clear_page": "Clear Page",
        "export_png": "Export PNG",
        "open": "Open .enbx / .bnx",
        "save": "Save .bnx",
        "new_page": "New Page",
        "delete_page": "Delete Page",
        "duplicate": "Duplicate",
        "page_item": "Page {n}",
        "window_title": "BananaNote — {name} (Page {i}/{n})",
        # dialogs
        "dlg_open_title": "Open",
        "dlg_save_title": "Save",
        "dlg_export_title": "Export PNG",
        "dlg_insert_image": "Insert Image",
        "file_dialog_filter":
            "Supported (*.enbx *.bnx);;EasiNote (*.enbx);;BananaNote (*.bnx)",
        "images_filter": "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)",
        # status
        "status_opened":
            "Opened {file}: {n} page(s). Parser notes: {note}",
        "status_saved": "Saved {file}",
        "status_exported": "Exported {file}",
        "status_cleared": "Page cleared",
        "status_page": "Page {i} — {n} elements",
        "save_default_name": "untitled.bnx",
        # messages
        "msg_open_failed": "Open failed",
        "msg_unsaved_title": "Unsaved changes",
        "msg_unsaved": "You have unsaved changes. Save before quitting?",
        "msg_save": "Save",
        "msg_discard": "Discard",
        "msg_cancel": "Cancel",
    },
    "zh": {
        "app_title": "BananaNote",
        "ready": "就绪 — BananaNote 26.1-prerelease-2",
        "menu_settings": "&设置",
        "menu_language": "语言(&L)",
        "lang_en": "English",
        "lang_zh": "简体中文",
        "tool_select": "选择",
        "tool_pen": "画笔",
        "tool_highlighter": "荧光笔",
        "tool_eraser": "橡皮",
        "tool_text": "文本",
        "tool_rect": "矩形",
        "tool_ellipse": "椭圆",
        "tool_line": "直线",
        "tool_image": "图片",
        "status_mode": "模式：{mode}",
        "custom_color": "自定义...",
        "width_label": "宽度",
        "undo": "撤销",
        "redo": "重做",
        "clear_page": "清空本页",
        "export_png": "导出 PNG",
        "open": "打开 .enbx / .bnx",
        "save": "保存 .bnx",
        "new_page": "新建页",
        "delete_page": "删除页",
        "duplicate": "复制本页",
        "page_item": "第 {n} 页",
        "window_title": "BananaNote — {name}（第 {i}/{n} 页）",
        "dlg_open_title": "打开",
        "dlg_save_title": "保存",
        "dlg_export_title": "导出 PNG",
        "dlg_insert_image": "插入图片",
        "file_dialog_filter":
            "支持格式 (*.enbx *.bnx);;希沃易课堂 (*.enbx);;BananaNote (*.bnx)",
        "images_filter": "图片 (*.png *.jpg *.jpeg *.bmp *.gif *.webp)",
        "status_opened": "已打开 {file}：{n} 页。解析提示：{note}",
        "status_saved": "已保存 {file}",
        "status_exported": "已导出 {file}",
        "status_cleared": "本页已清空",
        "status_page": "第 {i} 页 — {n} 个元素",
        "save_default_name": "未命名.bnx",
        "msg_open_failed": "打开失败",
        "msg_unsaved_title": "未保存",
        "msg_unsaved": "存在未保存的更改，退出前保存吗？",
        "msg_save": "保存",
        "msg_discard": "不保存",
        "msg_cancel": "取消",
    },
}

_current: str = "en"


def detect_default() -> str:
    import locale
    import os
    env = os.environ.get("LC_ALL") or os.environ.get("LANG") or ""
    code = env.split(".", 1)[0].lower()
    if not code:
        try:
            code = locale.getdefaultlocale()[0] or ""
        except Exception:  # noqa: BLE001
            code = ""
    return "zh" if code.startswith("zh") else "en"


def set_language(code: str) -> None:
    global _current
    if code in LANGS:
        _current = code


def get_language() -> str:
    return _current


def tr(key: str, **kw) -> str:
    text = TABLES.get(_current, {}).get(key) or TABLES["en"][key]
    if kw:
        text = text.format(**kw)
    return text
