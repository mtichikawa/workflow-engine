"""Enforce the generality standard (docs/standards.md): every JUDGMENT capability must be validated
leave-one-out on >= 3 unrelated domains.

Kept green while the campaign brings capabilities up to the bar via a shrinking IN_PROGRESS allowlist:
a capability below 3 MUST be listed there (a visible admission), and the test fails if an IN_PROGRESS
entry has actually reached the bar (forcing us to remove it) or if a NON-listed judgment capability
drops below 3. New judgment capabilities cannot ship below 3 without being added here on purpose.

    python tests/test_generality.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "state" / "examples"

JUDGMENT = {"classify", "rank", "verify", "forecast", "extract", "summarize", "sequence", "match"}
NON_DOMAIN = {"mike", "acme_corp", "t1", "t2"}
BAR = 3

# Judgment capabilities still being brought up to the >= 3 domain bar. SHRINK to empty.
# (each here is knowingly below 3; remove once it reaches the bar.)
#
# Counted on the PUBLIC corpus only (state/examples/) so the answer is the same in every clone —
# a claim anyone can check. 2026-10 publication pass: the film domain was deleted (TMDB's API terms
# forbid AI/ML use of its content and caching past 6 months), and golds that can't be redistributed
# (verbatim GitHub issues/replies, App Store reviews, full Stack Exchange question bodies, TheMealDB
# recipe text) moved to the private corpus — they still validate locally but don't count here.
# Rebuilding each to 3 public domains (e.g. Wikidata for film-style tasks) is the open campaign.
IN_PROGRESS: set[str] = {"extract", "forecast", "match", "rank", "sequence", "summarize", "verify"}
# classify:  10 public domains (art/baseline/communities/cooking/economics/government/legislation/nutrition/science/weather)
# extract:   history 100% · weather 97%                       (cooking 100% — private)
# forecast:  sports 60% · legislation 59%                     (film deleted)
# match:     general 97% · communities 75%                    (film deleted)
# rank:      baseline (synthetic rows)                         (reviews 82% — private; film deleted)
# sequence:  history 96%                                       (cooking 95% — private; film deleted)
# summarize: science 69% · general 80%                        (communities 77% — private)
# verify:    baseline 80% · weather 91%                       (cooking 88% — private)


def _domain_count(spec: str) -> int:
    if not EX.exists():
        return 0
    return sum(1 for s in EX.iterdir()             # wf-* = a saved workflow's own (untracked) corrections
               if s.is_dir() and s.name not in NON_DOMAIN and not s.name.startswith("wf-")
               and (s / f"{spec}.jsonl").exists())


def test_judgment_capabilities_meet_generality_bar():
    below = [(s, _domain_count(s)) for s in sorted(JUDGMENT)
             if s not in IN_PROGRESS and _domain_count(s) < BAR]
    assert not below, ("judgment capabilities below the >= %d domain bar (and not in IN_PROGRESS): %s"
                       % (BAR, below))


def test_no_stale_in_progress():
    # once a capability reaches the bar it must be removed from IN_PROGRESS (keeps the list honest)
    stale = [(s, _domain_count(s)) for s in sorted(IN_PROGRESS) if _domain_count(s) >= BAR]
    assert not stale, "these met the bar — remove from IN_PROGRESS: %s" % stale


if __name__ == "__main__":
    test_judgment_capabilities_meet_generality_bar()
    test_no_stale_in_progress()
    print("generality: OK")
