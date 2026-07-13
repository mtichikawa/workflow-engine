"""1B — WRITE's 'baseline' was actually Mike's voice: a TAILORED layer mislabeled as a craft floor.

Per the 3-layer model (learning-loop.md): a specialist's BASELINE should be config-agnostic *craft*,
and a specific person's/brand's voice is a TAILORED layer on top. WRITE's baseline exemplars are a
voice, so they belong in a tailored scope — leaving the baseline to the role (the craft floor) until
genuine craft exemplars are curated.

This moves WRITE's exemplars from `baseline` to a tailored voice scope. Idempotent: after the move,
re-runs are no-ops. Reversible: `move_examples("write", VOICE_SCOPE, "baseline")`.

    python examples/relabel_write_voice.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.examples import count_examples, move_examples

VOICE_SCOPE = "mike"

before = count_examples("write", "baseline")
moved = move_examples("write", "baseline", VOICE_SCOPE)
print(f"WRITE voice relabel: moved {moved} exemplars  baseline -> {VOICE_SCOPE} (tailored)")
print(f"  baseline now: {count_examples('write', 'baseline')}   {VOICE_SCOPE} now: {count_examples('write', VOICE_SCOPE)}")
if moved:
    print(f"  default WRITE leans on its role (the craft floor); the voice applies under --scope {VOICE_SCOPE}.")
elif before == 0:
    print("  nothing in baseline to move — already relabeled (or never seeded).")
