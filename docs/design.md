# Why it's built this way

The decisions behind the engine, what each one buys, what it costs, and the evidence where there is
some. Numbers come from [blind-evals.md](blind-evals.md) unless marked otherwise. Written 2026-10-14.

## 1. Small specialists with contracts, not one agent with tools

A workflow is a graph of steps; each step is a **specialist** that does one kind of judgment (classify,
rank, verify, extract…) or one mechanical job (fetch, act), behind a typed input/output contract.

**Why.** A contract is something a program can check. Before anything runs, the validator follows every
wire to the step it names and checks the step exists, has run by then, produces that field, with a
compatible type and a value it can actually produce. That's how it refuses 92.8% of 615 deliberately
broken workflows with no false alarms on real ones. An agent that decides its own next tool call has
nothing to check until it has already acted. Contracts are also what lets the composer say "the library
can't do this part" instead of improvising.

**What it costs.** More structure to write, and it is not always more accurate. On the clinic-routing
test, the same model with all 291 corrections pasted into one long prompt scored 98.0% — level with the
engine's 97.3% (rulebook + 6 examples). The engine's prompt was about 40% the size (≈11k vs ≈28k
characters per message, measured) and its rules can be read and locked; the accuracy was the same.

## 2. A graph with branches, loops and joins, not a chain

Real work branches (medical → a nurse; everything else → a reply) and loops (draft → check → redraft
until it passes, capped). Edges carry conditions on earlier steps' outputs, so "what runs next" is data
the validator can check — a branch with no else-path, an AND-join that can never fire, a loop with no
exit — rather than control flow buried in code. A step can also run **for each** element of a list
(each line item in a note), so iterating inside one input doesn't need a bespoke specialist.

## 3. The model judges; code does rules, forms and fixed text

In the care-intake demo the model reads the scans, fills the record and drafts the reply. Billing rules,
the CMS-1500 layout, the clinical handoff template and the safety sentence are plain code. Anything
that must be exact, auditable or legally fixed shouldn't depend on a model's wording on a given day.

## 4. People approve; outside actions wait for them

A gate stops an item for a person. A step that acts outside the engine (writing a file for someone,
labelling an issue) must sit behind a full gate — the validator enforces it — and is held **before it
runs**: approving is what runs it, rejecting means it never happens. (Until 2026-10-14 a gate on the
acting step let it run first and asked afterwards; driving the workbench in a browser exposed it.)
A gate can instead review a sample, or only the items the model is unsure of; such a partial gate never
counts as approval for an outside action.

## 5. Learning from corrections, without fine-tuning

Every review teaches: an approved output is an example, an edit is a correction, an output marked wrong
with a reason is a counterexample. The engine retrieves the most similar examples into each call and,
once a step has 8+, writes itself a short **rulebook** of the conventions they imply, which a person can
read, diff against the previous version, and lock in their own words. One reviewed item in five is kept
aside to measure the step rather than teach it.

**Evidence.** On 150 blind clinic messages routed by an unwritten 15-rule protocol: 59.3% with no
corrections, 79.3% with the six most similar corrections, 97.3% with the rulebook (written rules: 100%;
all corrections in one long prompt: 98.0%). Fine-tuning would need far more data, a training run per
customer, and gives nothing a person can read or overrule.

## 6. Each tenant — and each saved workflow — learns in its own scope

Examples live in a directory per scope; a run reads the shared baseline plus its own scope and writes
only to its own. Isolation by path means one customer's corrections can't leak into another's by
accident. This is isolation, not security: one process can read every directory, so real separation
between customers means deploying them separately (see `engine/scope.py`).

## 7. The composer admits gaps

Asked for something the library can't do (send a text, read a photo, call a system nobody connected),
the composer should say so rather than plan a workflow that pretends. It is measured on blind requests
for exactly that, and every miss is listed on the site. It still fakes some (2–9 per ~38 impossible
requests across the blind sets) — the reason for the human gate and for the validator.

## 8. Few dependencies, one swappable brain

The core is Python's standard library. The model sits behind one port (`engine/core/brain.py`): the
Claude CLI by default, the Anthropic API for a deployment. A recording "tape" replays the model's
answers exactly, so demos and tests are repeatable and a recorded run can be checked against new code.

## What I'd change next

- **References aren't marked.** In a step's inputs, `payload.text` is a reference and `result.txt` a
  literal, decided by whether the first part names a step. The validator now catches near-miss typos,
  but an explicit syntax (`$step.field`) would remove the ambiguity.
- **One process, no login.** The workbench is for one machine or a private network.
- **The tests were written by Claude agents** and the engine runs on Claude, so they may share blind
  spots. No person has checked the labels.
- **No general image reader in the library.** Reading scans exists only in the care-intake demo.
