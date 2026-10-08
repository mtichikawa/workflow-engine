"""Every registered specialist MUST carry a rich, co-located capability card (`spec.description`).

The card is what the Composer reads to reason about the library (registry.catalog() -> the "does"
field in the compose prompt). It states: purpose · USE WHEN · NOT (with ->sibling redirects) ·
whether it's CONFIG-DRIVEN (reuse-don't-clone) · IN->OUT. This is the STANDARD going forward: a new
specialist is not "done" until it ships a card. See docs/standards.md (the collapse rule).

Enforcing it here means the library stays Composer-legible as it grows, and directly fights the
over-drafting debt (a Composer that understands "classify is config-driven" won't clone it per domain).

    python tests/test_capability_cards.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import engine.specialists  # noqa: E402,F401  -- registers the library
from engine.core import all_specialists  # noqa: E402

# structural markers every card must carry (keeps them genuinely useful, not a one-liner)
REQUIRED_MARKERS = ("USE WHEN", "NOT", "IN ", "OUT", "->")
MIN_LEN = 120


def _library() -> dict:
    """The shipped library = specialists defined in the engine.specialists package. Excludes
    throwaway test fixtures and Composer-drafted provisional specialists that other modules register
    into the shared registry. Any NEW specialist added under engine/specialists/ is auto-included -->
    the card requirement is enforced going forward, by construction."""
    return {n: s for n, s in all_specialists().items()
            if type(s).__module__.startswith("engine.specialists.")}


def test_every_library_specialist_has_a_rich_colocated_card():
    lib = _library()
    assert lib, "no library specialists found (registration import failed?)"
    problems = []
    for name, spec in sorted(lib.items()):
        # co-located: read the specialist's OWN attribute, not the registry fallback
        card = getattr(spec, "description", "") or ""
        if len(card) < MIN_LEN:
            problems.append((name, f"card too thin ({len(card)} chars; need >= {MIN_LEN})"))
            continue
        missing = [m for m in REQUIRED_MARKERS if m not in card]
        if missing:
            problems.append((name, f"missing markers {missing}"))
    assert not problems, "capability cards incomplete:\n" + "\n".join(
        f"  {n}: {p}" for n, p in problems)
    print(f"    {len(lib)} library specialists, all carry a rich capability card")


if __name__ == "__main__":
    test_every_library_specialist_has_a_rich_colocated_card()
    print("capability cards: OK")
