#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 NEXUS project contributors
"""Publication scanner: working tree, git index, history, names and metadata.

Checks four surfaces and treats anything it cannot verify as a failure:

  tree     every file on disk, bytecode included
  index    what `git commit` would actually record — including staged content whose working
           copy has since been reverted or deleted
  refs     every ref and whatever it points at: commit, tree, blob or annotated tag
  history  every commit, tree, blob, message, identity and unreachable blob
  names    file names, directory names, index paths, history paths, branch and tag names

Git runs with --no-replace-objects, so a `refs/replace/*` entry cannot make the scan see a
substituted history that differs from what a push would transmit.

Exit codes
    0  clean
    1  findings (potential leak)
    2  error / unverifiable — never clean

Fail-closed rules: a git command that fails, returns an unexpected status, produces output that
cannot be parsed, a missing object, an unreadable file, an oversized file, an unmerged index or
a submodule entry all end in exit 2. Only two "empty" results are legitimate: no refs in a
fresh repository, and no files in an empty index.

Matched values are never printed: findings carry the kind and the location, plus [REDACTED].

Usage
    python3 tools/scan_publication.py                    # tree + index + names
    python3 tools/scan_publication.py --history          # + all refs, blobs, messages, unreachable
    python3 tools/scan_publication.py --root <path>      # scan another repository (tests)
    python3 tools/scan_publication.py --no-index         # skip the index (tests of tree only)
"""
from __future__ import annotations

import argparse
import math
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter

DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_BYTES = 8 * 1024 * 1024
GIT_TIMEOUT = 300

# RFC 5737 documentation ranges and loopback are safe to publish.
DOC_NETS = ("192.0.2.", "198.51.100.", "203.0.113.", "127.0.0.1", "0.0.0.0")
ALLOW_DOMAINS = {
    "example.com", "example.org", "example.invalid", "api.deepseek.com",
    "platform.claude.com", "claude.com", "openai.com", "ai.google.dev", "github.com",
    "docs.python.org", "sqlite.org", "ubuntu.com", "www.w3.org", "w3.org",
    "api-docs.deepseek.com", "hermes-agent.nousresearch.com", "nousresearch.com",
    # The unmodified GPL text links to these.
    "gnu.org", "www.gnu.org", "fsf.org", "www.fsf.org", "savannah.gnu.org",
}
# Internal-only suffixes. A public name never ends like this.
INTERNAL_SUFFIXES = tuple("." + s for s in (
    "internal", "local", "lan", "corp", "intranet", "home" + ".arpa",
    "svc", "cluster" + ".local", "localdomain"))

