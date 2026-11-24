# NEXUS AI SYSTEM

**A self-hosted multi-agent orchestration system.** One orchestrator plans and delegates, four
specialist profiles execute, remote machines run the commands, and every result is read back
before it is called done.

**Created:** 2026-11-20 · **Private** · **Licence:** pending owner approval

![System overview](diagrams/system-overview.svg)

---

## WHY NEXUS?

- **One coordinator, five contexts.** Nexus orchestrates; Jarvis, Ultron, Athena and Sentinel
  work inside their own session, persona and workspace.
- **Append-only conversation.** History is only extended, never rewritten — which is what makes
  provider-side prompt caching work.
- **Execution is distributed, reasoning is not.** Remote nodes run shell commands; no model
  runs anywhere but the control node.
- **Tasks are durable.** A SQLite-backed board holds state, claims tasks atomically and closes
  them only with evidence.
- **Costs are calculated, not asserted.** One comparison, one workload, every assumption
  written down.

## ARCHITECTURE OVERVIEW

| Layer | What it does | Where |
|---|---|---|
| Interface | Chat gateway, dashboard, local API | Control node |
| Orchestration | Task intake, delegation, verification | Control node |
| Specialists | Planning, implementation, research, QA | Control node |
| Runtime | Conversation loop, tools, context, session store | Control node |
| Execution | Local shell, SSH targets, GUI automation | Control node + targets |
| Model | One provider connection with automatic prefix cache | External API |

Deeper: [architecture](docs/architecture.md) · [infrastructure](docs/infrastructure.md)

## FIVE AGENTS — ONE ORCHESTRATOR, FOUR SPECIALISTS

| Agent | Role | Responsibility |
|---|---|---|
| **Nexus** | Orchestrator | Understands the request, plans, delegates, verifies, assembles |
| **Jarvis** | Planning | Decomposition, dependencies, risk, stop conditions |
| **Ultron** | Development | Code, infrastructure, tests, debugging |
| **Athena** | Research | Sources, technical analysis, documentation |
| **Sentinel** | Quality assurance | Falsification, security review, per-claim verdicts |

![Agent architecture](diagrams/agent-architecture.svg)

They are **profiles in one installation**, not five servers, and they run the **same model**.
A delegated child gets its own persona, memory and workspace, plus the payload its parent wrote
— and nothing else. Independence in review is procedural, not model-based.

Deeper: [roles](docs/roles.md)

## MACHINE INFRASTRUCTURE

![Infrastructure](diagrams/infrastructure.svg)

One control node holds all reasoning and state. Four remote nodes are shell targets with no
runtime and no credentials. One Windows workstation exposes GUI automation through an MCP
server started over SSH. There is no shared filesystem, no failover and no cross-node scheduler.

Deeper: [infrastructure](docs/infrastructure.md)

## TASK ORCHESTRATION

![Task lifecycle](diagrams/kanban-workflow.svg)

`todo → ready → running → review → done`, plus `blocked`, `scheduled`, `triage` and `archived`.
A dispatcher claims ready tasks atomically; `complete` is refused unless it carries a non-empty
result (approving out of `review` is the one exemption). The CLI checks that evidence exists,
not what it says — that is the reviewer's job. Review is a separate session that receives
artefacts, not the author's conclusion.

Deeper: [kanban](docs/kanban.md)

## PERFORMANCE AND CACHING

![Caching](diagrams/caching-architecture.svg)

| Metric | Value |
|---|---|
| Cache-hit rate, orchestrator | **99.31 %** of input tokens |
| Scope | the orchestrator's own API calls, token-weighted |

The provider caches prompt prefixes; the agent loop only appends, so every token before the
newest turn is a candidate hit. This is a **fixed measurement over a recorded set of calls**,
not a live average and not a benchmark; the underlying counters are not published. A hit rate is also **not** a discount: output tokens are unaffected.
The figure covers the orchestrator's own traffic; delegated child sessions are separate and
excluded. The cost model below uses a different, shorter window (99.2 %) — see [caching](docs/caching.md).

