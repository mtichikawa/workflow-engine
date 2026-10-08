"""Report the generality standing of every specialist — how many unrelated domains each is validated on.

The standard (docs/standards.md): every JUDGMENT capability must be validated leave-one-out on >= 3
unrelated domains. Adapters and tailored specialists are held to their own bars, not this one.

Counts the PUBLIC corpus (state/examples/) only — the claim anyone can check from a clone. Golds in
private/examples/ still feed few-shot + eval locally but don't count toward the bar.

    python tools/check_generality.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "state" / "examples"

# buckets (docs/standards.md)
JUDGMENT = ["classify", "rank", "verify", "forecast", "extract", "summarize", "sequence", "match"]
ADAPTERS = ["fetch", "act", "mcp_call"]
TAILORED = ["write", "respond", "review", "route"]
# scopes that are NOT domains for this purpose (tenant demos / transient test scopes)
NON_DOMAIN = {"mike", "acme_corp", "t1", "t2"}
BAR = 3


def domains_for(spec: str) -> list[str]:
    if not EX.exists():
        return []
    return sorted(
        s.name for s in EX.iterdir()
        if s.is_dir() and s.name not in NON_DOMAIN and (s / f"{spec}.jsonl").exists()
    )


def main():
    print(f"\n  Generality standing — judgment capabilities need >= {BAR} unrelated domains\n")
    print(f"  {'capability':<12}{'domains':<8}  standing")
    print("  " + "-" * 62)
    below = []
    for spec in JUDGMENT:
        d = domains_for(spec)
        ok = "OK" if len(d) >= BAR else f"BELOW (need {BAR - len(d)} more)"
        if len(d) < BAR:
            below.append(spec)
        print(f"  {spec:<12}{len(d):<8}  {ok:<18} {', '.join(d)}")
    print()
    for label, group in (("adapters (connector bar)", ADAPTERS), ("tailored (own bar)", TAILORED)):
        print(f"  {label}:")
        for spec in group:
            d = domains_for(spec)
            print(f"    {spec:<12}{len(d):<8}  {', '.join(d) or '(no gold scopes)'}")
    print()
    if below:
        print(f"  judgment capabilities below the bar: {', '.join(below)}")
    else:
        print("  all judgment capabilities meet the >= 3 domain bar.")


if __name__ == "__main__":
    sys.exit(main())
