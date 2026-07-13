"""fetch — capability specialist: call an external source, return structured items.

Pure code (no brain). Sources for the proof:
  - github : open issues of a public repo, via the authed `gh` CLI (PRs filtered out)
  - hn     : recent Hacker Story items, via the public Firebase API (no auth)
Reused by triage (intake) and content (gather sources) — same specialist, config only.
"""

from __future__ import annotations

import json
import subprocess
import urllib.request

from ..core import Contract, Specialist


class Fetch(Specialist):
    name = "fetch"
    kind = "capability"
    contract = Contract(input={"source": str, "params": dict}, output={"items": list})

    def _run(self, input, config):
        source = input["source"]
        params = input.get("params", {})
        if source == "github":
            items = _github_issues(params)
        elif source == "github_pr":
            items = _github_prs(params)
        elif source == "hn":
            items = _hn_items(params)
        else:
            raise ValueError(f"fetch: unknown source '{source}'")
        return {"items": items}


def _github_prs(params: dict) -> list[dict]:
    repo = params["repo"]
    limit = int(params.get("limit", 3))
    out = subprocess.run(
        ["gh", "api", f"repos/{repo}/pulls?state=open&per_page={limit}"],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0:
        raise RuntimeError(f"gh api failed: {out.stderr.strip()[:200]}")
    result = []
    for pr in json.loads(out.stdout)[:limit]:
        n = pr["number"]
        diff = subprocess.run(
            ["gh", "api", f"repos/{repo}/pulls/{n}",
             "-H", "Accept: application/vnd.github.v3.diff"],
            capture_output=True, text=True, timeout=60,
        ).stdout[:4000]
        result.append({
            "id": str(n), "title": pr.get("title", ""),
            "body": (pr.get("body") or "")[:1500],
            "url": pr.get("html_url", ""), "diff": diff,
        })
    return result


def _github_issues(params: dict) -> list[dict]:
    repo = params["repo"]
    limit = int(params.get("limit", 20))
    per_page = min(100, limit * 4 + 10)   # over-fetch: the endpoint mixes in PRs
    out = subprocess.run(
        ["gh", "api", f"repos/{repo}/issues?state=open&per_page={per_page}"],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0:
        raise RuntimeError(f"gh api failed: {out.stderr.strip()[:200]}")
    issues = json.loads(out.stdout)
    result = []
    for i in issues:
        if "pull_request" in i:           # the issues endpoint also returns PRs
            continue
        if len(result) >= limit:
            break
        result.append({
            "id": str(i["number"]),
            "title": i.get("title", ""),
            "body": (i.get("body") or "")[:2000],
            "url": i.get("html_url", ""),
            "labels": [l["name"] for l in i.get("labels", [])],
        })
    return result


def _hn_items(params: dict) -> list[dict]:
    limit = int(params.get("limit", 10))
    ids = _get_json("https://hacker-news.firebaseio.com/v0/topstories.json")[:limit]
    result = []
    for sid in ids:
        it = _get_json(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json")
        if not it:
            continue
        result.append({
            "id": str(it.get("id", sid)),
            "title": it.get("title", ""),
            "url": it.get("url", ""),
            "score": it.get("score", 0),
        })
    return result


def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "engine/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())