PATTERNS = [
    ("private-key-block", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("github-fine-grained", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("openai-style-key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("telegram-bot-token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_\-]{35}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b")),
    ("bearer-value", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{24,}")),
    ("credential-assignment",
     re.compile(r"(?i)\b(?:password|passwd|secret|api[_-]?key|token)\s*[:=]\s*"
                r"['\"]?[A-Za-z0-9_\-+/=]{16,}")),
]
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
HOME_PATH = re.compile(r"/(?:home|Users)/[A-Za-z0-9._\-]+")
EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
DOMAIN = re.compile(r"\b(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+"
                    r"(?:com|net|org|io|dev|no|ai|cloud|xyz|app|se|dk|uk|de|invalid|local|"
                    r"internal|lan|corp|intranet|svc|arpa)\b", re.I)
ENTROPY_TOKEN = re.compile(r"\b[A-Za-z0-9+/=_\-]{32,}\b")
# Hex needs its own rule: a 16-symbol alphabet caps Shannon entropy at 4.0 bits, so the
# 4.3-bit threshold below can never fire on a hex-encoded secret.
HEX_TOKEN = re.compile(r"\b[0-9a-fA-F]{32,}\b")
# A file name may contain any byte but NUL and "/" — including tabs and newlines, which can
# split a token so that no pattern matches across it.
NAME_CONTROL_CHAR = re.compile(r"[\x00-\x1f\x7f]")
# Zero-width and other format characters render as nothing but defeat a literal suffix match.
UNICODE_FORMAT = re.compile("[\u00ad\u061c\u180e\u200b-\u200f\u202a-\u202e\u2060-\u2064"
                            "\u2066-\u206f\ufeff\ufff9-\ufffb]")


class ScanError(RuntimeError):
    """A check could not be completed. Always a failure, never 'clean'."""


def shannon(s: str) -> float:
    n = len(s)
    if not n:
        return 0.0
    return -sum((c / n) * math.log2(c / n) for c in Counter(s).values())


def is_ipv4(text: str) -> bool:
    parts = text.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(p) <= 255 for p in parts)
    except ValueError:
        return False


# GitHub's noreply addresses are pseudonymous by construction: a bot login or a user id, not a
# personal mailbox. They appear in Dependabot commits and in every squash-merge by a GitHub user.
PSEUDONYMOUS_DOMAINS = ("users.noreply.github.com",)
# Role addresses GitHub itself stamps on bot commits; not personal mailboxes.
ROLE_ADDRESSES = {"noreply@github.com", "support@github.com"}


def _domain_is_allowed(d: str) -> bool:
    d = d.lower()
    if d in ALLOW_DOMAINS or d.endswith((".example.com", ".example.invalid")):
        return True
    return any(d == p or d.endswith("." + p) for p in PSEUDONYMOUS_DOMAINS)


def _email_is_allowed(value: str) -> bool:
    if value.lower() in ROLE_ADDRESSES:
        return True
    domain = value.rsplit("@", 1)[-1].lower()
    if domain in {"example.com", "example.invalid"}:
        return True
    return any(domain == p or domain.endswith("." + p) for p in PSEUDONYMOUS_DOMAINS)


def scan_text(text: str, label: str) -> list[tuple[str, str]]:
    """Scan decoded text for secret and identity shapes."""
    hits: list[tuple[str, str]] = []
    for kind, pat in PATTERNS:
        if pat.search(text):
            hits.append((kind, label))
    for m in IPV4.finditer(text):
        ip = m.group(0)
        if is_ipv4(ip) and not ip.startswith(DOC_NETS):
            hits.append(("ipv4", label))
            break
    if HOME_PATH.search(text):
        hits.append(("absolute-home-path", label))
    for m in EMAIL.finditer(text):
        if not _email_is_allowed(m.group(0)):
            hits.append(("email", label))
            break
    for m in DOMAIN.finditer(text):
        if not _domain_is_allowed(m.group(0)):
            hit = ("internal-hostname" if m.group(0).lower().endswith(INTERNAL_SUFFIXES)
                   else "domain-like")
            hits.append((hit, label))
            break
    for m in ENTROPY_TOKEN.finditer(text):
        if shannon(m.group(0)) >= 4.3:
            hits.append(("high-entropy", label))
            break
    for m in HEX_TOKEN.finditer(text):
        # Exactly 40 hex characters is almost always a git object id; every other long hex run
        # (32-39, 41+) counts as a possible key. The carve-out is documented in SECURITY.md.
        if len(m.group(0)) != 40:
            hits.append(("hex-secret", label))
            break
    return hits


def scan_bytes(data: bytes, label: str) -> list[tuple[str, str]]:
    """Scan raw bytes. latin-1 maps one byte to one char, so no input is skipped."""
    return scan_text(data.decode("latin-1"), label)


def scan_name(name: str, label: str) -> list[tuple[str, str]]:
    """Scan a path, file name, directory name or ref name.

    Names are scanned for secrets and infrastructure identifiers, but not for the generic
    domain rule beyond internal suffixes: a path that merely mentions a public documentation
    domain is not a leak, while a path that ends in an internal-only suffix is. Content
    scanning is never weakened by allowlisting a name.
    """
    hits: list[tuple[str, str]] = []
    if NAME_CONTROL_CHAR.search(name):
        hits.append(("name-control-char", label))
    cleaned = unicodedata.normalize("NFKC", UNICODE_FORMAT.sub("", name))
    for kind, pat in PATTERNS:
        if pat.search(name) or pat.search(cleaned):
            hits.append((f"name-{kind}", label))
    low = cleaned.lower()
    if low.endswith(INTERNAL_SUFFIXES) or any(part in low for part in INTERNAL_SUFFIXES):
        hits.append(("internal-hostname", label))
    for m in IPV4.finditer(cleaned):
        if is_ipv4(m.group(0)) and not m.group(0).startswith(DOC_NETS):
            hits.append(("name-ipv4", label))
            break
    if HOME_PATH.search(cleaned):
        hits.append(("absolute-home-path", label))
    base = cleaned.replace("/", " ").strip()
    for m in HEX_TOKEN.finditer(base):
        if len(m.group(0)) != 40:
            hits.append(("name-hex", label))
            break
    for m in ENTROPY_TOKEN.finditer(base):
        if shannon(m.group(0)) >= 4.5:
            hits.append(("name-high-entropy", label))
            break
    return hits


# --------------------------------------------------------------------------- git plumbing
# Variables that would point git somewhere other than the repository being scanned.
ENV_OVERRIDES = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
                 "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE",
                 "GIT_PREFIX", "GIT_CEILING_DIRECTORIES")


def git_env() -> dict[str, str]:
    """A git environment that cannot be redirected by the caller's shell.

    Without this, `GIT_DIR=/some/other/repo` makes every command read a different repository
    than --root, and the scan can report another repo's clean history.
    """
    env = {k: v for k, v in os.environ.items() if k not in ENV_OVERRIDES}
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    return env


def git(root: str, *args: str, allow: tuple[int, ...] = (0,)) -> bytes:
    """Run git and return stdout. Any status outside `allow` is a ScanError.

    Nothing here swallows a failure: a caller that expects a non-zero status must name it
    explicitly, and still gets the bytes back so it can check whether they make sense.
    """
    try:
        proc = subprocess.run(["git", "--no-replace-objects", "-C", root, *args],
                              capture_output=True, timeout=GIT_TIMEOUT, env=git_env())
    except (OSError, subprocess.SubprocessError) as exc:
        raise ScanError(f"git {' '.join(args)} could not run: {exc}") from exc
    if proc.returncode not in allow:
        detail = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise ScanError(f"git {' '.join(args)} exited {proc.returncode}"
                        + (f": {detail[0][:200]}" if detail else ""))
    return proc.stdout


def git_dir(root: str) -> str:
    """Return the repository's git directory, or raise if this is not a work tree."""
    out = git(root, "rev-parse", "--absolute-git-dir").strip()
    if not out:
        raise ScanError("git rev-parse --absolute-git-dir returned no output")
    return out.decode("utf-8", "replace")


def read_objects(root: str, shas: list[str]) -> dict[str, bytes]:
    """Read many objects through one `git cat-file --batch` process.

    Missing objects make the batch stream report `<sha> missing`; that is a ScanError, not an
    empty result.
    """
    if not shas:
        return {}
    payload = ("\n".join(shas) + "\n").encode()
    try:
        proc = subprocess.run(["git", "--no-replace-objects", "-C", root, "cat-file", "--batch"],
                              input=payload, capture_output=True, timeout=GIT_TIMEOUT,
                              env=git_env())
    except (OSError, subprocess.SubprocessError) as exc:
        raise ScanError(f"git cat-file --batch could not run: {exc}") from exc
    if proc.returncode != 0:
        raise ScanError(f"git cat-file --batch exited {proc.returncode}")

    out, blobs, pos = proc.stdout, {}, 0
    for sha in shas:
        nl = out.find(b"\n", pos)
        if nl < 0:
            raise ScanError(f"cat-file output ended before object {sha[:8]}")
        header = out[pos:nl].decode("utf-8", "replace").split()
        pos = nl + 1
        if len(header) == 2 and header[1] == "missing":
            raise ScanError(f"object {sha[:8]} is missing from the repository")
        if len(header) != 3:
            raise ScanError(f"unparsable cat-file header for {sha[:8]}: {header!r}")
        size = int(header[2])
        body = out[pos:pos + size]
        if len(body) != size:
            raise ScanError(f"truncated content for object {sha[:8]}")
        pos += size + 1  # trailing newline emitted by cat-file
        blobs[sha] = body
    return blobs


def split_nul(data: bytes) -> list[bytes]:
    return [record for record in data.split(b"\x00") if record]


def index_entries(root: str) -> tuple[list[tuple[str, str, str, int]], list[str]]:
    """Return ((mode, sha, path, stage), ...) and a list of unmerged paths.

    `git ls-files -s -z` emits `<mode> SP <sha> SP <stage> TAB <path> NUL`. Paths may contain
    spaces, newlines and any other byte except NUL, so records are split on NUL only.
    """
    out = git(root, "ls-files", "-s", "-z")
    entries: list[tuple[str, str, str, int]] = []
    unmerged: list[str] = []
    for record in split_nul(out):
        meta, sep, path_bytes = record.partition(b"\t")
        if not sep:
            raise ScanError(f"unparsable index entry: {meta[:40]!r}")
        parts = meta.split()
        if len(parts) != 3:
            raise ScanError(f"unparsable index entry header: {meta[:60]!r}")
        mode, sha, stage_txt = (p.decode("ascii", "replace") for p in parts)
        if not re.fullmatch(r"[0-7]{6}", mode) or not re.fullmatch(r"[0-9a-f]{40,64}", sha):
            raise ScanError(f"unexpected index mode/object: {mode} {sha[:12]}")
        try:
            stage = int(stage_txt)
        except ValueError as exc:
            raise ScanError(f"unexpected index stage: {stage_txt!r}") from exc
        path = os.fsdecode(path_bytes)
        entries.append((mode, sha, path, stage))
        if stage != 0:
            unmerged.append(path)
    return entries, sorted(set(unmerged))


def object_type(root: str, sha: str) -> str:
    value = git(root, "cat-file", "-t", sha).strip().decode("ascii", "replace")
    if value not in {"commit", "tree", "blob", "tag"}:
        raise ScanError(f"unexpected object type {value!r} for {sha[:8]}")
    return value


def tree_entries(root: str, treeish: str) -> list[tuple[str, str, str, str]]:
    """Return ((mode, type, sha, path), ...) for a whole tree, NUL-separated."""
    out = git(root, "ls-tree", "-r", "-z", "--full-tree", treeish)
    entries = []
    for record in split_nul(out):
        meta, sep, path_bytes = record.partition(b"\t")
        if not sep:
            raise ScanError(f"unparsable ls-tree record for {treeish[:8]}")
        parts = meta.split()
        if len(parts) != 3:
            raise ScanError(f"unparsable ls-tree header for {treeish[:8]}")
        mode, otype, sha = (p.decode("ascii", "replace") for p in parts)
        entries.append((mode, otype, sha, os.fsdecode(path_bytes)))
    return entries


def ref_objects(root: str) -> list[tuple[str, str, str]]:
    """Return ((type, sha, refname), ...) for every ref.

    Exit 0 with empty output legitimately means "no refs yet". Anything unparsable is an error:
    a ref we cannot classify is a surface we cannot certify.
    """
    out = git(root, "for-each-ref", "--format=%(objecttype) %(objectname) %(refname)")
    refs: list[tuple[str, str, str]] = []
    for line in out.decode("utf-8", "replace").splitlines():
        if not line.strip():
            continue
        parts = line.split(" ", 2)
        if len(parts) != 3:
            raise ScanError(f"unparsable ref line: {line[:80]!r}")
        otype, sha, name = parts
        if otype not in {"commit", "tree", "blob", "tag"}:
            raise ScanError(f"unknown object type {otype!r} for {name}")
        if not re.fullmatch(r"[0-9a-f]{40,64}", sha):
            raise ScanError(f"unexpected object id {sha[:12]!r} for {name}")
        refs.append((otype, sha, name))
    return refs


def scan_refs(root: str, findings: list, refs: list[tuple[str, str, str]] | None = None) -> int:
    """Scan every ref and whatever it points at, whatever the object type.

    `rev-list --all` walks commits only, so a ref that points straight at a blob or a tree —
    which `git push --tags` will happily transmit — has to be followed by hand.
    """
    refs = ref_objects(root) if refs is None else refs
    scanned = 0
    for otype, sha, name in refs:
        findings.extend(scan_name(name, f"ref:{name}"))
        if name.startswith("refs/replace/"):
            # Inert for this scan (git runs with --no-replace-objects), but a replaced history
            # is exactly the kind of thing a reviewer must look at by hand.
            findings.append(("history-replacement", f"ref:{name}"))
        targets = [(otype, sha)]
        if otype == "tag":
            # Follow the chain by hand: an intermediate annotated tag is its own object with
            # its own message, and `rev-parse ^{}` would skip straight past it.
            current = sha
            for _ in range(16):
                body = read_objects(root, [current])[current]
                findings.extend(scan_bytes(body, f"tag-object:{name}"))
                header = next((line for line in body.split(b"\n") if line.startswith(b"object ")),
                              None)
                if header is None:
                    raise ScanError(f"tag object {current[:8]} has no object header")
                current = header.split()[1].decode("ascii", "replace")
                ctype = object_type(root, current)
                if ctype != "tag":
                    targets.append((ctype, current))
                    break
            else:
                raise ScanError(f"tag chain longer than 16 links at {name}")
        for ttype, tsha in targets:
            if ttype == "blob":
                body = read_objects(root, [tsha])[tsha]
                findings.extend(scan_bytes(body, f"ref-blob:{name}"))
                scanned += 1
            elif ttype in ("tree", "commit"):
                # A commit ref is walked here too: without --history the commit's own tree is
                # otherwise never read, and the docs promise that every ref is followed.
                for mode, etype, esha, path in tree_entries(root, tsha):
                    findings.extend(scan_name(path, f"ref-{ttype}:{name}:{path}"))
                    if etype != "blob":
                        raise ScanError(f"non-blob entry {path} in {ttype} of {name}")
                    body = read_objects(root, [esha])[esha]
                    findings.extend(scan_bytes(body, f"ref-{ttype}:{name}:{path}"))
                    scanned += 1
    return scanned


# ---------------------------------------------------------------- individual scan surfaces
def bytecode_source(root: str, rel: str) -> str | None:
    """Return the source path a bytecode file is compiled from, if it exists in the tree.

    Bytecode cannot be scanned meaningfully — string constants sit next to each other in the
    marshalled file, so a pattern can match across two unrelated literals. It may be skipped
    only when its source is present and is scanned itself; otherwise it is unverifiable.
    """
    if not rel.endswith((".pyc", ".pyo")):
        return None
    head, _, base = rel.rpartition("/")
    parts = head.split("/") if head else []
    if not parts or parts[-1] != "__pycache__":
        # A .pyc outside __pycache__ is not the normal output of a build; scan it.
        return None
    # <dir>/__pycache__/<module>.cpython-3xx.pyc  ->  <dir>/<module>.py
    parent = "/".join(parts[:-1])
    stem = base.split(".")[0]
    candidate = f"{parent}/{stem}.py" if parent else f"{stem}.py"
    return candidate if os.path.isfile(os.path.join(root, candidate)) else None


def scan_worktree(root: str, findings: list) -> tuple[int, int, int]:
    """Walk everything except the git directory itself.

    Nothing disappears silently: an unreadable directory raises, bytecode is skipped only when
    its source is in the tree, and every skip is counted and reported.
    """
    files = links = skipped = 0

    def on_error(exc: OSError) -> None:
        raise ScanError(f"cannot read {exc.filename}: {exc.strerror}")

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=on_error):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for d in dirnames:
            rel = os.path.relpath(os.path.join(dirpath, d), root)
            findings.extend(scan_name(rel, f"dir:{rel}"))
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            findings.extend(scan_name(rel, f"path:{rel}"))
            if os.path.islink(full):
                links += 1
                findings.extend(scan_bytes(os.readlink(full).encode("utf-8", "replace"),
                                           f"symlink:{rel}"))
                continue
            if not os.path.isfile(full):
                raise ScanError(f"{rel} is not a regular file and cannot be verified")
            if bytecode_source(root, rel):
                skipped += 1
                continue
            if os.path.getsize(full) > MAX_BYTES:
                raise ScanError(f"{rel} exceeds {MAX_BYTES} bytes and cannot be verified")
            with open(full, "rb") as fh:
                findings.extend(scan_bytes(fh.read(), rel))
            files += 1
    return files, links, skipped


