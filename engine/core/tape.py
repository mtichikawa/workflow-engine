"""Tape — record a run's brain calls, then replay them exactly.

A live run is non-deterministic (the CLI brain has no temperature control) and only as fast as the
model is that day. A tape fixes both for a demo: record one good run, then replay it — the dispatcher,
the specialists' own code, the gates and every contract check all run for real; only the model's text
comes from the recording. Nothing is faked silently: a replayed call says so, and a prompt that isn't
on the tape is a miss the caller can see.

    with tape.recording(path):  ...run...      # live calls, each saved with its latency
    with tape.replaying(path):  ...run...      # same prompts -> same responses, at the recorded pace

Ambient via a ContextVar (like scope), so the dispatcher's worker threads inherit it and specialists
never see it. Keyed by sha256(system + prompt). A prompt that drifted slightly since recording (e.g. a
track-record count in the composer's catalog) falls back to the most similar unused entry — reported
as `approx`, never passed off as exact.
"""

from __future__ import annotations

import contextlib
import contextvars
import difflib
import hashlib
import json
import threading
import time
from pathlib import Path

_ACTIVE: contextvars.ContextVar["Tape | None"] = contextvars.ContextVar("tape", default=None)
_APPROX_MIN = 0.9          # a drifted prompt must still be this similar to count as the same call


def _files_sha(files: list[str] | None) -> str:
    h = hashlib.sha256()
    for f in files or ():
        h.update(Path(f).read_bytes())
    return h.hexdigest()


def _key(prompt: str, system: str | None, files: list[str] | None = None) -> str:
    h = hashlib.sha256(f"{system or ''}\x00{prompt}".encode())
    for f in files or ():                  # an image is part of the question: same words, other scan = other call
        h.update(Path(f).read_bytes())
    return h.hexdigest()


class TapeMiss(Exception):
    """A replayed prompt that isn't on the tape."""


class Tape:
    def __init__(self, path: str | Path, mode: str, pace: float = 1.0):
        self.path, self.mode, self.pace = Path(path), mode, pace
        self.entries: list[dict] = (json.loads(self.path.read_text())["calls"]
                                    if mode == "replay" else [])
        self.used: set[int] = set()
        self.log: list[dict] = []          # per call: how it was served (live | exact | approx | miss)
        self._lock = threading.Lock()

    def call(self, prompt: str, system: str | None, live, files: list[str] | None = None) -> str:
        if self.mode == "record":
            t0 = time.time()
            out = live()
            with self._lock:
                self.entries.append({"key": _key(prompt, system, files), "system": system,
                                     "files": _files_sha(files) if files else None, "prompt": prompt,
                                     "response": out, "seconds": round(time.time() - t0, 2)})
                self.log.append({"served": "live"})
            return out
        hit, how = self._find(prompt, system, files)
        if hit is None:
            with self._lock:
                self.log.append({"served": "miss"})
            raise TapeMiss(f"prompt not on the tape {self.path.name} (sha {_key(prompt, system, files)[:10]})")
        time.sleep(hit["seconds"] * self.pace)
        with self._lock:
            self.log.append({"served": how})
        return hit["response"]

    def _find(self, prompt: str, system: str | None, files: list[str] | None):
        k = _key(prompt, system, files)
        with self._lock:
            free = [(i, e) for i, e in enumerate(self.entries) if i not in self.used]
            for i, e in free:
                if e["key"] == k:
                    self.used.add(i)
                    return e, "exact"
            best, score = None, 0.0
            for i, e in free:
                if e.get("system") != system or e.get("files") != (_files_sha(files) if files else None):
                    continue                        # drift is tolerated in the words only — never in an image
                r = difflib.SequenceMatcher(None, e["prompt"], prompt, autojunk=False).ratio()
                if r > score:
                    best, score = (i, e), r
            if best and score >= _APPROX_MIN:
                self.used.add(best[0])
                return best[1], "approx"
        return None, "miss"

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"recorded": time.strftime("%Y-%m-%d %H:%M %Z"),
                                         "calls": self.entries}, indent=1))


def active() -> "Tape | None":
    return _ACTIVE.get()


@contextlib.contextmanager
def recording(path: str | Path):
    t = Tape(path, "record")
    tok = _ACTIVE.set(t)
    try:
        yield t
    finally:
        _ACTIVE.reset(tok)


@contextlib.contextmanager
def replaying(path: str | Path, pace: float = 1.0):
    t = Tape(path, "replay", pace)
    tok = _ACTIVE.set(t)
    try:
        yield t
    finally:
        _ACTIVE.reset(tok)
