"""Composer writes AND tests its own specialists — with an honest, non-circular benchmark.

The circularity trap: if the Composer writes a specialist, writes its own eval, and grades
itself, that proves nothing. So this module tests two ways that AREN'T self-grading:

1. STRUCTURAL self-test (objective, no ground truth): the written specialist obeys its contract,
   doesn't crash on diverse inputs, is CONSISTENT (same input at temp 0 -> same output), and is
   NON-DEGENERATE (different inputs -> different outputs; not a constant). Real software tests.

2. BENCHMARK against known-good originals (Mike's idea — the strong evidence): have the Composer
   re-derive a specialist we ALREADY have (classify/rank/route) from a neutral plain-English
   description, then score it against that specialist's REAL, human-labeled eval. Independent
   ground truth; the auto-written version competes against the hand-built one on the same test.

Trust still requires the human gate for a genuinely NEW specialist (self-generated domain truth
is circular). But structural correctness + the benchmark are real, verifiable evidence that the
Composer writes *working* specialists, not just plausible stubs.
"""

from __future__ import annotations

from collections import Counter

from .core import brain
from .drafting import DraftedSpecialist


def auto_write(name: str, description: str, input_fields: list[str], output_fields: list[str],
               kind: str = "domain", fix: str = "") -> DraftedSpecialist:
    """The Composer writes a specialist from a plain-English DESCRIPTION of the task (not from the
    original's code). `fix` carries a repair note from a failed structural test. Returns an
    in-memory DraftedSpecialist (not persisted)."""
    instruction = brain(
        f'Write a concise system instruction (a role) for an AI specialist named "{name}".\n'
        f'Task: {description}\n'
        f'It receives input fields {input_fields} and must return output fields {output_fields}.\n'
        "In 2-4 sentences, say exactly what it does and how to judge a good result. "
        + (f"\nA PRIOR version failed a structural test — fix it: {fix}\n" if fix else "")
        + "Return only the instruction text."
    ).strip()
    return DraftedSpecialist(name, description, input_fields, output_fields, instruction, kind=kind)


def write_and_test(name: str, description: str, input_fields: list[str], output_fields: list[str],
                   sample_inputs: list[dict], max_repairs: int = 2) -> tuple[DraftedSpecialist, dict]:
    """Write a specialist, run the structural self-test, and SELF-REPAIR the instruction if it
    fails (crashes / degenerate output), bounded by max_repairs. Returns (spec, report). Domain
    trust still requires the human gate — this proves it's structurally sound and runs, not that
    its domain judgments are correct."""
    fix, attempts = "", []
    spec = auto_write(name, description, input_fields, output_fields, fix=fix)
    for i in range(max_repairs + 1):
        report = structural_test(spec, sample_inputs)
        attempts.append({"attempt": i + 1, **{k: report[k] for k in ("crashes", "non_degenerate", "structural_pass")}})
        if report["structural_pass"]:
            break
        fix = (f"{report['crashes']} of {report['of']} inputs crashed or violated the output "
               f"contract; non_empty={report['non_empty']}, non_degenerate={report['non_degenerate']}. "
               f"Be explicit about the exact output keys, that every key must be filled (never null/empty), "
               f"and that outputs must vary with the input.")
        spec = auto_write(name, description, input_fields, output_fields, fix=fix)
    report["attempts"] = attempts
    report["repaired"] = len(attempts) > 1
    return spec, report


# ---- structural self-test (objective) ---------------------------------------
def _nonempty(out: dict) -> bool:
    """A draft that returns a required key as None/empty passes the contract (fields are `object`)
    but isn't actually producing output — catch that (3A)."""
    return bool(out) and all(v not in (None, "", [], {}) for v in out.values())


def _consistency(outputs: list) -> float:
    """Agreement rate over repeated runs of the SAME input — the fraction equal to the modal output.
    On the CLI brain (no temp/seed) this is a MEASURED rate, not True/False; 1.0 = deterministic."""
    if not outputs:
        return 0.0
    counts = Counter(str(o) for o in outputs)
    return counts.most_common(1)[0][1] / len(outputs)


def _degenerate(outputs: list) -> bool:
    """Different inputs -> identical outputs means the spec ignores its input (a constant)."""
    ok = [o for o in outputs if o is not None]
    return len(ok) > 1 and len({str(o) for o in ok}) <= 1