def scan_index(root: str, findings: list) -> tuple[int, list[str]]:
    """Scan what a commit would actually record, not what the working tree shows."""
    entries, unmerged = index_entries(root)
    for mode, _, path, stage in entries:
        # A gitlink points at a commit that normally is not in this repository: report that,
        # rather than a confusing "object missing".
        if stage == 0 and mode == "160000":
            raise ScanError(f"submodule entry cannot be verified: {path}")
    blobs = read_objects(root, sorted({sha for _, sha, _, stage in entries if stage == 0}))
    for mode, sha, path, stage in entries:
        if stage != 0:
            continue
        findings.extend(scan_name(path, f"index:{path}"))
        body = blobs.get(sha)
        if body is None:
            raise ScanError(f"index object missing for {path}")
        # For a symlink the blob body is the target path, which is exactly what we scan.
        findings.extend(scan_bytes(body, f"index:{path}"))
    if unmerged:
        staged = read_objects(root, sorted({sha for _, sha, _, stage in entries if stage}))
        for mode, sha, path, _ in (e for e in entries if e[3] != 0):
            findings.extend(scan_name(path, f"index-conflict:{path}"))
            body = staged.get(sha)
            if body is None:
                raise ScanError(f"conflict object missing for {path}")
            findings.extend(scan_bytes(body, f"index-conflict:{path}"))
    return len(entries), unmerged


