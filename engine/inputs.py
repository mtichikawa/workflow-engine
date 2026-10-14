"""Inputs — turn what a person hands in into work-items: (item_id, payload) pairs.

A workflow runs once per item. Every source gives each item a payload with a `text` field (what most
specialists read) plus whatever structure it had:

    text(s)               one item
    pasted(s, split)      one item per line, or per blank-line-separated block
    csv_rows(path)        one item per row: the row's columns, and `text` as "column: value" lines
    jsonl(path)           one item per JSON object
    folder(path)          one item per file: text files and PDFs with a text layer are read; images and
                          scanned PDFs are passed as `files` (the library has no general image reader yet —
                          the care-intake demo's read_document is one)

Item ids are stable — a row's own `id` column, a file's name, or a hash of the content — so a scheduled
run can tell new items from ones it has already seen (`new_only`). A webhook delivers one item per POST
(engine/app.py).
"""

from __future__ import annotations

import csv as _csv
import hashlib
import json
from pathlib import Path

TEXT_EXT = {".txt", ".md", ".csv", ".json", ".jsonl", ".eml", ".html", ".xml", ".log", ".tsv"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
SOURCES = ("text", "pasted", "csv", "jsonl", "folder", "webhook")


def _hid(content) -> str:
    return "h" + hashlib.sha256(json.dumps(content, sort_keys=True, default=str).encode()).hexdigest()[:10]


def text(s: str) -> list[tuple[str, dict]]:
    return [(_hid(s), {"text": s})] if s.strip() else []


def pasted(s: str, split: str = "line") -> list[tuple[str, dict]]:
    parts = s.splitlines() if split == "line" else [b for b in s.replace("\r\n", "\n").split("\n\n")]
    return [(_hid([i, p.strip()]), {"text": p.strip()}) for i, p in enumerate(parts) if p.strip()]


def _row_item(row: dict, i: int) -> tuple[str, dict]:
    row = {str(k).strip(): v for k, v in row.items() if k is not None}
    rid = next((str(row[k]) for k in ("id", "ID", "Id") if row.get(k)), None)
    payload = {**row, "text": "\n".join(f"{k}: {v}" for k, v in row.items() if v not in (None, ""))}
    return (rid or _hid(row)), payload


def csv_rows(path: str | Path, data: str | None = None) -> list[tuple[str, dict]]:
    """Rows of a CSV file (or of CSV text in `data`). The delimiter is sniffed (comma, tab, semicolon)."""
    raw = data if data is not None else Path(path).read_text(encoding="utf-8-sig")
    try:
        dialect = _csv.Sniffer().sniff(raw[:4096], delimiters=",\t;")
    except _csv.Error:
        dialect = _csv.excel
    return [_row_item(r, i) for i, r in enumerate(_csv.DictReader(raw.splitlines(), dialect=dialect))
            if any(v for v in r.values())]


def jsonl(path: str | Path, data: str | None = None) -> list[tuple[str, dict]]:
    raw = data if data is not None else Path(path).read_text()
    out = []
    for i, line in enumerate(l for l in raw.splitlines() if l.strip()):
        obj = json.loads(line)
        if not isinstance(obj, dict):
            obj = {"value": obj}
        payload = obj if "text" in obj else {**obj, "text": json.dumps(obj, ensure_ascii=False)}
        out.append((str(obj.get("id") or _hid(obj)), payload))
    return out


def folder(path: str | Path, pattern: str = "*") -> list[tuple[str, dict]]:
    """One item per file (not recursive; hidden files skipped), in name order."""
    root = Path(path)
    if not root.is_dir():
        raise ValueError(f"not a folder: {root}")
    out = []
    for f in sorted(root.glob(pattern)):
        if not f.is_file() or f.name.startswith("."):
            continue
        payload = {"file": f.name, "path": str(f.resolve())}
        ext = f.suffix.lower()
        if ext in TEXT_EXT:
            payload["text"] = f.read_text(errors="replace")
        elif ext in IMAGE_EXT:
            payload.update(text="", files=[str(f.resolve())])
        elif ext == ".pdf":
            payload.update(_pdf(f))
        else:
            continue                                   # a file type nothing here can read
        out.append((f.name, payload))
    return out


def _pdf(f: Path) -> dict:
    """A PDF's text layer if it has one; otherwise its pages as images for a model to read."""
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise ValueError("reading PDFs needs `pip install pypdf`") from e
    reader = PdfReader(str(f))
    txt = "\n".join((p.extract_text() or "") for p in reader.pages).strip()
    if len(txt) > 40:
        return {"text": txt}
    return {"text": "", "files": [str(f.resolve())]}         # scanned: a step that reads files must read it


def from_spec(spec: dict, upload: str | None = None) -> list[tuple[str, dict]]:
    """Items from a source description: {"kind": "csv", "path": ...} — or uploaded text for csv/jsonl."""
    kind = spec.get("kind", "text")
    if kind == "text":
        return text(upload if upload is not None else spec.get("text", ""))
    if kind == "pasted":
        return pasted(upload if upload is not None else spec.get("text", ""), spec.get("split", "line"))
    if kind == "csv":
        return csv_rows(spec.get("path", ""), upload)
    if kind == "jsonl":
        return jsonl(spec.get("path", ""), upload)
    if kind == "folder":
        return folder(spec["path"], spec.get("pattern", "*"))
    raise ValueError(f"unknown input kind '{kind}' (one of {', '.join(SOURCES)})")


def new_only(items: list[tuple[str, dict]], seen_file: Path) -> list[tuple[str, dict]]:
    """Drop items already seen (by id + content), and remember the rest — for scheduled runs."""
    seen = set(json.loads(seen_file.read_text())) if seen_file.exists() else set()
    fresh = [(i, p) for i, p in items if f"{i}|{_hid(p)}" not in seen]
    seen |= {f"{i}|{_hid(p)}" for i, p in fresh}
    seen_file.parent.mkdir(parents=True, exist_ok=True)
    seen_file.write_text(json.dumps(sorted(seen)))
    return fresh
