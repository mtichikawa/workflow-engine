# Data notice — where the gold examples come from, and their licenses

The engine's few-shot + evaluation examples ("golds") live in `state/examples/<scope>/<specialist>.jsonl`.
Most are harvested from public sources so each label is ground truth someone else recorded (see
`docs/provenance/` for the exact endpoints, counts and scores). Third-party data stays under its own
license — listed here — not under the code's terms.

| Scope · files | Source | License / terms | Credit |
|---|---|---|---|
| `art` · classify | The Metropolitan Museum of Art — Open Access API (catalog fields) | CC0 | optional: The Met Collection API |
| `baseline` · classify, rank, route | written for this repo (synthetic) | — | — |
| `baseline` · verify | public GitHub issue titles + engine-drafted replies | short titles; drafts are engine output | — |
| `acme_corp` · respond | written for this repo (synthetic tenant demo) | — | — |
| `communities` · classify, match | Stack Exchange network — question titles only | **CC BY-SA 4.0** (posts before 2018-05-02: CC BY-SA 3.0) | "Question titles from the Stack Exchange network" |
| `cooking` · classify | TheMealDB — dish name, ingredients, cuisine | TheMealDB terms of use | "Recipe data from TheMealDB (themealdb.com)" |
| `economics` · classify | FRED — economic series titles (no data values) | FRED API terms | "This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis." |
| `general` · match | Wikipedia — redirect / alias name pairs | facts | — |
| `general` · summarize | Wikipedia — article lead text | **CC BY-SA 4.0** | "Text from English Wikipedia; see each article's history for authors" |
| `government` · classify | Federal Register — document titles + abstracts | U.S. government work, public domain (17 U.S.C. §105) | — |
| `history` · extract, sequence | Wikipedia — "On this day" event text | **CC BY-SA 4.0** | "Text from English Wikipedia; see each article's history for authors" |
| `legislation` · classify, forecast | Congress.gov — bill titles, CRS policy area, outcome | U.S. government work, public domain | — |
| `nutrition` · classify | USDA FoodData Central — food descriptions | CC0 | optional: USDA FoodData Central |
| `science` · classify, summarize | arXiv API — titles, abstracts, categories | arXiv metadata: CC0 | optional: arXiv.org |
| `sports` · forecast | football-data.co.uk — teams, date, full-time result | match results (facts) | football-data.co.uk |
| `weather` · classify, extract, verify | U.S. National Weather Service — alert text | U.S. government work, public domain | NOAA / National Weather Service (text unaltered; not an official alert) |

**Share-alike.** The files drawn from Wikipedia and Stack Exchange (`communities/classify.jsonl`,
`communities/match.jsonl`, `general/summarize.jsonl`, `history/extract.jsonl`, `history/sequence.jsonl`)
are adaptations of CC BY-SA content and are released under **CC BY-SA 4.0**
(https://creativecommons.org/licenses/by-sa/4.0/) — reuse them under that license, with the credit above.

**Not in this repo.** Some golds the engine was developed with can't be redistributed — verbatim GitHub
issues and maintainer replies, App Store reviews, full Stack Exchange question bodies, and TheMealDB recipe
instructions. They live in a separate private corpus (`private/examples/`, loaded automatically if
present). A clone of this repo runs on the public golds only, so the evaluation numbers that depended on
private golds are marked as such in `docs/provenance/`. An earlier film domain sourced from TMDB was
deleted outright: TMDB's API terms prohibit using its content with an AI application.
