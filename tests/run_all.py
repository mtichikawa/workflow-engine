"""Run the whole test suite. Works with or without pytest installed.

    python tests/run_all.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import test_concurrency  # noqa: E402
import test_control_flow  # noqa: E402
import test_core  # noqa: E402
import test_examples_smoke  # noqa: E402
import test_pipelining  # noqa: E402
import test_validator  # noqa: E402


def run_functions(mod) -> bool:
    ok = True
    print(f"\n{mod.__name__}")
    for name in sorted(n for n in dir(mod) if n.startswith("test_")):
        fn = getattr(mod, name)
        if not callable(fn):
            continue
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as e:  # noqa: BLE001
            print(f"  FAIL  {name}  {type(e).__name__}: {e}")
            ok = False
    return ok


def main():
    ok = run_functions(test_core)
    ok = run_functions(test_control_flow) and ok
    ok = run_functions(test_validator) and ok
    ok = run_functions(test_examples_smoke) and ok
    for mod, label in ((test_concurrency, "test_concurrency"), (test_pipelining, "test_pipelining")):
        print(f"\n{label}")
        try:
            mod.main()
            print(f"  PASS  {label} (timed)")
        except Exception as e:  # noqa: BLE001
            print(f"  FAIL  {label}  {e}")
            ok = False
    print("\n" + ("ALL TESTS PASS" if ok else "TEST FAILURES"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
