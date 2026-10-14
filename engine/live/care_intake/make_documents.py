"""Generate the case's SYNTHETIC documents as the real artifacts would arrive.

    pip install playwright pillow && python -m playwright install chromium     # dev-only tools
    python -m engine.live.care_intake.make_documents

Each document is laid out as HTML, rendered by headless Chromium, then degraded the way the real thing
is: the referral becomes a 1-bit, slightly skewed fax with a machine header on every page, saved as an
image-only PDF (no text layer — a model has to read it); the insurance card becomes two phone photos on
a table, with perspective, glare and JPEG compression; the intake form and the billing guide stay
digital PDFs. The outputs are committed, so the demo itself needs none of these tools.
"""

from __future__ import annotations

import html
import io
import math
import random

from .documents import DOCS_DIR, MESSAGE, MIDWIFE, PATIENT, PLAN, PRACTICE, VISIT_LOG

FAX_W, FAX_H = 1728, 2200          # fax "fine" mode, US letter: 204 x 196 dpi
FOOT = "SYNTHETIC DEMO DOCUMENT — not a real patient, provider or plan"

_BASE_CSS = """
*{box-sizing:border-box} body{margin:0;background:#fff;color:#111}
"""


# ---------------------------------------------------------------- layouts (HTML)
def _fax_cover() -> str:
    m, p = MIDWIFE, PRACTICE
    return f"""<div class=pg style="font-family:Arial;padding:70px 90px">
<div style="display:flex;justify-content:space-between;border-bottom:3px solid #000;padding-bottom:14px">
 <div><div style="font:bold 34px Georgia">{m['practice']}</div>
 <div style="font-size:17px;margin-top:6px">{m['address']}<br>Tel {m['phone']} &nbsp;·&nbsp; Fax {m['fax']}</div></div>
 <div style="font:bold 64px Arial;letter-spacing:6px">FAX</div></div>
<table style="width:100%;margin-top:34px;font-size:21px;border-collapse:collapse">
 <tr><td style="width:150px;padding:9px 0"><b>To:</b></td><td>{p['name']} — Intake</td><td style="width:120px"><b>Fax:</b></td><td>{p['fax']}</td></tr>
 <tr><td style="padding:9px 0"><b>From:</b></td><td>{m['name']}</td><td><b>Date:</b></td><td>10/08/2026</td></tr>
 <tr><td style="padding:9px 0"><b>Re:</b></td><td>Doula recommendation — D. Morales</td><td><b>Pages:</b></td><td>2 (incl. cover)</td></tr>
</table>
<div style="margin-top:30px;font-size:21px"><b>[ ] Urgent &nbsp; [X] For review &nbsp; [ ] Please reply</b></div>
<div style="margin-top:36px;font-size:21px"><b>Comments:</b></div>
<div style="margin-top:12px;font:30px 'Courier 10 Pitch',monospace;line-height:1.5;transform:rotate(-1.2deg)">
Pt requesting doula support — G1P0, 34 wks.<br>Rec form attached. Please call pt to schedule.<br>Thx — PN</div>
<div style="position:absolute;bottom:120px;left:90px;right:90px;font-size:15px;line-height:1.45;border-top:1px solid #000;padding-top:12px">
<b>CONFIDENTIALITY NOTICE:</b> This facsimile contains protected health information that is privileged and
confidential. If you are not the intended recipient, any review, disclosure, copying or distribution is
prohibited. If you received this fax in error, please notify the sender by telephone and destroy all copies.</div>
<div style="position:absolute;bottom:60px;left:0;right:0;text-align:center;font-size:13px">{FOOT}</div></div>"""


def _box(checked: bool) -> str:
    return f"<span style='display:inline-block;width:22px;height:22px;border:2px solid #000;margin-right:12px;text-align:center;font:bold 19px Arial;line-height:19px'>{'X' if checked else '&nbsp;'}</span>"


def _line(label, value="", w="100%"):
    return (f"<div style='display:flex;align-items:flex-end;margin:16px 0;width:{w}'><span style='white-space:nowrap;margin-right:10px'>{label}</span>"
            f"<span style='flex:1;border-bottom:1.6px solid #000;padding:0 6px 2px;font:24px \"Courier 10 Pitch\",monospace'>{value}&nbsp;</span></div>")


