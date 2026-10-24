# BananaNote

Free, clean whiteboard / courseware editor. Imports Seewo EasiNote `.enbx`
files. No ads, no points, no accounts.

- Cross-platform (Windows first), Python + PySide6 (Qt6)
- Native save format: `.bnx` (a small zip: JSON + embedded resources)
- Reads `.enbx` V5 packages (verified against EasiNote 5.2.4.11582)

## Features (26.1-prerelease-2)

- Pen / Highlighter / Eraser / Text / Rect / Ellipse / Line / Image tools
- Multi-page sidebar (add / delete / duplicate)
- Undo / redo per page, clear page
- Open `.enbx` and `.bnx`, save `.bnx`, export current page as PNG
- Color swatches + custom color, stroke width control
- Structural `.enbx` import (new in prerelease-2):
  - slide order / size / page backgrounds (color and full-page images)
  - text boxes with font family / size / color / bold and wrap width
  - pictures with source crop and rotation, videos (poster frame), audio
    (speaker icon + file name label)
  - shapes: rectangles, ellipses, hand-drawn paths, embedded captions
  - tables (grid lines, merged cells, per-cell text), mind-map topic texts,
    classical-poetry panels (title / author / body)
  - unmapped widgets are skipped safely and listed in the status bar

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
Resources/ Media/  embedded images & media (payloads are plain PNG/JPEG/MP4)
SlideThumbnails/   pre-rendered page thumbnails
```

The importer parses the slide structure directly: `Board.xml` gives the page
order, each `Slide_N.xml` lists elements that are converted element by
element. Media is referenced through `id://<uuid>` keys into `Resources/`;
the payload bytes identify the real format.

Verified against a real 29-slide grade-2 language courseware (`春.enbx`): all
pages, backgrounds, images, shapes, tables, texts and media land where the
original EasiNote render puts them. Known limitations:

- animations / page transitions are ignored (reported after import)
- topic (mind-map) connector lines are not drawn; node texts are kept
- some decorative crop/aspect edge cases are approximate

Elements that cannot be mapped are skipped safely and reported in the status
bar after opening (nothing crashes, nothing silently vanishes without a note).

## Roadmap

- [ ] Topic connector lines; audio/video playback in-app
- [ ] Export all pages to PDF
- [ ] Table / chemistry / geometry widget equivalents
- [ ] Displaydriver-friendly fullscreen presentation mode
- [ ] Element-level undo and clipboard
