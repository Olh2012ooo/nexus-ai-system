# Changelog

All notable changes to this repository are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This repository holds the architecture documentation, the diagrams and the verification tooling
for a Nexus installation. The agent runtime itself is a separate program and is not distributed
here.

## [1.0.0] — first stable release

The first stable release marks the point where the documentation, the diagrams and the tooling
describe one verified state of the system, and where every claim in the documentation is
checked by a command in the repository.

### Documented architecture

- The orchestrator and its four specialist profiles (Jarvis, Ultron, Athena, Sentinel), what
  they share and what they do not: one runtime, one model, one tool configuration, and roles
  that are instructions rather than access control.
- The hybrid machine topology: one control node that reasons and holds state, four execution
  targets that run shell commands, one workstation reached for GUI automation over SSH.
- Durable task orchestration: nine states, atomic claims, a completion gate that refuses empty
  evidence, and review by a separate session.
- Prompt-prefix caching: what keeps a prefix stable, what invalidates it, and what a hit rate is
  and is not worth.
- Token economics: one normalised comparison, every assumption written down, and a calculator
  that reproduces it.
- Trust boundaries, capabilities, publication gates and the known limits of each.

### Tooling

- `tools/scan_publication.py` — publication scanner covering the working tree, the git index,
  every ref and the object it points at (commit, tree, blob, annotated tag chain), history,
  unreachable commits, tags and blobs, names, commit messages and identities. Fail-closed on
  every unverifiable state, with `--no-replace-objects` and a scrubbed git environment.
- **84 scanner test cases**, each asserting a verdict on a throwaway repository, including the
  reported index bypass, ref-to-blob and ref-to-tree publication, `refs/replace/*` substitution,
  shallow clones and Unicode-obfuscated names.
- `calculations/recompute.py` and **33 test cases** — the published cost comparison, with
  argument validation that rejects NaN, infinity and out-of-range shares.
- `tools/check_links.py` and `tools/check_diagrams.py` — relative links and SVG geometry.
- `.github/workflows/publication-check.yml` — the same checks on every push, with
  `contents: read` and GitHub-owned actions only.

### Licensing

- GPL-3.0-only, with the unmodified GNU GPL v3.0 text in `LICENSE` and SPDX identifiers in every
  first-party source file.

### Notes

- Every figure in the documentation is reproducible from the repository: the cost comparison from
  `calculations/recompute.py`, the diagrams from `diagrams/render.py`.
- Measurements that are not available — cost per completed task, quality per task, wall-clock per
  task — are named as not measured rather than estimated.
