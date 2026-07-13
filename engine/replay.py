"""Replay — an animated, scrubbable visualization of a run.

Reads a run's board (the recipe graph + the ordered event log we now record) and emits a
self-contained HTML page: the recipe as a graph, work-items as tokens that flow through it
as you scrub the timeline, nodes flashing as steps complete, branches/loops/gates visible.
Not live (a run takes seconds) — a replay you control the pace of.

    python -m engine.cli replay <run_id>
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from .core.board import Board


def _summary(step_id: str, out: dict | None) -> str:
    if not out:
        return ""
    for k in ("label", "score", "verdict", "component", "risk"):
        if k in out:
            v = out[k]
            extra = f" ({out['confidence']})" if k == "label" and "confidence" in out else ""
            return f"{k}: {v}{extra}"
    for k in ("reply", "post", "comment", "summary", "status"):
        if k in out:
            return str(out[k])[:80]
    return str(out)[:60]


def build(board: Board, recipe, standalone: bool = True) -> str:
    steps = recipe.steps
    nodes = [{"id": s.id, "gate": s.gate, "domain": s.domain,
              "spec": s.specialist} for s in steps]
    edges = [{"src": e.src, "dst": e.dst, "when": e.when or "",
              "back": recipe.is_backward(e)} for e in recipe.edges]
    item_titles = {i: str(board.items[i]["payload"].get("title",
                   board.items[i]["payload"].get("topic", i)))[:48] for i in board.items}
    # latest output summary per (item, step) for hover
    outs = {}
    for i in board.items:
        for sid, out in board.context.get(i, {}).items():
            outs[f"{i}|{sid}"] = _summary(sid, out)

    data = {
        "recipe": recipe.name, "run": board.run_id,
        "nodes": nodes, "edges": edges,
        "items": list(board.items), "titles": item_titles,
        "events": board.events, "outs": outs,
    }
    body = _BODY.replace("/*DATA*/", json.dumps(data))
    if not standalone:
        return f"<title>engine replay · {html.escape(board.run_id)}</title>\n{body}"
    return (f"<!doctype html><html><head><meta charset=utf-8>"
            f"<title>engine replay · {html.escape(board.run_id)}</title></head><body>{body}</body></html>")


def write_replay(run_id: str, out_dir: str = "output") -> Path:
    from .recipes import RECIPES
    board = Board.load(run_id)
    if board.recipe not in RECIPES:
        raise ValueError(f"replay needs a named recipe; '{board.recipe}' isn't one")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    path = Path(out_dir) / f"replay-{run_id}.html"
    path.write_text(build(board, RECIPES[board.recipe]))
    return path


_BODY = r"""
<style>
 :root{--bg:#0f1216;--panel:#171b21;--line:#262c35;--ink:#e6e9ee;--mut:#8b93a1;--brass:#c9a860}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--ink);font:13px/1.5 ui-monospace,Menlo,monospace}
 .wrap{max-width:1040px;margin:0 auto;padding:20px}
 h1{font-size:14px;letter-spacing:.12em;text-transform:uppercase;color:var(--brass);margin:0 0 2px}
 .sub{color:var(--mut);margin-bottom:14px;font-size:12px}
 canvas{width:100%;background:var(--panel);border:1px solid var(--line);border-radius:6px;display:block}
 .bar{display:flex;align-items:center;gap:12px;margin-top:12px}
 button{background:#20262e;color:var(--ink);border:1px solid var(--line);border-radius:4px;padding:6px 14px;cursor:pointer;font:inherit}
 button:hover{border-color:var(--brass)}
 input[type=range]{flex:1;accent-color:var(--brass)}
 .tstamp{color:var(--mut);min-width:120px;text-align:right}
 .legend{display:flex;gap:16px;flex-wrap:wrap;margin-top:12px;color:var(--mut);font-size:11px}
 .legend span{display:inline-flex;align-items:center;gap:6px}
 .dot{width:9px;height:9px;border-radius:50%}
 .tip{position:fixed;pointer-events:none;background:#000;border:1px solid var(--line);border-radius:4px;padding:6px 8px;font-size:11px;color:var(--ink);max-width:280px;display:none;z-index:9}
</style>
<div class="wrap">
  <h1 id="title">engine replay</h1>
  <div class="sub" id="sub"></div>
  <canvas id="c" height="360"></canvas>
  <div class="bar">
    <button id="play">▶ play</button>
    <input type="range" id="scrub" min="0" max="1" value="0" step="0.01">
    <span class="tstamp" id="ts">0 / 0</span>
    <button id="speed">1×</button>
  </div>
  <div class="legend" id="legend"></div>
</div>
<div class="tip" id="tip"></div>
<script>
const DATA = /*DATA*/;
const C = document.getElementById('c'), X = C.getContext('2d');
const STATUS = {done:'#4a9d72', gated:'#cb9a34', skipped:'#5a636f', failed:'#b45c52', loop:'#5286c9'};
const PAL = ['#c9a860','#6fb3d0','#c98a8a','#8ac99a','#b79ad0','#d0b06f','#7fa8c9','#c9a0b8'];
document.getElementById('title').textContent = 'engine · ' + DATA.recipe + ' replay';
document.getElementById('sub').textContent = DATA.items.length + ' work-item(s) · ' + DATA.events.length + ' events · rows flow through the graph — scrub to watch';

// ---- layout: nodes in a row; branch targets nudge vertically -------------
let W = 1000, H = 360, pos = {};
function layout(){
  W = C.clientWidth;
  // layer (column) = longest forward path from an entry; ignore backward (loop) edges
  const layer = {}; DATA.nodes.forEach(n => layer[n.id] = 0);
  for (let k = 0; k < DATA.nodes.length; k++)
    DATA.edges.forEach(e => { if (!e.back) layer[e.dst] = Math.max(layer[e.dst], layer[e.src] + 1); });
  const maxL = Math.max(0, ...Object.values(layer));
  const byL = {}; DATA.nodes.forEach(n => { (byL[layer[n.id]] = byL[layer[n.id]] || []).push(n.id); });
  const maxLane = Math.max(1, ...Object.values(byL).map(a => a.length));
  H = Math.max(300, maxLane * 84 + 96); C.width = W; C.height = H;
  const dx = W / (maxL + 2);
  Object.entries(byL).forEach(([L, ids]) => {
    const m = ids.length, gap = Math.min(110, (H - 90) / (m + 1));
    ids.forEach((id, i) => { pos[id] = { x: dx * (+L + 1), y: H / 2 + (i - (m - 1) / 2) * gap }; });
  });
}
layout(); addEventListener('resize', ()=>{layout(); draw();});

// ---- per-item event timeline --------------------------------------------
const byItem = {}; DATA.items.forEach(it=>byItem[it]=[]);
DATA.events.forEach(ev=>{ if(byItem[ev.item]) byItem[ev.item].push(ev); });
const itemColor = {}; DATA.items.forEach((it,i)=>itemColor[it]=PAL[i%PAL.length]);
const N = DATA.events.length;

// token drawn position (eased toward target)
const tok = {}; DATA.items.forEach(it=>{ const p=pos[DATA.nodes[0].id]; tok[it]={x:p.x,y:p.y,last:null,status:null}; });

function stateAt(t){                                  // integer event index reached
  return Math.max(0, Math.min(N, Math.round(t)));
}
function targets(idx){
  // for each item, its most-recent event with n < idx -> node + status
  const res = {};
  DATA.items.forEach(it=>{
    const evs = byItem[it].filter(e=>e.n < idx);
    if(evs.length){ const e=evs[evs.length-1]; res[it]={step:e.step, status:e.status}; }
    else res[it]={step:DATA.nodes[0].id, status:null};
  });
  return res;
}

// ---- draw ---------------------------------------------------------------
let flash = {};        // step -> flash strength
let nodeStatus = {};   // step -> latest status at current time
const R = 18;
function edgePath(a, b, back){
  X.beginPath(); X.moveTo(a.x, a.y);
  if (back){ const dip = Math.max(a.y, b.y) + 58 + Math.abs(a.x - b.x) * 0.05;
    X.bezierCurveTo(a.x, dip, b.x, dip, b.x, b.y); }
  else { const mx = (a.x + b.x) / 2; X.bezierCurveTo(mx, a.y, mx, b.y, b.x, b.y); }
}
function arrow(a, b, back){
  const ax = back ? a.x : (a.x + b.x) / 2;
  const ang = Math.atan2(b.y - (back ? Math.max(a.y, b.y) + 40 : b.y), b.x - ax);
  const tx = b.x - Math.cos(ang) * R, ty = b.y - Math.sin(ang) * R;
  X.beginPath(); X.moveTo(tx, ty);
  X.lineTo(tx - Math.cos(ang - 0.4) * 7, ty - Math.sin(ang - 0.4) * 7);
  X.lineTo(tx - Math.cos(ang + 0.4) * 7, ty - Math.sin(ang + 0.4) * 7);
  X.closePath(); X.fill();
}
function draw(){
  X.clearRect(0, 0, W, H);
  DATA.edges.forEach(e=>{
    const a = pos[e.src], b = pos[e.dst]; if (!a || !b) return;
    X.strokeStyle = e.back ? '#3a4a63' : (e.when ? '#3b4552' : '#2c3441');
    X.lineWidth = 1.6; X.setLineDash(e.when ? [5, 4] : []);
    edgePath(a, b, e.back); X.stroke(); X.setLineDash([]);
    X.fillStyle = e.back ? '#3a4a63' : '#39424e'; arrow(a, b, e.back);
    if (e.when){ X.fillStyle = '#7a8492'; X.font = '10px monospace'; X.textAlign = 'center';
      const lbl = e.when.length > 22 ? e.when.slice(0, 21) + '…' : e.when;
      X.fillText(lbl, (a.x + b.x) / 2, e.back ? Math.max(a.y, b.y) + 48 : (a.y + b.y) / 2 - 8); }
  });
  DATA.nodes.forEach(nd=>{
    const p = pos[nd.id], f = flash[nd.id] || 0, st = nodeStatus[nd.id];
    let base = st === 'skipped' ? '#191d23' : '#20262e';
    X.beginPath(); X.arc(p.x, p.y, R, 0, 7);
    X.fillStyle = f > 0 ? mix(base, STATUS.done, f) : base; X.fill();
    X.lineWidth = nd.gate ? 2.6 : 1.6;
    X.strokeStyle = st === 'skipped' ? '#333b45' : (nd.gate ? '#cb9a34' : (nd.domain ? '#b79ad0' : '#455160'));
    X.stroke();
    X.fillStyle = st === 'skipped' ? '#5a636f' : '#cdd3db'; X.font = '11px monospace'; X.textAlign = 'center';
    X.fillText(nd.id.length > 11 ? nd.id.slice(0, 10) + '…' : nd.id, p.x, p.y + R + 14);
  });
  DATA.items.forEach((it, idx)=>{
    const t = tok[it], n = DATA.items.length;
    const off = n > 1 ? 11 : 0, ang = idx / n * 6.283;
    const ox = Math.cos(ang) * off, oy = Math.sin(ang) * off - 26;   // orbit above the node
    let col = itemColor[it]; if (t.status === 'skipped' || t.status === 'failed') col = STATUS[t.status];
    X.beginPath(); X.arc(t.x + ox, t.y + oy, 6, 0, 7);
    X.globalAlpha = t.status === 'skipped' ? 0.35 : 1; X.fillStyle = col; X.fill(); X.globalAlpha = 1;
    X.lineWidth = 1.5; X.strokeStyle = '#0f1216'; X.stroke();
  });
}
function mix(a,b,t){ const pa=hx(a),pb=hx(b); return `rgb(${pa.map((v,i)=>Math.round(v+(pb[i]-v)*t)).join(',')})`; }
function hx(h){h=h.replace('#','');return [0,2,4].map(i=>parseInt(h.slice(i,i+2),16));}

// ---- animation ----------------------------------------------------------
let t=0, playing=false, speed=1;
const scrub=document.getElementById('scrub'); scrub.max=N; scrub.step=0.02;
function tick(){
  if(playing){ t += 0.04*speed; if(t>=N){t=N; playing=false; document.getElementById('play').textContent='▶ play';} scrub.value=t; }
  const idx = Math.floor(t)+1;
  const tg = targets(idx);
  DATA.items.forEach(it=>{
    const target = pos[tg[it].step]||pos[DATA.nodes[0].id];
    tok[it].x += (target.x - tok[it].x)*0.2; tok[it].y += (target.y - tok[it].y)*0.2;
    tok[it].status = tg[it].status;
  });
  // flash the node of the most recent event
  Object.keys(flash).forEach(k=>flash[k]*=0.9);
  const cut = Math.floor(t);
  const cur = DATA.events[cut]; if(cur) flash[cur.step]=1;
  nodeStatus = {}; DATA.events.forEach(ev=>{ if(ev.n<=cut) nodeStatus[ev.step]=ev.status; });
  draw();
  document.getElementById('ts').textContent = Math.min(Math.round(t),N)+' / '+N;
  requestAnimationFrame(tick);
}
document.getElementById('play').onclick=e=>{ if(t>=N)t=0; playing=!playing; e.target.textContent=playing?'❚❚ pause':'▶ play'; };
scrub.oninput=e=>{ t=parseFloat(e.target.value); playing=false; document.getElementById('play').textContent='▶ play'; };
document.getElementById('speed').onclick=e=>{ speed = speed>=4?0.5:speed*2; e.target.textContent=speed+'×'; };

// hover tooltip: which item output is at the node under the cursor
const tip=document.getElementById('tip');
C.onmousemove=ev=>{
  const rect=C.getBoundingClientRect(), mx=ev.clientX-rect.left, my=ev.clientY-rect.top;
  let hit=null; DATA.nodes.forEach(nd=>{const p=pos[nd.id]; if((mx-p.x)**2+(my-p.y)**2<340) hit=nd.id;});
  if(hit){ const lines=DATA.items.map(it=>{const s=DATA.outs[it+'|'+hit]; return s?`${DATA.titles[it]}: ${s}`:null;}).filter(Boolean);
    if(lines.length){ tip.style.display='block'; tip.style.left=(ev.clientX+12)+'px'; tip.style.top=(ev.clientY+12)+'px';
      tip.innerHTML='<b>'+hit+'</b><br>'+lines.map(l=>l.replace(/</g,'&lt;')).join('<br>'); return; } }
  tip.style.display='none';
};
C.onmouseleave=()=>tip.style.display='none';

// legend
document.getElementById('legend').innerHTML =
  Object.entries(STATUS).map(([k,v])=>`<span><i class="dot" style="background:${v}"></i>${k}</span>`).join('')
  + ' &nbsp; ' + DATA.items.map(it=>`<span><i class="dot" style="background:${itemColor[it]}"></i>${DATA.titles[it]}</span>`).join('');

layout(); tick();
</script>
"""
