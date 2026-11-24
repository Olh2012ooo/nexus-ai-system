#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 NEXUS project contributors
"""Render the six project diagrams as SVG.

One visual system for all of them: neutral canvas, one accent per meaning, 12–15 px labels,
nothing decorative that does not carry information. Figures are copied by hand from the
documents, so a changed number means a re-render.

    python3 diagrams/render.py
"""
from __future__ import annotations

import os

INK = "#0b1220"
MUTED = "#5b6b82"
BORDER = "#d7dee8"
PANEL = "#f6f8fb"
BG = "#ffffff"
BLUE = "#1d4ed8"
GREEN = "#047857"
AMBER = "#b45309"
RED = "#b91c1c"
PURPLE = "#6d28d9"
SLATE = "#94a3b8"
FONT = "Inter, 'Segoe UI', Helvetica, Arial, sans-serif"
OUT = os.path.dirname(os.path.abspath(__file__))


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Svg:
    def __init__(self, w: int, h: int, title: str, subtitle: str = ""):
        self.w, self.h, self.title, self.subtitle = w, h, title, subtitle
        self.parts: list[str] = []
        self.defs = "".join(
            f'<marker id="{mid}" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" '
            f'markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L8,4 L0,8 z" '
            f'fill="{color}"/></marker>'
            for mid, color in (("g", MUTED), ("b", BLUE), ("a", AMBER), ("r", RED), ("v", GREEN))
        )

    # primitives ---------------------------------------------------------
    def box(self, x, y, w, h, title, lines=(), accent=BLUE, fill=PANEL, r=10):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" '
                          f'fill="{fill}" stroke="{accent}" stroke-width="1.3"/>')
        self.parts.append(f'<rect x="{x}" y="{y}" width="4" height="{h}" rx="2" fill="{accent}"/>')
        ty = y + 25
        self.parts.append(f'<text x="{x + 15}" y="{ty}" font-family="{FONT}" font-size="14.5" '
                          f'font-weight="600" fill="{INK}">{esc(title)}</text>')
        for ln in lines:
            ty += 17
            self.parts.append(f'<text x="{x + 15}" y="{ty}" font-family="{FONT}" '
                              f'font-size="12" fill="{MUTED}">{esc(ln)}</text>')

    def pill(self, x, y, w, h, text, color=BLUE, size: float = 12):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h / 2}" '
                          f'fill="{color}" opacity="0.10" stroke="{color}"/>')
        self.parts.append(f'<text x="{x + w / 2}" y="{y + h / 2 + 4}" font-family="{FONT}" '
                          f'font-size="{size}" fill="{color}" text-anchor="middle" '
                          f'font-weight="600">{esc(text)}</text>')

    def text(self, x, y, s, size: float = 12, color=MUTED, anchor="start", weight="400"):
        self.parts.append(f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" '
                          f'fill="{color}" text-anchor="{anchor}" font-weight="{weight}">'
                          f'{esc(s)}</text>')

    def arrow(self, x1, y1, x2, y2, label="", color=MUTED, marker="g", dashed=False):
        dash = ' stroke-dasharray="4 4"' if dashed else ""
        self.parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
                          f'stroke-width="1.4" marker-end="url(#{marker})"{dash}/>')
        if label:
            self.text((x1 + x2) / 2, (y1 + y2) / 2 - 8, label, 11, color, "middle")

    def poly(self, points, color=MUTED, marker="g", dashed=False, label="", lx=None, ly=None):
        dash = ' stroke-dasharray="4 4"' if dashed else ""
        d = " ".join(("M" if i == 0 else "L") + f"{x},{y}" for i, (x, y) in enumerate(points))
        self.parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.4" '
                          f'marker-end="url(#{marker})"{dash}/>')
        if label:
            x, y = (points[0] if lx is None else (lx, ly))
            self.text(x, y, label, 11, color, "middle")

    def panel(self, x, y, w, h, title=""):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" '
                          f'fill="{PANEL}" stroke="{BORDER}" stroke-width="1"/>')
        if title:
            self.text(x + 18, y + 24, title.upper(), 10.5, MUTED, "start", "700")

    def legend(self, x, y, items):
        for i, (color, label) in enumerate(items):
            yy = y + i * 19
            self.parts.append(f'<rect x="{x}" y="{yy - 9}" width="11" height="11" rx="3" '
                              f'fill="{color}"/>')
            self.text(x + 18, yy + 1, label, 11.5)

    def note(self, x, y, s, color=MUTED, size: float = 11.5):
        self.text(x, y, s, size, color)

    def render(self) -> str:
        body = [f'<rect width="{self.w}" height="{self.h}" fill="{BG}"/>',
                f'<text x="44" y="48" font-family="{FONT}" font-size="23" font-weight="700" '
                f'fill="{INK}">{esc(self.title)}</text>']
        if self.subtitle:
            body.append(f'<text x="44" y="72" font-family="{FONT}" font-size="13" '
                        f'fill="{MUTED}">{esc(self.subtitle)}</text>')
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
                f'viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{esc(self.title)}">'
                f'<defs>{self.defs}</defs>' + "".join(body + self.parts) + "</svg>")


