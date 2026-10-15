"""The live view — compose, run, gate and read a case in the browser.

    python -m engine.live serve [--port 8600]            # then open http://<host>:8600

One page, polling a small JSON API. Everything on it is the real engine: the composer composes, the
dispatcher runs the recipe on a board, the gate waits for a person, and the staged packet is read back
from the board. A run is either LIVE (the model answers now; the calls are recorded) or REPLAY (the same
engine, but the model's answers come from a recorded tape — see engine/core/tape.py). The page always
says which.

Standard library only, like `engine train`'s review UI.
"""

from __future__ import annotations

import json
import mimetypes
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ..core import Board, Dispatcher, Tracer, all_specialists, get, tape, validate
from ..explorer import build_graph

HERE = Path(__file__).parent
TAPES = Path("state/live/tapes")           # every live session records here; `keep` promotes one


class Session:
    """One compose + run, in one mode, recorded to (or replayed from) one tape."""

    def __init__(self, case, mode: str):
        self.case, self.mode, self.id = case, mode, uuid.uuid4().hex[:8]
        self.tape_path = case.TAPE if mode == "replay" else TAPES / f"{self.id}.json"
        self.tapes: list = []
        self.compose: dict = {"status": "idle"}
        self.run_id: str | None = None
        self.board: Board | None = None
        self.disp: Dispatcher | None = None
        self.t0 = self.t_gate = self.t_end = None
        self.error: str | None = None
        self.lock = threading.Lock()

    def _tape(self):
        if self.mode == "replay":
            return tape.replaying(self.tape_path)
        return tape.recording(self.tape_path)

    def _keep(self, t) -> None:
        self.tapes.append(t)
        if self.mode == "live":                             # one tape per session: compose + run calls
            with self.lock:
                prior = json.loads(self.tape_path.read_text())["calls"] if self.tape_path.exists() else []
                t.entries = prior + t.entries
                t.save()

    # ---- compose ---------------------------------------------------------
    def start_compose(self) -> None:
        self.compose = {"status": "running", "started": time.time()}
        threading.Thread(target=self._compose, daemon=True).start()

    def _compose(self) -> None:
        from ..composer import compose
        from ..specialists import CAPABILITIES
        try:
            with self._tape() as t:
                res = compose(self.case.REQUEST)
            self._keep(t)
            steps = []
            for s in res["steps"]:
                name = s["specialist"]
                tag = ("new" if name in res["missing"] else "reuse" if name in CAPABILITIES else "domain")
                steps.append({"id": s["id"], "specialist": name, "tag": tag, "gate": bool(s.get("gate"))})
            self.compose = {"status": "done", "seconds": round(time.time() - self.compose["started"], 1),
                            "steps": steps, "gaps": res["gaps"], "edges": res["edges"],
                            "findings": [str(f) for f in res["findings"]], "runnable": res["runnable"],
                            "served": [c["served"] for c in t.log]}
        except Exception as e:  # noqa: BLE001 — shown on the page, never a silent hang
            self.compose = {"status": "failed", "error": str(e)}

    # ---- run -------------------------------------------------------------
    def start_run(self) -> None:
        self.run_id = f"care_intake-{self.mode}-{self.id}"
        self.board = Board(self.case.RECIPE.name, self.run_id)
        p = self.case.payload()
        self.board.add_item(p["id"], p)
        self.disp = Dispatcher(self.case.RECIPE, self.board, Tracer(self.run_id, echo=False), concurrency=6)
        self.t0, self.t_gate, self.t_end, self.error = time.time(), None, None, None
        self.board.save()
        threading.Thread(target=self._drive, args=(lambda: self.disp.run(),), daemon=True).start()

    def _drive(self, fn) -> None:
        """Run a dispatcher action on a worker thread, under this session's tape."""
        try:
            with self._tape() as t:
                fn()
            self._keep(t)
        except Exception as e:  # noqa: BLE001
            self.error = str(e)
        if self.board.with_status("gated"):
            self.t_gate = self.t_gate or time.time()
        else:
            self.t_end = time.time()

    def decide(self, approve: bool, reason: str = "") -> None:
        item = next(iter(self.board.items))
        gate = next(c.step_id for c in self.board.with_status("gated"))
        def go():
            (self.disp.approve(item, gate) if approve else self.disp.reject(item, gate, reason))
            self.disp.run()
        threading.Thread(target=self._drive, args=(go,), daemon=True).start()

    def state(self) -> dict:
        if not self.run_id:
            return {"status": "idle"}
        data = json.loads((Path("state") / f"{self.run_id}.json").read_text())
        cards = {c["step_id"]: c for c in data["cards"]}
        ctx = next(iter(data["context"].values()), {})
        statuses = {c["status"] for c in cards.values()}
        status = ("failed" if self.error else "gated" if "gated" in statuses
                  else "running" if not self.t_end            # includes the instant before intake makes cards
                  else "rejected" if "rejected" in statuses else "done")
        now = time.time()
        served = [c["served"] for t in self.tapes for c in t.log]
        return {
            "status": status, "error": self.error, "mode": self.mode, "run_id": self.run_id,
            "elapsed": round((self.t_gate or self.t_end or now) - self.t0, 1),
            "cards": {sid: {"status": c["status"], "seconds": c.get("seconds"), "visits": c["visits"],
                            "started": c.get("started"), "input": c["input"], "output": c["output"],
                            "attempts": c["attempts"],
                            "running_for": round(now - c["started"], 1) if c["status"] == "running" and c.get("started") else None}
                      for sid, c in cards.items()},
            "events": data["events"],
            "packet": (ctx.get("packet") or {}).get("documents"),
            "staged": (ctx.get("stage") or {}).get("result"),
            "served": {k: served.count(k) for k in set(served)},
        }


