# Provenance — nutrition / classify (food group)

Specialist/config: **`classify` @ scope `nutrition`** (new config of `classify`). Harvester:
`tools/harvest/usda_classify.py`. Key-gated: `USDA_API_KEY`.

- **Source** — USDA FoodData Central `/fdc/v1/foods/search` (Foundation + SR Legacy).
- **Real label** — the food's catalogued `foodCategory`. Task: given a food description, predict its
  food group.
- **Label space** — the 6 most-populated food groups from a diverse query set (Vegetables, Baked
  Products, Sweets, Dairy & Egg, Legumes, Finfish & Shellfish); 32 foods, balanced.
- **Date pulled** — 2026-07-21.
- **Eval** — `python tools/eval_scope.py classify nutrition` → **32/32 (100%)**. Trusted.
