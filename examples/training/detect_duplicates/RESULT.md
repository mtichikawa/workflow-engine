# detect_duplicates — autonomous training on real data

The Composer flags `detect_duplicates` as a gap (no library specialist finds/groups duplicates). To train
it *honestly*, we need real ground truth — not the model grading itself. GitHub provides it: issues a
maintainer closed as "duplicate of #N" are real, human-labeled duplicate pairs.

**`real_github_pairs.json`** — 13 real duplicate pairs harvested from next.js, vscode, pytorch, node, go,
rust, each with the maintainer's actual closing note.

**Measured** (leave-one-out: does giving the specialist real exemplars improve it at picking the true
duplicate among candidates?):

| condition | accuracy |
|---|---|
| cold (zero-shot) | **12/13 = 92%** |
| warm (4 real exemplars) | 6/13 = 46% |

**Finding: keep `detect_duplicates` zero-shot.** It's already strong without training, and naive few-shot
*hurt* it — exactly the per-specialist "does few-shot help?" check the engine uses to turn few-shot ON only
where it measurably helps. The honest result was "no training needed here," not a fabricated 100%.
