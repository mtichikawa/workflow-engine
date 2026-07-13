# Known issues & deferred fixes

Logged from the code review (2026-07-09). Fixed items removed once resolved.

## Deferred — fix with the control-flow work (don't hack now)

- **`verify`'s verdict is never consumed.** In every recipe, `verify` runs and reports pass/fail, but `act`
  runs regardless — a quality gate that doesn't gate. This is fundamentally a *missing edge*: there should be
  a conditional edge `verify → act WHEN verdict == pass` (and somewhere else on fail). The linear model can't
  express it; the control-flow graph (`control-flow.md`) fixes it directly. Don't special-case it — fix it
  when edges become first-class.

- **Literal-vs-reference ambiguity in `inputs`.** A source string that isn't `payload` and isn't a known step
  is treated as a literal (so filenames like `post.txt` work). A partial guard now catches references to a
  *real* step with no output yet (forward ref / failed step). But a *typo that matches no step*
  (`clasify.label`) still silently becomes a literal. Proper fix: make references syntactically explicit
  (e.g. `$step.field`) so a bare string is unambiguously a literal and a marked ref with an unknown head is a
  loud error. This touches the recipe schema — do it as part of the control-flow schema change, not before.

## Low priority — note, not urgent

- **`registry` / `examples` do read-modify-write without a lock.** Safe today (only called single-threaded
  from the dispatcher's main thread), but latent if ever parallelized. Left a note in the code.
- **`brain` passes the whole prompt as an argv.** For very large inputs (a big diff) this could approach the
  OS command-length limit; passing via stdin would be sturdier. Not hit in practice yet.
- **Board JSON has no version field.** If the `Card`/`Board` shape changes, old `state/*.json` won't load. Add
  a `version` tag if/when the schema changes.

## Resolved (kept briefly for context)

- `act` file writes: leaked handle + unsafe under concurrency + path-traversal on filename → fixed (with-block,
  lock, basename).
- Dead `_MAX_ITERS` constant → removed.
- Forward-reference / failed-step reference silently treated as a literal → now raises loudly.
- Intake fetch failure crashed the CLI with a traceback → now a clean `intake: couldn't fetch …` message.

## Triage: a failed verify is a dead end (no escalation)
Triage's only edge out of `verify` is `verify → act` guarded by `verdict == 'pass'`. If verify
fails, no edge is taken and the work-item silently terminates at verify — nothing staged, no human
escalation. A triage that fails its own sanity check should probably route to a human, not vanish.
(Contrast refine, which has a `verify → write` fail-loop.) Surfaced 2026-07-12 while building the
use-case explorer. Open question: what does the Composer produce for triage — does it add a fail path?

**Deeper design question (2026-07-13, open — Mike flagged, not yet decided): advisory verify vs. blocking gate.**
The gate is `verdict == 'pass'` only — verify's `issues` list is advisory (rides along as notes, blocks
nothing). So verify can flag real concerns and still pass the item to staging. Observed on issue #95698:
verify passed (0.6) but listed 3 issues — and one ("the reply invents a '711' figure, fabricated
precision") was itself WRONG (711 = 712−1, and 712 is stated in the issue). So verify is fallible on
fuzzy judgments. Insight: **hard loops fit objective checks** (refine: "≥2 numeric stats" — crisp),
**advisory + human gate fits subjective checks** (triage: "does this cohere?" — fuzzy, checker errs;
hard-blocking on a fallible check would loop-reject good output). Leaning: keep triage advisory, but fix
the fail dead-end above (fail → stage marked "needs a look", never vanish). The triage-vs-refine contrast
is a deliberate design choice worth making legible in the explorer, not a flaw. DECISION OWED by Mike.