def case_info(case) -> dict:
    specs = all_specialists()
    lib = __import__("engine.specialists", fromlist=["CAPABILITIES"])
    steps = {}
    for s in case.RECIPE.steps:
        spec = get(s.specialist)
        reused = s.specialist in lib.CAPABILITIES or s.specialist in lib.DOMAIN
        how = getattr(spec, "how", None) or ("code" if s.specialist in ("act", "fetch") else "model")
        steps[s.id] = {"specialist": s.specialist, "reused": reused, "gate": s.gate, "how": how,
                       "does": case.STEPS.get(s.id, ""), "config": s.config}
    nodes, wires = _compact_graph(case.RECIPE, steps)
    docs = []
    for d in case.DOCUMENTS:
        docs.append({**d, "preview": [f"/docs/{p}" for p in d.get("preview", [])],
                     "download": [f"/docs/{f}" for f in d["files"]]})
    findings = [str(f) for f in validate(case.RECIPE)]
    recorded = None
    if case.TAPE.exists():
        recorded = json.loads(case.TAPE.read_text()).get("recorded")
    return {"title": case.TITLE, "request": case.REQUEST, "synthetic": case.SYNTHETIC, "documents": docs,
            "nodes": nodes, "wires": wires, "steps": steps, "validator": findings,
            "library": len([s for s in specs if s in lib.CAPABILITIES or s in lib.DOMAIN]),
            "tape": {"exists": case.TAPE.exists(), "recorded": recorded}}


