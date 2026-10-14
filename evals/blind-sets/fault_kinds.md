# Workflow-definition fault kinds

Model assumed: steps (id, specialist, input wiring, optional `gate`), edges (from, to, optional `when`,
optional loop bound), join mode (`all` | `any`) on multi-incoming steps, specialists with declared
input/output contracts (field names, types, optional enums), workflow payload schema.

"Upstream" below means: the source step is guaranteed to have completed before the consuming step/edge
runs (it dominates it in the forward graph, back-edges removed).

## A. Statically detectable (25)

| # | id | description | mechanical injection | verdict |
|---|----|-------------|----------------------|---------|
| 1 | duplicate_step_id | Two steps share an id, so edges/wiring are ambiguous | Copy a step and keep its id | BLOCK |
| 2 | dangling_edge | Edge `from` or `to` names a step that does not exist | Rename an edge endpoint to `ghost_step` | BLOCK |
| 3 | unknown_specialist | Step names a specialist not in the registry (or with no contract) | Change a step's specialist to `nonexistent_specialist` | BLOCK |
| 4 | entry_ambiguity | Zero or more than one entry step (no incoming forward edge) | Add a forward edge into the sole entry step, or add a second step with no incoming edges | BLOCK |
| 5 | unreachable_step | A step can never be reached from the entry | Delete every incoming edge of a non-entry step | BLOCK |
| 6 | no_path_to_terminal | From some reachable step no terminal step can be reached (trap / dead end that is not a declared terminal) | Redirect a step's only exit edge into a cycle with no exit, or remove a non-terminal step's out-edges | BLOCK |
| 7 | unconditional_loop | A back-edge (or self-edge) with no `when`, or a cycle in which every edge is unconditional: the loop can never exit | Delete the `when` from an existing back-edge, or add `step -> step` with no condition | BLOCK |
| 8 | unbounded_loop | Conditional back-edge with no max-iterations / retry cap, so termination depends entirely on runtime output | Remove the `max_iterations` from a loop edge | WARN |
| 9 | malformed_reference | Wiring string does not parse as `payload.field` or `stepid.field` (missing dot, empty part, bad prefix) | Change `draft.text` to `draft` or `draft..text` | BLOCK |
| 10 | wire_unknown_source | Wiring names a step id that does not exist | Change `draft.text` to `drafft.text` | BLOCK |
| 11 | wire_unknown_field | Wiring names a field not in the source specialist's output contract | Change `draft.text` to `draft.body` | BLOCK |
| 12 | wire_not_upstream | Input wired from a step that runs later, in parallel on another branch, or is the step itself — it cannot have produced output yet | Rewire an early step's input to a downstream step's output | BLOCK |
| 13 | wire_maybe_not_run | Input wired from a step that is only on some paths (behind a conditional edge or the losing side of a join-any), so on some runs the value is absent | Rewire a post-join input to a step on one conditional branch only | BLOCK (WARN if the input is declared optional / has a default) |
| 14 | missing_required_input | A required input of the step's specialist contract is not wired | Delete one required input's wiring | BLOCK |
| 15 | unknown_target_input | Step wires an input name the specialist's contract does not declare (typo or stale field; silently ignored) | Rename an input key, e.g. `topic` -> `topik` | WARN (BLOCK in strict mode) |
| 16 | payload_field_undeclared | `payload.x` where `x` is not in the workflow's declared payload schema | Change `payload.topic` to `payload.subject` | BLOCK if a payload schema exists, else WARN |
| 17 | type_mismatch | Source field type incompatible with target input type (list into string, object into number, enum value outside target enum) | Wire a `list[str]` output into a `str` input | BLOCK |
| 18 | condition_syntax_error | `when` expression does not parse or uses disallowed operators/functions | Change `check.verdict == 'pass'` to `check.verdict = 'pass'` | BLOCK |
| 19 | condition_unknown_ref | `when` references a nonexistent step or a field not in that step's output contract | Change `check.verdict` to `check.verdcit` | BLOCK |
| 20 | condition_not_upstream | `when` reads a step that is not guaranteed to have run when the edge is evaluated (downstream, parallel, or conditional-only) | Point the condition at a step after the edge's source | BLOCK |
| 21 | condition_unsatisfiable | Condition can never be true (literal outside the field's enum/type, e.g. `verdict == 'passed'` when enum is pass/fail; self-contradiction `x=='a' and x=='b'`) — a dead edge | Misspell the compared literal | BLOCK if it makes a step unreachable or is a typo against a known enum, else WARN |
| 22 | non_exhaustive_branch | A step's outgoing edges are all conditional and do not cover every possible value (no default/else), so the item can stall | Delete the `fail` branch of a pass/fail split | BLOCK when the enum is known and a gap is provable; WARN otherwise |
| 23 | overlapping_conditions | Two outgoing conditional edges can both be true for the same output where exclusive routing was intended (accidental fan-out) | Change `score < 5` / `score >= 5` to `score < 5` / `score >= 3` | WARN |
| 24 | join_deadlock | A join-`all` waits on an incoming edge that can never fire on the same run (mutually exclusive conditional branches, or a loop back-edge into the join), so it never completes; also: join with no mode or invalid mode | Make two branches exclusive (`==pass` / `==fail`) and merge them at a join-`all` | BLOCK |
| 25 | gate_bypass | A path exists from entry to a side-effecting / terminal-publish step that does not pass through a required human approval gate; or a gate is misconfigured (no approver, no decision output, nothing branches on its decision) | Add an edge that skips the gate, or delete the gate's `when decision == 'approve'` edge | BLOCK when the policy marks the step as gate-required; WARN otherwise |

Notes on boundaries between ids:
- 12 vs 13: 12 = the source *never* precedes the consumer; 13 = it precedes on *some* paths only.
- 7 vs 8: 7 = loop provably cannot exit; 8 = exit exists but nothing caps iterations.
- 19/20/21 mirror 10/12/17 for conditions rather than input wiring.
- A self-edge is a case of 7 (no condition) or 8 (condition, no cap).

## B. Not statically detectable (semantic)

These need runtime evidence, domain knowledge, or a human/LLM judgment of intent:

1. **Wrong specialist for the job** — contract-compatible but does the wrong thing (a summarizer where a fact-checker was needed).
2. **Swapped same-typed wiring** — `title` and `body` both `str`; wiring them crossed type-checks perfectly.
3. **Inverted or wrong-polarity condition** — `verdict == 'fail'` routes to publish; syntactically and type-wise valid.
4. **Wrong thresholds / constants** — `score >= 3` where intent was `>= 8`.
5. **Loop that never converges in practice** — has an exit condition and a cap, but the reviser never satisfies the checker, so it always burns the cap.
6. **Loop cap wrong size** — too low to ever succeed, too high to be affordable.
7. **Gate in the wrong place** — approval happens before the content it is meant to approve is final (later steps change it).
8. **Missing step the business requires** — e.g. no legal/compliance check; nothing in the graph says it should exist.
9. **Contract lies** — a specialist declares an output field it doesn't reliably produce, or produces values outside its declared enum; the static checker trusts the contract.
10. **Join-`any` race semantics** — which branch wins is runtime-dependent; whether the winner's output is the *right* one is intent.
11. **Side-effect ordering / idempotency** — a step that posts or charges sits inside a loop and fires once per iteration; only visible if side effects are declared, otherwise semantic.
12. **Prompt / instruction quality** inside a specialist's configuration.
13. **Data-quality assumptions** — payload fields present but empty, stale, or malformed in content.
14. **Cost / latency blow-up** — valid graph that is too slow or expensive at real volumes.
15. **Nondeterminism making conditions flaky** — LLM-judged verdicts that flip between runs.
16. **Redundant but harmless steps** — duplicate work that a checker cannot distinguish from intentional redundancy (e.g. two independent reviews).