def scan_history(root: str, findings: list) -> dict[str, int]:
    shallow = git(root, "rev-parse", "--is-shallow-repository").strip()
    if shallow == b"true":
        raise ScanError("shallow repository: history is truncated and cannot be certified; "
                        "clone with full history (fetch-depth: 0)")
    commits_out = git(root, "rev-list", "--all")
    commits = [c for c in commits_out.decode("ascii", "replace").split() if c]
    if commits_out.strip() and not commits:
        raise ScanError("rev-list --all produced unparsable output")
    if any(not re.fullmatch(r"[0-9a-f]{40,64}", c) for c in commits):
        raise ScanError("rev-list --all produced a non-hash line")

    blob_paths: dict[str, str] = {}
    for commit in commits:
        for mode, otype, sha, path in tree_entries(root, commit):
            findings.extend(scan_name(path, f"history-path:{path}"))
            if otype == "commit" or mode == "160000":
                raise ScanError(f"submodule entry in history cannot be verified: {path}")
            if otype == "blob":
                blob_paths.setdefault(sha, path)
            elif otype != "tree":
                raise ScanError(f"unexpected object type {otype} at {path}")

    for sha, body in read_objects(root, sorted(blob_paths)).items():
        findings.extend(scan_bytes(body, f"history:{blob_paths[sha]}"))

    findings.extend(scan_bytes(git(root, "log", "--all", "--format=%B"), "commit-messages"))
    findings.extend(scan_bytes(git(root, "log", "--all", "--format=%an%n%ae%n%cn%n%ce"),
                               "commit-identities"))
    # Reflog subject lines can carry a message that no longer exists on any ref.
    findings.extend(scan_bytes(git(root, "reflog", "--all", "--format=%gs"), "reflog-subjects"))

    fsck = git(root, "fsck", "--unreachable", "--no-reflogs", "--no-progress", allow=(0,))
    blobs: list[str] = []
    tags: list[str] = []
    for line in fsck.decode("utf-8", "replace").splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[0] not in {"unreachable", "dangling"}:
            continue
        if parts[1] == "blob":
            blobs.append(parts[2])
        elif parts[1] == "tag":
            tags.append(parts[2])
    # A deleted tag is still in the object store, and its message is a scanned surface when the
    # tag is reachable — so it stays one when it is not.
    for sha in tags:
        body = read_objects(root, [sha]).get(sha)
        if body is None:
            raise ScanError(f"unreachable tag {sha[:8]} cannot be read")
        findings.extend(scan_bytes(body, f"unreachable-tag:{sha[:8]}"))
        header = next((ln for ln in body.split(b"\n") if ln.startswith(b"object ")), None)
        if header is not None:
            target = header.split()[1].decode("ascii", "replace")
            if object_type(root, target) == "blob":
                blobs.append(target)
    unreachable = blobs
    for sha in unreachable:
        for body in read_objects(root, [sha]).values():
            findings.extend(scan_bytes(body, f"unreachable:{sha[:8]}"))

    return {"commits": len(commits), "blobs": len(blob_paths), "unreachable": len(unreachable)}


