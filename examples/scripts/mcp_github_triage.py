"""USE CASE A — the engine triages a live GitHub issue tracker, pulling the issues through an EXTERNAL MCP server.

The point: an external MCP tool does the I/O (fetch live issues), and the engine's own judgment specialists do the
reasoning (classify + route + summarize) — composed in one run. This is the "reasoning agent over a live
tracker" shape.

Two phases, both on the real dispatcher:
  1. IMPORT  — a one-step recipe whose `mcp_call` step calls `list_issues` on an external MCP server and
               returns real open issues.
  2. TRIAGE  — a board with one card per issue; each issue is classified (bug/feature/docs/question), routed
               to a component, and summarized. Three specialists, per issue, in parallel.

Runs with ZERO secrets against the bundled github-issues MCP server (GitHub's public API). To use the
OFFICIAL GitHub MCP server instead, set SERVER below to:
    {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"],
     "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "<token>"}}
— same `mcp_call` config, just a different server dict (that's the whole "swap a provider = config change"
point). The engine also has a NATIVE fetch(source=github) specialist; see examples/scripts/mcp_symmetry.py for why the two
are interchangeable.

    pip install -e '.[mcp]'
    python examples/scripts/mcp_github_triage.py [owner/repo] [limit]
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

REPO = sys.argv[1] if len(sys.argv) > 1 else "modelcontextprotocol/servers"
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 4

# The external MCP server that supplies issues. Bundled + zero-secret by default; swap per the module docstring.
SERVER = {"command": sys.executable, "args": [str(ROOT / "examples/mcp_servers/github_issues_server.py")]}

CATEGORIES = ["bug", "feature-request", "documentation", "question", "security"]
COMPONENTS = ["filesystem", "git", "fetch", "memory", "docs", "build/ci", "other"]


def _mcp_installed() -> bool:
    try:
        import mcp  # noqa: F401
        return True
    except ImportError:
        return False


def import_issues():
    """Phase 1: pull live issues through the external MCP server, via the real dispatcher."""
    import engine.specialists  # noqa: F401
    from engine.core import Board, Dispatcher, Recipe, Step, Tracer

    recipe = Recipe("gh-import", steps=[
        Step(id="pull", specialist="mcp_call",
             config={"server": SERVER, "tool": "list_issues"},
             inputs={"arguments": "payload"})])
    board = Board("gh-import", "gh-triage-import")
    board.add_item("q", {"repo": REPO, "limit": LIMIT})
    Dispatcher(recipe, board, Tracer("gh-triage-import", echo=False)).run(auto_approve=True)
    pull = board.context.get("q", {}).get("pull")
    return pull["result"] if pull else []      # [] if the external fetch failed (e.g. offline)


def triage(issues):
    """Phase 2: classify + route + summarize each issue, one board card per issue."""
    from engine.core import Board, Dispatcher, Recipe, Step, Tracer

    recipe = Recipe("gh-triage", steps=[
        Step(id="classify", specialist="classify",
             inputs={"item": "payload", "categories": CATEGORIES,
                     "criteria": "Triage an open-source GitHub issue by its title and body."}),
        Step(id="route", specialist="route",
             inputs={"item": "payload", "components": COMPONENTS}),
        Step(id="summary", specialist="summarize",
             inputs={"text": "payload.body",
                     "brief": "one sentence a maintainer can scan"}),
    ])
    board = Board("gh-triage", "gh-triage-run")
    for iss in issues:
        board.add_item(iss["id"], iss)
    Dispatcher(recipe, board, Tracer("gh-triage-run", echo=False), concurrency=4).run(auto_approve=True)

    def _fail_reason(item_id):
        """If a step didn't produce output (e.g. no brain configured), report why, don't KeyError."""
        for step in ("classify", "route", "summary"):
            card = board.card(item_id, step)
            if card and card.status == "failed" and card.attempts:
                return card.attempts[-1].get("error", "step failed")
        return None

    rows = []
    for iss in issues:
        ctx = board.context.get(iss["id"], {})
        cls, rte, smy = ctx.get("classify"), ctx.get("route"), ctx.get("summary")
        if not (cls and rte and smy):
            rows.append({"id": iss["id"], "title": iss["title"],
                         "error": _fail_reason(iss["id"]) or "incomplete"})
            continue
        rows.append({
            "id": iss["id"], "title": iss["title"],
            "label": cls["label"], "confidence": cls["confidence"],
            "component": rte["component"], "escalate": rte["escalate"],
            "summary": smy["summary"],
        })
    return rows


def main():
    if not _mcp_installed():
        print("skipped (install the optional dependency: pip install -e '.[mcp]')")
        return
    print(f"=== IMPORT: pulling up to {LIMIT} open issues of {REPO} via an external MCP server ===")
    issues = import_issues()
    print(f"  got {len(issues)} real issues\n")
    if not issues:
        print("  (no open issues returned — try another repo)")
        return
    print("=== TRIAGE: the engine classifies + routes + summarizes each (real brain) ===\n")
    for r in triage(issues):
        print(f"#{r['id']}  {r['title'][:70]}")
        if "error" in r:
            print(f"   (triage step did not complete: {str(r['error'])[:120]})\n")
            continue
        print(f"   label={r['label']} ({r['confidence']:.2f})  ->  component={r['component']}"
              f"  escalate={r['escalate']}")
        print(f"   summary: {r['summary']}\n")


if __name__ == "__main__":
    main()