def _fax_rec() -> str:
    p, m = PATIENT, MIDWIFE
    services = ["One initial visit",
                "Up to eight additional visits (prenatal and/or postpartum)",
                "Support during labor and delivery, including miscarriage or abortion",
                "Up to two extended postpartum visits (up to three hours each)"]
    return f"""<div class=pg style="font-family:Arial;padding:70px 90px;font-size:20px">
<div style="text-align:center;font:bold 27px Arial">LICENSED PROVIDER RECOMMENDATION FOR DOULA SERVICES</div>
<div style="text-align:center;font-size:16px;margin-top:6px">Complete and give to the member or the doula. The doula keeps this form on file.</div>
<div style="margin-top:34px;font-weight:bold;border-bottom:2px solid #000">SECTION 1 — MEMBER INFORMATION</div>
<div style="display:flex;gap:26px">{_line("First name", p['first'], "38%")}{_line("Middle", p['middle'], "18%")}{_line("Last name", p['last'], "44%")}</div>
<div style="display:flex;gap:26px">{_line("Date of birth", p['dob'], "45%")}{_line("Member ID (if known)", "", "55%")}</div>
<div style="margin-top:30px;font-weight:bold;border-bottom:2px solid #000">SECTION 2 — SERVICES RECOMMENDED</div>
<div style="margin-top:14px">I recommend this member receive doula services, including:</div>
{''.join(f"<div style='margin:14px 0 0 10px'>{_box(True)}{s}</div>" for s in services)}
<div style="margin-top:34px;font-weight:bold;border-bottom:2px solid #000">SECTION 3 — LICENSED PROVIDER</div>
<div style="display:flex;gap:26px">{_line("Provider name", m['name'], "55%")}{_line("NPI", m['npi'], "45%")}</div>
<div style="display:flex;gap:26px">{_line("Phone", m['phone'], "45%")}{_line("Date of recommendation", "10/08/2026", "55%")}</div>
<div style="display:flex;gap:26px;margin-top:30px">{_line("Signature", "", "100%")}</div>
<div style="position:absolute;bottom:60px;left:0;right:0;text-align:center;font-size:13px">{FOOT}</div></div>"""


def _card_front() -> str:
    p = PATIENT
    return f"""<div class=card style="background:linear-gradient(135deg,#0f5d6b,#13808f 60%,#7cc4c7);color:#fff;font-family:Arial">
<div style="display:flex;justify-content:space-between;align-items:center">
 <div style="font:bold 44px Georgia">Demo Health Plan</div>
 <div style="font-size:20px;text-align:right;line-height:1.2">MEDICAID<br>MANAGED CARE</div></div>
<div style="background:rgba(255,255,255,.95);color:#111;border-radius:12px;margin-top:20px;padding:20px 28px;font-size:27px;line-height:1.45">
 <div><span style="color:#555;font-size:19px">MEMBER NAME</span><br><b style="font-size:36px">{p['first'].upper()} {p['middle']} {p['last'].upper()}</b></div>
 <div style="display:flex;gap:44px;margin-top:10px">
  <div><span style="color:#555;font-size:19px">MEMBER ID</span><br><b style="letter-spacing:2px">{p['member_id']}</b></div>
  <div><span style="color:#555;font-size:19px">DATE OF BIRTH</span><br><b>{p['dob']}</b></div>
  <div><span style="color:#555;font-size:19px">EFFECTIVE</span><br><b>01/01/2026</b></div></div>
 <div style="display:flex;gap:44px;margin-top:10px;font-size:22px">
  <div><span style="color:#555;font-size:19px">PCP</span><br>Riverside Family Clinic</div>
  <div><span style="color:#555;font-size:19px">PCP PHONE</span><br>(555) 010-2400</div>
  <div><span style="color:#555;font-size:19px">PLAN TYPE</span><br>Medicaid</div></div></div>
<div style="display:flex;justify-content:space-between;margin-top:18px;font-size:21px;line-height:1.5">
 <div>RxBIN 999999 &nbsp; RxPCN DEMO &nbsp; RxGRP DHPMCD<br>Behavioral health 1-555-010-0180<br>Member Services 1-555-010-0100 (TTY 711)</div>
 <div style="text-align:right">Copay: $0<br>demohealthplan.example<br>SYNTHETIC · DEMO ONLY</div></div></div>"""


