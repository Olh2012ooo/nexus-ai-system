#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 NEXUS project contributors
"""Check that every relative markdown link and image in the repository resolves.

Ignores absolute URLs and in-page anchors. Exits 1 on any broken link.

    python3 tools/check_links.py
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
FENCE = re.compile(r"```.*?```", re.S)


def strip_code(text: str) -> str:
    return FENCE.sub("", text)


def main() -> int:
    broken: list[tuple[str, str]] = []
    checked = 0
    for dirpath, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in {".git", "__pycache__"}]
        for name in files:
            if not name.endswith(".md"):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding="utf-8") as fh:
                text = strip_code(fh.read())
            for target in LINK.findall(text):
                target = target.strip()
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                file_part = target.split("#", 1)[0]
                if not file_part:
                    continue
                resolved = os.path.normpath(os.path.join(dirpath, file_part))
                checked += 1
                if not os.path.exists(resolved):
                    broken.append((os.path.relpath(path, ROOT), target))
    print(f"checked {checked} relative links in {ROOT}")
    if broken:
        print(f"BROKEN ({len(broken)}):")
        for src, target in broken:
            print(f"  {src} -> {target}")
        return 1
    print("all relative links resolve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
