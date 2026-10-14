"""The workbench — one local page to make, keep, run, review and teach workflows.

    python -m engine.app [--port 8602]            # then open http://<host>:8602

  Workflows   describe a task → the composer drafts a workflow → edit it in a form → save (versioned)
  Run         on pasted text, a pasted list, CSV / JSONL, or a folder on this machine; or by webhook
              (POST /hook/<workflow>); or on a schedule (a folder re-read every N minutes, new files only)
  Review      every item waiting at a gate: mark each step right / edit it / mark it wrong with a reason,
              then approve or reject — every decision becomes an example or a counterexample
  Rulebooks   what the engine has worked out from corrections, every version, a diff, lock / unlock
  Quality     per-step error rates from review, and each specialist's score on its hold-out cases

Standard library only. No login: it is meant for one machine or a private network. A webhook can
require a token (the workflow's source `token`, sent as the X-Token header).
"""

from __future__ import annotations

import argparse
import json
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import fewshot, inputs, review, workflows
from .core import Board, Dispatcher, Tracer, all_specialists, get, validate

HERE = Path(__file__).parent
JOBS: dict[str, dict] = {}
_BOARD_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_LOCK = threading.Lock()


def _board_lock(run_id: str) -> threading.Lock:
    with _LOCKS_LOCK:
        return _BOARD_LOCKS.setdefault(run_id, threading.Lock())


def _job(fn, *args) -> str:
    jid = uuid.uuid4().hex[:10]
    JOBS[jid] = {"status": "running", "started": time.time()}

    def go():
        try:
            JOBS[jid].update(status="done", result=fn(*args))
        except Exception as e:  # noqa: BLE001 — the page shows the error
            JOBS[jid].update(status="error", error=str(e), trace=traceback.format_exc()[-1500:])
    threading.Thread(target=go, daemon=True).start()
    return jid


# ---- what the page reads ------------------------------------------------------------------------
def catalogue() -> list[dict]:
    out = []
    for name, sp in sorted(all_specialists().items()):
        out.append({"name": name, "kind": getattr(sp, "kind", ""), "does": getattr(sp, "description", ""),
                    "input": list(sp.contract.input), "output": list(sp.contract.output),
                    "side_effect": bool(getattr(sp, "side_effect", False))})
    return out


def compose_draft(request: str) -> dict:
    from .composer import compose
    res = compose(request)
    return {"recipe": workflows.to_dict(res["recipe"]) if res["recipe"] else None,
            "gaps": res["gaps"], "missing": res["missing"], "errors": res["errors"],
            "warnings": [f.msg for f in res["findings"] if f.level == "warning"], "runnable": res["runnable"]}


def check(recipe: dict) -> dict:
    try:
        r = workflows.from_dict("draft", recipe)
    except (KeyError, TypeError) as e:
        return {"errors": [f"malformed workflow: {e}"], "warnings": []}
    f = validate(r)
    return {"errors": [x.msg for x in f if x.level == "error"], "warnings": [x.msg for x in f if x.level == "warning"]}


def workflow_detail(name: str, version: int | None = None) -> dict:
    _, meta = workflows.load(name, version)
    return {**meta, "versions": workflows.versions(name), "runs": workflows.runs(name)[-20:][::-1]}


def run_workflow(name: str, body: dict) -> dict:
    _, meta = workflows.load(name)
    spec = {**meta["source"], **{k: v for k, v in body.items() if k in ("kind", "path", "split", "pattern")}}
    items = inputs.from_spec(spec, body.get("data"))
    if not items:
        raise ValueError("no items in that input")
    run_id = workflows.run(name, items)
    return {"run": run_id, "items": len(items)}


def run_summary(run_id: str) -> dict:
    board = Board.load(run_id)
    recipe = workflows.lookup(board.recipe)
    rows = []
    for item_id, item in board.items.items():
        cards = {c.step_id: c.status for c in board.cards_for(item_id)}
        rows.append({"item": item_id, "text": str(item["payload"].get("text", ""))[:300],
                     "steps": {s.id: {"status": cards.get(s.id),
                                      "output": board.context.get(item_id, {}).get(s.id)} for s in recipe.steps}})
    return {"run": run_id, "workflow": board.recipe, "steps": recipe.step_ids(), "items": rows,
            "snapshot": {k: len(v) for k, v in board.snapshot().items()}}


def review_queue() -> list[dict]:
    """Every item waiting at a gate, across all saved workflows' runs, oldest run first."""
    out = []
    for wf in workflows.all_workflows():
        for r in workflows.runs(wf["name"]):
            if not Path(f"state/{r['run']}.json").exists():
                continue
            board = Board.load(r["run"])
            if not board.with_status("gated"):
                continue
            recipe = workflows.lookup(board.recipe)
            for p in review.pending(board, recipe):
                out.append({"workflow": wf["name"], "run": r["run"], **p})
    return out


def decide(run_id: str, item_id: str, body: dict) -> dict:
    with _board_lock(run_id):
        board = Board.load(run_id)
        recipe = workflows.lookup(board.recipe)
        disp = Dispatcher(recipe, board, Tracer(run_id, echo=False))
        return review.decide(disp, recipe, item_id, approve=bool(body.get("approve")),
                             verdicts=body.get("verdicts") or {}, reason=body.get("reason", ""),
                             by=body.get("by", ""))


def rule_detail(sl: str) -> dict:
    h = fewshot.history(sl)
    return {"slot": sl, "history": h, "locked": fewshot.locked(sl), "diff": fewshot.diff(sl)}


