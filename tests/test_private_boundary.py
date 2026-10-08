"""The public/private boundary holds: nothing private is tracked by this (public) repo.

private/ is a separate repo nested inside this one (working notes + golds that can't be
redistributed). A dropped .gitignore line or a stray `git add -f` would publish it on the next
push, so this fails loudly instead. Also guards the public gold corpus against the two classes of
data that were moved out of it: verbatim GitHub issues (copyright + usernames) and TMDB film data
(its API terms forbid AI use).

    python tests/test_private_boundary.py
"""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "state" / "examples"


def _git(*args):
    try:
        p = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        return None
    return p.stdout if p.returncode == 0 else None


def test_private_dir_is_ignored_and_untracked():
    if _git("rev-parse", "--is-inside-work-tree") is None:
        return   # not a git checkout (e.g. an sdist) — nothing to guard
    assert "/private/" in (ROOT / ".gitignore").read_text().splitlines(), \
        ".gitignore must keep the '/private/' rule"
    tracked = _git("ls-files", "--", "private")
    assert not (tracked or "").strip(), f"private/ files are tracked by the PUBLIC repo:\n{tracked}"


def test_public_golds_hold_no_verbatim_github_issues():
    leaks = []
    for f in sorted(EX.glob("*/*.jsonl")):
        for n, line in enumerate(f.read_text().splitlines(), 1):
            if line.strip() and "/issues/" in json.dumps(json.loads(line).get("input")):
                leaks.append(f"{f.relative_to(ROOT)}:{n}")
    assert not leaks, "real GitHub issue rows belong in private/examples/: " + ", ".join(leaks)


def test_no_film_scope():
    assert not (EX / "film").exists(), "film golds were TMDB-derived — TMDB's terms forbid AI use"


if __name__ == "__main__":
    test_private_dir_is_ignored_and_untracked()
    test_public_golds_hold_no_verbatim_github_issues()
    test_no_film_scope()
    print("private boundary: OK")
