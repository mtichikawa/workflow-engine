"""Field extraction from phone photos of insurance cards — how often is each field right, and is a field
that isn't on the card left empty rather than guessed?

    python evals/extraction.py make     # dev tools (playwright, pillow, numpy): render 30 SYNTHETIC cards
    python evals/extraction.py score    # read each photo with the care-intake demo's own steps, score fields
    ... make stress / score stress      # 15 more, photographed badly on purpose

The cards are generated, so the right answer for every field is known by construction (truth.jsonl) — no
labeller. Three layouts, varied names, ID formats and dates; some cards leave out the group number or the
pharmacy lines; every card is photographed on a table with the demo's perspective / glare / JPEG
degradation, a third of them harder (lower quality, more blur, steeper angle). Scored with the demo's
read_document (the model reads the photo) then fill_form (fields from the transcript).
"""

from __future__ import annotations

import io
import json
import random
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DIR = ROOT / "evals/extraction-set"
N = 30

FIELDS = [
    {"name": "member_first", "type": "text", "hint": "member's first name"},
    {"name": "member_last", "type": "text", "hint": "member's last name (family name)"},
    {"name": "member_id", "type": "text", "hint": "member / subscriber ID, exactly as printed"},
    {"name": "dob", "type": "date", "hint": "member's date of birth"},
    {"name": "effective_date", "type": "date", "hint": "coverage effective date"},
    {"name": "group_number", "type": "text", "hint": "group number, exactly as printed"},
    {"name": "rx_bin", "type": "text", "hint": "pharmacy RxBIN"},
    {"name": "rx_pcn", "type": "text", "hint": "pharmacy RxPCN"},
    {"name": "plan_name", "type": "text", "hint": "the health plan's name"},
    {"name": "member_services_phone", "type": "text", "hint": "member services phone number"},
]

FIRST = ["Maria", "José", "Aaliyah", "Nguyen", "Siobhan", "Olusegun", "Kateryna", "Mei-Ling", "Darnell", "Inés",
         "Priya", "Tomasz", "Zoë", "Abdirahman", "Luz", "Hannah", "Kwame", "Yesenia", "Björn", "Fatima"]
LAST = ["Delgado-Ruiz", "O'Connell", "Nakamura", "Abernathy", "Nwosu", "Kowalczyk", "Ramírez", "Thibodeaux",
        "Haddad", "Van der Berg", "Okafor", "Lindqvist", "MacPherson", "Achterberg", "Quiñones", "St. Clair"]
PLANS = ["Demo Health Plan", "Cascade Community Care", "Sunrise Medicaid Partners", "Harbor Family Health",
         "Lakeside Health Alliance", "Prairie State Medi-Plan"]


def _card(rng: random.Random, i: int) -> dict:
    first, last = rng.choice(FIRST), rng.choice(LAST)
    fmt = i % 3
    mid = ["", f"{rng.choice('ABCDEJLMR')}"][rng.random() < 0.5]
    dob = f"{rng.randint(1975, 2006)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
    eff = f"{rng.choice([2025, 2026])}-{rng.choice([1, 1, 1, 4, 7, 10]):02d}-01"
    member_id = [lambda: f"9{rng.randint(10**8, 10**9 - 1)}",
                 lambda: f"{rng.choice('ABCDEHKMW')}{rng.choice('ABCDEHKMW')}{rng.randint(10**7, 10**8 - 1)}",
                 lambda: f"{rng.randint(100, 999)}-{rng.randint(10, 99)}-{rng.randint(1000, 9999)}"][rng.randrange(3)]()
    no_group = rng.random() < 0.3
    no_rx = rng.random() < 0.25
    return {"id": f"card{i + 1:02d}", "layout": fmt, "hard": i % 3 == 2, "member_first": first, "member_middle": mid,
            "member_last": last, "member_id": member_id, "dob": dob, "effective_date": eff,
            "group_number": None if no_group else f"{rng.choice(['G', 'GRP', ''])}{rng.randint(1000, 99999)}",
            "rx_bin": None if no_rx else f"{rng.randint(0, 999999):06d}",
            "rx_pcn": None if no_rx else rng.choice(["MCAIDPROD", "ADV", "DEMORX", "CASCRX", "9999"]),
            "plan_name": rng.choice(PLANS),
            "member_services_phone": f"1-555-01{rng.randint(0, 9)}-{rng.randint(1000, 9999)}"}


def _us(d: str) -> str:
    y, m, dd = d.split("-")
    return f"{m}/{dd}/{y}"