def _card_back() -> str:
    return """<div class=card style="background:#f4f6f6;color:#111;font-family:Arial;font-size:24px;line-height:1.55">
<div style="background:#13808f;height:46px;margin:-34px -40px 22px"></div>
<b>Members:</b> Member Services 1-555-010-0100 (TTY 711)<br>
24/7 Nurse Advice Line 1-555-010-0199<br>
<b>Providers:</b> Eligibility &amp; claims 1-555-010-0150<br>
Paper claims (CMS-1500): Demo Health Plan, PO Box 0000, Springfield, CA 95999<br>
EDI payer ID: DEMO0<br>
Pharmacy help desk 1-555-010-0160 &nbsp;·&nbsp; Prior authorization fax (555) 010-0161<br>
Interpreter services at no cost: 1-555-010-0100<br>
<div style="margin-top:14px;font-size:16px;color:#444">Having this card does not guarantee eligibility. Emergency? Call 911 or go to the nearest
emergency room. &nbsp; SYNTHETIC CARD — DEMO ONLY.</div></div>"""


def _intake() -> str:
    rows = [
        ("Full name", "Dana Morales"), ("Date of birth", "03/17/1994"),
        ("Sex (as listed with your insurance)", ""), ("Pronouns", "she/her"),
        ("Phone", PATIENT["phone"]), ("Email", "dana.m@example.com"),
        ("Home address", PATIENT["address"]), ("Preferred language(s)", "English, Spanish"),
        ("Estimated due date", PATIENT["due"]), ("Is this your first pregnancy?", "Yes"),
        ("Where do you plan to give birth?", "Springfield General Hospital"),
        ("Health insurance", "Demo Health Plan (Medicaid)"), ("Member ID", "DMO-4182-7730"),
        ("Who referred you?", "My midwife, Priya at Riverside Midwifery"),
        ("Emergency contact", "Luis Morales (partner) · (555) 010-4472"),
        ("Services you're interested in", "Prenatal support; Birth support; Postpartum support"),
        ("Anything you'd like us to know?", "Nervous about the birth, my family lives far away"),
        ("Doula services agreement", "Signed electronically — Dana Morales — 10/09/2026 9:41 PM"),
    ]
    body = "".join(f"<div class=r><div class=q>{html.escape(q)}</div><div class=a>{html.escape(a) or '<span class=e>No answer</span>'}</div></div>"
                   for q, a in rows)
    return f"""<html><head><style>{_BASE_CSS}
body{{font-family:'Liberation Sans',Arial;padding:28px 46px}} .hd{{border-bottom:2px solid #3a6ea5;padding-bottom:10px;margin-bottom:8px}}
.t{{font-size:22px;font-weight:bold;color:#1f3d5c}} .s{{font-size:12px;color:#666;margin-top:3px}}
.r{{display:flex;border-bottom:1px solid #e3e6ea;padding:7px 0;font-size:12.5px}} .q{{width:44%;color:#555}} .a{{flex:1}}
.e{{color:#aaa;font-style:italic}} .ft{{margin-top:16px;font-size:10px;color:#888;display:flex;justify-content:space-between}}
</style></head><body><div class=hd><div class=t>{PRACTICE['name']} — New Client Intake</div>
<div class=s>Submission #48213 · Submitted Oct 9, 2026, 9:41 PM · IP logged</div></div>{body}
<div class=ft><span>Exported from online forms · page 1 of 1</span><span>{FOOT}</span></div></body></html>"""


