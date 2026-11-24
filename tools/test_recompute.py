#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 NEXUS project contributors
"""Tests for the cost calculator: default output, argument validation, exit codes.

Run:  python3 tools/test_recompute.py
Exit 0 only if every case behaves as specified.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

CALC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "calculations", "recompute.py")
RESULTS: list[bool] = []


def report(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name:46}{'' if ok else '  ' + detail}")


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, CALC, *args], capture_output=True, text=True,
                          timeout=60)


def expect_exit(name: str, code: int, *args: str) -> None:
    proc = run(*args)
    ok = proc.returncode == code and "Traceback" not in (proc.stdout + proc.stderr)
    report(name, ok, f"expected exit {code}, got {proc.returncode}: {proc.stderr.strip()[:120]}")


def main() -> int:
    proc = run()
    text = proc.stdout
    report("defaults exit 0", proc.returncode == 0, proc.stderr[:120])
    for label, pattern in [
        ("defaults: Claude total 53 127 NOK", r"5,484\.61 USD = +53,127 NOK"),
        ("defaults: Nexus 62.1 NOK", r"6\.41 USD = +62\.1 NOK"),
        ("defaults: ratio 856x", r"ratio 856x"),
        ("defaults: reduction 99.88 %", r"reduction 99\.88 %"),
        ("defaults: difference 53,065 NOK", r"difference 53,065 NOK"),
        ("defaults: peak 124 NOK", r"peak prices: 124 NOK"),
    ]:
        report(label, bool(re.search(pattern, text)), pattern)

    # Valid edge values must still work.
    expect_exit("--claude-hit 0 is accepted", 0, "--claude-hit", "0")
    expect_exit("--claude-hit 1 is accepted", 0, "--claude-hit", "1")
    expect_exit("--mix 0.5 is accepted", 0, "--mix", "0.5")
    expect_exit("--fx 9.6866 is accepted", 0, "--fx", "9.6866")

    # Invalid shares: outside the interval, non-numeric, NaN, infinite.
    for value in ("1.5", "-0.1", "0", "1", "nan", "inf", "-inf", "abc"):
        expect_exit(f"--mix {value!r} is rejected", 2, "--mix", value)
    for value in ("1.5", "-0.1", "2", "nan", "inf", "abc"):
        expect_exit(f"--claude-hit {value!r} is rejected", 2, "--claude-hit", value)

    # Invalid currency rate.
    for value in ("0", "-1", "nan", "inf", "abc"):
        expect_exit(f"--fx {value!r} is rejected", 2, "--fx", value)

    # The validation message must name the flag and the rule, not a stack trace.
    proc = run("--mix", "1.5")
    report("error names the flag", "--mix" in proc.stderr, proc.stderr.strip()[:120])
    report("error states the rule", "0 < x < 1" in proc.stderr, proc.stderr.strip()[:120])
    report("no traceback on bad input", "Traceback" not in proc.stderr, proc.stderr.strip()[:120])

    passed, total = sum(RESULTS), len(RESULTS)
    print(f"\n{passed}/{total} cases behaved as specified")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