def quality() -> dict:
    from .examples import load_holdout
    held = {s: len(load_holdout(s)) for s in all_specialists()}
    return {"steps": review.error_rates(), "holdout": {k: v for k, v in held.items() if v}}


# ---- schedules: a folder re-read every N minutes, new files only --------------------------------
def _scheduler(stop: threading.Event) -> None:
    last: dict[str, float] = {}
    while not stop.wait(30):
        for wf in workflows.all_workflows():
            src = wf["source"]
            every = float(src.get("every_min") or 0)
            if src.get("kind") != "folder" or every <= 0 or time.time() - last.get(wf["name"], 0) < every * 60:
                continue
            last[wf["name"]] = time.time()
            try:
                fresh = inputs.new_only(inputs.folder(src["path"], src.get("pattern", "*")),
                                        workflows.DIR / wf["name"] / "seen.json")
                if fresh:
                    workflows.run(wf["name"], fresh)
            except Exception as e:  # noqa: BLE001 — one bad schedule must not stop the others
                print(f"schedule {wf['name']}: {e}")


# ---- HTTP ---------------------------------------------------------------------------------------
def serve(port: int = 8602, host: str = "0.0.0.0") -> None:
    from . import specialists  # noqa: F401  (registers the library)
    from .drafting import load_drafted
    load_drafted()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code: int, body, ctype: str = "application/json") -> None:
            data = body.encode() if isinstance(body, str) else json.dumps(body, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _route(self, method: str) -> None:
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            parts = [p for p in u.path.split("/") if p]
            body = {}
            if method == "POST":
                n = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(n) if n else b""
                body = json.loads(raw or b"{}") if raw.strip() else {}
            try:
                self._send(200, self._handle(method, parts, q, body)) if parts and parts[0] in ("api", "hook") \
                    else self._send(200, (HERE / "app.html").read_text(), "text/html; charset=utf-8")
            except KeyError as e:
                self._send(404, {"error": str(e).strip("'\"")})
            except (ValueError, PermissionError) as e:
                self._send(400, {"error": str(e)})
            except Exception as e:  # noqa: BLE001
                self._send(500, {"error": str(e), "trace": traceback.format_exc()[-1500:]})

        def _handle(self, method, parts, q, body):
            p = parts[1:] if parts[0] == "api" else parts
            if parts[0] == "hook" and method == "POST" and len(p) == 2:          # POST /hook/<workflow>
                _, meta = workflows.load(p[1])
                token = meta["source"].get("token")
                if token and self.headers.get("X-Token") != token:
                    raise PermissionError("wrong or missing X-Token")
                rows = body if isinstance(body, list) else [body]
                items = [(str(r.get("id") or inputs._hid(r)), {**r, "text": r.get("text") or json.dumps(r)})
                         for r in rows if isinstance(r, dict)]
                return {"job": _job(workflows.run, p[1], items), "items": len(items)}
            if method == "GET":
                if p == ["specialists"]:
                    return catalogue()
                if p == ["workflows"]:
                    return workflows.all_workflows()
                if len(p) == 2 and p[0] == "workflows":
                    return workflow_detail(p[1], int(q["v"]) if q.get("v") else None)
                if len(p) == 3 and p[0] == "workflows" and p[2] == "diff":
                    return {"diff": workflows.diff(p[1], int(q["a"]), int(q["b"]))}
                if len(p) == 2 and p[0] == "jobs":
                    return JOBS[p[1]]
                if len(p) == 2 and p[0] == "runs":
                    return run_summary(p[1])
                if p == ["review"]:
                    return review_queue()
                if p == ["rules"]:
                    return fewshot.slots()
                if len(p) == 2 and p[0] == "rules":
                    return rule_detail(p[1])
                if p == ["quality"]:
                    return quality()
            if method == "POST":
                if p == ["compose"]:
                    return {"job": _job(compose_draft, body["request"])}
                if p == ["check"]:
                    return check(body["recipe"])
                if len(p) == 2 and p[0] == "workflows":
                    v = workflows.save(p[1], body["recipe"], request=body.get("request", ""),
                                       source=body.get("source"), note=body.get("note", ""), by=body.get("by", ""))
                    return {"version": v}
                if len(p) == 3 and p[0] == "workflows" and p[2] == "run":
                    return {"job": _job(run_workflow, p[1], body)}
                if len(p) == 3 and p[0] == "review":
                    return decide(p[1], p[2], body)
                if len(p) == 3 and p[0] == "rules" and p[2] == "lock":
                    fewshot.lock(p[1], rules_text=body.get("rules", ""), by=body.get("by", ""))
                    return rule_detail(p[1])
                if len(p) == 3 and p[0] == "rules" and p[2] == "unlock":
                    fewshot.unlock(p[1])
                    return rule_detail(p[1])
                if len(p) == 3 and p[0] == "quality" and p[1] == "holdout":
                    return {"job": _job(review.holdout_score, p[2])}
            raise KeyError(f"no such endpoint: {method} /{'/'.join(parts)}")

        def do_GET(self):
            self._route("GET")

        def do_POST(self):
            self._route("POST")

    stop = threading.Event()
    threading.Thread(target=_scheduler, args=(stop,), daemon=True).start()
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"workbench: http://localhost:{port}  (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m engine.app")
    ap.add_argument("--port", type=int, default=8602)
    ap.add_argument("--host", default="0.0.0.0")
    a = ap.parse_args()
    serve(a.port, a.host)


if __name__ == "__main__":
    main()
