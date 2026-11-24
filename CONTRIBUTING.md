# Contributing to Nexus

Thanks for taking the time to look at this. Nexus is a small repository: documentation, seven
diagrams, and a handful of scripts that verify the documentation is true. Contributions that
make it more accurate or harder to fool are welcome.

## Before you start

- Read [README.md](README.md) for what this repository is (and is not), and
  [docs/architecture.md](docs/architecture.md) for the system it describes.
- For a security problem, follow [SECURITY.md](SECURITY.md) instead of opening an issue.
- By contributing you agree that your contribution is licensed under **GPL-3.0-only**, the
  licence of this project.

## Development environment

Nothing to install:

- Python **3.9+** — standard library only, no third-party packages
- Git
- A POSIX shell

Optional, for a second opinion on the secret scanner: `gitleaks` or `detect-secrets`.

## Repository layout

| Path | What lives there |
|---|---|
| `docs/` | Seven documents: architecture, roles, infrastructure, kanban, caching, economics, security |
| `diagrams/` | `render.py` and the seven SVGs it generates — never hand-edit an SVG |
| `calculations/` | `recompute.py`, the cost calculator |
| `tools/` | Publication scanner, its 84 cases, link checker, diagram validator, calculator tests |
| `.github/workflows/` | `publication-check.yml`, which runs all of the above |

## Conventions

- **Standard library only.** No new dependencies without a very good reason; this repository must
  stay inspectable on a bare Python install.
- **No secrets, ever.** Not in code, tests, fixtures, docs, commit messages or branch names.
  Test material is assembled at runtime from fragments, so no secret-shaped literal exists in the
  tree.
- **Evidence over adjectives.** A claim in the docs needs a command that demonstrates it. If a
  number is an estimate or an assumption, say so in the same sentence.
- **Diagrams are generated.** Change `diagrams/render.py`, then run it; the SVG is output.
- **Keep the ASCII/UTF-8 style of each file.** Prose is plain English with short sentences.

## Testing

Run everything before opening a pull request:

```bash
python3 tools/test_scan_publication.py    # scanner behaviour, 84 cases
python3 tools/test_recompute.py           # calculator output and validation, 33 cases
python3 tools/scan_publication.py --history
python3 tools/check_links.py
python3 tools/check_diagrams.py
python3 calculations/recompute.py
```

A change that alters a number must update, in the same commit: `docs/economics.md`,
`calculations/recompute.py`, `diagrams/render.py` (then re-render), and README if it is quoted
there. The tests exist to catch exactly that kind of drift.

## Pull requests

- One topic per pull request; explain **why**, not only what.
- Say what you ran and what it returned. "Tests pass" without the command is not evidence.
- If you fix a scanner bypass, add the reproduction as a test case first — a fix without a
  regression test will be asked for one.
- Do not reformat unrelated files, rename documents, or restructure the repository in the same
  pull request as a content change.

## What will not be accepted

- Claims that cannot be reproduced by a command in the repository.
- Benchmark numbers without a stated method.
- Removal of the fail-closed behaviour of any check.
- Re-licensing, dual licensing, or vendored code with an incompatible licence.
- Personal infrastructure details: hostnames, addresses, paths, account identifiers.

## Licence

GPL-3.0-only. See [LICENSE](LICENSE).
