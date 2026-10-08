# Provenance — history / sequence (chronological ordering)

Specialist/config: **`sequence` @ scope `history`** — a net-new *capability* (order a whole set), also
adds a *history* domain. Harvester: `tools/harvest/wikipedia_sequence.py`.

- **Source** — Wikipedia REST on-this-day feed (public, no auth): `/feed/onthisday/events/MM/DD`.
- **Real label** — the true chronological order, from each event's actual `year`. Each puzzle is ~6
  events presented in a neutral (alphabetical-by-text) order; the task is to order them earliest-first.
  The event TEXT omits the year, so it's genuine historical reasoning, not date-reading.
- **Count** — 24 puzzles (6 events each) drawn from 8 dates, years spanning antiquity → modern.
- **Date pulled** — 2026-07-21.
- **Eval** — leave-one-out with **normalized Kendall tau** vs the true year order (`_sequence_match`),
  pass at ≥ 0.75 (tau ≥ 0.5 — substantially more concordant than discordant). Partial-credit ordering.
  `python tools/eval_scope.py sequence history` → **23/24 (96%)** on 2026-07-21. Trusted — orders
  historical events chronologically almost perfectly from content alone.
