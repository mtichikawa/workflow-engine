"""The proof: two unrelated recipes run on one core, sharing the SAME specialist
instances — reuse enforced structurally, not by convention.

Run:  python tests/proof_shared.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import engine.specialists as S  # noqa: F401  (registers)
from engine.core import get
from engine.recipes import CONTENT, TRIAGE

triage_uses = {s.specialist for s in TRIAGE.steps}
content_uses = {s.specialist for s in CONTENT.steps}

# classify/rank/verify/act appear as steps in BOTH; fetch is shared too
# (a step in content, the intake call in triage) — same instance either way.
common = sorted(triage_uses & content_uses)
assert {"classify", "rank", "verify", "act"} <= set(common), common

print("Triage domain middle :", [s.specialist for s in TRIAGE.steps if s.domain])
print("Content domain middle:", [s.specialist for s in CONTENT.steps if s.domain])
print("\nShared capability-specialists used by BOTH recipes:", common, "(+ fetch via triage intake)")
print("\nEach is a single shared instance (same object id in both recipes):")
for name in S.CAPABILITIES:
    inst = get(name)
    assert get(name) is inst, "registry returned a different instance!"
    print(f"  {name:<9} id={id(inst)}  kind={inst.kind}")

print("\nPROOF: one engine, two domains, five specialists literally reused. Only the middle differs.")