def _guide() -> str:
    rows = "".join(f"<tr><td><b>{c['code']}</b></td><td>{c['what']}</td><td>{PLAN['modifier']}</td><td>{', '.join(c['dx'])}</td><td>{c['limit']}</td></tr>"
                   for c in PLAN["codes"])
    pos = " · ".join(f"{k} {v}" for k, v in PLAN["pos"].items())
    req = "".join(f"<li>{r}</li>" for r in PLAN["requirements"])
    return f"""<html><head><style>{_BASE_CSS}
body{{font-family:'Liberation Sans',Arial;padding:30px 44px;font-size:12.5px}} h1{{font-size:21px;color:#0f5d6b;margin:0}}
h2{{font-size:14px;color:#0f5d6b;margin:20px 0 6px}} table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #b9c6c8;padding:6px 8px;text-align:left;vertical-align:top}} th{{background:#e6f0f1}}
.ft{{margin-top:22px;font-size:10px;color:#888}}</style></head><body>
<h1>Demo Health Plan — Doula Services Billing Guide</h1><div style="color:#555">Medicaid managed care · excerpt · rev. 2026</div>
<h2>Codes, modifiers and limits</h2><table><tr><th>Code</th><th>Description</th><th>Modifier</th><th>ICD-10 (any one)</th><th>Frequency</th></tr>{rows}</table>
<p>A maximum of <b>{PLAN['perinatal_cap']}</b> visits per pregnancy are allowed for Z1034 and Z1038 combined. Additional visits need a second
recommendation. Report modifier {PLAN['modifier']} as the primary modifier; telehealth adds 93 or 95 in the second position.</p>
<h2>Place of service</h2><p>{pos}</p>
<h2>A clean claim needs</h2><ul>{req}</ul>
<p>Billing taxonomy for doulas: <b>{PLAN['taxonomy']}</b>. Submit electronically (837P) or on paper (CMS-1500 only).</p>
<div class=ft>{FOOT}</div></body></html>"""


def _fax_page_html(inner: str) -> str:
    return (f"<html><head><style>{_BASE_CSS} .pg{{position:relative;width:{FAX_W}px;height:{FAX_H}px;background:#fff}}"
            f"</style></head><body>{inner}</body></html>")


def _card_html(inner: str) -> str:
    return (f"<html><head><style>{_BASE_CSS} body{{background:transparent}} "
            ".card{width:1012px;height:638px;border-radius:38px;padding:34px 40px;overflow:hidden}</style></head>"
            f"<body>{inner}</body></html>")


