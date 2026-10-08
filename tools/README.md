# tools/ — utility scripts

Standalone scripts that *build real product data* or automate a one-off task. Not part of the
shipped `engine/` package, not demos, not tests.

| file | what it does |
|---|---|
| `harvest/` | one harvester per public source (Met, arXiv, Congress, Federal Register, FRED, USDA, NWS, Wikipedia, Stack Exchange titles, TheMealDB, football results) → real-label golds in `state/examples/<scope>/`. Each has a manifest in `docs/provenance/`; licenses in `DATA-NOTICE.md`. NWS asks for a contact in the User-Agent: set `NWS_CONTACT`. |
| `eval_scope.py` | leave-one-out score for one scope's golds in isolation — `python tools/eval_scope.py classify art` |
| `check_generality.py` | how many unrelated public domains each judgment capability is validated on (the ≥ 3 bar, `docs/standards.md`) |
| `build_explorer.py` | regenerates a use-case explorer (`usecases/<slug>/index.html`) from its recipe + a real run log — no hand-editing. This repo is the live site, so committing + pushing the result is the deploy. |
