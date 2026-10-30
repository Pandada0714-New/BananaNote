"""Minimal i18n: tr(key, **kw) with en / zh string tables."""

from __future__ import annotations

LANGS = ["en", "zh"]

TABLES: dict[str, dict[str, str]] = {
    "en": {
        "app_title": "BananaNote",
        "ready": "Ready — BananaNote 26.1-prerelease-2",
        "menu_settings": "&Settings",
        "menu_language": "&Language",
        "menu_upgrade_memory": "Upgrade Memory &Image",
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
        "present": "Present (F5)",
        "present_title": "BananaNote — Presentation",
        "present_exit": "Exit (Esc)",
        "present_prev": "◀ Prev",
        "present_next": "Next ▶",
        "present_page_label": "Page {i} / {n}",
        "status_present_ended": "Presentation ended — annotations kept",
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
        "easter_title": "Level up! Lv11 Silver 🎉",
        "easter_caption":
            "You found the hidden easter egg! Teacher panda has been using "
            "EasiNotes for 1622 days, created 121 courseware files, and just "
            "reached Lv11 Silver — top 55.9% nationwide.",
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
        "menu_upgrade_memory": "升级记忆图片(&I)",
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
        "present": "放映 (F5)",
        "present_title": "BananaNote — 放映模式",
        "present_exit": "结束放映 (Esc)",
        "present_prev": "◀ 上一页",
        "present_next": "下一页 ▶",
        "present_page_label": "第 {i} / {n} 页",
        "status_present_ended": "放映结束 — 批注已保留",
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
        "easter_title": "恭喜升级！Lv11 白银 🎉",
        "easter_caption":
            "你发现了 BananaNote 的隐藏彩蛋！panda 老师已使用希沃白板 1622 天，"
            "制作过 121 份课件，等级已超过全国 55.9% 的老师——恭喜升级 Lv11 白银！",
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
