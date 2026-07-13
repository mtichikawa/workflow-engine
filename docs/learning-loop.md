# The learning loop

How a specialist gets better over time. **Both halves built** (2026-07-10). Front half:
capture real outputs, surface the ones worth a human, curate exemplars. Back half: a specialist
retrieves and injects its relevant exemplars (few-shot), and a provisional specialist earns trust
by eval — proven end-to-end (`examples/learning_loop_demo.py`).

```
   RUN (specialist on real inputs)
        │
        ▼
   SURFACE the ones worth a human  (disagreement · low-confidence · rare · a missed planted failure)
        │
        ▼
   CURATE  → approve / improve → exemplars in state/examples/<specialist>.jsonl
        │
        ├──► few-shot: inject the RELEVANT exemplars into the prompt   (designed)
        └──► eval: the exemplars are labeled test cases                (designed)
                        │
                        ▼
            PROMOTE provisional → trusted                          (designed)
```

## What's built — the trainer (`engine train <specialist>`)

A local review app (stdlib server, no deps; three-column layout — the standard, the input,
the output). It generates a batch, surfaces the contested items first, and you approve /
improve / skip. Kept exemplars land in `state/examples/<specialist>.jsonl`.

**Coverage-aware generation.** Don't sample inputs — *compose* them to span the space:
- **classify** — a multi-repo pool + hand seeds (spam, question, edge cases) so all
  categories appear, not just the 90%-bug default of one tracker.
- **rank** — the same pool scored for urgency + high-urgency **seeds** (RCE / outage /
  data-loss), because open-source trackers contain no real emergencies to anchor the top.
- **verify** — real subjects built by running the upstream chain, plus **planted failures**
  (wrong label / mis-route / irrelevant reply), because a checker must see failures to learn
  to catch them.

**Surfacing — spend the human on the hard calls.** A confidence-gated **devil's advocate**:
run once, then on the uncertain ones ask the model to *argue the other side* (or concede).
Genuine disagreement, low confidence, rare categories, and missed planted failures sort to
the top, tagged with why. Everything else is a clean near-duplicate to skim.

**Metering.** Every brain call is logged (`engine costs`) so the cost of a generation run is
measured, not guessed. See `cost-model.md`.

**Baselines built (proof):** classify (5 exemplars, 4 categories) · rank (5, full 0→1 spread) ·
verify (4, pass + caught failures). The three **shared judgment specialists** — the reusable
core in every recipe. `act`/`fetch` are mechanical (smoke tests, no examples); `route` /
`respond` / `write` are domain specialists, trained per recipe.

## The design decisions (the load-bearing ones)

1. **Few-shot, not fine-tuning.** We prompt the model with examples; we don't change weights.
   Cheaper, instant, and — crucially — it *keeps the specialist universal*: you swap the
   examples per task instead of baking one domain into the weights.

2. **Training is layered.** The **skill** generalizes (the role + base model — classify is
   config-driven, told its categories at call time, so it's not hardwired to any domain). The
   **examples** are task-specific and *don't* generalize. So: a **universal** layer (role +
   a shipped baseline) + a **customer** layer (their examples). Universal specialists are
   trained once and dropped in **untouched**; per-customer customization is **new domain
   modules + config**, never mutating a shared specialist's examples.

3. **Retrieval, not drawers.** Don't bucket examples into named categories with a router (the
   boxes proliferate and things don't fit). Keep one example memory; at call time retrieve the
   few **most similar** to the current call. Unique use case → nothing retrieved → runs on the
   general skill (fine). Partial fit → a relevant mix. The **floor is always the general
   skill**; examples are upside-only when relevant, harmlessly absent when not. *(Requirement:
   few-shot injection must ship together with similarity selection, or blanket-injecting all
   examples would overfit — the exact thing the layering avoids.)*

