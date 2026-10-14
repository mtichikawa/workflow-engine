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
