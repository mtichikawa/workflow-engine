// graph_core.js — shared layout + orthogonal routing for the recipe graph.
//
// Used by BOTH the full explorer (engine/explorer_engine.html) and the gallery mini
// (tools/build_gallery.py), inlined into each at build time so both stay self-contained.
// Pure geometry + routing: no DOM, no window references (the viewport axis comes in via cfg).
//
//   const G = makeGraphCore(NODES, WIRES, {axisY:()=>innerHeight/2, detailPx});
//   G.computeRouting();                       // decide routes (needs card heights measured first)
//   const geom = G.computeGeom(expandedId);   // laid-out boxes {x,y,w,h} per node id
//   const d    = G.roundedPath(G.route(i, geom));   // an SVG path for wire i in that geometry
//
// NODES: [{id, kind, col, outs:[sock…], ins:[sock…], sub?, w0?}]
// WIRES: [[srcId, srcSock, dstId, dstSock, type?]]   type: "gate" | "loop" | (absent = data)
function makeGraphCore(NODES, WIRES, cfg){
  cfg = Object.assign({
    W:160, WEXP:360, HEAD:27, SUBH:23, ROW:23, PAD:7, R:9,
    MX:60, COLGAP:124, HGAP:22, LANE:10, VGAP:34, FORK:22, CLEAR:16,
    detailPx:{}, axisY:function(){ return 300; }
  }, cfg||{});
  const {W,WEXP,HEAD,SUBH,ROW,PAD,R,MX,COLGAP,HGAP,LANE,VGAP,FORK,CLEAR}=cfg;
  const detailPx=cfg.detailPx;

  const headH=n=>HEAD+(n.sub?SUBH:0);   // header (+ optional always-visible subtitle) before the sockets
  const wBase=n=>n.w0||W;
  const rowsOf=n=>n.outs.length+n.ins.length;   // gate sockets are regular ins (named "when …")
  const socketH=n=>headH(n)+rowsOf(n)*ROW+PAD;
  const heightOf=(n,exp)=> socketH(n) + (exp?(detailPx[n.id]||0):0);
  function socketsOf(n){ const l=[]; let r=0; const y0=headH(n);
    n.outs.forEach(o=>{l.push({name:o,io:"out",side:"EAST",y:y0+(r+.5)*ROW});r++;});
    n.ins.forEach(i=>{l.push({name:i,io:"in",side:"WEST",y:y0+(r+.5)*ROW});r++;});
    return l; }

  const wtype=WIRES.map(w=>w[4]||"data");   // control type: "data" | "gate" | "loop"
  // topology of the plain data wires: a source socket feeding >1 dest = split (fan-out); a dest socket fed by >1 = merge (fan-in)
  const _sN={}, _dN={};
  WIRES.forEach(w=>{ if((w[4]||"data")!=="data") return; const s=w[0]+"."+w[1], d=w[2]+"."+w[3]; _sN[s]=(_sN[s]||0)+1; _dN[d]=(_dN[d]||0)+1; });
  const wtopo=WIRES.map(w=>{ const t=w[4]||"data"; if(t!=="data") return t;
    if(_dN[w[2]+"."+w[3]]>1) return "merge"; if(_sN[w[0]+"."+w[1]]>1) return "split"; return "data"; });
  const WCOL={gate:["#c9a860",".82",1], loop:["#cf7a68",".85",1], merge:["#a986d6",".62",0], split:["#54b4a2",".58",0], data:["#b7c0cf",".3",0]};

  const colOf=Object.fromEntries(NODES.map(n=>[n.id,n.col]));
  const socketRel={}; NODES.forEach(n=>{ socketRel[n.id]={}; socketsOf(n).forEach(s=>socketRel[n.id][s.name+"."+s.io]=s.y); });
  const cols={}; NODES.forEach(n=>(cols[n.col]=cols[n.col]||[]).push(n));
  const colIdx=Object.keys(cols).map(Number).sort((a,b)=>a-b);

  // self-layout: each column centered on one axis (single cards sit dead-center, grow symmetrically)
  function computeGeom(expId){
    const wOf=n=> expId===n.id?WEXP:wBase(n), hOf=n=> heightOf(n,expId===n.id);
    const colW={}; colIdx.forEach(c=> colW[c]=Math.max(...cols[c].map(wOf)));
    const colX={}; let x=MX; colIdx.forEach(c=>{ colX[c]=x; x+=colW[c]+COLGAP; });
    const axisY=cfg.axisY(), g={};
    colIdx.forEach(c=>{ const list=cols[c];
      const total=list.reduce((s,n)=>s+hOf(n),0)+VGAP*(list.length-1);
      let y=axisY-total/2;
      list.forEach(n=>{ g[n.id]={x:colX[c],y,w:wOf(n),h:hOf(n)}; y+=hOf(n)+VGAP; }); });
    return g;
  }
  function sock(id,name,io,g){ const b=g[id]; return {x: io==="out"? b.x+b.w : b.x, y: b.y+socketRel[id][name+"."+io]}; }
  function colRight(c,g){ let m=-1e9; NODES.forEach(n=>{if(n.col===c)m=Math.max(m,g[n.id].x+g[n.id].w);}); return m; }
  function colLeft(c,g){ let m=1e9; NODES.forEach(n=>{if(n.col===c)m=Math.min(m,g[n.id].x);}); return m; }
  function channelX(k,g){ return (colRight(k,g)+colLeft(k+1,g))/2; }
  function clearH(y,x1,x2,cs,ct,g){ const lo=Math.min(x1,x2),hi=Math.max(x1,x2);
    for(const n of NODES){ if(n.col<=cs||n.col>=ct) continue; const b=g[n.id];
      if(y>b.y-CLEAR&&y<b.y+b.h+CLEAR&&b.x<hi&&b.x+b.w>lo) return false; } return true; }
  function band(cs,ct,g){ let top=1e9,bot=-1e9; NODES.forEach(n=>{ if(n.col<=cs||n.col>=ct)return; const b=g[n.id]; top=Math.min(top,b.y); bot=Math.max(bot,b.y+b.h); }); return {top,bot}; }

  // routing decided ONCE, but each wire's path is chosen clear across EVERY reachable state (collapsed +
  // each single-card expansion). So decisions never change between states → no snap, no fold — never grazes
  // a card. Must run after card heights are measured (needs the expanded geometries).
  let DEC=[], OFF={};
  function computeRouting(){
    const states=[computeGeom(null)].concat(NODES.map(n=>computeGeom(n.id)));
    const base=states[0];
    const clearAllStates=(w,which)=> states.every(g=>{ const a=sock(w[0],w[1],"out",g),b=sock(w[2],w[3],"in",g),cs=colOf[w[0]],ct=colOf[w[2]];
      return clearH(which==="a"?a.y:b.y,a.x,b.x,cs,ct,g); });
    DEC=WIRES.map(w=>{ const cs=colOf[w[0]],ct=colOf[w[2]];
      if(ct-cs<=1) return {t:"vnt"};
      if(clearAllStates(w,"a")) return {t:"vnt"};
      if(clearAllStates(w,"b")) return {t:"vns"};
      const a=sock(w[0],w[1],"out",base),b=sock(w[2],w[3],"in",base),bd=band(cs,ct,base);
      return {t:"hwy",side:(Math.min(a.y,b.y)-bd.top)<=(bd.bot-Math.max(a.y,b.y))?"above":"below"}; });
    OFF={}; WIRES.forEach((_,i)=>OFF[i]={a:0,b:0,hy:0});
    const vsegs=[];
    WIRES.forEach((w,i)=>{ const cs=colOf[w[0]],ct=colOf[w[2]],d=DEC[i], a=sock(w[0],w[1],"out",base),b=sock(w[2],w[3],"in",base),mid=(a.y+b.y)/2;
      if(d.t==="vnt") vsegs.push({i,ch:ct-1,mid,slot:"a"});
      else if(d.t==="vns") vsegs.push({i,ch:cs,mid,slot:"a"});
      else { vsegs.push({i,ch:cs,mid,slot:"a"}); vsegs.push({i,ch:ct-1,mid,slot:"b"}); } });
    const byCh={}; vsegs.forEach(s=>(byCh[s.ch]=byCh[s.ch]||[]).push(s));
    Object.values(byCh).forEach(list=>{ list.sort((p,q)=>p.mid-q.mid); const n=list.length; list.forEach((s,k)=> OFF[s.i][s.slot]=(k-(n-1)/2)*LANE); });
    ["above","below"].forEach(side=>{ const list=WIRES.map((w,i)=>({i,d:DEC[i]})).filter(x=>x.d.t==="hwy"&&x.d.side===side);
      list.sort((p,q)=> sock(WIRES[p.i][0],WIRES[p.i][1],"out",base).y - sock(WIRES[q.i][0],WIRES[q.i][1],"out",base).y);
      list.forEach((x,k)=> OFF[x.i].hy=k*LANE); });
  }
  let _li=0; const LOOPOFF=WIRES.map(w=>w[4]==="loop"?(_li++)*15:0);   // stack multiple loops
  function route(i,g){ const w=WIRES[i], dec=DEC[i], o=OFF[i],
    a=sock(w[0],w[1],"out",g), b=sock(w[2],w[3],"in",g), cs=colOf[w[0]], ct=colOf[w[2]];
    if(wtype[i]==="loop"){                                             // feedback: route up and over EVERYTHING, back into the target
      const stub=22+LOOPOFF[i], top=Math.min(...NODES.map(n=>g[n.id].y))-44-LOOPOFF[i];
      return [a,{x:a.x+stub,y:a.y},{x:a.x+stub,y:top},{x:b.x-stub,y:top},{x:b.x-stub,y:b.y},b]; }
    // split source / merge dest: start/end at a fork/join junction so the branch is visible
    const aa=(_sN[w[0]+"."+w[1]]>1)?{x:a.x+FORK,y:a.y}:a, bb=(_dN[w[2]+"."+w[3]]>1)?{x:b.x-FORK,y:b.y}:b;
    // straight shot only when nothing forces a detour — a highway means the direct line is blocked
    if(Math.abs(aa.y-bb.y)<0.5 && dec.t!=="hwy") return [aa,bb];
    if(dec.t==="vnt"){ const lx=channelX(ct-1,g)+o.a; return [aa,{x:lx,y:aa.y},{x:lx,y:bb.y},bb]; }
    if(dec.t==="vns"){ const lx=channelX(cs,g)+o.a; return [aa,{x:lx,y:aa.y},{x:lx,y:bb.y},bb]; }
    const l1=channelX(cs,g)+o.a, l2=channelX(ct-1,g)+o.b, bd=band(cs,ct,g),
      hY=dec.side==="above"?bd.top-HGAP-o.hy:bd.bot+HGAP+o.hy;
    return [aa,{x:l1,y:aa.y},{x:l1,y:hY},{x:l2,y:hY},{x:l2,y:bb.y},bb]; }

  function roundedPath(pts){
    const q=[pts[0]]; for(let i=1;i<pts.length;i++){const a=q[q.length-1],b=pts[i]; if(Math.abs(a.x-b.x)>.5||Math.abs(a.y-b.y)>.5)q.push(b);}
    if(q.length<2) return `M ${pts[0].x} ${pts[0].y}`;
    let d=`M ${q[0].x} ${q[0].y}`;
    for(let i=1;i<q.length-1;i++){const p0=q[i-1],p1=q[i],p2=q[i+1];
      const d1x=Math.sign(p1.x-p0.x),d1y=Math.sign(p1.y-p0.y),d2x=Math.sign(p2.x-p1.x),d2y=Math.sign(p2.y-p1.y);
      const r=Math.min(R,Math.hypot(p1.x-p0.x,p1.y-p0.y)/2,Math.hypot(p2.x-p1.x,p2.y-p1.y)/2);
      d+=` L ${p1.x-d1x*r} ${p1.y-d1y*r} Q ${p1.x} ${p1.y} ${p1.x+d2x*r} ${p1.y+d2y*r}`;}
    const l=q[q.length-1]; d+=` L ${l.x} ${l.y}`; return d; }

  // fork/join junctions: where a socket fans out (split) or fans in (merge) — a dot + short trunk
  const junctions=[]; { const _js=new Set();
    WIRES.forEach(w=>{ if((w[4]||"data")!=="data") return; const sk=w[0]+"."+w[1], dk=w[2]+"."+w[3];
      if(_sN[sk]>1 && !_js.has("o"+sk)){ _js.add("o"+sk); junctions.push({node:w[0],sock:w[1],io:"out",col:WCOL.split[0]}); }
      if(_dN[dk]>1 && !_js.has("i"+dk)){ _js.add("i"+dk); junctions.push({node:w[2],sock:w[3],io:"in",col:WCOL.merge[0]}); } }); }
  function juncPoint(j,g){ const p=sock(j.node,j.sock,j.io,g); return {x:p.x, y:p.y, jx: j.io==="out"?p.x+FORK:p.x-FORK}; }

  return { NODES, WIRES, FORK, R, HEAD, ROW, WCOL,
    socketsOf, socketRel, heightOf, socketH, sock,
    wtype, wtopo, colOf, computeGeom, channelX, band,
    computeRouting, route, roundedPath, junctions, juncPoint, LOOPOFF,
    _sN, _dN, get DEC(){return DEC;}, get OFF(){return OFF;} };
}
if (typeof module!=="undefined" && module.exports) module.exports={makeGraphCore};
