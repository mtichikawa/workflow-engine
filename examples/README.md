# examples/ — runnable demos & proofs

Illustrations of the product, run directly (`python examples/<file>.py`). **These contain
synthetic / illustrative data** (fake tenants, hand-authored golds, dummy specialists) kept
here deliberately, *out of the `engine/` product package.* Not part of the shipped library and
not run by the test suite.

| file | what it shows |
|---|---|
| `hello_world.py` | the smallest end-to-end run — a recipe over the board |
| `proof_shared.py` | the reuse proof — two recipes share one set of specialist instances |
| `complex_demo.py` | a non-linear graph: fan-out → AND-join → refine↔verify loop → gated publish |
| `learning_loop_demo.py` | the learning loop — a weak specialist climbs 4/8 → 8/8 → promoted (synthetic policy) |
| `tailored_voice_demo.py` | a tenant's tailored voice layered on the baseline via the scope seam (synthetic "Acme" voice) |

For the automated test suite see `tests/`; for utility scripts (e.g. building baseline data)
see `tools/`.
