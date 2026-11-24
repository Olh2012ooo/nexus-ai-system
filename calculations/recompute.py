#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 NEXUS project contributors
"""Cost calculator for the published comparison.

Two columns, one workload unit (1 billion tokens):

  Claude Opus 5.5  published list prices, 80 % cache hit, 20.42 % output share.
  Nexus            an observed window: cost, token volumes and cache hits as logged by the
                   runtime, normalised to one billion tokens.

Both are CALCULATED API token costs. Neither is an invoice, and the two columns do not share a
token mix — see docs/economics.md.

Published prices (verify before reuse):
  Claude Opus 5.5  https://platform.claude.com/docs/en/about-claude/pricing
  DeepSeek Flash   https://api-docs.deepseek.com/quick_start/pricing

Usage
    python3 calculations/recompute.py
    python3 calculations/recompute.py --fx 9.6866 --claude-hit 0.80
"""
from __future__ import annotations

import argparse
import math

FX_DEFAULT = 9.6866      # USD/NOK assumption used throughout the project

# --- Claude column: published prices, assumed workload shape ------------------------------
CLAUDE_BASE = 4.00       # USD per 1M input tokens
CLAUDE_READ = 0.20       # cache hit (0.05x base)
CLAUDE_WRITE_1H = 8.00   # one-hour cache write (2x base)
CLAUDE_OUT = 20.00
CLAUDE_HIT_DEFAULT = 0.80
MIX_DEFAULT = 0.2042     # output share of total tokens

# --- Nexus column: one observed window, normalised to 1 billion tokens --------------------
# The rate and mix of one aggregated, undated observation window. The absolute spend and token
# volumes are deliberately not part of this repository (see SECURITY.md); the mix and the rate
# are what the comparison needs.
OBS_COST_PER_BILLION_USD = 6.41
OBS_OUTPUT_SHARE = 0.0039     # output tokens as a share of the total
OBS_HIT_RATE = 0.9922         # cached input tokens as a share of input

# DeepSeek Flash, off-peak, USD per 1M tokens
FLASH_HIT = 0.003
FLASH_MISS = 0.15
FLASH_OUT = 0.60
FLASH_PEAK_MULTIPLIER = 2.0


def _finite(text: str, flag: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}") from None
    if not math.isfinite(value):
        raise argparse.ArgumentTypeError(f"must be a finite number, got {text!r}")
    return value


def share(text: str, flag: str, *, open_interval: bool) -> float:
    """Parse a proportion. Rejects NaN, infinity, non-numbers and out-of-range values."""
    value = _finite(text, flag)
    low_ok = value > 0 if open_interval else value >= 0
    high_ok = value < 1 if open_interval else value <= 1
    if not (low_ok and high_ok):
        bound = "0 < x < 1" if open_interval else "0 <= x <= 1"
        raise argparse.ArgumentTypeError(f"must satisfy {bound}, got {text!r}")
    return value


def positive(text: str, flag: str) -> float:
    value = _finite(text, flag)
    if value <= 0:
        raise argparse.ArgumentTypeError(f"must be greater than 0, got {text!r}")
    return value


def fx_arg(text: str) -> float:
    return positive(text, "--fx")


def mix_arg(text: str) -> float:
    return share(text, "--mix", open_interval=True)


def hit_arg(text: str) -> float:
    return share(text, "--claude-hit", open_interval=False)


def claude(total_tokens: float, mix: float, hit: float) -> dict:
    inp_m, out_m = total_tokens * (1 - mix) / 1e6, total_tokens * mix / 1e6
    read = inp_m * hit * CLAUDE_READ
    write = inp_m * (1 - hit) * CLAUDE_WRITE_1H
    output = out_m * CLAUDE_OUT
    return dict(read=read, write=write, out=output, total=read + write + output)


def observed_per_billion() -> dict:
    """Cost and token mix for exactly one billion tokens, from the observed window."""
    total = 1_000_000_000
    output = total * OBS_OUTPUT_SHARE
    inp = total - output
    return dict(
        cost_usd=OBS_COST_PER_BILLION_USD,
        input_tokens=inp,
        output_tokens=output,
        cached_tokens=inp * OBS_HIT_RATE,
        output_share=OBS_OUTPUT_SHARE,
        hit_rate=OBS_HIT_RATE,
    )


def price_check() -> float:
    """Cost of one billion tokens at the observed mix, recomputed from list prices."""
    n = observed_per_billion()
    return (n["cached_tokens"] / 1e6 * FLASH_HIT
            + (n["input_tokens"] - n["cached_tokens"]) / 1e6 * FLASH_MISS
            + n["output_tokens"] / 1e6 * FLASH_OUT)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fx", type=fx_arg, default=FX_DEFAULT,
                    help="USD/NOK, must be finite and greater than 0")
    ap.add_argument("--mix", type=mix_arg, default=MIX_DEFAULT,
                    help="Claude output share of total tokens, 0 < x < 1")
    ap.add_argument("--claude-hit", type=hit_arg, default=CLAUDE_HIT_DEFAULT,
                    help="Claude cache-hit ratio, 0 <= x <= 1")
    a = ap.parse_args()

    c = claude(1_000_000_000, a.mix, a.claude_hit)
    n = observed_per_billion()
    claude_nok = c["total"] * a.fx
    nexus_nok = n["cost_usd"] * a.fx
    ratio = claude_nok / nexus_nok

    print("Workload unit: 1 000 000 000 tokens per column\n")
    print(f"Claude Opus 5.5, {a.claude_hit * 100:.0f} % cache hit, {a.mix * 100:.2f} % output")
    print(f"  cache read    {c['read']:10,.2f} USD")
    print(f"  cache write   {c['write']:10,.2f} USD   (1-hour tier)")
    print(f"  output        {c['out']:10,.2f} USD")
    print(f"  total         {c['total']:10,.2f} USD = {claude_nok:>10,.0f} NOK per billion\n")
    print("Nexus, observed window normalised to 1 billion tokens")
    print(f"  tokens        {n['input_tokens'] / 1e6:,.1f} M input "
          f"({n['cached_tokens'] / 1e6:,.1f} M cached, {n['hit_rate'] * 100:.2f} % hit), "
          f"{n['output_tokens'] / 1e6:,.2f} M output ({n['output_share'] * 100:.2f} %)")
    print(f"  cost          {n['cost_usd']:10,.2f} USD = {nexus_nok:>10,.1f} NOK per billion")
    print(f"  mix check     {price_check():10,.2f} USD at list prices "
          f"({100 * (price_check() - n['cost_usd']) / n['cost_usd']:+.1f} % vs the rate; "
          f"percentages are rounded)\n")
    peak_nok = nexus_nok * FLASH_PEAK_MULTIPLIER
    print(f"ratio {ratio:,.0f}x  ·  reduction {100 * (1 - 1 / ratio):.2f} %  ·  difference "
          f"{claude_nok - nexus_nok:,.0f} NOK per billion")
    print(f"Nexus at peak prices: {peak_nok:,.0f} NOK "
          f"(ratio {claude_nok / peak_nok:,.0f}x)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
