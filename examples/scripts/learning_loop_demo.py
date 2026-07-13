"""The learning loop, end to end, on a WEAK drafted specialist — the proof that curated
golds measurably improve a specialist and earn it trust.

The specialist decides escalate|standard for a support message. The company's REAL policy is
deliberately ORTHOGONAL to severity: escalate iff the message signals churn (mentions a
competitor, or wants to cancel / refund) — regardless of how angry or severe it sounds. The
base instruction does NOT contain this rule, so the model follows its natural prior
(escalate on severity) and gets the decoupled cases wrong. Curated examples teach the rule.

    python examples/learning_loop_demo.py

Eval set is INDEPENDENT of the training golds (no circularity): different messages, same
policy. We score cold (no examples), inject the golds (few-shot), score warm, and promote.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import registry
from engine.core import get, register
from engine.drafting import DraftedSpecialist
from engine.examples import save_example, path as ex_path

NAME = "escalate_policy"
# deliberately generic — no hint of the real (churn-signal) rule
BASE_INSTRUCTION = (
    "You triage inbound support messages. Decide whether a message should be 'escalate' or "
    "'standard', and give a one-sentence reason. Use your best judgment.")

# INDEPENDENT eval set — ground truth per the real policy. Severity and the escalate signal
# are decoupled: severe-but-no-signal = standard; mild-but-signal = escalate.
EVAL = [
    ({"message": "URGENT: total outage, the entire app is down and nothing works!!!"}, "standard"),
    ({"message": "This is the worst software I've ever used, completely broken."}, "standard"),
    ({"message": "The app deleted three hours of my work, I'm livid."}, "standard"),
    ({"message": "Loving it so far! Quick question — how do I cancel one of my old seats?"}, "escalate"),
    ({"message": "Great tool overall; we're also trialing Acme Corp for comparison."}, "escalate"),
    ({"message": "All good here, just need a quick refund on a duplicate charge."}, "escalate"),
    ({"message": "Minor typo on your pricing page."}, "standard"),
    ({"message": "Cancelling today — fed up with the constant bugs."}, "escalate"),
]

# TRAINING golds — a human's curated corrections. Different messages, same decoupled policy.
GOLDS = [
    ({"message": "Absolutely furious — the app crashed and lost my data."},
     {"decision": "standard", "reasoning": "Severe and angry, but no churn signal (no competitor, cancel, or refund)."}),
    ({"message": "Hey, really happy with the product — how do I cancel a duplicate account?"},
     {"decision": "escalate", "reasoning": "Mentions cancelling — a churn signal — regardless of the positive tone."}),
    ({"message": "Just so you know, we're piloting a competitor alongside you."},
     {"decision": "escalate", "reasoning": "Explicitly evaluating a competitor — a churn signal."}),
    ({"message": "The whole dashboard is down and I'm losing money by the minute."},
     {"decision": "standard", "reasoning": "Severe outage but no churn signal, so standard per policy."}),
    ({"message": "No complaints really — can I get a refund for last month?"},
     {"decision": "escalate", "reasoning": "Refund request is a churn signal even without dissatisfaction."}),
    ({"message": "Tiny alignment glitch on the footer."},
     {"decision": "standard", "reasoning": "Minor and no churn signal."}),
]


def score() -> tuple[int, int, list]:
    ok, detail = 0, []
    for inp, expected in EVAL:
        out = get(NAME).run(inp, {})
        got = str(out.get("decision", "")).strip().lower()
        hit = got.startswith(expected)
        ok += hit
        detail.append((expected, got, hit, inp["message"][:52]))
    return ok, len(EVAL), detail


def show(label, ok, total, detail):
    print(f"\n{label}: {ok}/{total} = {ok / total:.0%}")
    for expected, got, hit, msg in detail:
        print(f"  {'✓' if hit else '✗'} want {expected:<8} got {got:<10} {msg}")


def main():
    # start clean so the demo is repeatable
    p = ex_path(NAME, "baseline")
    if p.exists():
        p.unlink()

    spec = DraftedSpecialist(NAME, "escalate support messages per company policy",
                             ["message"], ["decision", "reasoning"], BASE_INSTRUCTION)
    register(spec)
    registry.mark_provisional(NAME)
    print(f"drafted '{NAME}' (provisional, no examples). Base instruction hides the real rule.")

    cold_ok, total, cold_detail = score()
    show("COLD (no examples — follows its severity prior)", cold_ok, total, cold_detail)

    print(f"\ncurating {len(GOLDS)} golds (the human's corrections)…")
    for inp, out in GOLDS:
        save_example(NAME, inp, out)

    warm_ok, _, warm_detail = score()
    show("WARM (few-shot: the curated golds injected)", warm_ok, total, warm_detail)

    registry.record_eval(NAME, warm_ok / total, "accuracy")
    promoted = registry.promote(NAME, min_eval=0.8, min_examples=4)
    print(f"\nCLIMB: {cold_ok}/{total} → {warm_ok}/{total}   ({(warm_ok - cold_ok) / total:+.0%})")
    print(f"provisional before: True → after promote(): {'TRUSTED' if promoted else 'still provisional'}"
          f"  (bar: eval ≥ 0.8 on ≥ 4 examples)")


if __name__ == "__main__":
    main()
