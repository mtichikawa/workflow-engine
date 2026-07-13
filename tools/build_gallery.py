"""Regenerate usecases/index.html from usecases/usecases.json — the single source of truth.

Compact accordion gallery. Each expanded card shows a MINI of that recipe's real graph, laid out and
routed by the SAME shared core the full explorers use (engine/graph_core.js) — identical node layout,
channel lanes, highways, loops, fork/join junctions — with dots flowing along the actual wires. The
core is inlined so the page stays self-contained.

    python tools/build_gallery.py
"""

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.explorer import build_graph  # noqa: E402

UC = ROOT / "usecases"

# slug -> (recipe ref, work-item noun) — the mini graph is generated from the real recipe
RECIPES = {
    "triage":  ("engine.recipes.triage:TRIAGE", "issue"),
    "content": ("engine.recipes.content:CONTENT", "topic"),
    "refine":  ("engine.recipes.refine:REFINE", "brief"),
}

HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Use cases — one engine, many recipes</title>
<style>
  :root{
    --bg:#0e1015; --panel:#191e26; --panel2:#1b202a; --line:#39424f; --line2:#4d5867;
    --ink:#eef1f6; --mut:#a7b0be; --dim:#79828f;
    --brass:#d0af62; --green:#57b083; --blue:#5b8fd6; --red:#cf6b5c;
    --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
    --sans:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.6}
  .wrap{max-width:820px;margin:0 auto;padding:26px 24px 80px}
  h1{font-family:var(--mono);font-size:clamp(24px,4vw,34px);font-weight:700;letter-spacing:-.01em;margin:0}
  .eyebrow{font-family:var(--mono);font-size:12px;letter-spacing:.2em;text-transform:uppercase;color:var(--brass);margin:0 0 12px}
  .lede{color:var(--mut);max-width:62ch;margin:14px 0 0}
  .lede b{color:var(--ink)}
  .cards{display:flex;flex-direction:column;gap:12px;margin-top:36px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden;transition:border-color .15s,box-shadow .15s}
  .card:hover{border-color:var(--line2)}
  .card.open{border-color:var(--brass);box-shadow:0 0 0 1px rgba(208,175,98,.25)}
  .chead{display:flex;align-items:baseline;gap:14px;padding:16px 20px;cursor:pointer;user-select:none}
  .chead h2{font-family:var(--mono);font-size:16px;margin:0;color:var(--ink);flex:none}
  .chead .sub{color:var(--mut);font-size:14px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .chead .chev{color:var(--mut);font-family:var(--mono);font-size:18px;line-height:1;transition:transform .25s,color .15s;flex:none;align-self:center}
  .card:hover .chev{color:var(--ink)}
  .card.open .chev{transform:rotate(90deg);color:var(--brass)}
  .cbody{display:grid;grid-template-rows:0fr;transition:grid-template-rows .3s ease}
  .card.open .cbody{grid-template-rows:1fr}
  .cinner{overflow:hidden;min-height:0}
  .cpad{padding:2px 20px 20px}
  .cpad .desc{color:var(--mut);font-size:14px;margin:0 0 12px}
  .mg{width:100%;height:auto;display:block;border-radius:8px;background:#101319;border:1px solid var(--line)}
  .reuse{font-family:var(--mono);font-size:12px;color:var(--mut);margin:12px 0 0}
  .reuse b{color:var(--ink);font-weight:600}
  .actions{margin-top:16px}
  a.btn{font-family:var(--mono);font-size:13px;text-decoration:none;padding:9px 16px;border-radius:7px;border:1px solid var(--brass);color:var(--brass)}
  a.btn:hover{color:#0e1015;background:var(--brass)}
  .back{font-family:var(--mono);font-size:13px;color:var(--mut);text-decoration:none}
  .back:hover{color:var(--ink)}
  /* top page-tabs (Overview · Use cases) — identical bar on both pages so they don't shift when you switch */
  .topbar-inner{max-width:940px;margin:0 auto;padding:16px 24px 0}
  .pagetabs{display:flex;gap:6px;font-family:var(--mono)}
  .pagetabs a{font-size:13px;padding:8px 16px;border-radius:8px;text-decoration:none;color:var(--mut);border:1px solid transparent;transition:color .15s,background .15s,border-color .15s}
  .pagetabs a:hover{color:var(--ink)}
  .pagetabs a.on{color:var(--ink);background:var(--panel);border-color:var(--brass)}
  footer{color:var(--dim);font-family:var(--mono);font-size:12px;margin-top:40px;border-top:1px solid var(--line);padding-top:20px}
</style>
</head>
<body>
<div class="topbar"><div class="topbar-inner">
  <nav class="pagetabs" aria-label="Pages">
    <a href="../">Overview</a>
    <a class="on" href="./" aria-current="page">Use cases</a>
  </nav>
</div></div>
<div class="wrap">
  <p class="eyebrow">the same engine, many recipes</p>
  <h1>Use cases</h1>
  <p class="lede">Each is a different job built from the <b>same shared library</b> of small AI
    specialists — only the middle differs. Expand one to watch its flow, then <b>explore the real run</b> step by step.</p>

  <div class="cards">
"""

FOOT = """  </div>

  <footer>one shared library · {n} recipes so far · each run is human-gated before anything happens</footer>
</div>
<script>
__GRAPH_CORE__
</script>
<script>
"use strict";
/* MINI of the real recipe graph — laid out + routed by the shared core (makeGraphCore), the exact same
   code the full explorers use. We render small SVG cards from the core's geometry and stream dots along
   route()'s real paths. Returns {start,stop}; only the open card animates. */
const NS="http://www.w3.org/2000/svg";
const el=(t,a)=>{const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);return e;};
const KC={in:"#5b8fd6",shared:"#7b9bc4",domain:"#d0af62",gate:"#d8944a",out:"#57b083"};
const HC={in:"#26384f",shared:"#2c3a49",domain:"#43391f",gate:"#432e18",out:"#213f30"};
function minigraph(svg, NODES, WIRES){
  const G=makeGraphCore(NODES, WIRES, {axisY:()=>0});   // explorer's exact proportions → wires identical, just scaled by viewBox
  G.computeRouting();
  const g=G.computeGeom(null);
  // frame exactly to the nodes AND every routed wire point (so loop highways fit with no wasted band)
  let x0=1e9,y0=1e9,x1=-1e9,y1=-1e9;
  NODES.forEach(n=>{const b=g[n.id]; x0=Math.min(x0,b.x);y0=Math.min(y0,b.y);x1=Math.max(x1,b.x+b.w);y1=Math.max(y1,b.y+b.h);});
  const routes=WIRES.map((_,i)=>G.route(i,g));
  routes.forEach(pts=>pts.forEach(p=>{ x0=Math.min(x0,p.x);y0=Math.min(y0,p.y);x1=Math.max(x1,p.x);y1=Math.max(y1,p.y); }));
  const P=16; svg.setAttribute("viewBox",`${x0-P} ${y0-P} ${x1-x0+2*P} ${y1-y0+2*P}`);
  // z-order: wires < dots < junctions < nodes — so cards occlude any wire/dot passing behind them
  const gW=el("g",{}),gP=el("g",{}),gJ=el("g",{}),gN=el("g",{}); svg.append(gW,gP,gJ,gN);
  // wires (real routed paths, colored by topology exactly like the explorer)
  const paths=[];
  routes.forEach((pts,i)=>{ const [c,op,dash]=G.WCOL[G.wtopo[i]]||G.WCOL.data;
    const p=el("path",{d:G.roundedPath(pts),fill:"none",stroke:c,"stroke-width":2.2,opacity:Math.max(+op,.42)});
    if(+dash)p.setAttribute("stroke-dasharray","6 4"); gW.appendChild(p);
    paths.push({el:p,len:0,dots:[]}); });
  // fork/join junctions
  G.junctions.forEach(j=>{ const p=G.juncPoint(j,g);
    gJ.appendChild(el("path",{d:`M ${p.x} ${p.y} L ${p.jx} ${p.y}`,stroke:j.col,"stroke-width":2.4,fill:"none",opacity:.85}));
    gJ.appendChild(el("circle",{cx:p.jx,cy:p.y,r:3.4,fill:j.col})); });
  // nodes: the explorer's card — header + specialist name + socket dots (same proportions, just scaled)
  const HH=G.HEAD;
  NODES.forEach(n=>{ const b=g[n.id], c=KC[n.kind]||"#7b9bc4", hc=HC[n.kind]||"#333a45";
    const r=el("rect",{x:b.x,y:b.y,width:b.w,height:b.h,rx:7,fill:"#2a2f38",stroke:c,"stroke-width":1.5});
    if(n.kind==="gate")r.setAttribute("stroke-dasharray","6 4"); gN.appendChild(r);
    gN.appendChild(el("rect",{x:b.x+1.5,y:b.y+1.5,width:b.w-3,height:HH-3,rx:5.5,fill:hc}));
    const t=el("text",{x:b.x+11,y:b.y+HH*0.63,fill:"#fff","font-family":"ui-monospace,Menlo,monospace","font-size":13,"font-weight":700}); t.textContent=n.title||n.id; gN.appendChild(t);
    G.socketsOf(n).forEach(s=>{ const x=s.io==="out"?b.x+b.w:b.x;
      gN.appendChild(el("circle",{cx:x,cy:b.y+s.y,r:3.8,fill:s.io==="out"?c:"#828b99",stroke:"#14171c","stroke-width":1.5})); }); });
  // dots ride the real routed paths
  let raf=0,last=0,acc=0;
  function frame(ts){ if(!last)last=ts; const dt=Math.min(.05,(ts-last)/1000); last=ts;
    acc-=dt; if(acc<=0){ acc=.16; for(const pp of paths){ if(pp.dots.length<3 && Math.random()<.5) pp.dots.push({f:0}); } }
    while(gP.firstChild) gP.removeChild(gP.firstChild);
    for(const pp of paths){ if(!pp.len) pp.len=pp.el.getTotalLength(); if(!pp.len) continue;
      pp.dots=pp.dots.filter(d=>d.f<=1);
      for(const d of pp.dots){ d.f+=dt*0.5; if(d.f>1) continue; const q=pp.el.getPointAtLength(d.f*pp.len);
        gP.appendChild(el("circle",{cx:q.x.toFixed(1),cy:q.y.toFixed(1),r:3.3,fill:"#cfe0f5"})); } }
    raf=requestAnimationFrame(frame); }
  return { start(){ if(!raf){ last=0; raf=requestAnimationFrame(frame); } }, stop(){ cancelAnimationFrame(raf); raf=0; } };
}
const anims=new Map();
document.querySelectorAll(".card").forEach(card=>{
  const svg=card.querySelector("svg.mg");
  if(svg){ const g=JSON.parse(svg.dataset.graph); anims.set(card, minigraph(svg, g.nodes, g.wires)); }
  card.querySelector(".chead").addEventListener("click",()=>{
    const open=card.classList.contains("open");
    document.querySelectorAll(".card.open").forEach(x=>{ x.classList.remove("open"); anims.get(x)?.stop(); });
    if(!open){ card.classList.add("open"); requestAnimationFrame(()=>anims.get(card)?.start()); }
  });
});
</script>
</body>
</html>
"""


def _split_title(title):
    for sep in (" — ", " - "):
        if sep in title:
            head, sub = title.split(sep, 1)
            return head, sub
    return title, ""


def _graph(slug, work_item):
    ref, _ = RECIPES[slug]
    mod, name = ref.split(":")
    recipe = getattr(importlib.import_module(mod), name)
    g = build_graph(recipe, work_item)
    nodes = []
    for n in g["nodes"]:
        title = f"the {work_item}" if n["kind"] == "in" else "staged" if n["kind"] == "out" else n["id"]
        nodes.append({"id": n["id"], "kind": n["kind"], "col": n["col"],
                      "outs": n["outs"], "ins": n["ins"], "title": title})
    wires = []
    for w in g["wires"]:
        a = [w["src"], w["srcSock"], w["dst"], w["dstSock"]]
        if w["type"] != "data":
            a.append(w["type"])
        wires.append(a)
    return {"nodes": nodes, "wires": wires}


def _custom(flow):
    stages = [c for c in flow if c["k"] != "loop"]
    return [c["s"] for c in stages if c["k"] == ""], len(stages)


def _card(uc, first):
    slug = uc["slug"]
    head, sub = _split_title(uc["title"])
    href = f"{slug}/index.html" if uc.get("explorer") else f"{slug}/replay.html"
    custom, n = _custom(uc["flow"])
    reuse = f"<b>{n - len(custom)} of {n}</b> steps reused from the library &nbsp;·&nbsp; custom for this job: <b>{', '.join(custom) or 'none'}</b>"
    graph = json.dumps(_graph(slug, RECIPES[slug][1]), ensure_ascii=False)
    return f"""    <div class="card">
      <div class="chead">
        <h2>{head}</h2>
        <span class="sub">{sub}</span>
        <span class="chev">▸</span>
      </div>
      <div class="cbody"><div class="cinner"><div class="cpad">
        <p class="desc">{uc["tagline"]}</p>
        <svg class="mg" preserveAspectRatio="xMidYMid meet" data-graph='{graph}'></svg>
        <p class="reuse">{reuse}</p>
        <div class="actions"><a class="btn" href="{href}">explore step by step →</a></div>
      </div></div></div>
    </div>
"""


def build():
    data = json.loads((UC / "usecases.json").read_text())
    cases = data["usecases"]
    core = (ROOT / "engine" / "graph_core.js").read_text()
    html = HEAD + "\n".join(_card(uc, i == 0) for i, uc in enumerate(cases)) + FOOT.replace("{n}", str(len(cases)))
    html = html.replace("__GRAPH_CORE__", core)
    (UC / "index.html").write_text(html)
    print(f"built usecases/index.html — {len(cases)} use cases: {', '.join(c['slug'] for c in cases)}")


if __name__ == "__main__":
    build()