def write(name: str, svg: Svg) -> None:
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
        fh.write(svg.render())
    print(f"wrote diagrams/{name}")


# 1 ---------------------------------------------------------------- overview
def system_overview() -> Svg:
    s = Svg(1200, 770, "Nexus — system overview",
            "Request → orchestration → specialists → tools and execution → verification → result. "
            "One control node reasons; the rest executes.")
    # top flow
    s.box(44, 108, 150, 72, "Operator", ["request"], SLATE)
    s.box(224, 108, 170, 72, "Gateway", ["session, routing"], BLUE)
    s.box(424, 108, 190, 72, "Nexus", ["orchestrator"], BLUE)
    s.box(644, 108, 250, 72, "Specialists", ["Jarvis · Ultron · Athena · Sentinel"], PURPLE)
    s.arrow(194, 144, 224, 144)
    s.arrow(394, 144, 424, 144)
    s.arrow(614, 144, 644, 144, "")
    s.text(629, 100, "delegate", 11, MUTED, "middle")
    # tools row
    s.box(424, 240, 190, 88, "Tool layer", ["shell · SSH · MCP", "files · HTTP"], BLUE)
    s.box(644, 240, 250, 88, "Execution", ["4 remote nodes", "1 Windows workstation"], AMBER)
    s.box(924, 240, 232, 88, "Model API", ["prefix cache", "1M context"], RED)
    s.arrow(518, 180, 518, 240, "")
    s.arrow(614, 284, 644, 284, "")
    s.text(629, 268, "SSH", 11, MUTED, "middle")
    s.arrow(894, 270, 924, 270, "")
    # verification + result
    s.box(424, 380, 300, 92, "Verification", ["read back the artefact:", "file · hash · exit code · row"], GREEN)
    s.box(764, 380, 392, 92, "Result", ["task board updated · documentation mirrored",
                                        "claim stated with its evidence"], GREEN)
    s.arrow(518, 328, 518, 380, "")
    s.arrow(724, 426, 764, 426, "")
    s.poly([(1156, 380), (1186, 380), (1186, 166), (900, 166)], GREEN, "v", dashed=True,
           label="review / rework", lx=1046, ly=158)
    # kanban strip
    s.panel(44, 512, 1112, 124, "task board — every request becomes a task")
    states = ["todo", "ready", "running", "review", "done"]
    x = 68
    for i, st in enumerate(states):
        s.pill(x, 552, 176, 34, st, GREEN if st == "done" else BLUE)
        if i:
            s.arrow(x - 22, 569, x - 4, 569)
        x += 200
    s.pill(68, 596, 176, 30, "blocked", AMBER, 11)
    s.text(268, 616, "a task closes with evidence — review approval is the documented exemption")
    s.legend(44, 668, [(BLUE, "agent / control"), (PURPLE, "specialist profiles"),
                       (AMBER, "remote execution"), (GREEN, "state and verification")])
    return s


