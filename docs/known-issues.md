# Known issues & deferred fixes

Logged from the code review (2026-07-09). Fixed items removed once resolved.

## Open

- **Literal-vs-reference ambiguity in `inputs`.** A source string that isn't `payload`, `each` or a known
  step is treated as a literal (so filenames like `post.txt` work). The validator now flags a reference
  whose head is a near-miss of a real step (`clasify.label` → "did you mean 'classify'?"), but a typo that
  resembles nothing still becomes a literal. Proper fix: explicit reference syntax (`$step.field`).
- **`registry` does read-modify-write without a lock.** Safe while only the dispatcher's main thread calls it.
- **Board JSON has no version field.** New Card fields get defaults (e.g. `approved`), so old boards still
  load; a breaking change would need a `version` tag.

## Resolved (kept briefly for context)

- `verify`'s verdict never consumed → edges are first-class; recipes gate `act` on `verify.verdict == 'pass'`.
- The brain passed the prompt as argv (128 KB limit) → stdin.
- A gate on an outside action let it run before approval → such steps are held before they run (2026-10-14).
- Triage's failed verify was a dead end → it now stages the item flagged for a human; the validator warns
  on any lone guarded edge (check 8).

- `act` file writes: leaked handle + unsafe under concurrency + path-traversal on filename → fixed (with-block,
  lock, basename).
- Dead `_MAX_ITERS` constant → removed.
- Forward-reference / failed-step reference silently treated as a literal → now raises loudly.
- Intake fetch failure crashed the CLI with a traceback → now a clean `intake: couldn't fetch …` message.
