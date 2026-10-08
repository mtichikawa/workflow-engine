# Standards — how we build specialists honestly

The load-bearing rules. Enforced by tests where possible, not just prose. Companion to
the provenance manifests (`docs/provenance/`) and `learning-loop.md` (the design).

## Buckets — which standard applies to which specialist

Not every specialist gets the same treatment. Three buckets:

- **Judgment capabilities** — `classify · rank · verify · forecast · extract · summarize · sequence · match`.
  Reusable skills that make a judgment. These get the **generality standard** + the honest-improvement rules.
- **I/O adapters** — `fetch · act`. They connect to sources/targets, they don't judge. Their bar is
  **connector coverage** (supports N sources/targets), not domain breadth. Exempt from the domain bar.
- **Tailored / generative domain specialists** — `write · respond · review` (and `route`, pending a call).
  Intentionally domain- or voice-flavored, and their output is free text with no clean automatic matcher.
  Their bar is **tailored quality**, not domain breadth. Forcing them onto the domain bar would distort them.

A genuinely new *generalized* capability is rare (most real use is a new **config** of an existing one), so
deciding a new specialist's bucket is a cheap, infrequent human call — not a per-specialist training regime.

## The generality standard (judgment capabilities)

> **Every judgment capability must be validated leave-one-out on ≥ 3 UNRELATED domains.**

Why three, why unrelated: a genuinely general capability survives three unrelated domains; a secretly-narrow
one gets exposed by the second or third. **Breadth is the structural guard against narrowing.** One domain
can't tell "general" from "overfit to this domain" apart — three can.

Enforced by `tests/test_generality.py` (+ `tools/check_generality.py` for the live report). A capability
below the bar must be listed explicitly in the test's `IN_PROGRESS` set — a visible admission, not a silent
gap. New judgment capabilities can't ship below three without that admission.

## No synthetic improvement (provisional → trusted)

Certification is **eval-driven, never a human sign-off**: `registry.promote()` flips provisional→trusted
when the *real* leave-one-out score crosses ≥ 80% on enough golds. Never move the number by hand.

To raise a real score, in order of safety:
1. **More / better real golds** — improve the specialist's material; the score follows.
2. **Truer ground truth** — a more valid test (e.g. real duplicate pairs vs a loose proxy).
3. **A more-valid metric** — only if genuinely fairer, not because it scores higher.
4. **Fix a genuinely-wrong config** — honest only when the old one mis-stated the task.

Hard rules:
- **Improve at the config / data / metric layer — never by narrowing the capability.** The contract, base
  prompt, and card stay domain-agnostic. Domain specificity lives in configs/exemplars, by design.
- **A fix that lifts one domain must keep the other domains green.** If it drops them, it's a narrowing —
  revert it.
- **No Goodharting.** Don't iterate configs against the same held-out golds until the number turns green
  (that's overfitting to the test). Search config space only against FRESH golds the search never saw.
- An honest 75% that won't move is more valuable than a tuned-to-look-like-90% — the 90% lies to whoever
  relies on it. Provisional is a correct, shippable, permanent label when the real number won't cross honestly.

## Integrity split (Kind-A vs Kind-B)

Build autonomously only where **external ground truth** exists (a museum catalog, a maintainer, an author, an
outcome). Where the right answer is a **judgment** — taste, convention, a person's voice — the human labels the
hard cases via the gate (as with the 6 ROUTE boundary labels). **Never self-label the eval**: if you both write
the input and pick the answer, the eval only measures your own consistency.

## Other load-bearing rules

- **Collapse rule** — a specialist is a reusable capability, not a domain; grow wide in skills, dedup within a
  skill via configs. No per-domain clones.
- **Capability cards** — every specialist ships a co-located, test-enforced card the Composer reads to reuse
  (not clone) the library.
- **Curated data is source** — golds are tracked + provenance-documented + regenerable from a harvester; only
  runtime churn is gitignored.