# 2 --------------------------------------------------------------- agents
def agent_architecture() -> Svg:
    s = Svg(1200, 640, "Agent architecture",
            "Nexus is the only entry point. The other four run only as delegated child sessions.")
    s.box(470, 104, 260, 92, "Nexus", ["orchestrator · root session"], BLUE)
    roles = [("Jarvis", "planning", "decomposition, risk"), ("Ultron", "development", "code, infra, tests"),
             ("Athena", "research", "sources, analysis"), ("Sentinel", "quality", "falsify, verdicts")]
    for i, (name, role, desc) in enumerate(roles):
        x = 44 + i * 288
        s.box(x, 280, 262, 104, name, [role, desc], PURPLE)
        s.arrow(600, 196, x + 131, 280, "", PURPLE, "g")
    s.box(44, 424, 540, 92, "child context", ["own prompt · own memory · own workspace",
                                              "plus the payload the parent wrote"], SLATE)
    s.box(616, 424, 540, 92, "returned to the parent", ["status · summary · token counts",
                                                        "tool trace · transcript"], GREEN)
    s.note(44, 552, "Same runtime and same model for all five: independence is procedural, not model diversity.")
    s.note(44, 574, "Limits: 4 children per batch · depth 1 · 60 iterations · no shared conversation.")
    s.note(44, 608, "Delegation is a routing decision (profile), not a second machine.", MUTED)
    return s


# 3 --------------------------------------------------------- infrastructure
def infrastructure() -> Svg:
    s = Svg(1200, 690, "Machine architecture",
            "One control node holds all reasoning and state. Execution targets hold neither.")
    s.panel(44, 104, 470, 300, "Nexus control node")
    s.box(68, 136, 200, 92, "agents", ["5 profiles"], BLUE)
    s.box(288, 136, 202, 92, "runtime", ["loop · tools · context"], BLUE)
    s.box(68, 248, 200, 84, "state", ["session DB · boards"], GREEN)
    s.box(288, 248, 202, 84, "services", ["gateway · dashboard", "monitoring"], SLATE)
    s.panel(552, 104, 300, 300, "remote execution nodes")
    for i in range(4):
        s.box(576, 136 + i * 66, 252, 54, f"node {i + 1}", ["shell only · no runtime"], AMBER)
    s.panel(890, 104, 266, 300, "windows workstation")
    s.box(914, 136, 218, 96, "GUI automation", ["MCP over SSH", "screen · pointer · keys"], RED)
    s.box(914, 250, 218, 96, "policy", ["never accept elevation", "report and stop"], SLATE)
    s.arrow(514, 200, 552, 200, "SSH")
    s.poly([(514, 300), (552, 300)], AMBER, "a")
    s.poly([(300, 404), (300, 456), (1023, 456), (1023, 232)], RED, "r", dashed=True,
           label="MCP over SSH", lx=660, ly=448)
    s.box(44, 500, 540, 84, "external services", ["model API (HTTPS)", "package and git remotes (outbound)"], SLATE)
    s.box(616, 500, 540, 84, "not in scope", ["no shared filesystem", "no failover · no cross-node scheduler"], SLATE)
    s.legend(44, 600, [(BLUE, "reasoning"), (AMBER, "shell"), (RED, "GUI privilege"), (GREEN, "state")])
    return s


# 4 ---------------------------------------------------------------- kanban
def kanban_workflow() -> Svg:
    s = Svg(1200, 680, "Task lifecycle",
            "One board per project stream. States change through commands; a task closes only with evidence.")
    states = [("todo", "defined, not actionable"), ("ready", "waiting for a worker"),
              ("running", "atomic claim held"), ("review", "awaiting check"), ("done", "closed with result")]
    x = 44
    for i, (name, desc) in enumerate(states):
        s.box(x, 140, 200, 104, name, [desc], GREEN if name == "done" else BLUE)
        if i:
            s.arrow(x - 24, 192, x - 4, 192)
        x += 224
    # dispatch loop
    s.poly([(644, 140), (644, 100), (556, 100), (556, 140)], BLUE, "b", dashed=True,
           label="dispatch claims atomically", lx=600, ly=92)
    # review loop
    s.poly([(864, 244), (864, 288), (756, 288), (756, 244)], GREEN, "v", dashed=True,
           label="request-changes returns it", lx=810, ly=306)
    # blocked
    s.box(44, 320, 304, 88, "blocked", ["reason recorded on the task", "returns with unblock"], AMBER)
    s.arrow(148, 244, 148, 320, "", AMBER, "a", dashed=True)
    # evidence panel
    s.panel(380, 320, 776, 154, "what completion requires")
    s.note(404, 354, "result string: what changed, which files, which command, what it returned")
    s.note(404, 380, "review by a separate session that receives artefacts, not the author's conclusion")
    s.note(404, 406, "comments, links and attachments stay on the task as its record")
    s.note(404, 432, "board is authoritative · documentation mirrors it")
    s.note(404, 458, "manual: priority, scope, approval · automatic: claim, dispatch, retries, heartbeats")
    s.legend(44, 528, [(BLUE, "active flow"), (GREEN, "completion"), (AMBER, "blocked")])
    s.note(44, 596, "A result string is a receipt. 'Looks done' is not a state transition.")
    s.note(44, 620, "One board database per stream; cross-board dependencies are not modelled.")
    return s