def _html(c: dict) -> str:
    name = f"{c['member_first']} {c['member_middle'] + ' ' if c['member_middle'] else ''}{c['member_last']}"
    rx = (f"RxBIN {c['rx_bin']} &nbsp; RxPCN {c['rx_pcn']}" if c["rx_bin"] else "Pharmacy benefits: see plan website")
    grp = f"<div><span class=l>GROUP</span><br><b>{c['group_number']}</b></div>" if c["group_number"] else ""
    if c["layout"] == 0:                     # the demo's teal card
        return f"""<div class=card style="background:linear-gradient(135deg,#0f5d6b,#13808f 60%,#7cc4c7);color:#fff;font-family:Arial">
<style>.l{{color:#555;font-size:19px}}</style>
<div style="font:bold 42px Georgia">{c['plan_name']}</div>
<div style="background:rgba(255,255,255,.95);color:#111;border-radius:12px;margin-top:18px;padding:18px 26px;font-size:26px;line-height:1.45">
 <div><span class=l>MEMBER NAME</span><br><b style="font-size:34px">{name.upper()}</b></div>
 <div style="display:flex;gap:40px;margin-top:8px"><div><span class=l>MEMBER ID</span><br><b>{c['member_id']}</b></div>
  <div><span class=l>DATE OF BIRTH</span><br><b>{_us(c['dob'])}</b></div><div><span class=l>EFFECTIVE</span><br><b>{_us(c['effective_date'])}</b></div>{grp}</div></div>
<div style="margin-top:16px;font-size:21px;line-height:1.5">{rx}<br>Member Services {c['member_services_phone']} (TTY 711)</div></div>"""
    if c["layout"] == 1:                     # white, label: value rows, ID first
        rows = [("ID#", c["member_id"]), ("Subscriber", f"{c['member_last'].upper()}, {c['member_first'].upper()} {c['member_middle']}".strip()),
                ("DOB", _us(c["dob"])), ("Eff. Date", _us(c["effective_date"]))]
        if c["group_number"]:
            rows.append(("Grp", c["group_number"]))
        if c["rx_bin"]:
            rows += [("BIN", c["rx_bin"]), ("PCN", c["rx_pcn"])]
        return f"""<div class=card style="background:#fff;color:#1a1a1a;font-family:Helvetica,Arial;border:2px solid #d0d0d0">
<div style="display:flex;justify-content:space-between;border-bottom:4px solid #c2410c;padding-bottom:10px">
 <b style="font-size:36px;color:#c2410c">{c['plan_name']}</b><span style="font-size:18px;color:#666">Member ID Card</span></div>
<table style="font-size:25px;margin-top:14px;border-collapse:collapse">{''.join(f'<tr><td style="color:#666;padding:3px 26px 3px 0">{k}</td><td><b>{v}</b></td></tr>' for k, v in rows)}</table>
<div style="position:absolute;bottom:40px;font-size:19px;color:#444">Questions? Call {c['member_services_phone']}</div></div>"""
    lines = [f"<div style='font-size:31px'><b>{c['member_first']} {c['member_last']}</b></div>",   # dark, dense
             f"<div>Member {c['member_id']} &nbsp;·&nbsp; Born {_us(c['dob'])}</div>",
             f"<div>Coverage from {_us(c['effective_date'])}" + (f" &nbsp;·&nbsp; Group {c['group_number']}" if c["group_number"] else "") + "</div>",
             f"<div style='font-size:20px;margin-top:8px'>{rx}</div>"]
    return f"""<div class=card style="background:#1f2937;color:#f3f4f6;font-family:Verdana,Arial;font-size:23px;line-height:1.55">
<div style="display:flex;justify-content:space-between"><b style="font-size:30px;color:#fbbf24">{c['plan_name']}</b><span style="font-size:17px">MEDICAID</span></div>
<div style="margin-top:22px">{''.join(lines)}</div>
<div style="position:absolute;bottom:38px;font-size:18px;color:#d1d5db">Member Services: {c['member_services_phone']} · Emergency? Call 911</div></div>"""


# "stress": 15 more cards, photographed badly on purpose — small, blurred, heavily compressed, steep —
# to find where reading breaks (the normal set scored perfectly, which says it was too easy).
TIERS = {"normal": (N, 20261014, ""), "stress": (15, 20261015, "stress"),
         "stress2": (20, 20261016, "stressb")}         # fresh bad photos, made after the reader was changed