4. **Coverage is the real threat, not accuracy.** Curation keeps exemplars *correct* (you fix the
   wrong ones — there is no threshold, you correct everything, so nothing degrades down a
   chain). The danger is **narrow** inputs: 5 correct-but-identical easy bugs teach nothing.
   So compose inputs to span the range (categories / urgency bands / planted failures) — a
   training batch is *composed like a test suite's edge cases*, not sampled from the wild.

5. **The confidence threshold is a per-mode cost dial.** High in **training** (challenge
   almost everything — a bounded batch costs cents, coverage is everything); low in
   **production** (escalate only genuine doubt — cost compounds at volume). Same mechanism,
   two settings. This is the cascade / escalation pattern (also in microclaw: stronger model
   for hard calls / as a fallback).

6. **Onboarding a customer doesn't need fabrication.** Fabricating inputs is a *cold-start
   crutch* for when there's no data (our situation now — no customer). A real customer brings
   **real inputs**, and the **gated pipeline chains them for free**: step 1 runs on real data
   → the human corrects at the gate → that corrected output *is* step 2's real input. The
   **gate manufactures the examples** (gate-as-example-factory). You don't run a per-specialist
   gauntlet — most of the recipe is pre-trained universals; curation concentrates on the few
   bespoke domain specialists the eval flags. Greenfield (no data at all) → ship on the general
   skill under heavy gating, learn live.

7. **Two kinds of training: BASELINE and TAILORED.** *(Terminology: the second layer is
   "tailored," not "specialized" — "specialized" collides with "specialist," the agent itself.)*
   **Baseline training** = the universal floor, shared across every deployment. **Tailored
   training** = a customer's own examples layered on top (their voice / their edge cases).
   **Baseline is conditional; tailoring is always. — "baseline if reusable; tailor always."**
   A new specialist isn't rigidly "train baseline, then tailor." Two births:
   - A **truly generic** capability (e.g. `summarize`) gets a real **universal baseline** and
     joins the **shared shelf** — trained once, reused across every customer forever.
   - A **bespoke** capability (a customer's idiosyncratic internal rule) may **skip the
     universal baseline entirely** — it's *born tailored*, because there's no meaningful
     "universal" version. It ships on its general-skill floor + that customer's examples and
     lives in **their deployment**, not the shared shelf.

   Mechanically this is already the drafting path: a drafted specialist starts **provisional**,
   accrues a track-record, and is **promoted to a trusted library part _only if it proves
   reusable_**. A one-off customer specialist just stays provisional in that customer's
   deployment. **Consequence — the compounding curve:** the library accumulates, so each new
   customer needs *fewer new specialists* than the last (customer 12's use case assembles mostly
   from existing trusted parts). New-specialist work is **front-loaded and decays**; per-customer
   cost trends toward "just layer their examples on existing parts." That decay is the business
   case. *(Clean separation of many customers' examples/recipes = multi-tenancy, deliberately
   held — today is single-tenant.)*

## What the trainer taught us (honest findings)

- **Order-perturbation is a weak disagreement signal** — re-asking with shuffled options gets
  the same answer. The adversarial *argue-the-other-side* prompt is the real one.
- **Real issues are mostly unambiguous** — even aggressive challenging found ~zero genuine
  disagreements. The lever is insurance for ambiguous inputs, not a constant source of work.
- **Manufactured failures must be unambiguously wrong** — a mis-route planted on a *spam* item
  (where routing is moot) produced a false "miss." Same trap as a fake-ambiguous seed.

## The back half (built — Phase 17)

- **Few-shot injection + similarity retrieval** (`fewshot.py`) — a specialist retrieves the
  exemplars most *similar* to the current input (Jaccard token overlap, dependency-free) and
  injects the relevant few into its prompt; nothing similar → nothing injected → the general
  skill (§3). Wired into the drafted-specialist runner as the single generic injection point.
- **Promotion** (`registry.promote`) — a provisional specialist clears to trusted once its
  eval ≥ 0.8 on ≥ 4 examples.

**Proof — `examples/learning_loop_demo.py`.** A deliberately weak specialist whose real policy
is *orthogonal to severity* (escalate on a churn signal — competitor / cancel / refund — not
on anger). Cold, with no examples, it follows its severity prior and scores **4/8**; inject 6
curated exemplars and it learns the actual rule, scoring **8/8** — a **+50%** climb on an
*independent* eval set (no circularity), and it crosses the bar to **TRUSTED**. That is a
specialist measurably learning, from human corrections, a rule it could not have guessed.

## Scale + measure (Phase 19)

- **Few-shot wired into every judgment specialist** — CLASSIFY/RANK/VERIFY/ROUTE and
  WRITE/RESPOND now inject their relevant exemplars, with a **similarity floor** (`MIN_SIM`):
  nothing similar → nothing injected → the general skill. The hand-written evals still pass
  100%, confirming unrelated exemplars stay out.
- **Examples-as-eval** (`evals/examples_eval.py`, in `engine eval`) — **leave-one-out** over a
  specialist's exemplars (inject the others, test the held-out one; never eval on an injected
  example). Works from a handful and strengthens as exemplars accrue. Baseline: classify / rank /
  route / verify all **100%** (the exemplars are internally coherent).