# 5 --------------------------------------------------------------- caching
def caching_architecture() -> Svg:
    s = Svg(1200, 660, "Caching architecture",
            "The provider caches prompt prefixes. An append-only loop keeps the prefix identical, "
            "so everything before the newest turn can be a hit.")
    rows = [("1", [("system + tools", 0), ("turn 1", 0)], "prefix written to cache"),
            ("2", [("system + tools", 1), ("turn 1", 1), ("turn 2", 0)], "prefix reused"),
            ("3", [("system + tools", 1), ("turn 1", 1), ("turn 2", 1), ("turn 3", 0)], "prefix reused"),
            ("4", [("system + tools", 1), ("turn 1", 1), ("turn 2", 1), ("turn 3", 1), ("turn 4", 0)], "prefix reused")]
    for i, (n, blocks, note) in enumerate(rows):
        y = 120 + i * 78
        s.text(44, y + 28, n, 13, INK, "start", "700")
        x = 82
        for label, cached in blocks:
            w = 28 + 7.0 * len(label)
            fill = "#e7f5ee" if cached else "#fdf1dc"
            stroke = GREEN if cached else AMBER
            s.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="38" rx="6" fill="{fill}" '
                           f'stroke="{stroke}"/>')
            s.text(x + w / 2, y + 24, label, 11.5, INK, "middle")
            x += w + 6
        s.text(1140, y + 24, note, 11.5, MUTED, "end")
    s.box(44, 452, 520, 96, "measured on the orchestrator",
          ["99.31 % of input tokens cached", "token-weighted, orchestrator traffic"], GREEN)
    s.box(600, 452, 556, 96, "what keeps the prefix stable",
          ["append-only history · fixed system prompt", "stable tool schema · rare compression"], BLUE)
    s.note(44, 580, "A hit is not a discount: output tokens are unaffected and they are a large share of cost.")
    s.note(44, 602, "Cold sessions start far lower; that case is not published and has not been benchmarked.")
    s.legend(44, 636, [(GREEN, "cache hit"), (AMBER, "new content (miss)")])
    return s


# 6 -------------------------------------------------------------- security
def security_boundaries() -> Svg:
    s = Svg(1200, 600, "Security boundaries",
            "Content is data, never instruction. Credentials stay on the control node.")
    s.panel(44, 104, 340, 300, "trusted — control node")
    s.box(68, 136, 292, 80, "agent processes", ["same tool layer for every profile"], BLUE)
    s.box(68, 230, 292, 80, "secrets", ["outside the repository", "mode 0600 · never printed"], RED)
    s.box(68, 324, 292, 62, "publication gate", ["scan → review → owner approval"], GREEN)
    s.panel(416, 104, 340, 300, "semi-trusted — execution")
    s.box(440, 136, 292, 80, "remote nodes", ["commands in, bytes out", "no credentials"], AMBER)
    s.box(440, 230, 292, 80, "GUI workstation", ["high privilege", "never accept elevation"], AMBER)
    s.box(440, 318, 292, 76, "limits", ["no shared filesystem", "no failover"], SLATE)
    s.panel(788, 104, 368, 300, "untrusted — content")
    s.box(812, 136, 320, 62, "web pages", ["data only"], RED)
    s.box(812, 210, 320, 62, "screen and OCR text", ["data only"], RED)
    s.box(812, 284, 320, 62, "remote stdout", ["data only"], RED)
    s.arrow(384, 170, 440, 170, "SSH", AMBER, "a")
    s.arrow(812, 250, 732, 260, "inspect", RED, "r", dashed=True)
    s.box(44, 432, 1112, 92, "publication rules",
          ["no credentials · no hostnames, addresses or domains · no prompts or personas",
           "no logs, databases or transcripts · no personal spend · licence: GPL-3.0-only"], GREEN)
    s.note(44, 556, "Publication needs a clean fail-closed scan of tree, index, history and names — run locally and in CI, not as a git hook.")
    s.note(44, 578, "A clean scan means no finding of the kinds we detect — not a guarantee of absence.")
    return s


