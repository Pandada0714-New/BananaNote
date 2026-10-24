"""Inspect an .enbx package: structure, slide XML dumps, resource inventory.

Usage:
    python -m banananote.enbx.debug_dump 1.enbx [Slide_0.xml]

Used to calibrate the heuristic parser when new element types appear in
real-world courseware.
"""

from __future__ import annotations

import sys
import zipfile
from xml.etree import ElementTree as ET

from .reader import read_enbx


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        return
    path = sys.argv[1]
    with zipfile.ZipFile(path) as zf:
        print("== package contents ==")
        for info in zf.infolist():
            print(f"  {info.filename}  ({info.file_size} bytes)")
        doc = read_enbx(path)
        print(f"\n== parsed: {doc.name} — {len(doc.pages)} page(s), "
              f"{doc.width}x{doc.height} ==")
        for i, page in enumerate(doc.pages):
            print(f"  page {i}: bg={page.background} "
                  f"elements={[e.kind for e in page.elements]}")
        for w in getattr(doc, "warnings", []):
            print(f"  warning: {w}")
        print("\n== slide xml dumps ==")
        for name in zf.namelist():
            if name.startswith("Slides/") and name.endswith(".xml"):
                if len(sys.argv) > 2 and sys.argv[2] not in name:
                    continue
                head = zf.read(name)
                try:
                    pretty = ET.tostring(ET.fromstring(head), encoding="unicode")
                except ET.ParseError:
                    pretty = head.decode("utf-8", "replace")
                print(f"--- {name} ---")
                print(pretty)


if __name__ == "__main__":
    main()
