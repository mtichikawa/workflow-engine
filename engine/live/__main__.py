"""engine.live — the browser view of a case, and its recorded run.

    python -m engine.live serve [--port 8600]     # the page: compose, run, gate, read the packet
    python -m engine.live record                  # one full live run (compose + run + approve) -> the case's tape
    python -m engine.live check                   # replay the tape at full speed; fail on any miss or drift
    python -m engine.live keep <session>          # promote a session recorded from the page to the tape
    python -m engine.live export-run <run_id>     # save a recorded run's steps (timings, outputs) beside the tape
    python -m engine.live static [--out demo]     # the recorded run as static files: a public page, no server

Needs the optional extra: pip install -e '.[live]'
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from ..core import Board, Dispatcher, Tracer, tape, validate
from . import care_intake as CASE
from .server import TAPES, serve


def _run_case(label: str) -> tuple[dict, float, float, Board]:
    """Compose, run to the gate, approve, finish. Returns (decisions, compose seconds, run seconds, board)."""
    from ..composer import compose
    t0 = time.time()
    res = compose(CASE.REQUEST)
    t_compose = time.time() - t0
    run_id = f"care_intake-{label}-{int(time.time())}"
    board = Board(CASE.RECIPE.name, run_id)
    p = CASE.payload()
    board.add_item(p["id"], p)
    disp = Dispatcher(CASE.RECIPE, board, Tracer(run_id, echo=False), concurrency=6)
    t1 = time.time()
    disp.run()
    t_run = time.time() - t1
    gated = [c.step_id for c in board.with_status("gated")]
    if gated:
        disp.approve(p["id"], gated[0])
        disp.run()
    ctx = board.context[p["id"]]
    decisions = {
        "composed": [s["specialist"] for s in res["steps"]],
        "fields": {k: v["value"] for k, v in ctx["fields"]["fields"].items()},
        "missing": ctx["fields"]["missing"],
        "identity": ctx["identity"]["same"],
        "triage": ctx["triage"]["label"],
        "rules_failed": [c["check"] for c in ctx["coverage"]["checks"] if not c["met"]],
        "claim_holds": ctx["claim"]["holds"],
        "handoff": ctx["handoff"]["needed"],
        "reply_check": ctx["reply_check"]["verdict"],
        "reply_drafts": board.card(p["id"], "reply").visits,
        "staged": board.card(p["id"], "stage").status,
    }
    return decisions, t_compose, t_run, board


RUN = CASE.TAPE.with_name("tape-run.json")


def export_run(board: Board) -> Path:
    """The recorded run's steps — timing, status and output — for pages that replay it (the site's run page).
    Written beside the tape, so the replay and the page come from the same run."""
    item = next(iter(board.items))
    steps = [{"id": s.id, "specialist": s.specialist, "status": board.card(item, s.id).status,
              "seconds": board.card(item, s.id).seconds, "visits": board.card(item, s.id).visits,
              "output": board.context.get(item, {}).get(s.id)} for s in CASE.RECIPE.steps]
    RUN.write_text(json.dumps({"run_id": board.run_id, "steps": steps}, indent=1, default=str))
    return RUN


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m engine.live")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sv = sub.add_parser("serve")
    sv.add_argument("--port", type=int, default=8600)
    sv.add_argument("--host", default="0.0.0.0")
    sub.add_parser("record")
    sub.add_parser("check")
    kp = sub.add_parser("keep")
    kp.add_argument("session")
    ex = sub.add_parser("export-run")
    ex.add_argument("run_id")
    st = sub.add_parser("static")
    st.add_argument("--out", default="demo")
    a = ap.parse_args(argv)

    CASE.load()
    errors = [f for f in validate(CASE.RECIPE) if f.level == "error"]
    if errors:
        print("recipe invalid:", *errors, sep="\n  ")
        return 1

    if a.cmd == "serve":
        serve(CASE, port=a.port, host=a.host)
    elif a.cmd == "record":
        with tape.recording(CASE.TAPE) as t:
            decisions, tc, tr, board = _run_case("record")
        t.save()
        export_run(board)
        (CASE.TAPE.with_name("tape-decisions.json")).write_text(json.dumps(decisions, indent=1))
        print(f"recorded {len(t.entries)} model calls -> {CASE.TAPE}")
        print(f"compose {tc:.1f}s · run to the gate {tr:.1f}s")
        print(json.dumps(decisions, indent=1))
    elif a.cmd == "check":
        if not CASE.TAPE.exists():
            print("no tape — run `python -m engine.live record` first")
            return 1
        with tape.replaying(CASE.TAPE, pace=0) as t:
            decisions, tc, tr, _ = _run_case("check")
        served = [c["served"] for c in t.log]
        want = json.loads(CASE.TAPE.with_name("tape-decisions.json").read_text())
        drift = {k: (want.get(k), v) for k, v in decisions.items() if want.get(k) != v}
        print(f"replayed {len(served)} calls: " + ", ".join(f"{served.count(k)} {k}" for k in sorted(set(served))))
        print("decisions match the recording" if not drift else f"DRIFT: {json.dumps(drift, indent=1)}")
        return 0 if not drift and "miss" not in served else 1
    elif a.cmd == "keep":
        src = TAPES / f"{a.session}.json"
        shutil.copy(src, CASE.TAPE)
        print(f"{src} -> {CASE.TAPE}  (decisions file not updated — run `check` to see the replay's)")
    elif a.cmd == "export-run":
        print("wrote", export_run(Board.load(a.run_id)))
    elif a.cmd == "static":
        from .export import export
        out = export(CASE, Path(a.out))
        print(f"wrote {out}/index.html, recorded.json and docs/ — open index.html over http (any static host)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