# 7 ------------------------------------------------------------ cost model
def cost_comparison() -> Svg:
    s = Svg(1200, 580, "Cost per 1 billion tokens",
            "Claude Opus 5.5 at its documented assumptions vs Nexus in one observed window. "
            "The two columns are not mix-adjusted.")
    total, nexus = 53127, 62
    x0, w = 300, 470
    rows = [("Claude Opus 5.5", "80 % cache hit · 20.42 % output", total, RED, "53 127 NOK"),
            ("Nexus", "99.2 % cache hit · 0.39 % output", nexus, GREEN, "62 NOK")]
    for i, (name, sub, nok, color, label) in enumerate(rows):
        y = 128 + i * 116
        s.text(x0 - 26, y + 26, name, 16, INK, "end", "700")
        s.text(x0 - 26, y + 48, sub, 11.5, MUTED, "end")
        bw = max(nok / total * w, 6)
        s.parts.append(f'<rect x="{x0}" y="{y}" width="{bw:.1f}" height="56" rx="7" '
                       f'fill="{color}" opacity="0.92"/>')
        if bw > 200:
            s.text(x0 + bw - 16, y + 35, label, 17, "#ffffff", "end", "700")
        else:
            s.text(x0 + bw + 16, y + 35, label, 17, color, "start", "700")
    s.text(x0, 352, "true length 0.12 % (about half a pixel); the Nexus bar is drawn at a 6 px "
                       "minimum so it stays visible", 11.5, MUTED)

    # ratio panel
    s.parts.append(f'<rect x="810" y="118" width="346" height="216" rx="14" fill="{PANEL}" '
                   f'stroke="{BORDER}"/>')
    s.text(836, 176, "856×", 52, GREEN, "start", "700")
    s.text(836, 206, "lower calculated cost", 13, MUTED)
    s.parts.append(f'<line x1="836" y1="226" x2="1130" y2="226" stroke="{BORDER}"/>')
    s.text(836, 258, "99.88 % reduction", 15, INK, "start", "600")
    s.text(836, 288, "53 065 NOK saved per billion", 15, INK, "start", "600")
    s.text(836, 314, "USD/NOK 9.6866", 11.5, MUTED)

    s.note(44, 396, "Nexus: $6.41 per billion at an observed mix (0.39 % output, 99.2 % cache "
                    "hit) → 62 NOK.", MUTED)
    s.note(44, 414, "Calculated from runtime token volumes at published DeepSeek prices; absolute "
                    "spend is not published.", MUTED)
    s.note(44, 438, "Claude: $4.00/M input, $0.20/M cache read, $8.00/M 1-hour write, $20.00/M "
                    "output, 80 % cache hit, 20.42 % output share — assumptions unchanged.")
    s.note(44, 466, "Not mix-adjusted: each column is per billion tokens at its own token mix, so "
                    "the ratio combines price, caching and workload shape.", AMBER)
    s.note(44, 490, "Nexus at peak Flash prices: 124 NOK · ratio 428× · off-peak share assumed "
                    "100 %", MUTED)
    s.note(44, 514, "Cost per completed task, quality and wall-clock per task are not measured.",
           RED)
    s.note(44, 538, "Estimates of API token cost, not invoices. Neither figure was reported by a "
                    "provider.", MUTED)
    return s


def main() -> None:
    write("system-overview.svg", system_overview())
    write("agent-architecture.svg", agent_architecture())
    write("infrastructure.svg", infrastructure())
    write("kanban-workflow.svg", kanban_workflow())
    write("caching-architecture.svg", caching_architecture())
    write("security-boundaries.svg", security_boundaries())
    write("cost-comparison.svg", cost_comparison())


if __name__ == "__main__":
    main()
