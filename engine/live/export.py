"""A static copy of the live view's recorded run, for a public link that needs no server.

    python -m engine.live static [--out demo]      # -> demo/index.html, demo/recorded.json, demo/docs/…

A replay is deterministic: the same tape gives the same answers every time. So this runs the replay once,
through the real server code (engine/live/server.py's Session: composer, validator, dispatcher, gate), and
saves every answer the page asks the server for: the case, the composer's log, the run at the gate, and the
run after approve and after reject. The same page.html, given `window.STATIC_DEMO`, reads those from
recorded.json instead of the API. Nothing runs in the browser and no model is called; the page says so.

The export fails rather than ship a replay that wasn't exact: every model answer must come from the tape.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from .server import Session, _page, case_info

ROOT = Path(__file__).resolve().parents[2]


def _wait(cond, what: str, timeout: float = 60) -> None:
    t0 = time.time()
    while not cond():
        if time.time() - t0 > timeout:
            raise TimeoutError(f"export: {what} didn't finish in {timeout:.0f} s")
        time.sleep(0.05)


def _exact(served: list | dict, what: str) -> None:
    kinds = set(served) if isinstance(served, list) else set(served)
    if kinds - {"exact"}:
        raise RuntimeError(f"export: the {what} wasn't an exact replay ({sorted(kinds)}); "
                           "state/registry.json must be the one the tape was recorded with (OPEN-ITEMS DEMO-a)")


def record(case) -> dict:
    """Every answer the page needs, from one replay. Runs in a scratch directory (boards and the staged
    file land there), with this checkout's track record copied in so the composer's prompt matches the tape."""
    reg = ROOT / "state/registry.json"
    if not reg.exists():
        raise FileNotFoundError("export: needs state/registry.json, the track record the tape was recorded with")
    here = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "state").mkdir()
        shutil.copy(reg, Path(tmp) / "state/registry.json")
        os.chdir(tmp)
        try:
            s = Session(case, "replay")
            s.start_compose()
            _wait(lambda: s.compose["status"] != "running", "the composer")
            if s.compose["status"] != "done":
                raise RuntimeError(f"export: the composer failed: {s.compose.get('error')}")
            _exact(s.compose["served"], "composer")
            s.start_run()
            _wait(lambda: s.state()["status"] != "running", "the run")
            gated = s.state()
            if gated["status"] != "gated":
                raise RuntimeError(f"export: the run ended {gated['status']} ({gated.get('error')}), not at the gate")
            _exact(list(gated["served"]), "run")
            s.decide(True)
            _wait(lambda: s.state()["status"] == "done", "approving")
            approved = s.state()
            r = Session(case, "replay")
            r.start_run()
            _wait(lambda: r.state()["status"] == "gated", "the second run")
            r.decide(False, "rejected at the gate in the demo")
            _wait(lambda: r.state()["status"] == "rejected", "rejecting")
            rejected = r.state()
        finally:
            os.chdir(here)
    info = case_info(case)
    for d in info["documents"]:                            # served beside the page, not from a server's /docs/
        d["preview"] = [p.lstrip("/") for p in d["preview"]]
        d["download"] = [p.lstrip("/") for p in d["download"]]
    return {"exported": time.strftime("%Y-%m-%d %H:%M %Z"), "case": info, "composed": s.compose,
            "run": {"gated": gated, "approved": approved, "rejected": rejected}}


def export(case, out: Path) -> Path:
    data = record(case)
    src = Path(case.__file__).with_name("docs")
    # the readers' inputs name the files on this machine; here they're the copies published beside the page
    text = json.dumps(data, default=str).replace(str(src.resolve()) + "/", "docs/")
    if any(x in text for x in (str(ROOT), str(Path.home()), tempfile.gettempdir() + "/")):
        raise RuntimeError("export: a path on this machine leaked into the recording")
    out.mkdir(parents=True, exist_ok=True)
    (out / "recorded.json").write_text(text)
    docs = out / "docs"
    docs.mkdir(exist_ok=True)
    for d in data["case"]["documents"]:
        for p in d["preview"] + d["download"]:
            shutil.copy(src / Path(p).name, docs / Path(p).name)
    page = _page().replace("<script>\n\"use strict\";",
                           '<script>window.STATIC_DEMO={data:"recorded.json"};</script>\n<script>\n"use strict";', 1)
    if "window.STATIC_DEMO" not in page:
        raise RuntimeError("export: page.html no longer has the script block the export hooks into")
    (out / "index.html").write_text(page)
    return out