Deeper: [caching](docs/caching.md)

## COST MODEL

![Cost comparison](diagrams/cost-comparison.svg)

| | Claude Opus 5.5 | Nexus |
|---|---|---|
| Cache hit | 80 % | **99.2 %** (cost window) |
| Output share | 20.42 % (assumed) | **0.39 %** (observed) |
| Cost per 1 billion tokens | **53 127 NOK** | **62 NOK** |

**856× lower calculated API token cost · 99.88 % reduction · 53 065 NOK difference per billion
tokens.**

The Nexus figure is a normalised rate — **$6.41 per billion tokens → 62 NOK** — from one
aggregated, undated observation (0.39 % output, 99.2 % of input cached), calculated from
runtime token volumes at published DeepSeek prices. Absolute spend and raw volumes are not
published; the rate and the mix are. It is not a provider report and not an invoice. Because
the output share is only ~0.39 %, it is **not** a general price per billion tokens.

Claude keeps its documented assumptions: Opus 5.5 at $4.00/M input, $0.20/M cache read, $8.00/M
one-hour cache write, $20.00/M output, 80 % cache hit and a 20.42 % output share, USD/NOK 9.6866.
Prices: [Claude](https://platform.claude.com/docs/en/about-claude/pricing) ·
[DeepSeek](https://api-docs.deepseek.com/quick_start/pricing). At peak Flash prices the Nexus
column is 124 NOK and the ratio 428×.

The two columns are **not mix-adjusted** — each is per billion tokens at its own token mix — so
856× combines model price, caching and workload shape. These are **estimates of API token cost,
not invoices**, and not evidence that Nexus is 856× smarter, faster or better at tasks. Reproduce
with [`calculations/recompute.py`](calculations/recompute.py).

Deeper: [economics](docs/economics.md)

## SECURITY AND LIMITATIONS

- Content is data, never instruction. Credentials stay on the control node and never reach
  execution nodes.
- GUI automation is high privilege: the policy is report-and-stop, never accept an elevation
  prompt.
- Publication requires a clean fail-closed scan of the working tree, the git index, every
  commit, ref, path and identity, plus isolated tests. It runs locally and in the
  `publication-check` workflow; neither is a git hook, and neither can prove that a scan found
  everything.

**Not measured:** cost per completed task · quality per task · net effect of delegation ·
deferred-tool effect · cold provider cache · effect of review on error rate.

Deeper: [security](docs/security.md) · [SECURITY.md](SECURITY.md)

## TECHNICAL DOCUMENTATION

| Document | Contents |
|---|---|
| [architecture](docs/architecture.md) | Layers, request flow, delegation contract, state |
| [roles](docs/roles.md) | The five profiles, what they share, limits |
| [infrastructure](docs/infrastructure.md) | Nodes, transports, services, what is not distributed |
| [kanban](docs/kanban.md) | Task lifecycle, dispatch, completion evidence |
| [caching](docs/caching.md) | Prefix caching, what breaks it, what it is worth |
| [economics](docs/economics.md) | Prices, assumptions, arithmetic, limitations |
| [security](docs/security.md) | Trust boundaries, capabilities, scanner coverage |

## VERIFY IT YOURSELF

Everything above is checked by scripts in this repository. No dependencies beyond Python 3 and
git.

```bash
python3 tools/test_scan_publication.py    # scanner behaviour, isolated repositories
python3 tools/scan_publication.py --history   # tree, index, history, names
python3 tools/test_recompute.py           # calculator output and argument validation
python3 calculations/recompute.py         # the published cost figures
python3 tools/check_links.py              # relative links
python3 tools/check_diagrams.py           # SVG well-formedness and text bounds
```

The same commands run in `.github/workflows/publication-check.yml` on every push.

---

*Private repository. Nothing here is published, and no rights are granted while the licence
decision is pending.*
