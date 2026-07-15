"""Smoke test: every example demo still runs end-to-end without code drift.

Import-only checks miss `main()`-body API drift — which is exactly how a cited demo silently
rotted once (a moved module path that only bit at call time). So we actually RUN each script as
a subprocess, with the brain forced to the `api` backend and NO credentials:

  - brain-free demos run to completion (exit 0);
  - brain-needing demos fail FAST and OFFLINE at their first real brain call, with the SDK's
    recognizable auth error — which still proves their `main()` body executed up to that point.

Either outcome is fine (and free — no brain calls, no network). Anything else — an ImportError,
NameError, AttributeError, or a TypeError from our own code — is real drift and fails the test.

    python tests/test_examples_smoke.py
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMOS = sorted((ROOT / "examples" / "scripts").glob("*.py"))

# The demo reached a genuine brain call and only lacks credentials/SDK — NOT code drift.
BRAIN_MARKERS = (
    "could not resolve authentication",
    "anthropic_api_key",
    "api_key",
    "no module named 'anthropic'",
    "requires pip install anthropic",
    "claude cli not found",
    "requires a brain",   # engine's own guidance when no brain is configured
)


def _run(script: Path):
    env = dict(os.environ)
    env["ENGINE_BRAIN"] = "api"           # force the API backend...
    env.pop("ANTHROPIC_API_KEY", None)    # ...with no credentials -> fails fast, offline, free
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    p = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=180,
    )
    return p.returncode, (p.stdout + p.stderr)


def test_examples_run_without_drift():
    assert DEMOS, "no example demos found under examples/scripts/"
    failures = []
    for script in DEMOS:
        code, out = _run(script)
        if code == 0:
            status = "ran to completion"
        elif any(m in out.lower() for m in BRAIN_MARKERS):
            status = "reached the brain (skipped: no creds)"
        else:
            last = out.strip().splitlines()[-1] if out.strip() else f"exit {code}"
            failures.append((script.name, last))
            status = f"DRIFT — {last}"
        print(f"    {script.name}: {status}")
    assert not failures, "example demos have code drift:\n" + "\n".join(
        f"  {name}: {err}" for name, err in failures
    )


if __name__ == "__main__":
    test_examples_run_without_drift()
    print("examples smoke: OK")
