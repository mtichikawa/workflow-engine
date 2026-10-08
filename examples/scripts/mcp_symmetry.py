"""USE CASE B — the symmetry, made visible: a native engine specialist and an external MCP tool are the same
shape, so they are drop-in interchangeable as the SOURCE of a workflow.

The engine already has a native `fetch(source=hn)` specialist. We also ship a tiny external MCP server exposing a
`top_stories` tool (examples/mcp_servers/hn_server.py). Both return the SAME typed items. This demo pulls the
current Hacker News top stories BOTH ways, shows the item shapes are identical, then runs the SAME downstream
reasoning step (classify each story's topic) on each — proving the rest of the workflow doesn't care which
supplied the data.

That is the core MCP insight in the engine: "a specialist and an MCP tool are the same shape," so importing a tool
is just choosing a different source for the same recipe tail.

    pip install -e '.[mcp]'
    python examples/scripts/mcp_symmetry.py [limit]
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 3
HN_SERVER = {"command": sys.executable, "args": [str(ROOT / "examples/mcp_servers/hn_server.py")]}
TOPICS = ["AI/ML", "programming", "security", "hardware", "startup/business", "science", "other"]


def _mcp_installed() -> bool:
    try:
        import mcp  # noqa: F401
        return True
    except ImportError:
        return False


def via_native_specialist():
    """SOURCE #1: the engine's own fetch specialist (source=hn)."""
    from engine.core import get
    return get("fetch").run({"source": "hn", "params": {"limit": LIMIT}}, {})["items"]


def via_external_mcp():
    """SOURCE #2: the same data through an external MCP tool, run on the real dispatcher."""
    from engine.core import Board, Dispatcher, Recipe, Step, Tracer
    recipe = Recipe("hn-mcp", steps=[
        Step(id="pull", specialist="mcp_call",
             config={"server": HN_SERVER, "tool": "top_stories"},
             inputs={"arguments": "payload"})])
    board = Board("hn-mcp", "sym-mcp")
    board.add_item("q", {"limit": LIMIT})
    Dispatcher(recipe, board, Tracer("sym-mcp", echo=False)).run(auto_approve=True)
    return board.context["q"]["pull"]["result"]


def classify_topic(story: dict) -> dict:
    """The SHARED downstream tail — identical regardless of which source produced `story`."""
    from engine.core import get
    r = get("classify").run(
        {"item": {"title": story["title"]}, "categories": TOPICS,
         "criteria": "Classify the primary topic of a Hacker News story from its title."}, {})
    return {"label": r["label"], "confidence": r["confidence"]}


def main():
    if not _mcp_installed():
        print("skipped (install the optional dependency: pip install -e '.[mcp]')")
        return
    import engine.specialists  # noqa: F401

    native = via_native_specialist()
    external = via_external_mcp()

    print("=== SAME SHAPE: fetch(source=hn) specialist  vs  external MCP top_stories tool ===")
    print("  native   keys:", sorted(native[0].keys()) if native else "(none)")
    print("  external keys:", sorted(external[0].keys()) if external else "(none)")
    print("  identical item contract:", native and external and native[0].keys() == external[0].keys())

    print("\n=== SAME TAIL: the same classify step runs on each source's items ===")
    for src_name, items in (("native  fetch(hn)", native), ("external MCP tool", external)):
        print(f"\n  via {src_name}:")
        for s in items:
            t = classify_topic(s)
            print(f"    [{t['label']:>16} {t['confidence']:.2f}]  {s['title'][:60]}")

    print("\nThe source is swappable (native specialist <-> MCP tool); the recipe tail is unchanged.")


if __name__ == "__main__":
    main()
