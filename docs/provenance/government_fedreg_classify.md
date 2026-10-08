# Provenance — government / classify (issuing agency)

Specialist/config: **`classify` @ scope `government`** (new *config* of `classify`, no new specialist).
Harvester: `tools/harvest/fedreg_classify.py`.

- **Source** — Federal Register API (public, no auth). `documents.json?conditions[agencies][]=<slug>`.
- **Real label** — the federal agency that officially issued the document (Office of the Federal
  Register record). Task: given title + abstract, predict the issuing agency. Ground truth is the
  government's own record, not authored by me.
- **Label space** — 6 agencies: EPA, IRS, FDA, FCC, SEC, FAA. Only documents issued by exactly one of
  these are kept (co-issued docs skipped to keep labels unambiguous).
- **Count** — 32 golds (6 each except SEC=2; most SEC docs were co-issued and filtered out).
- **Date pulled** — 2026-07-21.
- **License / redistribution** — U.S. government public-record metadata (not copyrighted). Title +
  abstract + agency. Regenerable: rerun the harvester.
- **Eval (leave-one-out, isolated)** — `python tools/eval_scope.py classify government` → **32/32
  (100%)** on 2026-07-21. Above the trusted bar. No code change — a new config on real labels.