- **Voice, jump-started.** 12 WRITE exemplars authored in the user's voice (via his portfolio
  Claude) were ingested; on a **fresh topic not among them**, WRITE produced a first-person,
  concrete, no-hype post in that same voice — the few-shot carrying the voice to unseen
  inputs. This is the retrieval-not-drawers design doing exactly its job for a subjective
  trait.

## Scaled exemplar sets — the honest eval (Phase 19 cont.)

Scaled the objective baselines from ~5 to 13–15 each (classify 13 across all 5 categories, rank
15 across the full 0→1 gradient, route 14 across all 7 components, verify 10 = 6 pass + 4 caught
failures). The leave-one-out numbers **dropped from a flat 100% — and that's the point:**

```
classify  12/13  92%      verify   9/10  90%
rank      15/15 100%      route    9/14  64%
```

At 5 easy, near-duplicate exemplars everything trivially self-agreed (100% told us nothing). At
13–15 exemplars spanning the *hard boundaries*, LOO actually **tests** the specialist — and route's
64% is the signal: its misses are all on genuinely contested calls (build-vs-core, ui-vs-core,
the fuzzy routing boundaries we already found), and a couple even flag *debatable curation on my
part* (a duplicate whose content is really a build issue). The eval doing its job. Curation also
caught and dropped 2 muddy classify exemplars whose label came from GitHub metadata, not content.

Takeaway: **a lower LOO on a bigger, harder exemplar set is more informative than a perfect one on a
trivial set.** Route's number says routing is inherently ambiguous — which argues for more exemplars
on its contested boundaries, not a different specialist.

## RESPOND's universal baseline — voice from real data, no impersonation

RESPOND's shipped floor (the "good technical reply" voice) is built from **real, public
maintainer replies**, not authored examples — `examples/harvest_respond_voice.py` pulls real
issue→first-reply pairs from 5 respected repos (got / datasette / fastapi / yargs / click) via
the GitHub API.

