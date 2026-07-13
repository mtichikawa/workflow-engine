"""Render a board as a self-contained HTML view — the presentation layer.

A grid: rows = work-items (the hopper), columns = recipe steps (the stages), each
cell showing status + the specialist's key output. Watch the machine at a glance.
    python -m engine.cli view <run_id>
"""

from __future__ import annotations

import html
from pathlib import Path

from .core.board import Board

_COLOR = {"done": "#1f6f3f", "gated": "#8a6d00", "running": "#1c4f8a",
          "ready": "#333", "todo": "#2a2a2a", "failed": "#7a1f1f", "blocked": "#444"}


def summarize(step_id: str, out: dict | None) -> str:
    if not out:
        return ""
    if "label" in out:
        return f"{out['label']} ({out.get('confidence', '')})"
    if "score" in out:
        return f"score {out['score']}"
    if "component" in out:
        return f"→ {out['component']}" + (" ⚠" if out.get("escalate") else "")
    if "verdict" in out:
        return out["verdict"] + (f" · {len(out.get('issues', []))} issues" if out.get("issues") else "")
    if "reply" in out:
        return html.escape(out["reply"][:70]) + "…"
    if "post" in out:
        return html.escape(out["post"][:70]) + "…"
    if "status" in out:
        return out["status"]
    return html.escape(str(out)[:50])


def render_html(board: Board, step_ids: list[str]) -> str:
    head = "".join(f"<th>{html.escape(s)}</th>" for s in step_ids)
    rows = ""
    for item_id in board.items:
        cells = ""
        for step_id in step_ids:
            card = board.card(item_id, step_id)
            status = card.status if card else "—"
            bg = _COLOR.get(status, "#222")
            summary = summarize(step_id, card.output if card else None)
            cells += (f'<td style="background:{bg}"><div class="st">{status}</div>'
                      f'<div class="sm">{summary}</div></td>')
        title = html.escape(str(board.items[item_id]["payload"].get("title",
                            board.items[item_id]["payload"].get("topic", item_id)))[:60])
        rows += f'<tr><th class="item">{title}</th>{cells}</tr>'
    return f"""<!doctype html><meta charset=utf-8>
<title>engine · {html.escape(board.run_id)}</title>
<style>
 body{{background:#111;color:#ddd;font:13px/1.4 ui-monospace,Menlo,monospace;padding:24px}}
 h1{{font-size:15px;color:#8ac}} .sub{{color:#777;margin-bottom:16px}}
 table{{border-collapse:collapse;width:100%}} th,td{{border:1px solid #000;padding:6px 8px;vertical-align:top}}
 thead th{{background:#000;color:#8ac;text-align:left}}
 th.item{{background:#000;color:#ccc;max-width:220px;text-align:left}}
 td{{min-width:110px}} .st{{font-weight:bold;text-transform:uppercase;font-size:10px;letter-spacing:.5px}}
 .sm{{color:#cfe;opacity:.85;margin-top:3px}}
</style>
<h1>engine — {html.escape(board.recipe)} recipe</h1>
<div class=sub>run {html.escape(board.run_id)} · {len(board.items)} work-items · rows = the hopper, columns = the pipeline stages</div>
<table><thead><tr><th class=item>work-item</th>{head}</tr></thead><tbody>{rows}</tbody></table>
"""


def write_view(run_id: str, step_ids: list[str], out_dir: str = "output") -> Path:
    board = Board.load(run_id)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    path = Path(out_dir) / f"board-{run_id}.html"
    path.write_text(render_html(board, step_ids))
    return path
