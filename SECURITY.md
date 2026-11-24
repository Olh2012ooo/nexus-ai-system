# Security policy

Nexus is documentation plus verification tooling. It runs no service, opens no port and stores
no credentials, but it does describe a security model — so both disclosure and documentation
accuracy matter here.

## Reporting a vulnerability

Please **do not** open a public issue for a security problem.

1. Use GitHub's private reporting: open the repository's **Security** tab → **Report a
   vulnerability**. That channel is private between you and the maintainer and is the preferred
   route.
2. If that channel is unavailable, open a minimal public issue asking for a private contact
   route **without** including details, proofs of concept, hostnames or credentials.

Useful reports include: a scanner bypass (with the exact reproduction), a leak in the
documentation (hostname, path, key fragment), an incorrect security claim, or a dependency whose
licence or provenance is wrong.

Please give the maintainer a reasonable window to fix the issue before publishing details.

## Publication gate

This repository was developed privately. Before any change of visibility, all of the following
must hold:

1. A clean full-history scan (fail-closed, exit 0) plus at least one independent scanner.
2. No real hostname, IP address, domain, internal path or account name in the file content, and
   no personal identity in the commit metadata. E-mail- and domain-shaped identities are caught
   automatically; a bare personal name is **not** — the author/committer line has to be read
   before publishing.
3. No prompt text, persona file or internal instruction.
4. No database, log, transcript or configuration dump. Deleting a file later is not enough — the
   object remains in history.
5. Cost and usage appear only as a normalised rate per token volume plus the token mix. No
   absolute spend, balance, token totals, call counts, daily figures, dates or account history.
6. A licence is in place — GPL-3.0-only, see [LICENSE](LICENSE).

The scan runs before any visibility change and in the `publication-check` workflow on every push
and pull request. It is **not** a git hook: nothing blocks a push, so a red build and a manual run
are reporting steps, not enforcement.

| Exit | Meaning |
|---|---|
| 0 | clean — no finding of the kinds listed below |
| 1 | findings — at least one potential leak; values are redacted in the output |
| 2 | error — a required check could not run; treat exactly like a finding |

## What the scanner does

```bash
python3 tools/scan_publication.py --history   # tree + every blob, all refs, messages, identities
python3 tools/test_scan_publication.py        # isolated fail/pass cases
```

- **Fail-closed.** Missing git, a failing git command, a shallow clone, an unreadable or
  oversized file returns ERROR (exit 2) — never "clean".
- **Coverage.** Always: dotfiles and `.env`, extensionless files, names with spaces, tabs and
  newlines, binary content, symlink targets, every ref and whatever it points at (commit tree,
  tree, blob, annotated tag chain), and the names of every file, directory and ref. With
  `--history` (always used for the publication gate): every commit message, author and committer
  identity, reflog subject, unreachable blob and deleted annotated tag. GitHub's pseudonymous
  `users.noreply.github.com` addresses and its `noreply@`/`support@` role addresses are allowed;
  a real personal address is not.
- **Replacement refs.** Git runs with `--no-replace-objects`, so `refs/replace/*` cannot make the
  scan see a history different from the one a push would transmit; the ref itself is reported for
  manual review.
- **Secrets.** Token and key shapes, private-key blocks, JWTs, high-entropy strings, and long hex
  runs (32–39 or 41+ characters; exactly 40 hex is assumed to be a git object id).
- **Redaction.** Findings print the kind and the file, never the value.
- **Isolation.** Git runs with a scrubbed environment: `GIT_DIR`, `GIT_WORK_TREE` and the other
  repository-redirecting variables are removed, so the scan cannot be pointed at another
  repository than `--root`.
- **Limits.** It cannot recognise a secret written as prose, split at runtime or across lines,
  base64-encoded, or hidden in a file above the size limit (that case fails, it is not skipped).
  Messages of unreachable commits are not scanned; unreachable blobs are. A bare personal name
  with a neutral e-mail address is not detected. A clean run means *no finding of the kinds we
  detect*, not a guarantee of absence.

## Supported versions

The `main` branch is the only supported line; there are no releases yet. Fixes land on `main`.

## Scope

Agent capabilities, trust boundaries and deployment limits are described in
[docs/security.md](docs/security.md).