def make(tier: str = "normal") -> None:
    from PIL import Image, ImageFilter
    from playwright.sync_api import sync_playwright
    from engine.live.care_intake.make_documents import _card_html, _photo
    n, seed, prefix = TIERS[tier]
    rng = random.Random(seed)
    DIR.mkdir(parents=True, exist_ok=True)
    cards = [_card(rng, i) for i in range(n)]
    for c in cards:
        if prefix:
            c["id"], c["hard"] = f"{prefix}{c['id'][4:]}", True
    suffix = "" if tier == "normal" else f"-{tier}"
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        pg = br.new_page(viewport={"width": 1012, "height": 638})
        for c in cards:
            mark = ("<div style='position:absolute;right:40px;bottom:12px;font:13px Arial;opacity:.75'>"
                    "SYNTHETIC TEST CARD · not a real member or plan</div></div>")
            pg.set_content(_card_html(_html(c)[:-6] + mark).replace(".card{", ".card{position:relative;"))
            shot = pg.locator(".card").screenshot(omit_background=True)
            if prefix:                                   # stress: steep, small, blurred, heavily compressed
                jpg = _photo(shot, rng, rng.choice([-1, 1]) * rng.uniform(15, 28))
                im = Image.open(io.BytesIO(jpg)).resize((640, 480)).filter(ImageFilter.GaussianBlur(1.6))
                im.save(DIR / f"{c['id']}.jpg", "JPEG", quality=30)
                continue
            jpg = _photo(shot, rng, rng.uniform(-14, 14) if c["hard"] else rng.uniform(-6, 6))
            im = Image.open(io.BytesIO(jpg)).resize((1200, 900))
            if c["hard"]:
                im = im.filter(ImageFilter.GaussianBlur(1.3))
            im.save(DIR / f"{c['id']}.jpg", "JPEG", quality=48 if c["hard"] else 72)
        br.close()
    (DIR / f"truth{suffix}.jsonl").write_text(
        "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cards))
    print(f"wrote {len(cards)} cards to {DIR}")


def _norm(v) -> str | None:
    if v in (None, ""):
        return None
    s = str(v).strip().lower()
    s = re.sub(r"[\s\-().·]", "", s)
    return s or None


def score(tier: str = "normal") -> None:
    from engine import specialists  # noqa: F401
    from engine.core import get
    from engine.live import care_intake
    care_intake.load()                                   # registers read_document / fill_form
    from evals.blind import pmap, rate
    suffix = "" if tier == "normal" else f"-{tier}"
    truth = [json.loads(l) for l in (DIR / f"truth{suffix}.jsonl").read_text().splitlines() if l.strip()]
    reader, filler = get("read_document"), get("fill_form")

    def one(c):
        text = reader.run({"files": [str(DIR / f"{c['id']}.jpg")]}, {})["text"]
        got = filler.run({"documents": {"insurance card (photo)": text}, "fields": FIELDS}, {})["fields"]
        return {f["name"]: got[f["name"]]["value"] for f in FIELDS}

    t0 = time.time()
    outs = pmap(one, truth, workers=6)
    per_field, rows = {}, []
    for c, o in zip(truth, outs):
        if "error" in o and len(o) == 1:
            rows.append({"id": c["id"], "error": o["error"]})
            continue
        row = {"id": c["id"], "hard": c["hard"], "layout": c["layout"], "fields": {}}
        for f in FIELDS:
            want, have = c[f["name"]], o.get(f["name"])
            ok = _norm(want) == _norm(have)
            kind = "absent" if want is None else "present"
            per_field.setdefault(f["name"], []).append((ok, kind))
            row["fields"][f["name"]] = {"want": want, "got": have, "ok": ok}
        rows.append(row)
    allf = [x for v in per_field.values() for x in v]
    present = [ok for ok, k in allf if k == "present"]
    printed = [x for r in rows if "fields" in r for x in r["fields"].values() if x["want"] is not None]
    misread = sum(1 for x in printed if not x["ok"] and x["got"] is not None)
    blank = sum(1 for x in printed if x["got"] is None)
    absent = [ok for ok, k in allf if k == "absent"]
    done = [r for r in rows if "fields" in r]
    perfect = [all(x["ok"] for x in r["fields"].values()) for r in done]
    hard = [ok for r in done if r["hard"] for ok in (x["ok"] for x in r["fields"].values())]
    easy = [ok for r in done if not r["hard"] for ok in (x["ok"] for x in r["fields"].values())]
    res = {"what": f"{len(truth)} generated SYNTHETIC insurance-card photos ({tier}); truth known by construction",
           "pipeline": "read_document (model reads the photo) -> fill_form", "cards": len(truth),
           "errors": sum(1 for r in rows if "error" in r),
           "fields printed on the card, read exactly right": rate(sum(present), len(present)),
           "fields NOT on the card, left empty (not guessed)": rate(sum(absent), len(absent)),
           "printed fields MISREAD (a wrong value given)": rate(misread, len(printed)),
           "printed fields left empty (unreadable or missed)": rate(blank, len(printed)),
           "cards with every field right": rate(sum(perfect), len(perfect)),
           "harder photos, fields right": rate(sum(hard), len(hard)),
           "normal photos, fields right": rate(sum(easy), len(easy)),
           "by field": {k: rate(sum(ok for ok, _ in v), len(v)) for k, v in per_field.items()},
           "seconds": round(time.time() - t0, 1), "measured": time.strftime("%Y-%m-%d %H:%M %Z"), "items": rows}
    (ROOT / f"evals/blind-results/extraction{suffix}.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(json.dumps({k: v for k, v in res.items() if k not in ("items", "by field")}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    {"make": make, "score": score}[sys.argv[1]](*sys.argv[2:])
