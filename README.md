# BananaNote

Free, clean whiteboard / courseware editor. Imports Seewo EasiNote `.enbx`
files. No ads, no points, no accounts.

- Cross-platform (Windows first), Python + PySide6 (Qt6)
- Native save format: `.bnx` (a small zip: JSON + embedded resources)
- Reads `.enbx` V5 packages (verified against EasiNote 5.2.4.11582)

## Features (v0.1)

- Pen / Highlighter / Eraser / Text / Rect / Ellipse / Line / Image tools
- Multi-page sidebar (add / delete / duplicate)
- Undo / redo per page, clear page
- Open `.enbx` and `.bnx`, save `.bnx`, export current page as PNG
- Color swatches + custom color, stroke width control

## Quick start

```bash
pip install -r requirements.txt
python -m banananote
```

Linux headless test (no display needed):

```bash
QT_QPA_PLATFORM=offscreen python -m banananote.enbx.debug_dump your_file.enbx
```

## Windows

1. Install Python 3.11+ from python.org (check "Add to PATH").
2. `pip install -r requirements.txt`
3. `python -m banananote`

Build a standalone exe:

```bash
pip install pyinstaller
pyinstaller --windowed --name BananaNote -m banananote
```

The exe appears in `dist/BananaNote/`.

## About .enbx support

``.enbx`` is a ZIP package. Confirmed layout:

```
Board.xml          slide size + ordered slide GUID list
Slides/Slide_N.xml per-slide size / background / element markup
Document.xml       metadata
Resources/ Media/  embedded images & media
SlideThumbnails/   pre-rendered page thumbnails
```

Page structure, size, order and background parse hard. Element markup inside
slides is undocumented, so element conversion is heuristic: text / ink /
image / shape nodes are matched by tag-name hints. Real courseware with rich
content helps calibrate this quickly - run the debug_dump command above on
such a file and share the output.

Elements that cannot be mapped are skipped safely and reported in the status
bar after opening (nothing crashes, nothing silently vanishes without a note).

## Roadmap

- [ ] Calibrate element parser against real rich courseware
- [ ] Export all pages to PDF
- [ ] Table / chemistry / geometry widget equivalents
- [ ] Displaydriver-friendly fullscreen presentation mode
- [ ] Element-level undo and clipboard
