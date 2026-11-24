#!/usr/bin/env python3
"""Validate the generated diagrams: well-formed XML, and no text outside the viewBox.

The width estimate is deliberately generous: it catches clipped or overflowing labels, not
typographic perfection.

Run:  python3 tools/check_diagrams.py
Exit 0 when every SVG parses and every text run is estimated to fit.
"""
from __future__ import annotations

import glob
import os
import re
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIAGRAMS = os.path.join(ROOT, "diagrams")
NS = "{http://www.w3.org/2000/svg}"


def check(path: str) -> list[str]:
    problems: list[str] = []
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        return [f"not well-formed XML: {exc}"]
    root = tree.getroot()
    try:
        width = float(root.get("width", "0"))
        height = float(root.get("height", "0"))
    except ValueError:
        return ["width/height are not numbers"]
    if width <= 0 or height <= 0:
        problems.append("missing or non-positive width/height")
    viewbox = root.get("viewBox")
    if not viewbox:
        problems.append("missing viewBox")
    for node in root.iter(f"{NS}text"):
        text = "".join(node.itertext())
        if not text.strip():
            continue
        try:
            x = float(node.get("x", "0"))
            y = float(node.get("y", "0"))
            size = float(node.get("font-size", "12"))
        except ValueError:
            problems.append(f"non-numeric position for {text[:24]!r}")
            continue
        width_est = len(text) * size * 0.56
        anchor = node.get("text-anchor", "start")
        left = x - width_est if anchor == "end" else (x - width_est / 2 if anchor == "middle"
                                                      else x)
        if left < 0 or left + width_est > width or y > height:
            problems.append(f"text outside viewBox: {text[:40]!r}")
    return problems


def main() -> int:
    paths = sorted(glob.glob(os.path.join(DIAGRAMS, "*.svg")))
    if not paths:
        print("ERROR: no SVG files found", file=sys.stderr)
        return 2
    failed = 0
    for path in paths:
        problems = check(path)
        name = os.path.basename(path)
        if problems:
            failed += 1
            print(f"FAIL {name}")
            for problem in problems[:5]:
                print(f"     {problem}")
        else:
            print(f"ok   {name}")
    print(f"\n{len(paths) - failed}/{len(paths)} diagrams valid")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