def _compact_graph(recipe, steps) -> tuple[list, list]:
    """The explorer's graph (engine/explorer.build_graph), simplified for a screen: one input and one
    output socket per step (a step's own field-level wiring is in its drawer), the gate/loop sockets kept,
    the case file's documents kept as separate outputs, and no separate OUT node — `stage` is the end."""
    g = build_graph(recipe, work_item="case")
    contract_out = {s.id: next(iter(get(s.specialist).contract.output)) for s in recipe.steps}
    nodes, wires, seen = [], [], set()
    for n in g["nodes"]:
        if n["id"] == "OUT":
            continue
        st = steps.get(n["id"])
        if n["id"] == "IN":
            nodes.append({**n, "title": "the case file", "sub": f"{len(n['outs'])} documents, as received"})
            continue
        gates = [i for i in n["ins"] if i.startswith("when ")]
        reads = [i for i in n["ins"] if not i.startswith("when ")]
        kind = "gate" if n.get("gate") else ("shared" if st["reused"] else "domain")
        label = (reads[0] + (f" +{len(reads) - 1}" if len(reads) > 1 else "")) if reads else None
        nodes.append({**n, "kind": kind, "title": n["id"], "sub": st["how"],
                      "outs": [contract_out[n["id"]]] if n["id"] != "stage" else [],
                      "ins": gates + ([label] if label else [])})
    by_id = {n["id"]: n for n in nodes}
    later = {w["dst"] for w in g["wires"] if w["src"] != "IN" and w["type"] == "data"}
    shown = {w["srcSock"] for w in g["wires"] if w["src"] == "IN" and w["dst"] not in later}
    for w in g["wires"]:
        if w["dst"] == "OUT" or (w["src"] == "IN" and w["dst"] in later and w["srcSock"] in shown):
            continue                       # a document already wired to its first reader; later reads are in the drawer
        if w["type"] == "loop" and not w.get("when"):
            continue                       # the loop's feedback data rides the guarded loop edge drawn below
        src_sock = w["srcSock"] if w["src"] == "IN" else by_id[w["src"]]["outs"][0]
        dst = by_id[w["dst"]]
        dst_sock = w["dstSock"] if w["dstSock"].startswith("when ") else dst["ins"][-1]
        key = (w["src"], src_sock, w["dst"], dst_sock)
        if key not in seen:
            seen.add(key)
            wires.append(list(key) + ([w["type"]] if w["type"] != "data" else []))
    return nodes, wires


def _page() -> str:
    from .. import explorer
    core = (Path(explorer.__file__).parent / "graph_core.js").read_text()
    return (HERE / "page.html").read_text().replace("__GRAPH_CORE__", core)


def serve(case, port: int = 8600, host: str = "0.0.0.0") -> None:
    sessions: dict[str, Session] = {}
    docs_dir = Path(case.__file__).with_name("docs")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            data = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj, default=str))

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/":
                self._send(200, _page(), "text/html; charset=utf-8")
            elif path == "/api/case":
                self._json(case_info(case))
            elif path.startswith("/docs/"):
                f = docs_dir / Path(path[6:]).name                 # basename only: no traversal
                if f.is_file():
                    self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")
                else:
                    self._json({"error": "no such document"}, 404)
            elif path.startswith("/api/session/"):
                s = sessions.get(path.split("/")[3])
                if not s:
                    return self._json({"error": "no such session"}, 404)
                self._json({"id": s.id, "mode": s.mode, "compose": s.compose, "run": s.state()})
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or "{}")
            parts = self.path.strip("/").split("/")
            if parts == ["api", "session"]:
                mode = body.get("mode", "live")
                if mode == "replay" and not case.TAPE.exists():
                    return self._json({"error": "no recorded run yet — record one with `python -m engine.live record`"}, 400)
                s = Session(case, mode)
                sessions[s.id] = s
                return self._json({"id": s.id})
            s = sessions.get(parts[2]) if len(parts) > 3 else None
            if not s:
                return self._json({"error": "no such session"}, 404)
            action = parts[3]
            if action == "compose":
                s.start_compose()
            elif action == "run":
                s.start_run()
            elif action in ("approve", "reject"):
                if not s.board or not s.board.with_status("gated"):
                    return self._json({"error": "nothing is waiting at the gate"}, 409)
                s.decide(action == "approve", body.get("reason", ""))
            else:
                return self._json({"error": "unknown action"}, 404)
            self._json({"ok": True})

    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"live view: http://localhost:{port}  (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
