# Provenance — weather / classify (alert event type)

Specialist/config: **`classify` @ scope `weather`** (new config of `classify`, no key needed).
Harvester: `tools/harvest/weather_classify.py`.

- **Source** — National Weather Service API (public, no auth; requires a User-Agent).
  `/alerts/active?status=actual&message_type=alert`.
- **Real label** — the alert's official NWS `event` type. Task: given the alert's headline + description
  (the human-facing text, NOT the structured event field), predict the event type.
- **Label space** — the 6 most-common active event types at harvest time (Special Weather Statement,
  Flood Warning, Heat Advisory, Small Craft Advisory, Gale Warning, Air Quality Alert); 36 alerts, 6 each.
  (Active alerts vary by day/season — regenerating gives a different label set.)
- **Date pulled** — 2026-07-21.
- **Eval** — `python tools/eval_scope.py classify weather` → **35/36 (97%)**. Trusted. One miss (Heat
  Advisory vs Special Weather Statement, the catch-all category — plausible).
