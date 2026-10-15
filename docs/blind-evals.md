# Blind evaluations (2026-10-14)

Four measurements of the engine on test sets nobody tuned on. Every set is **synthetic** and was written
by an agent that saw neither the code under test nor any training examples, then labelled again by a
second blind agent; only items both labelled the same are scored. Each set was sealed (sha256 in
`evals/blind-sets/SEALED.json`) before its first score and scored once. Intervals are Wilson 95%.
Writers, labellers and the system under test are all Claude models — shared blind spots are possible,
and that is the main limit on these numbers.

    python evals/blind.py triage | routing | validator | composer      # raw results: evals/blind-results/

## 1. The medical line — 320 blind patient messages

A care team's app must send anything medical (symptoms, medication, mental-health warning signs, "is this
normal?") to a person and never answer it. 160 medical, 160 not; 45% written to be hard (a symptom
buried in a scheduling question, "lol my ankles are like balloons", "honestly don't see the point of
anything lately", non-medical messages full of medical words); 31 in Spanish. Labellers agreed on 320/320.

| system | medical messages caught | false alarms |
|---|---|---|
| **engine** (`classify` + the written policy in `engine/live/care_intake`) | **160/160 — 100% (97.7–100)** | **0/160 — 0% (0–2.3)** |
| same model, no written policy | 160/160 — 100% (97.7–100) | 27/160 — 16.9% (11.9–23.4) |
| keyword rule | 79/160 — 49.4% (41.7–57.1) | 9/160 — 5.6% (3.0–10.3) |

Hard cases: engine 72/72 caught, 0/72 false alarms. Spanish: 16/16 caught.

## 2. Learning from corrections — a routing protocol it can't know

A blind agent invented a doula organization's internal routing protocol (14 rules with precedence, e.g.
"a message from a partner goes to the care coordinator whatever it's about", "no-show fees go to
scheduling, not billing") and wrote 400 messages labelled by it; 396 kept after the second labeller.
Split once (seed 20261014): 150 test, 246 as the pool of past corrections. The model gets only the five
queue names and their one-line public descriptions; the corrections reach it through the engine's own
few-shot retrieval (the 6 most similar per message). No fine-tuning.

| corrections available | accuracy on 150 | on the 92 tricky ones |
|---|---|---|
| 0 | 74 — 49.3% (41.5–57.3) | 16 — 17.4% |
| 10 | 84 — 56.0% (48.0–63.7) | 26 — 28.3% |
| 25 | 99 — 66.0% (58.1–73.1) | 42 — 45.7% |
| 50 | 113 — 75.3% (67.9–81.5) | 56 — 60.9% |
| 100 | 118 — 78.7% (71.4–84.5) | 61 — 66.3% |
| 246 | **120 — 80.0% (72.9–85.6)** | **65 — 70.7%** |
| rules written out, no corrections (upper reference) | 150 — 100% (97.5–100) | 92 — 100% |

"Tricky" = the writer marked the message as one where guessing from the queue names gives the wrong
answer. The reference row shows the labels are consistent and the remaining gap is in learning from
examples (6 retrieved per message), not in the task.

### 2b. The same question after adding the rulebook — a new sealed set

The examples-only curve above flattens near 80%. The engine then gained a rulebook (`fewshot.rulebook`): from
8 corrections on, the brain reads all of a workflow's corrections once and writes the rules they imply,
and every call sees those rules plus the 6 most similar corrections. The system changed, so it was scored
on a NEW set: a blind agent's 15-rule routing protocol for a women's-health clinic (6 queues), 450
messages, 441 kept after the second labeller (224 tricky). Split once: 150 test, 291 corrections.

| corrections | examples only | rulebook + examples |
|---|---|---|
| 0 | 89 — 59.3% (51.3–66.9) | 89 — 59.3% |
| 10 | 104 — 69.3% | 107 — 71.3% |
| 25 | 108 — 72.0% | 108 — 72.0% |
| 50 | 111 — 74.0% | 124 — 82.7% (75.8–87.9) |
| 100 | 108 — 72.0% | 137 — 91.3% (85.7–94.9) |
| 291 | 119 — 79.3% (72.2–85.0) | **146 — 97.3% (93.3–99.0)** |
| rules written out, no corrections (upper reference) | 150 — 100% (97.5–100) | |

Errors fall from 61 to 4 of 150. Each rulebook the run wrote is saved in
`evals/blind-results/routing2-rulebooks/`; the one written from 291 corrections matches the clinic's real
protocol nearly rule for rule.

## 3. The validator — seeded faults from an independent list

A blind agent listed 25 kinds of fault a static checker could catch (`evals/blind-sets/fault_kinds.md`);
6 don't apply to this engine (reasons in `evals/faults.py`). Each remaining kind was injected at every
site it fits in the five real recipes (615 mutants).

| validator | mutants caught | kinds fully caught | false alarms on the 5 real recipes |
|---|---|---|---|
| before (9 checks) | 161/615 — 26.2% (22.9–29.8) | 4 of 18 | 0 |
| after (checks 10-16 + duplicate ids) | **571/615 — 92.9% (90.5–94.6)** | **17 of 18** | **0** |