def structural_test(spec: DraftedSpecialist, sample_inputs: list[dict], samples: int = 3) -> dict:
    """Contract compliance + no-crash + NON-EMPTY outputs + non-degeneracy, plus a measured
    consistency rate. No ground truth needed. Pass/fail gates on what the draft controls (crashes,
    empty, degenerate); consistency is reported but NOT gated — the CLI brain's non-determinism isn't
    the draft's fault (see 5A/2B'). Domain correctness still needs the human gate."""
    outputs, crashes = [], 0
    for inp in sample_inputs:
        try:
            out = spec.run(inp, {})
            spec.contract.validate_output(out)          # raises if a required field is missing/mistyped
            outputs.append(out)
        except Exception:  # noqa: BLE001
            crashes += 1
            outputs.append(None)
    ok = [o for o in outputs if o is not None]
    non_empty = all(_nonempty(o) for o in ok) if ok else False
    non_degenerate = (not _degenerate(outputs)) if len(ok) > 1 else None
    # consistency: repeat the first input `samples` times and measure agreement (honest, not temp-0)
    consistency = None
    if sample_inputs and ok:
        reps = []
        for _ in range(max(1, samples)):
            try:
                reps.append(spec.run(sample_inputs[0], {}))
            except Exception:  # noqa: BLE001
                reps.append(None)
        consistency = round(_consistency(reps), 2)
    return {"ran": len(ok), "of": len(sample_inputs), "crashes": crashes,
            "non_empty": non_empty, "non_degenerate": non_degenerate, "consistency": consistency,
            "structural_pass": crashes == 0 and non_empty and non_degenerate is not False}


# ---- the benchmark: re-derive known-good specialists ------------------------
# Neutral descriptions — what a USER would say, NOT the originals' instructions.
BENCH = {
    "classify": {
        "description": "Assign the given item to exactly one category from the provided list, "
                       "using the given criteria. Never invent a category outside the list.",
        "input": ["item", "categories", "criteria"],
        "output": ["label", "confidence", "reasoning"],
    },
    "rank": {
        "description": "Score the given item from 0.0 to 1.0 on the provided scoring dimension, "
                       "calibrated (reserve the extremes for clear cases).",
        "input": ["item", "scoring"],
        "output": ["score", "reasoning"],
    },
    "route": {
        "description": "Send the given item to exactly one component from the provided list — the "
                       "team that would own the fix — and decide whether to escalate.",
        "input": ["item", "components"],
        "output": ["component", "escalate", "reasoning"],
    },
}


def benchmark(target: str) -> dict:
    """Re-derive `target` from its neutral description and score it against the REAL eval."""
    from evals import suite
    meta = BENCH[target]
    spec = auto_write(f"{target}_bench", meta["description"], meta["input"], meta["output"])

    if target == "classify":
        cats = suite._CATS
        cases = [({"item": i["item"], "categories": cats, "criteria": "the kind of issue"}, e)
                 for i, e in suite._CLASSIFY]
        passed = sum(1 for inp, exp in cases
                     if str(spec.run(inp, {}).get("label", "")).strip() == exp)
        total = len(cases)
    elif target == "route":
        comps = suite._COMPONENTS
        cases = [({"item": i["item"], "components": comps}, e) for i, e in suite._ROUTE]
        passed = sum(1 for inp, exp in cases
                     if str(spec.run(inp, {}).get("component", "")).strip() == exp)
        total = len(cases)
    elif target == "rank":  # pairwise: the more-urgent item must score >= the less-urgent
        cfg = {"scoring": suite._RANK_SCORING}
        passed = total = 0
        for hi, lo in suite._RANK_PAIRS:
            sh = _num(spec.run({"item": hi, **cfg}, {}).get("score"))
            sl = _num(spec.run({"item": lo, **cfg}, {}).get("score"))
            passed += int(sh >= sl)
            total += 1
    else:
        raise ValueError(target)

    sample = [c[0] for c in (cases if target != "rank" else [])][:4] or \
             [{"item": hi, "scoring": suite._RANK_SCORING} for hi, _ in suite._RANK_PAIRS]
    struct = structural_test(spec, sample)
    return {"target": target, "score": f"{passed}/{total}", "pct": passed / total if total else 0,
            "structural": struct, "instruction": spec._instruction[:200]}


def run_benchmark() -> list[dict]:
    """Re-derive every known-good specialist and score against its real eval. Reproducible
    evidence: `engine benchmark`."""
    return [benchmark(t) for t in ("classify", "rank", "route")]


def _num(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d
