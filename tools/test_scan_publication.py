#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 NEXUS project contributors
"""Isolated tests for the publication scanner.

Every case builds a throwaway repository in a temporary directory. Fake credentials are
assembled at runtime, so no secret-shaped literal exists in this file — which means the
scanner can and does scan this file as part of the repository.

What is asserted is the scanner's *verdict* (exit code 0 / 1 / 2 and, where it matters, that
nothing is printed), never that a function was called.

Run:  python3 tools/test_scan_publication.py
Exit 0 only if every case behaves as specified.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

SCANNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scan_publication.py")
GIT_ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")

# Fake material, assembled at runtime so this file stays clean.
#
# The assembly goes through a function call on purpose: adjacent string literals would be
# constant-folded into the compiled .pyc, and bytecode is scanned like any other file. With
# `join` the compiled artifact only ever contains the fragments.
def parts(*chunks: str) -> str:
    return "".join(chunks)


FAKE_GH = parts("gh", "p_", "A1b2", "C3d4", "E5f6", "G7h8", "I9j0", "K1l2", "M3n4", "O5p6", "Q7r8")
FAKE_SK = parts("sk-", "Ab1Cd2Ef3Gh4Ij5Kl6Mn7Op8Qr9St0")
FAKE_KEY = parts("-----BEGIN ", "OPENSSH PRIVATE KEY-----")
FAKE_JWT = parts("eyJ", "hbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r")
HOME_PATH = parts("/ho", "me/someuser/project")
PRIVATE_IP = parts("10.", "11.12.13")
DOC_IP = parts("192.0.", "2.10")
FAKE_EMAIL = parts("someone@", "realmail.example.invalid")
FAKE_DOMAIN = parts("internalcorp", ".com")
INTERNAL_HOST = parts("db01", ".internal")
INTERNAL_DIR = parts("router01", ".local")
IDENTITY = parts("Real ", "Person")
IDENTITY_MAIL = parts("real", ".person@company", ".example")
ENTROPY = parts("Zx9Q", "w8Er", "7Ty6", "Ui5O", "p4As", "3Df2", "Gh1J", "k0Lm")
HEX_SECRET = parts("9f2c", "41ab", "7d38", "e504", "6b1a", "c2f7", "8d90", "1e3b",
                   "4a6c", "5f82", "0d7e", "3c91", "ab46", "2d8f", "5e07", "c3a4")
# A synthetic 40-character object id: shape only, not a credential.
GIT_SHA = "a944840f9e1a99ddd05ddd0a3d876f7f0470f208"  # pragma: allowlist secret
SPACED = "notes with spaces.txt"
UNICODE_NAME = "notat med æøå.txt"
NEWLINE_NAME = "inject\nname.txt"

RESULTS: list[bool] = []


def report(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name:48}{'' if ok else '  ' + detail}")


def run(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, SCANNER, *args], capture_output=True, text=True,
                          timeout=180, env=env)


def git(repo: str, *args: str, env: dict | None = None, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                          env=env or GIT_ENV)
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc


def new_repo() -> str:
    path = tempfile.mkdtemp(prefix="scan-test-")
    subprocess.run(["git", "init", "-q", path], check=True, env=GIT_ENV)
    return path


def write(repo: str, name: str, content: bytes | str) -> str:
    full = os.path.join(repo, name)
    os.makedirs(os.path.dirname(full) or repo, exist_ok=True)
    mode = "wb" if isinstance(content, bytes) else "w"
    with open(full, mode) as fh:
        fh.write(content)
    return full


def commit(repo: str, message: str = "t") -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message)


def scan(repo: str, *extra: str) -> subprocess.CompletedProcess:
    return run("--root", repo, *extra)


def expect(name: str, repo: str, code: int, *extra: str, secrets: tuple[str, ...] = ()) -> None:
    proc = scan(repo, *extra)
    ok = proc.returncode == code
    if ok and secrets:
        blob = proc.stdout + proc.stderr
        leaked = [s for s in secrets if s in blob]
        if leaked:
            ok = False
            report(name, False, "value leaked in output")
            return
    detail = (proc.stdout + proc.stderr).strip().replace("\n", " | ")[:160]
    report(name, ok, f"expected {code}, got {proc.returncode}: {detail}")


# ------------------------------------------------------------------ tree and content rules
def case_content() -> None:
    repo = new_repo()
    try:
        write(repo, "README.md", "# project\n\nNothing sensitive.\n")
        expect("clean repository", repo, 0)
        expect("clean repository with history", repo, 0, "--history")
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    simple = [
        ("token in untracked .env", {".env": "KEY=" + FAKE_SK + "\n"}, 1, ()),
        ("token in non-standard extension", {"data/settings.cfg": "k=" + FAKE_SK + "\n"}, 1, ()),
        ("token in file without extension", {"bin/config": FAKE_SK + "\n"}, 1, ()),
        ("private key block", {"id_key": FAKE_KEY + "\nAAAA\n"}, 1, ()),
        ("private ipv4", {"net.md": "host " + PRIVATE_IP + "\n"}, 1, ()),
        ("documentation ipv4 is allowed", {"net.md": "host " + DOC_IP + "\n"}, 0, ()),
        ("absolute home path", {"run.sh": "cd " + HOME_PATH + "\n"}, 1, ()),
        ("email address", {"contact.md": FAKE_EMAIL + "\n"}, 1, ()),
        ("private-looking domain", {"dns.md": "api." + FAKE_DOMAIN + "\n"}, 1, ()),
        ("internal hostname suffix", {"hosts.md": "host " + INTERNAL_HOST + "\n"}, 1, ()),
        ("high entropy blob", {"blob.bin": ENTROPY + "\n"}, 1, ()),
        ("64-char hex secret", {"config.txt": "key=" + HEX_SECRET + "\n"}, 1, ()),
        ("40-char git object id is allowed",
         {"CHANGELOG.md": "commit " + GIT_SHA + " fixes the thing\n"}, 0, ()),
        ("binary content with token",
         {"image.png": b"\x89PNG\r\n\x1a\n" + FAKE_GH.encode() + b"\x00\xff"}, 1, ()),
        ("filename with spaces", {SPACED: "token " + FAKE_GH + "\n"}, 1, ()),
        ("clean unicode filename", {UNICODE_NAME: "vanlig tekst\n"}, 0, ()),
        ("normal project filenames",
         {"docs/architecture.md": "text\n", "diagrams/system-overview.svg": "<svg/>\n",
          "calculations/recompute.py": "print(1)\n"}, 0, ()),
    ]
    for name, files, code, _ in simple:
        repo = new_repo()
        try:
            for rel, content in files.items():
                write(repo, rel, content)
            commit(repo)
            expect(name, repo, code, secrets=(FAKE_GH, FAKE_SK, FAKE_KEY, ENTROPY))
        finally:
            shutil.rmtree(repo, ignore_errors=True)


# ------------------------------------------------------------------------------ git index
def case_index() -> None:
    # The reported bypass: staged secret, working copy reverted.
    repo = new_repo()
    try:
        write(repo, "config.txt", "key = " + FAKE_GH + "\n")
        git(repo, "add", "config.txt")
        write(repo, "config.txt", "key = \"\"\n")
        shown = git(repo, "show", ":config.txt").stdout
        assert FAKE_GH in shown, "fixture did not stage the secret"
        expect("staged secret, clean worktree", repo, 1)
        expect("staged secret, git status clean", repo, 1, secrets=(FAKE_GH,))
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # Staged secret, working file deleted.
    repo = new_repo()
    try:
        write(repo, "config.txt", "key = " + FAKE_GH + "\n")
        git(repo, "add", "config.txt")
        os.remove(os.path.join(repo, "config.txt"))
        expect("staged secret, workfile deleted", repo, 1)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # Staged secret in a brand-new file that was never committed.
    repo = new_repo()
    try:
        write(repo, "README.md", "text\n")
        commit(repo)
        write(repo, "secrets/new.txt", "token " + FAKE_TOKEN_ALT() + "\n")
        git(repo, "add", "secrets/new.txt")
        expect("staged secret in new file", repo, 1)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # Staged secret in a file whose name needs careful parsing.
    repo = new_repo()
    try:
        write(repo, SPACED, "token " + FAKE_GH + "\n")
        git(repo, "add", SPACED)
        write(repo, SPACED, "clean\n")
        expect("staged secret, spaced filename", repo, 1)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    repo = new_repo()
    try:
        write(repo, NEWLINE_NAME, "token " + FAKE_GH + "\n")
        git(repo, "add", NEWLINE_NAME)
        write(repo, NEWLINE_NAME, "clean\n")
        expect("staged secret, filename with newline", repo, 1)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # Clean staging: a normal change plus a staged deletion.
    repo = new_repo()
    try:
        write(repo, "a.txt", "one\n")
        write(repo, "b.txt", "two\n")
        commit(repo)
        write(repo, "a.txt", "one changed\n")
        git(repo, "add", "a.txt")
        git(repo, "rm", "-q", "b.txt")
        expect("clean staging with a deletion", repo, 0)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # Unmerged index: secret in a conflict stage, clean later stages.
    repo = new_repo()
    try:
        write(repo, "base.txt", "base\n")
        commit(repo)
        ours = subprocess.run(["git", "-C", repo, "hash-object", "-w", "--stdin"],
                              input="token " + FAKE_GH + "\n", capture_output=True, text=True,
                              env=GIT_ENV, check=True).stdout.strip()
        theirs = subprocess.run(["git", "-C", repo, "hash-object", "-w", "--stdin"],
                                input="other\n", capture_output=True, text=True,
                                env=GIT_ENV, check=True).stdout.strip()
        info = f"100644 {ours} 1\tconflict.txt\n100644 {theirs} 2\tconflict.txt\n"
        subprocess.run(["git", "-C", repo, "update-index", "--index-info"], input=info,
                       text=True, capture_output=True, env=GIT_ENV, check=True)
        expect("staged secret in unmerged index", repo, 1)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # Unmerged index with clean content: verifiable but not certifiable.
    repo = new_repo()
    try:
        write(repo, "base.txt", "base\n")
        commit(repo)
        one = subprocess.run(["git", "-C", repo, "hash-object", "-w", "--stdin"],
                             input="ours\n", capture_output=True, text=True, env=GIT_ENV,
                             check=True).stdout.strip()
        two = subprocess.run(["git", "-C", repo, "hash-object", "-w", "--stdin"],
                             input="theirs\n", capture_output=True, text=True, env=GIT_ENV,
                             check=True).stdout.strip()
        info = f"100644 {one} 1\tconflict.txt\n100644 {two} 2\tconflict.txt\n"
        subprocess.run(["git", "-C", repo, "update-index", "--index-info"], input=info,
                       text=True, capture_output=True, env=GIT_ENV, check=True)
        expect("clean but unmerged index is an error", repo, 2)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # The index check can be skipped explicitly (tests only; never for publication).
    repo = new_repo()
    try:
        write(repo, "config.txt", "key = " + FAKE_GH + "\n")
        git(repo, "add", "config.txt")
        write(repo, "config.txt", "clean\n")
        expect("--no-index skips the staged secret", repo, 0, "--no-index")
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def FAKE_TOKEN_ALT() -> str:
    return parts("gh", "p_", "Z9y8", "X7w6", "V5u4", "T3s2", "R1q0", "P9o8", "N7m6", "L5k4", "J3i2")


# --------------------------------------------------------------------------- names and refs
def case_names() -> None:
    repo = new_repo()
    try:
        write(repo, "keys/" + FAKE_GH + ".txt", "nothing\n")
        expect("filename containing a token", repo, 1)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    repo = new_repo()
    try:
        write(repo, "config/" + INTERNAL_HOST + "/app.yml", "text\n")
        expect("directory with internal hostname", repo, 1)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    repo = new_repo()
    try:
        write(repo, "notes/" + INTERNAL_DIR + ".md", "text\n")
        expect("filename with .local hostname", repo, 1)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    repo = new_repo()
    try:
        write(repo, "host-" + PRIVATE_IP + ".txt", "text\n")
        expect("filename with private ipv4", repo, 1)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    repo = new_repo()
    try:
        write(repo, "control\x07name.txt", "text\n")
        expect("filename with control character", repo, 1)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    repo = new_repo()
    try:
        write(repo, "split\nname.txt", "text\n")
        expect("filename with a newline", repo, 1)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # Zero-width characters render as nothing but defeat a literal suffix match.
    repo = new_repo()
    try:
        write(repo, "srv." + "\u200b" + "internal.txt", "text\n")
        expect("zero-width character inside an internal name", repo, 1)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # Bytecode is a file like any other: it can be named anything and is scanned.
    repo = new_repo()
    try:
        write(repo, "creds.pyc", b"\x00\x01" + FAKE_GH.encode() + b"\x00")
        expect("secret inside a .pyc file", repo, 1)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # Branch names are a published surface even without --history.
    repo = new_repo()
    try:
        write(repo, "README.md", "text\n")
        commit(repo)
        git(repo, "branch", "feature-" + FAKE_GH)
        expect("branch name caught without --history", repo, 1)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    repo = new_repo()
    try:
        write(repo, "file-" + HEX_SECRET + ".bin", "text\n")
        expect("filename with hex secret", repo, 1)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    repo = new_repo()
    try:
        write(repo, "README.md", "text\n")
        commit(repo)
        git(repo, "branch", "feature/" + FAKE_GH)
        expect("branch name containing a token", repo, 1, "--history")
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    repo = new_repo()
    try:
        write(repo, "README.md", "text\n")
        commit(repo)
        git(repo, "tag", "release-" + INTERNAL_HOST)
        expect("tag name with internal hostname", repo, 1, "--history")
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    repo = new_repo()
    try:
        write(repo, "README.md", "text\n")
        commit(repo)
        git(repo, "tag", "-a", "v1", "-m", "release token " + FAKE_GH)
        expect("secret in annotated tag message", repo, 1, "--history")
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    repo = new_repo()
    try:
        write(repo, "README.md", "text\n")
        commit(repo)
        git(repo, "tag", "-a", "v1", "-m", "release notes")
        expect("clean annotated tag", repo, 0, "--history")
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # A ref may point straight at a blob: `git push --tags` would publish it.
    repo = new_repo()
    try:
        write(repo, "README.md", "text\n")
        commit(repo)
        blob = subprocess.run(["git", "-C", repo, "hash-object", "-w", "--stdin"],
                              input="DB_PASSWORD=" + FAKE_SK + "\n", capture_output=True,
                              text=True, env=GIT_ENV, check=True).stdout.strip()
        git(repo, "update-ref", "refs/tags/leaked-blob", blob)
        expect("ref pointing at a secret blob", repo, 1)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # A ref may point at a tree, whose blobs are never reached by rev-list.
    repo = new_repo()
    try:
        write(repo, "README.md", "text\n")
        commit(repo)
        blob = subprocess.run(["git", "-C", repo, "hash-object", "-w", "--stdin"],
                              input="token " + FAKE_GH + "\n", capture_output=True, text=True,
                              env=GIT_ENV, check=True).stdout.strip()
        inner = subprocess.run(["git", "-C", repo, "mktree"], text=True, capture_output=True,
                               input=f"100644 blob {blob}\tconf.txt\n", env=GIT_ENV,
                               check=True).stdout.strip()
        outer = subprocess.run(["git", "-C", repo, "mktree"], text=True, capture_output=True,
                               input=f"040000 tree {inner}\tconfig\n", env=GIT_ENV,
                               check=True).stdout.strip()
        git(repo, "update-ref", "refs/tags/snapshot", outer)
        expect("ref pointing at a tree with a secret", repo, 1)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # An annotated tag may point at another annotated tag: the middle object is published too.
    repo = new_repo()
    try:
        write(repo, "README.md", "text\n")
        commit(repo)
        git(repo, "tag", "-a", "inner", "-m", "build " + FAKE_SK)
        git(repo, "tag", "-a", "outer", "-m", "release", "inner")
        git(repo, "tag", "-d", "inner")
        expect("secret in a chained annotated tag", repo, 1)
        expect("secret in a chained annotated tag (history)", repo, 1, "--history")
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # A tag on a commit that no branch references: the worktree is clean, the commit is not.
    repo = new_repo()
    try:
        write(repo, "README.md", "text\n")
        commit(repo)
        git(repo, "checkout", "-q", "-b", "side")
        write(repo, "hidden.txt", "token " + FAKE_GH + "\n")
        commit(repo, "side work")
        git(repo, "tag", "-a", "snapshot", "-m", "snapshot")
        git(repo, "checkout", "-q", "-")
        git(repo, "branch", "-D", "side")
        expect("tag on an otherwise unreferenced commit", repo, 1)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # Bytecode next to its own source is a build artifact and is skipped, and said so.
    repo = new_repo()
    try:
        write(repo, "mod.py", "VALUE = 1\n")
        write(repo, "__pycache__/mod.cpython-311.pyc", b"\x00" + FAKE_GH.encode() + b"\x00")
        proc = scan(repo)
        ok = proc.returncode == 0 and "bytecode" in proc.stdout
        report("bytecode with its source is skipped and counted", ok,
               f"exit {proc.returncode}: {proc.stdout.strip()[:80]}")
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # A replace ref hides a leaking commit from rev-list, ls-tree and fsck alike.
    repo = new_repo()
    try:
        write(repo, "README.md", "text\n")
        commit(repo, "init")
        clean = git(repo, "rev-parse", "HEAD").stdout.strip()
        write(repo, "leak.txt", "token " + FAKE_GH + "\n")
        commit(repo, "add leak")
        leaky = git(repo, "rev-parse", "HEAD").stdout.strip()
        git(repo, "rm", "-q", "leak.txt")
        git(repo, "commit", "-qm", "remove")
        git(repo, "replace", leaky, clean)
        expect("replace ref cannot hide a leaking commit", repo, 1, "--history")
        expect("replace ref is reported in default mode", repo, 1)
    finally:
        shutil.rmtree(repo, ignore_errors=True)


# ------------------------------------------------------------------------------- metadata
def case_metadata() -> None:
    repo = new_repo()
    try:
        write(repo, "README.md", "text\n")
        commit(repo, "add " + FAKE_GH)
        expect("secret in commit message", repo, 1, "--history")
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    repo = new_repo()
    try:
        write(repo, "file.txt", "plain\n")
        git(repo, "add", "-A")
        subprocess.run(["git", "-C", repo, "commit", "-qm", "plain"],
                       capture_output=True, env=dict(GIT_ENV, GIT_AUTHOR_NAME=IDENTITY,
                                                     GIT_AUTHOR_EMAIL=IDENTITY_MAIL,
                                                     GIT_COMMITTER_NAME=IDENTITY,
                                                     GIT_COMMITTER_EMAIL=IDENTITY_MAIL),
                       check=True)
        expect("personal commit identity", repo, 1, "--history")
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    repo = new_repo()
    try:
        write(repo, "file.txt", "plain\n")
        subprocess.run(["git", "-C", repo, "add", "-A"], capture_output=True, env=GIT_ENV,
                       check=True)
        subprocess.run(["git", "-C", repo, "commit", "-qm", "plain"],
                       capture_output=True, env=GIT_ENV, check=True)
        expect("neutral commit identity is allowed", repo, 0, "--history")
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # A submodule entry points at a commit that is not in this repository: unverifiable.
    repo = new_repo()
    try:
        write(repo, "README.md", "text\n")
        commit(repo)
        git(repo, "update-index", "--add", "--cacheinfo",
            "160000,1111111111111111111111111111111111111111,vendor/lib")
        expect("submodule entry fails closed", repo, 2)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # A deleted annotated tag still sits in the object store with its message.
    repo = new_repo()
    try:
        write(repo, "README.md", "text\n")
        commit(repo)
        git(repo, "tag", "-a", "doomed", "-m", "build " + FAKE_SK)
        git(repo, "tag", "-d", "doomed")
        expect("secret in an unreachable annotated tag", repo, 1, "--history")
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # Secret in a blob that is no longer reachable from any ref.
    repo = new_repo()
    try:
        write(repo, "leak.txt", "token " + FAKE_GH + "\n")
        commit(repo)
        git(repo, "rm", "-q", "leak.txt")
        git(repo, "commit", "-qm", "remove")
        reachable = scan(repo, "--history")
        if reachable.returncode == 0:
            report("history scan misses reachable leak", False, "expected 1, got 0")
            return
        git(repo, "reset", "-q", "--hard", "HEAD~1")
        git(repo, "update-ref", "-d", "refs/heads/master", check=False)
        git(repo, "update-ref", "-d", "refs/heads/main", check=False)
        git(repo, "reflog", "expire", "--expire=now", "--all")
        expect("secret only in an unreachable blob", repo, 1, "--history")
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # Secret in a historical path that no longer exists.
    repo = new_repo()
    try:
        write(repo, "old/" + INTERNAL_HOST, "text\n")
        commit(repo)
        git(repo, "rm", "-q", "old/" + INTERNAL_HOST)
        git(repo, "commit", "-qm", "remove")
        expect("internal hostname only in a history path", repo, 1, "--history")
    finally:
        shutil.rmtree(repo, ignore_errors=True)


# --------------------------------------------------------------------- failures, fail-closed
def case_failures() -> None:
    # Fresh repository without refs: legitimate, must be clean.
    repo = new_repo()
    try:
        write(repo, "README.md", "text\n")
        expect("repository with no commits", repo, 0, "--history")
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # Normal branch and tag.
    repo = new_repo()
    try:
        write(repo, "README.md", "text\n")
        commit(repo)
        git(repo, "tag", "v1")
        expect("normal branch and tag", repo, 0, "--history")
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # Corrupt HEAD: git cannot answer, so nothing can be certified.
    repo = new_repo()
    try:
        write(repo, "README.md", "text\n")
        commit(repo)
        with open(os.path.join(repo, ".git", "HEAD"), "w") as fh:
            fh.write("garbage\n")
        expect("corrupt HEAD", repo, 2, "--history")
        expect("corrupt HEAD without --history", repo, 2)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # Corrupt packed-refs: for-each-ref fails, which is not "no refs".
    repo = new_repo()
    try:
        write(repo, "README.md", "text\n")
        commit(repo)
        git(repo, "pack-refs", "--all")
        with open(os.path.join(repo, ".git", "packed-refs"), "w") as fh:
            fh.write("this is not a packed-refs file\n")
        expect("corrupt packed-refs", repo, 2, "--history")
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # Missing object: cat-file cannot produce content.
    repo = new_repo()
    try:
        write(repo, "data.txt", "content\n")
        commit(repo)
        sha = git(repo, "rev-parse", "HEAD:data.txt").stdout.strip()
        os.remove(os.path.join(repo, ".git", "objects", sha[:2], sha[2:]))
        expect("missing object", repo, 2, "--history")
        expect("missing object in index", repo, 2)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # git fsck fails with output that looks plausible.
    repo = new_repo()
    try:
        write(repo, "data.txt", "content\n")
        commit(repo)
        sha = git(repo, "rev-parse", "HEAD:data.txt").stdout.strip()
        obj = os.path.join(repo, ".git", "objects", sha[:2], sha[2:])
        os.chmod(obj, 0o644)
        with open(obj, "wb") as fh:
            fh.write(b"corrupt")
        expect("corrupt object makes fsck fail", repo, 2, "--history")
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # A shallow clone cannot certify history: exit 2, not a clean scan.
    src = new_repo()
    shallow = tempfile.mkdtemp(prefix="scan-shallow-")
    shutil.rmtree(shallow, ignore_errors=True)
    try:
        write(src, "a.txt", "token " + FAKE_GH + "\n")
        commit(src, "add leak")
        for i in range(3):
            write(src, "a.txt", f"clean {i}\n")
            commit(src, f"clean {i}")
        subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{src}", shallow],
                       check=True, capture_output=True, env=GIT_ENV)
        expect("shallow clone fails closed", shallow, 2, "--history")
    finally:
        shutil.rmtree(src, ignore_errors=True)
        shutil.rmtree(shallow, ignore_errors=True)

    # Repository-redirecting variables must not point the scan at another repository.
    #
    # The secret is history-only (removed from the worktree in a later commit): if it were also
    # in the tree, the case would pass on a scanner that honours GIT_DIR.
    target = new_repo()
    decoy = new_repo()
    try:
        write(target, "leak.txt", "token " + FAKE_GH + "\n")
        commit(target, "add leak")
        git(target, "rm", "-q", "leak.txt")
        commit(target, "remove leak")
        write(decoy, "README.md", "clean\n")
        commit(decoy)
        overrides = {
            "GIT_DIR": os.path.join(decoy, ".git"),
            "GIT_WORK_TREE": decoy,
            "GIT_INDEX_FILE": os.path.join(decoy, ".git", "index"),
            "GIT_OBJECT_DIRECTORY": os.path.join(decoy, ".git", "objects"),
        }
        for var, value in overrides.items():
            proc = run("--root", target, "--history", env=dict(os.environ, **{var: value}))
            report(f"{var} cannot redirect the scan", proc.returncode == 1,
                   f"expected 1, got {proc.returncode}: {(proc.stdout + proc.stderr)[:120]}")
        expect("the decoy repository itself is clean", decoy, 0, "--history")
    finally:
        shutil.rmtree(target, ignore_errors=True)
        shutil.rmtree(decoy, ignore_errors=True)

    # Not a repository at all.
    repo = tempfile.mkdtemp(prefix="scan-nogit-")
    try:
        write(repo, "file.txt", "text\n")
        expect("history without git", repo, 2, "--history")
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    expect("missing root directory", "/nonexistent/scan-root", 2)

    # Oversized file cannot be verified.
    repo = new_repo()
    try:
        path = os.path.join(repo, "big.bin")
        with open(path, "wb") as fh:
            fh.truncate(8 * 1024 * 1024 + 1)
        expect("oversized file fails closed", repo, 2)
    finally:
        shutil.rmtree(repo, ignore_errors=True)

    # Unreadable file cannot be verified.
    repo = new_repo()
    try:
        path = write(repo, "secret.txt", "text\n")
        os.chmod(path, 0o000)
        expect("unreadable file fails closed", repo, 2)
    finally:
        os.chmod(path, 0o600)
        shutil.rmtree(repo, ignore_errors=True)

    # An unreadable directory must not disappear from the walk.
    repo = new_repo()
    hidden = os.path.join(repo, "hidden")
    try:
        write(repo, "hidden/leak.txt", "token " + FAKE_GH + "\n")
        os.chmod(hidden, 0o000)
        expect("unreadable directory fails closed", repo, 2)
    finally:
        os.chmod(hidden, 0o700)
        shutil.rmtree(repo, ignore_errors=True)


def main() -> int:
    case_content()
    case_index()
    case_names()
    case_metadata()
    case_failures()
    passed, total = sum(RESULTS), len(RESULTS)
    print(f"\n{passed}/{total} cases behaved as specified")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