# ------------------------------------------------------------------------------- entrypoint
def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="repository to scan (default: this repository)")
    ap.add_argument("--history", action="store_true",
                    help="also scan every ref, blob, message, identity and unreachable object")
    ap.add_argument("--no-index", action="store_true", help="skip the git index")
    ap.add_argument("--quiet", action="store_true", help="print findings only")
    args = ap.parse_args(argv)

    root = os.path.abspath(args.root or DEFAULT_ROOT)
    if not os.path.isdir(root):
        print(f"ERROR: not a directory: {root}", file=sys.stderr)
        return 2

    findings: list[tuple[str, str]] = []
    skipped: list[str] = []
    unmerged: list[str] = []
    stats = {"files": 0, "links": 0, "index": 0, "unmerged": 0, "commits": 0, "blobs": 0,
             "refs": 0, "ref_objects": 0, "unreachable": 0, "bytecode": 0}

    try:
        stats["files"], stats["links"], stats["bytecode"] = scan_worktree(root, findings)

        has_git = os.path.exists(os.path.join(root, ".git"))
        if has_git:
            git_dir(root)  # validates that this really is a work tree
        elif args.history or not args.no_index:
            raise ScanError(f"no git repository at {root}; index and history cannot be verified")

        if has_git:
            # Refs are a published surface in their own right: scan them regardless of mode.
            refs_list = ref_objects(root)
            stats["ref_objects"] = len(refs_list)
            stats["refs"] = scan_refs(root, findings, refs_list)
        if has_git and not args.no_index:
            stats["index"], unmerged = scan_index(root, findings)
            stats["unmerged"] = len(unmerged)

        if args.history:
            stats.update(scan_history(root, findings))

    except ScanError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"ERROR: could not read the working tree: {exc}", file=sys.stderr)
        return 2

    if findings:
        unique = sorted(set(findings))
        print(f"FAIL: {len(unique)} potential leak(s), values redacted:", file=sys.stderr)
        for kind, label in unique:
            print(f"  [{kind}] {label}: [REDACTED]", file=sys.stderr)
        return 1

    if unmerged:
        print(f"ERROR: index has {len(unmerged)} unmerged path(s); a commit from this state "
              f"cannot be certified", file=sys.stderr)
        return 2

    if not args.quiet:
        parts = [f"{stats['files']} files", f"{stats['links']} symlinks"]
        if stats["bytecode"]:
            parts.append(f"{stats['bytecode']} bytecode files skipped (sources scanned)")
        if has_git:
            parts.append(f"{stats['ref_objects']} refs ({stats['refs']} extra objects)")
        if has_git and not args.no_index:
            parts.append(f"{stats['index']} index entries")
        if args.history:
            parts += [f"{stats['commits']} commits", f"{stats['blobs']} blobs",
                      f"{stats['unreachable']} unreachable blobs"]
        print("clean: " + ", ".join(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