The design point (Mike's): **keep the words, drop the identity.** We strip @mentions and name
greetings and **blend across sources with a per-source cap**, so no single person's voice
dominates. What we capture is the *craft* of a good reply (engage the actual problem, hypothesize
a cause, ask for exactly what's missing, promise nothing) — a **composite, reusable style**, not
a person. That makes it a legitimate **universal baseline** (design #7: a generic reusable
capability gets a universal baseline), not impersonation — and explicitly *not* a shippable
"reply as <named dev>" feature. A future customer layers *their* brand voice on top of this.

Curated 11 exemplars (blend: yargs 4, simonw 3, pallets 2, sindresorhus 1, tiangolo 1). **Voice
transfer confirmed on a fresh issue** RESPOND had never seen: it engaged the surprising symptom
("hanging rather than erroring"), hypothesized a specific cause, and asked for exactly the
missing diagnostics — the maintainer craft, not the bland "have you tried restarting?" default.
Second voice proven to transfer (after WRITE), and the first built from a *found* corpus.

### The general technique — GitHub as a voice/expertise corpus for the tech domain

Worth naming as a reusable pattern, not a one-off: **public GitHub activity is a rich, free,
labeled corpus for both *voice* and *expertise* in the software domain.** Issue/PR replies,
review comments, commit messages, design discussions — each is a real expert response to a real
technical prompt, exactly the shape most tech specialists need. The RESPOND baseline is one
instance (reply craft); the same harvest-and-strip approach generalizes:
- **RESPOND / support voice** — maintainer issue replies (done).
- **REVIEW / code-review judgment** — PR review comments → what a good reviewer flags and how.
- **WRITE / technical explanation** — well-regarded READMEs, docs, design write-ups.
- **CLASSIFY / RANK / ROUTE baselines** — labeled real data (issue labels, triage decisions).

The invariant that keeps it legitimate (design boundary): **capture the words, not the person.**
Strip identity, blend across many sources with a per-source cap → a *composite craft*, never an
individual's voice, and never a shippable "act as <named dev>." Used this way, GitHub is a
standing baseline-training corpus for any tech-domain specialist. *(Reusable harvester:
`examples/harvest_respond_voice.py` — parameterize the repos + the reply-selection heuristic.)*

## Tailored layer on the scope seam — the loop closed end-to-end (Phase 21)

The final mechanism test (`examples/tailored_voice_demo.py`): a tenant's tailored RESPOND exemplars
(a deliberately formal "Acme Support" voice) layered on top of the maintainer **baseline**, via
the scope seam. Same specialist, same fresh issue, two scopes:
- **baseline** → terse-technical maintainer voice ("open devtools → Console/Network, paste any
  red errors");
- **`--scope acme_corp`** → "Dear Valued Customer… Warm regards, Acme Support Team."

Instrumented retrieval: the tenant layer took **6/6 few-shot slots** and shifted the voice.
**The learning loop is now proven end-to-end through the tenant seam** — baseline + tailored,
isolated by path, retrieved, injected, voice-shifted. The machinery is complete; what remains is
choosing and dressing the portfolio use cases, not building.

**Honest caveat (a known refinement, not required today):** it won because the tenant's support
tickets are more *topically* similar to the fresh issue than baseline's GitHub-maintainer
replies, so pure-similarity retrieval favored them. If a tailored set were same-domain and
differed only in *tone*, similarity alone might not favor it — the fix is to **weight the tailored
layer above baseline** (tenant exemplars fill the slots first, baseline backfills). Documented; wire
it if a real tailored set ever fails to surface.

## Coverage telemetry — baseline-fallback detection (Phase 22)

The tailored/baseline split resolves the tension found in Phase 21: retrieval picks the *nearest*
examples from either layer, so an input far from a tenant's (thin) tailored set falls back toward
**baseline** — in the customer's *wrong* voice/judgment. That fallback is now **detected and
recorded on every card** (`card.coverage`): when a tenant scope is active, we record the layer
split of the injected slots — `{tailored, baseline, total, ratio, flag}`.

It's **active learning**: a fallback is the single highest-value place to add a tailored exemplar (the
system tells you exactly where its customization is thin), *and* a quality warning (this output
wasn't in the customer's voice). Built **uniformly for every specialist** (capture more data, learn
the unexpected), and the **raw ratio is always stored** — the flag is a *tunable* threshold view,
not a baked-in number: `ratio == 0` → `no-coverage` (hard fallback), `< 0.5` → `thin-coverage`.
Surfaced in the board report as "prime spots to add a tailored example." Matters more for voice than
judgment, but captured for all so the data can tell us.

**Bug this surfaced (fixed):** `ThreadPoolExecutor` does **not** propagate `contextvars` to worker
threads — so few-shot inside a threaded specialist silently ignored `--scope`, i.e. the whole tenant
seam broke under `concurrency > 1`. Fixed by `copy_context()` at submit + running the worker via
`ctx.run`. (The Phase-21 test passed only because it ran in-thread.)

## The 3-layer model — role · baseline craft · tailored (the office-sorter)

Every specialist's knowledge sits in three layers, and *which* layers can even exist depends on
whether the specialist's OUTPUT is the config vocabulary or free-form.

1. **ROLE** — the config-agnostic floor. The system instruction: the universal skill, independent
   of any config knob. Always exists, always transfers.
2. **BASELINE exemplars (craft)** — curated exemplars that teach craft. Config-agnostic *only when
   the output is free-form*.
3. **TAILORED** — a per-tenant layer (a customer's exemplars, a specific voice) on the scope seam.

**The load-bearing distinction — can a config-agnostic baseline exemplar even exist?**

- **Output IS the config vocabulary** (CLASSIFY → one of the config's labels; ROUTE → one of the
  config's components). An exemplar's output is bound to *that* config's vocabulary, so exemplars
  are inherently **config-keyed** — they don't transfer to a different label/component set. The
  config-agnostic knowledge for these lives in the **ROLE only** ("assign to exactly one; never
  invent one outside the list"). There is no such thing as a config-agnostic CLASSIFY exemplar.
- **Output is free-form** (RESPOND → a reply; WRITE → a post). "What makes a good reply/post" is
  craft that transfers across configs, so a **config-agnostic baseline of craft exemplars** is real
  and useful. The specific config (this brand's tone) layers on top as TAILORED.

**The office-sorter analogy.** Picture a mailroom.
- A clerk who **sorts mail into bins** is CLASSIFY/ROUTE. "One item, one bin, don't invent a bin"
  is universal (the ROLE) — but example sortings don't transfer between offices, because Office A's
  bins (Legal / Finance / HR) aren't Office B's. The *bins are the config knob*; the exemplars are
  config-keyed.
- A clerk who **drafts replies** is RESPOND/WRITE. "Write a clear, courteous reply" transfers to any
  office (a config-agnostic craft baseline). *This* office's house style is a TAILORED layer on top.

**Status of the model in code:**
- ✅ **1A** — config-keyed retrieval: config-keyed specialists (classify/route) inject only
  same-config exemplars; free-form (`fewshot.FREE_FORM_OUTPUT` = respond/write) inject across configs.
- ✅ **1B** — WRITE's voice moved out of `baseline` into a tailored scope
  (`examples/relabel_write_voice.py`; scope `mike`). The baseline is now the role (the craft floor);
  the voice applies under `--scope`. *Remaining nicety:* curate genuine config-agnostic craft
  exemplars for WRITE's baseline (optional — the role carries craft for now).

*(Captured from the terminology/architecture discussion; the analogy is the intended teaching frame
— confirm it lands.)*

## Still ahead

- ✅ **Empirical few-shot policy (1C, shipped).** `engine fit` runs leave-one-out WITH vs WITHOUT
  few-shot per specialist and caches the verdict in the registry; `fewshot.block()` reads it, so a
  CHECKER (verify) turns few-shot off *from data*, not from the old per-name hardcode. Mapper-vs-
  checker emerges.
- **1A/1B — the config-agnostic exemplar model** (see *The 3-layer model* above).
- More exemplars on ROUTE's contested boundaries (build/core/ui) to firm up its LOO.
- The "weight tailored > baseline" retrieval lever, if a same-domain tailored set needs it.
- Feed coverage flags into the gate/trainer directly (auto-queue "add a tailored exemplar here").