The new checks were written after seeing this list, so the "after" row measures coverage of a known list,
not of unseen faults. The 44 misses are one kind: a wire like `.label` with nothing before the dot, which
is indistinguishable from a literal string value. The exercise also found two real bugs: the validator
crashed on an edge to an unknown step, and the dispatcher skipped any step joined by a pass edge and a
fail edge from the same source — so `triage`'s gated `act` step could never run.

## 4. The composer — 120 blind requests

A blind agent read only the specialist catalogue and wrote 120 requests: 72 the library can serve, 48
that need a capability it lacks (speech-to-text, OCR, payments, SMS, image generation…; half subtle).
Labellers agreed on 120/120. Drafting was off (the default).

| | result |
|---|---|
| possible: runnable plan, no gap claimed | 58/72 — 80.6% (70.0–88.1) |
| possible: flagged a gap anyway | 14/72 — 19.4% — mostly "for each item" iteration inside one work-item, which the engine really lacks |
| impossible: gap flagged instead of faked | **41/48 — 85.4% (72.8–92.8)** |
| impossible: faked (a runnable plan, no gap) | 7/48 — 14.6% — mostly `act` (which only stages a file) planned as if it could text, pay or fax |

### 4b. Composer changes, each measured on a fresh blind set (2026-10-14, later)

Set 1's misses (14 doable requests flagged as gaps, 7 impossible ones faked) were studied, so set 1 can't
measure the fixes. Each change was instead scored on a NEW set, written blind from the catalogue after the
change, double-labelled (only agreed items kept), sealed, and scored once on the code just before and just
after the change.

| set | the change | doable → runnable plan | impossible → faked |
|---|---|---|---|
| 2 (99) | for-each steps; whole-list judgments; `act`'s card says what it can't send | 51/61 → **61/61** | 17/38 → **9/38** |
| 3 (96) | an outside system with no MCP server named is a gap | 58/58 → 55/58 | 4/38 → **2/38** |
| 4 (95) | how items arrive is never a gap; the library reads text only | 54/57 → **56/57** | 4/38 → **0/38** |

The change on set 3 was a trade (3 doable requests newly flagged as gaps); set 4's change targeted those.
On set 4, which no version was tuned on, **this morning's composer faked 12/38 and planned 54/57; the final
composer faked 0/38 (95% CI 0–9.2%) and planned 56/57**. Raw: `evals/blind-results/composer{2,3,4}*.json`.

## 5. One long prompt instead of the engine's learning

Same split and 150 test messages as 2b. The same model, with **all 291 corrections pasted into each prompt**
(no rulebook, no retrieval): **147/150 — 98.0% (94.3–99.3)**, tricky ones 83/86. The engine's rulebook +
examples: 146/150 — 97.3%. **No accuracy difference.** The engine's prompt was ≈11.3k characters per message
against ≈28.3k (measured on 20 test messages), and its rules are readable and lockable; at a few hundred
corrections, those — not accuracy — are what the rulebook buys. (`python evals/blind.py bigprompt --set routing2`)

## 6. Reading insurance-card photos (generated, not blind)

30 SYNTHETIC cards in three layouts, photographed on a table (perspective, glare, JPEG; a third blurred and
steeper). Truth is known by construction, so no labeller. The care-intake demo's own steps
(`read_document` → `fill_form`): **282/282 printed fields exact (98.7–100), 18/18 absent fields left empty**.
Too easy to separate anything, so 15 cards were photographed badly on purpose (640×480, heavy blur, JPEG 30,
15–28°): 84/138 printed fields exact, and **27 of the 54 misses were confident wrong values** (a member ID
`KK…` read as `KR…`, an invented phone number) — worse than a blank, which a person would see.
(`python evals/extraction.py score [stress]`)

**The fix, measured on 20 fresh bad photos** (made after the change; same reader before vs after): the
reader now writes `[?]` for a character it can't make out, and the form-filler turns such a value into a gap
for a person instead of a guess.

| reader | printed fields right | **confidently wrong** | left empty for a person |
|---|---|---|---|
| before | 119/190 | **45/190 — 23.7% (18.2–30.2)** | 26/190 |
| marks what it can't read | 73/190 | **3/190 — 1.6% (0.5–4.5)** | 114/190 |

Two of the three remaining are accents (`Zoë` → `ZOÉ`, `Ramírez` → `Ramirez`). The cost is real: about 46
fields it used to read right now come back blank, for a person to key in. On the 30 normal photos the fix
changed nothing: 282/282 exact, 0 wrongly blanked. (`python evals/extraction.py score stress2`)

## 7. Does learning from examples help on ordinary tasks? (not blind)

Leave-one-out over the engine's own public example sets (19 sets with ≥ 8 examples, a fixed-seed sample of
15 per set, 285 in all), each scored with no examples, the 6 most similar examples, and examples plus a
rulebook: **89.1% (85.0–92.2) → 90.2% (86.2–93.1) → 90.9% (87.0–93.7)**. No clear gain: on public tasks the
model already does well. Examples **hurt summaries** (general 13 → 11 of 15, science 12 → 9), which is what the
per-specialist few-shot switch (`engine fit`) is for, and helped most where a convention isn't obvious
(legislation forecasts 9 → 11 with the rulebook, weather extraction 13 → 15). Learning earns its keep on
unwritten conventions (section 2b: 59% → 97%), not on tasks the model already knows.
(`python evals/fewshot_onoff.py`)