# ---------------------------------------------------------------- degradation (PIL)
def _faxify(png: bytes, page: int, pages: int, rng: random.Random):
    from PIL import Image, ImageDraw, ImageFont
    im = Image.open(io.BytesIO(png)).convert("L").resize((FAX_W, FAX_H // 2))   # standard mode: 98 lines/inch
    im = im.resize((FAX_W, FAX_H), Image.NEAREST)
    im = im.rotate(rng.uniform(-0.9, 0.9), resample=Image.BICUBIC, fillcolor=255, expand=False)
    im = im.point(lambda v: 0 if v < 150 else 255)                         # 1-bit threshold, like a fax
    d = ImageDraw.Draw(im)
    for _ in range(900):                                                   # speckle
        x, y = rng.randrange(FAX_W), rng.randrange(FAX_H)
        d.point((x, y), fill=0)
    y = rng.randrange(600, FAX_H - 400)                                    # one short dropout streak
    x0 = rng.randrange(0, FAX_W // 2)
    d.line((x0, y, x0 + rng.randrange(200, 700), y), fill=0, width=2)
    font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf", 26)
    head = (f"OCT-08-2026 14:12   FROM: RIVERSIDE MIDWIFERY   5550102201   "
            f"TO: 5550103301          P.{page:03d}/{pages:03d}")
    d.rectangle((0, 0, FAX_W, 44), fill=255)
    d.text((24, 10), head, fill=0, font=font)
    return im.convert("1")


def _photo(card_png: bytes, rng: random.Random, angle: float):
    from PIL import Image, ImageDraw, ImageFilter
    W, H = 1600, 1200
    bg = Image.new("RGB", (W, H))
    px = bg.load()
    for y in range(H):                                                     # a speckled counter, lit from above
        for x in range(W):
            light = 1.0 - 0.35 * (((x - W * 0.45) / W) ** 2 + ((y - H * 0.35) / H) ** 2) * 2
            g = (178 + rng.gauss(0, 9)) * light
            if rng.random() < 0.012:
                g -= rng.uniform(40, 90)                                   # flecks in the stone
            px[x, y] = (int(g), int(g * 0.97), int(g * 0.92))
    card = Image.open(io.BytesIO(card_png)).convert("RGBA")
    card = card.resize((int(card.width * 1.32), int(card.height * 1.32)))
    w, h = card.size
    k = rng.uniform(0.05, 0.09)                                            # perspective: far edge narrower
    coeffs = _persp([(0, 0), (w, 0), (w, h), (0, h)],
                    [(w * k, h * 0.04), (w * (1 - k * 0.6), 0), (w, h), (0, h * 0.97)])
    card = card.transform((w, h), Image.PERSPECTIVE, coeffs, Image.BICUBIC)
    card = card.rotate(angle, expand=True, resample=Image.BICUBIC)
    shadow = Image.new("RGBA", card.size, (0, 0, 0, 0))
    shadow.putalpha(card.getchannel("A").point(lambda a: int(a * 0.55)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    ox, oy = (W - card.width) // 2, (H - card.height) // 2
    bg.paste(shadow, (ox + 22, oy + 30), shadow)
    bg.paste(card, (ox, oy), card)
    glare = Image.new("L", (W, H), 0)                                      # soft glare from a ceiling light
    gd = ImageDraw.Draw(glare)
    cx, cy = ox + card.width * rng.uniform(0.55, 0.75), oy + card.height * rng.uniform(0.15, 0.35)
    for r in range(260, 0, -8):
        gd.ellipse((cx - r * 1.6, cy - r, cx + r * 1.6, cy + r), fill=int(70 * (1 - r / 260)))
    bg = Image.composite(Image.new("RGB", (W, H), (255, 255, 250)), bg, glare.filter(ImageFilter.GaussianBlur(30)))
    bg = bg.filter(ImageFilter.GaussianBlur(0.8))
    out = io.BytesIO()
    bg.save(out, "JPEG", quality=74)
    return out.getvalue()


def _persp(src, dst):
    """Coefficients for PIL's PERSPECTIVE transform (maps output pixels back to input pixels)."""
    import numpy as np  # noqa: PLC0415 — dev-only, like the rest of this tool
    a = []
    for (x, y), (u, v) in zip(dst, src):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    b = [c for p in src for c in p]
    return np.linalg.solve(np.array(a, float), np.array(b, float)).tolist()


# ---------------------------------------------------------------- main
def main() -> None:
    from playwright.sync_api import sync_playwright
    rng = random.Random(42)                                                # same documents every time
    DOCS_DIR.mkdir(exist_ok=True)
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        pg = br.new_page(viewport={"width": FAX_W, "height": FAX_H})

        fax = []
        for i, inner in enumerate((_fax_cover(), _fax_rec()), 1):
            pg.set_content(_fax_page_html(inner))
            fax.append(_faxify(pg.screenshot(full_page=False), i, 2, rng))
        fax[0].save(DOCS_DIR / "referral-fax.pdf", save_all=True, append_images=fax[1:], resolution=200)
        for i, im in enumerate(fax, 1):
            im.convert("L").resize((FAX_W // 2, FAX_H // 2)).save(DOCS_DIR / f"referral-fax-p{i}.png")

        pg.set_viewport_size({"width": 1012, "height": 638})
        for name, inner, angle in (("card-front", _card_front(), 4.5), ("card-back", _card_back(), -3.0)):
            pg.set_content(_card_html(inner))
            shot = pg.locator(".card").screenshot(omit_background=True)
            (DOCS_DIR / f"{name}.jpg").write_bytes(_photo(shot, rng, angle))

        for name, doc in (("intake-form", _intake()), ("billing-guide", _guide())):
            pg.set_viewport_size({"width": 816, "height": 1056})
            pg.set_content(doc)
            pg.pdf(path=str(DOCS_DIR / f"{name}.pdf"), format="Letter", print_background=True)
            pg.screenshot(path=str(DOCS_DIR / f"{name}.png"), full_page=True)
        br.close()

    (DOCS_DIR / "visit-log.csv").write_text(VISIT_LOG)
    (DOCS_DIR / "message.txt").write_text(MESSAGE + "\n")
    print("wrote", sorted(p.name for p in DOCS_DIR.iterdir()))


if __name__ == "__main__":
    main()
