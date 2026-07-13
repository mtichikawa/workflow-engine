"""engine train — a local review app to build and curate a specialist's example set.

Isolated per specialist, on purpose: you never review one specialist's output on top of
another's mistakes. Generate a batch of ONE specialist's outputs on clean inputs, then
approve or improve each in a polished local UI. The kept (input, approved output) pairs land
in state/examples/<specialist>.jsonl — the universal baseline the specialist learns from.

    python -m engine.cli train classify --generate 6     # fetch + run, then open the UI
    python -m engine.cli train classify                  # resume the pending batch

Every screen shows THE STANDARD first (a rubric + one reference exemplar) so your eye is
calibrated before you judge the real output — the north star comes from the role, not
from the examples (that resolves the chicken-and-egg).
"""

from __future__ import annotations

import json
import math
import webbrowser
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .core import brain_json, get
from .examples import save_example
from .specialists._util import one_sentence, text_of

REVIEW_DIR = Path("state/review")


# ---- what "good" looks like, per specialist (the north star panel) ----------
# Authored from each specialist's role. Extend as we walk the specialists in order.
RANK_SCORING = ("urgency: security or data-loss or outage > blocks many users > "
                "broken feature > nice-to-have")
# high-urgency seeds — open-source trackers rarely contain real emergencies, so seed the
# top of the scale (in production these are the customer's actual outages).
RANK_SEEDS = [
    {"id": "rseed-rce", "title": "Unauthenticated RCE via crafted request header in 3.2",
     "body": "A malicious header lets an unauthenticated attacker run arbitrary code on the "
             "server. Confirmed exploit, affects all 3.2 deployments. Needs a patch now."},
    {"id": "rseed-outage", "title": "All production builds failing since 3.2 — every deploy broken",
     "body": "Since 3.2, `next build` crashes on every project in CI. No deploys are getting "
             "through org-wide. No workaround found."},
    {"id": "rseed-dataloss", "title": "Migration in 3.2 silently drops user records",
     "body": "Upgrading to 3.2 runs a migration that deletes rows from the users table without "
             "warning. Data is unrecoverable without a backup."},
]

TRIAGE_COMPONENTS = ["core", "api", "docs", "build", "ui", "auth", "other"]
VERIFY_STANDARD = ("the classification and routing fit the issue, and the reply is relevant "
                   "and asks for anything genuinely missing")
RESPOND_TONE = "helpful, concise, no promised timelines"
RESPOND_VOICE = ("a sharp, warm senior support engineer: concise and specific, no corporate "
                 "fluff; ask for exactly what's missing and promise nothing")
WRITE_BRIEF = ("a sharp, no-hype technical founder: concrete, numbers over adjectives, one "
               "idea per post, no fluff, no emojis")
WRITE_TOPICS = [
    "why most AI agent demos fall apart in production",
    "the hidden cost of skipping tests",
    "what 'done' actually means for a feature",
    "why a pipeline is only as reliable as its flakiest step",
]

STANDARDS = {
    "respond": {
        "rubric": [
            "Open by engaging the actual problem — never a canned greeting.",
            "Ask for exactly what's genuinely missing to move forward (repro, version, logs) — "
            "nothing boilerplate.",
            "Concise and specific; no corporate fluff, no promised timelines.",
            "Sound like a competent human peer, not a support macro.",
        ],
        "exemplar": {
            "input": {"item": {"title": "Export returns an empty CSV",
                               "body": "Clicking export downloads a 0-byte file."}, "tone": RESPOND_VOICE},
            "output": {"reply": "Thanks for flagging — a 0-byte export usually means the request "
                       "failed before the file was written. Which browser and version are you on, "
                       "and does the network tab show the /export call returning 200 or an error? "
                       "A 200 with an empty body points at the server; an error points at the "
                       "request. That'll tell us where to dig."},
        },
    },
    "write": {
        "rubric": [
            "One idea, stated concretely. Numbers over adjectives.",
            "No hype, no emojis, no throat-clearing — the first sentence is the point.",
            "Sound like a founder who has shipped, not a marketer.",
            "2–4 sentences; every one earns its place.",
        ],
        "exemplar": {
            "input": {"topic": "why most AI agent demos fail in production", "sources": [], "brief": WRITE_BRIEF},
            "output": {"post": "Most agent demos run one happy path against a cached prompt. "
                       "Production hits you with a 3% tool-timeout rate, retries that double your "
                       "token bill, and a 12-step chain where 95% per-step reliability compounds "
                       "to 54% end to end. The demo skipped the error handling because there "
                       "wasn't any."},
        },
    },
    "route": {
        "rubric": [
            "Send the issue to exactly ONE component — the team that would actually own the fix.",
            "Route by the ROOT of the problem, not surface words (an 'auth error' thrown by the "
            "build system is a build issue, not auth).",
            "Escalate=true only for security, data-loss, or an outage.",
            "Reasoning names the signal that decided the component.",
        ],
        "exemplar": {
            "input": {"item": {"title": "OAuth login returns 401 for all Google users",
                               "body": "Since the 2.4 deploy, Google SSO rejects every token."},
                      "components": TRIAGE_COMPONENTS},
            "output": {"component": "auth", "escalate": True,
                       "reasoning": "An SSO token rejection is an authentication-subsystem failure, "
                       "and a total login outage escalates."},
        },
    },
    "verify": {
        "rubric": [
            "Pass only if ALL hold: the label fits the issue, the component is right, and the "
            "reply is relevant and asks for what's genuinely missing.",
            "Fail if any part is off — wrong label, mis-route, or a generic/irrelevant reply — "
            "and name the specific problem in `issues`.",
            "Don't rubber-stamp, but don't invent problems either. A clean, correct triage "
            "should pass with empty issues.",
            "Confidence reflects how clear-cut the call is.",
        ],
        "exemplar": {
            "input": {"subject": {"issue_title": "App crashes on startup after upgrade",
                                  "classified_as": "feature", "routed_to": "docs",
                                  "draft_reply": "Thanks! Have you tried restarting?"},
                      "standard": VERIFY_STANDARD},
            "output": {"verdict": "fail", "confidence": 0.9,
                       "issues": ["a crash is a bug, not a feature",
                                  "a core crash routed to docs is wrong",
                                  "the reply is generic and asks for nothing useful"]},
        },
    },
    "rank": {
        "rubric": [
            "Score urgency 0–1, calibrated: reserve >0.8 for security, data-loss, or an "
            "outage that blocks everyone.",
            "Mid band (0.4–0.7) = a real but contained defect — broken feature, affects "
            "some users, or has a workaround.",
            "Low (<0.3) = cosmetic, nice-to-have, or a question. Don't inflate everything "
            "to the middle — the spread is the point.",
            "Reasoning names the factor that set the level: blast radius, data at risk, "
            "workaround availability.",
        ],
        "exemplar": {
            "input": {"item": {"title": "Login broken for all SSO users after 2.4 upgrade",
                               "body": "Every SSO login 500s since the 2.4 deploy. No workaround; "
                                       "users are locked out entirely."},
                      "scoring": RANK_SCORING},
            "output": {"score": 0.92, "reasoning": "A total auth outage with no workaround, "
                       "locking out every SSO user — maximum blast radius."},
        },
    },
    "classify": {
        "rubric": [
            "Assign the item to exactly ONE category from the given list — never invent one.",
            "Pick the single best fit even when several brush close; commit to the strongest.",
            "Confidence is earned: >0.85 only when the text clearly signals the type; "
            "0.5–0.8 when plausible but underspecified; low when it's a genuine guess.",
            "Reasoning is one short, concrete sentence naming what in the text decided it.",
        ],
        "exemplar": {
            "input": {
                "item": {"title": "App crashes on startup after upgrading to 3.2",
                         "body": "Fresh install works; upgrading throws a null deref in "
                                 "init(). Stack trace attached. Reverting to 3.1 fixes it."},
                "categories": ["bug", "feature", "question", "duplicate", "spam"],
                "criteria": "the kind of issue",
            },
            "output": {"label": "bug", "confidence": 0.96,
                       "reasoning": "A reproducible crash tied to a version upgrade with a "
                                    "stack trace — a clear defect report."},
        },
    },
}


# ---- coverage-aware batch generation ----------------------------------------
# The idea (Mike's): flood a diverse pool, run the specialist twice, and surface only the
# items that actually need a human — where the two passes DISAGREE, confidence is low, or
# the category is rare. Easy near-duplicates sink to the bottom. You adjudicate the
# contested handful instead of rubber-stamping softballs.

CATS = ["bug", "feature", "question", "duplicate", "spam"]
# high-traffic repos that get a MIX of bugs / features / questions (one repo alone = all bugs)
DIVERSE_REPOS = ["vercel/next.js", "facebook/react", "denoland/deno", "microsoft/TypeScript"]
# hand seeds guarantee coverage GitHub won't reliably give: real spam, a plain question,
# and a deliberate bug-or-feature edge case (the hardest, highest-value kind).
SEEDS = [
    {"id": "seed-spam", "title": "★★★ BUY CHEAP GITHUB STARS — 1000x BOOST ★★★",
     "body": "Grow your repo overnight! visit cheap-stars.example, limited offer, crypto accepted!!!"},
    {"id": "seed-question", "title": "How do I load environment variables at runtime?",
     "body": "New to this. Where do I put API keys so they're available when the app runs? Is there a .env convention?"},
    {"id": "seed-edge", "title": "Dev server should default to port 8080, not 3000",
     "body": "Port 3000 collides with other tools I run. The server ought to pick 8080 by default."},
    {"id": "seed-dup", "title": "Same as #12345: build fails on Windows with EPERM",
     "body": "This is the exact issue already reported and being tracked in #12345 — filing as a duplicate."},
]

# route coverage seeds — the pool's repos yield core/build/docs but rarely auth/ui/api
ROUTE_SEEDS = [
    {"id": "rt-auth", "title": "OAuth login returns 401 for all users after 2.4",
     "body": "Every SSO/Google login fails with 401 since the 2.4 deploy; valid tokens are rejected."},
    {"id": "rt-ui", "title": "Settings dropdown renders behind the modal on Safari",
     "body": "The dropdown appears behind the modal overlay — a z-index/stacking bug, Safari only."},
    {"id": "rt-api", "title": "POST /v2/orders returns 500 when 'currency' is omitted",
     "body": "The public REST endpoint 500s instead of validating; it should return a 400 with a clear error."},
]
LOW_CONF = 0.75
# Run the devil's advocate on any item whose confidence is BELOW this. High = challenge
# almost everything (training-mode: cost is trivial on a small batch, coverage is all).
# Production lowers this so only genuinely-uncertain items get a second call.
CHALLENGE_BELOW = 0.99
_SIGNAL_ORDER = {"disagree": 0, "low-conf": 1, "rare": 2, "clean": 3}

_DA_SYSTEM = ("You are a rigorous classification reviewer. You argue for a different label "
              "ONLY when there is a genuine case for one, and you readily concede when the "
              "proposed label is clearly correct. You never manufacture disagreement.")


def _classify_pool(total: int, repos: list[str]) -> list[dict]:
    per = max(1, math.ceil(total / max(1, len(repos))))
    pool = []
    for repo in repos:
        try:
            pool.extend(get("fetch").run({"source": "github", "params": {"repo": repo, "limit": per}}, {})["items"])
        except Exception as e:  # noqa: BLE001
            print(f"  (skipped {repo}: {e})")
    return pool + [dict(s) for s in SEEDS]


def _devils_advocate(item: dict, label: str, categories: list[str]) -> dict:
    """Adversarial second opinion: make the strongest case for a DIFFERENT label, or concede.
    A real, different label with an argument = a genuinely contestable item."""
    prompt = (
        f'An item was classified as "{label}" from these categories: {categories}\n\n'
        f"ITEM:\n{text_of(item)}\n\n"
        f'Make the strongest case that the correct category is something OTHER than "{label}". '
        f'If "{label}" is clearly correct, concede — do not invent a disagreement.\n'
        'Return JSON: {"alt_label": <your own best category from the list>, '
        '"agree": <true if the original label is best>, "argument": <one or two sentences>}'
    )
    try:
        r = brain_json(prompt, system=_DA_SYSTEM, temperature=0.0)
    except Exception:  # noqa: BLE001 — a failed challenge just means "no disagreement found"
        return {"alt_label": label, "agree": True, "argument": ""}
    alt = str(r.get("alt_label", "")).strip()
    if alt not in categories:
        alt = label
    return {"alt_label": alt, "agree": bool(r.get("agree", alt == label)),
            "argument": one_sentence(r.get("argument", ""))}


def _reuse_pool(limit: int, repo: str) -> list[dict]:
    """Reuse the items already fetched for the classify batch (same real issues, zero extra
    fetch). Fall back to a fresh diverse pull if there's no prior batch."""
    p = _path("classify")
    if p.exists():
        items = [it["input"]["item"] for it in json.loads(p.read_text()).get("items", [])]
        if items:
            return items
    return _classify_pool(limit, DIVERSE_REPOS if (not repo or repo == "auto") else [repo])


def _band(s: float) -> str:
    return "high" if s >= 0.66 else ("low" if s < 0.34 else "mid")


def _rank_devils_advocate(item: dict, score: float) -> dict:
    prompt = (
        f"An issue was scored {score:.2f} for urgency (0 = trivial, 1 = critical), on this "
        f"dimension: {RANK_SCORING}\n\n"
        f"ITEM:\n{text_of(item)}\n\n"
        f"Make the strongest case the score should be MATERIALLY higher or lower. "
        f"If {score:.2f} is about right, concede.\n"
        'Return JSON: {"alt_score": <0..1>, "agree": <true if the score is about right>, '
        '"argument": <one or two sentences>}'
    )
    try:
        r = brain_json(prompt, system=_DA_SYSTEM, temperature=0.0)
    except Exception:  # noqa: BLE001
        return {"alt_score": score, "agree": True, "argument": ""}
    alt = max(0.0, min(1.0, float(r.get("alt_score", score) or score)))
    return {"alt_score": alt, "agree": bool(r.get("agree", abs(alt - score) < 0.15)),
            "argument": one_sentence(r.get("argument", ""))}


def generate_batch(specialist: str, limit: int, repo: str) -> dict:
    if specialist == "classify":
        return _gen_classify(limit, repo)
    if specialist == "rank":
        return _gen_rank(limit, repo)
    if specialist == "verify":
        return _gen_verify(limit, repo)
    if specialist == "route":
        return _gen_route(limit, repo)
    if specialist in ("respond", "write"):
        return _gen_generative(specialist, limit, repo)
    raise SystemExit(f"coverage generation is wired for classify + rank + verify + route + "
                     f"respond + write; '{specialist}' isn't in the tester.")


def _gen_generative(specialist: str, limit: int, repo: str) -> dict:
    """Generative specialists (respond/write) — no disagreement signal; you edit the prose to
    the voice. The standard panel carries the voice + a reference exemplar to anchor it."""
    if specialist == "respond":
        pool = _reuse_pool(limit, repo)[:8]
        raw = [{"input": {"item": it, "tone": RESPOND_VOICE},
                "output": get("respond").run({"item": it, "tone": RESPOND_VOICE}, {})} for it in pool]
    else:  # write
        raw = [{"input": {"topic": t, "sources": [], "brief": WRITE_BRIEF},
                "output": get("write").run({"topic": t, "sources": [], "brief": WRITE_BRIEF}, {})}
               for t in WRITE_TOPICS]
    print(f"  drafted {len(raw)} {specialist} outputs — edit each to the voice.")
    items = [{"i": i, "input": r["input"], "output": r["output"], "counter": "",
              "signal": "clean", "signal_detail": "edit to voice",
              "decision": None, "gold": None, "committed": False} for i, r in enumerate(raw)]
    batch = {"specialist": specialist, "standard": STANDARDS.get(specialist, {}),
             "generative": True, "items": items}
    _save(specialist, batch)
    return batch


def _route_devils_advocate(item: dict, comp: str) -> dict:
    prompt = (
        f'An issue was routed to the "{comp}" component, from: {TRIAGE_COMPONENTS}\n\n'
        f"ITEM:\n{text_of(item)}\n\n"
        f'Make the strongest case it belongs to a DIFFERENT component. If "{comp}" is clearly right, concede.\n'
        'Return JSON: {"alt_component": <one component>, "agree": <true if the original is right>, '
        '"argument": <one or two sentences>}'
    )
    try:
        r = brain_json(prompt, system=_DA_SYSTEM, temperature=0.0)
    except Exception:  # noqa: BLE001
        return {"alt_component": comp, "agree": True, "argument": ""}
    alt = str(r.get("alt_component", "")).strip()
    if alt not in TRIAGE_COMPONENTS:
        alt = comp
    return {"alt_component": alt, "agree": bool(r.get("agree", alt == comp)),
            "argument": one_sentence(r.get("argument", ""))}


def _gen_route(limit: int, repo: str) -> dict:
    pool = _reuse_pool(limit, repo) + [dict(s) for s in ROUTE_SEEDS]   # seed auth/ui/api
    print(f"  pool: {len(pool)} items ({len(ROUTE_SEEDS)} auth/ui/api seeds); routing to components…")
    raw = [{"input": {"item": it, "components": TRIAGE_COMPONENTS}, "item": it,
            "output": get("route").run({"item": it, "components": TRIAGE_COMPONENTS}, {})} for it in pool]
    dist = Counter(r["output"]["component"] for r in raw)
    rare = {c for c, n in dist.items() if n <= max(1, len(raw) // 8)}
    challenged = 0
    for r in raw:
        comp = r["output"]["component"]
        da = _route_devils_advocate(r["item"], comp)       # challenge every one (training mode)
        challenged += 1
        if da and not da["agree"] and da["alt_component"] != comp:
            r["signal"], r["signal_detail"] = "disagree", f'{comp} vs {da["alt_component"]}'
            r["counter"] = da["argument"]
        elif comp in rare:
            r["signal"], r["signal_detail"] = "rare", comp
        else:
            r["signal"], r["signal_detail"] = "clean", comp
    raw.sort(key=lambda r: _SIGNAL_ORDER.get(r["signal"], 9))
    print(f"  components {dict(dist)}; challenged {challenged}.")
    items = [{"i": i, "input": r["input"], "output": r["output"], "counter": r.get("counter", ""),
              "signal": r["signal"], "signal_detail": r["signal_detail"],
              "decision": None, "gold": None, "committed": False} for i, r in enumerate(raw)]
    batch = {"specialist": "route", "standard": STANDARDS.get("route", {}),
             "dist": dict(dist), "items": items}
    _save("route", batch)
    return batch


# ---- verify: the chained checker — needs planted failures to learn to catch them --------
_BAD_REPLY = ("Thanks for reaching out! Have you tried turning it off and on again? "
              "Let us know how it goes.")


def _build_subject(item: dict) -> dict:
    """Run the real upstream chain (classify + route + respond) to produce a realistic subject."""
    cl = get("classify").run({"item": item, "categories": CATS, "criteria": "the kind of issue"}, {})
    rt = get("route").run({"item": item, "components": TRIAGE_COMPONENTS}, {})
    rs = get("respond").run({"item": item, "tone": RESPOND_TONE}, {})
    return {"issue_title": str(item.get("title", "")), "classified_as": cl["label"],
            "routed_to": rt["component"], "draft_reply": rs["reply"]}


def _plant(subject: dict, kind: str) -> dict:
    """Corrupt one field so verify SHOULD fail — a known-wrong subject."""
    s = dict(subject)
    if kind == "wrong_label":
        s["classified_as"] = next((c for c in CATS if c != subject["classified_as"]), subject["classified_as"])
    elif kind == "wrong_route":
        s["routed_to"] = next((c for c in TRIAGE_COMPONENTS if c != subject["routed_to"]), subject["routed_to"])
    else:  # irrelevant_reply
        s["draft_reply"] = _BAD_REPLY
    return s


def _verify_devils_advocate(subject: dict, verdict: str) -> dict:
    prompt = (
        f'A triage decision was judged "{verdict}" against this standard: {VERIFY_STANDARD}\n\n'
        f"SUBJECT:\n{text_of(subject)}\n\n"
        f'Make the strongest case the verdict should be the OPPOSITE of "{verdict}". '
        f'If "{verdict}" is clearly right, concede.\n'
        'Return JSON: {"alt_verdict": "pass" or "fail", "agree": <true if the original is right>, '
        '"argument": <one or two sentences>}'
    )
    try:
        r = brain_json(prompt, system=_DA_SYSTEM, temperature=0.0)
    except Exception:  # noqa: BLE001
        return {"alt_verdict": verdict, "agree": True, "argument": ""}
    alt = "pass" if str(r.get("alt_verdict", "")).lower().startswith("pass") else "fail"
    return {"alt_verdict": alt, "agree": bool(r.get("agree", alt == verdict)),
            "argument": one_sentence(r.get("argument", ""))}


_VERIFY_ORDER = {"missed": 0, "disagree": 1, "flagged": 2, "clean": 3}


def _gen_verify(limit: int, repo: str) -> dict:
    pool = _reuse_pool(limit, repo)[:10]                    # each subject = 3 upstream calls
    print(f"  building {len(pool)} real subjects (classify+route+respond) + planted failures…")
    kinds = ["wrong_label", "irrelevant_reply", "wrong_route"]
    raw = []
    for i, item in enumerate(pool):
        subj = _build_subject(item)
        title = str(item.get("title", ""))[:58]
        raw.append({"subject": subj, "planted": None, "title": title})
        if i < (len(pool) + 1) // 2:                        # plant a failure in ~half
            raw.append({"subject": _plant(subj, kinds[i % 3]), "planted": kinds[i % 3], "title": title})

    challenged = 0
    for r in raw:
        inp = {"subject": r["subject"], "standard": VERIFY_STANDARD}
        r["input"] = inp
        v = get("verify").run(inp, {})
        r["output"] = v
        verdict = v["verdict"]
        da = _verify_devils_advocate(r["subject"], verdict) if v.get("confidence", 1.0) < CHALLENGE_BELOW else None
        if da:
            challenged += 1
        if r["planted"] and verdict == "pass":
            r["signal"], r["signal_detail"] = "missed", f'planted {r["planted"]} — verify passed it'
        elif da and not da["agree"] and da["alt_verdict"] != verdict:
            r["signal"], r["signal_detail"] = "disagree", f'{verdict} → {da["alt_verdict"]}'
            r["counter"] = da["argument"]
        elif not r["planted"] and verdict == "fail":
            r["signal"], r["signal_detail"] = "flagged", "failed a real subject — check its issues"
        else:
            r["signal"], r["signal_detail"] = "clean", ("planted→fail ✓" if r["planted"] else "clean→pass ✓")
    raw.sort(key=lambda r: _VERIFY_ORDER.get(r["signal"], 9))
    caught = sum(1 for r in raw if r["planted"] and r["output"]["verdict"] == "fail")
    planted = sum(1 for r in raw if r["planted"])
    print(f"  planted {planted} failures; verify caught {caught}/{planted}. challenged {challenged}.")

    items = [{"i": i, "input": r["input"], "output": r["output"], "planted": r["planted"],
              "signal": r["signal"], "signal_detail": r["signal_detail"], "counter": r.get("counter", ""),
              "decision": None, "gold": None, "committed": False} for i, r in enumerate(raw)]
    batch = {"specialist": "verify", "standard": STANDARDS.get("verify", {}),
             "planted": planted, "caught": caught, "items": items}
    _save("verify", batch)
    return batch


def _gen_rank(limit: int, repo: str) -> dict:
    pool = _reuse_pool(limit, repo) + [dict(s) for s in RANK_SEEDS]   # seed the high band
    print(f"  pool: {len(pool)} items ({len(RANK_SEEDS)} high-urgency seeds); scoring urgency…")
    raw = [{"input": {"item": it, "scoring": RANK_SCORING}, "item": it,
            "output": get("rank").run({"item": it, "scoring": RANK_SCORING}, {})} for it in pool]

    challenged = 0
    for r in raw:
        s = r["output"]["score"]
        r["band"] = _band(s)
        da = _rank_devils_advocate(r["item"], s) if s < CHALLENGE_BELOW else None
        if da:
            challenged += 1
        if da and not da["agree"] and abs(da["alt_score"] - s) >= 0.2:
            r["signal"], r["signal_detail"] = "disagree", f'{s:.2f} → {da["alt_score"]:.2f}'
            r["counter"] = da["argument"]
        else:
            r["signal"], r["signal_detail"] = "clean", f'{r["band"]} · {s:.2f}'
    raw.sort(key=lambda r: (0 if r["signal"] == "disagree" else 1, -r["output"]["score"]))
    bands = Counter(r["band"] for r in raw)
    print(f"  challenged {challenged}/{len(raw)}; bands {dict(bands)}")

    items = [{"i": i, "input": r["input"], "output": r["output"], "band": r["band"],
              "signal": r["signal"], "signal_detail": r["signal_detail"], "counter": r.get("counter", ""),
              "decision": None, "gold": None, "committed": False} for i, r in enumerate(raw)]
    batch = {"specialist": "rank", "standard": STANDARDS.get("rank", {}),
             "bands": dict(bands), "items": items}
    _save("rank", batch)
    return batch


def _gen_classify(limit: int, repo: str) -> dict:
    repos = DIVERSE_REPOS if (not repo or repo == "auto") else [repo]
    pool = _classify_pool(limit, repos)
    print(f"  pool: {len(pool)} items from {len(repos)} repo(s) + {len(SEEDS)} seeds; classifying…")

    raw = []
    for item in pool:
        inp = {"item": item, "categories": CATS, "criteria": "the kind of issue"}
        raw.append({"input": inp, "item": item, "output": get("classify").run(inp, {})})

    dist = Counter(r["output"]["label"] for r in raw)
    rare = {lab for lab, c in dist.items() if c <= max(1, len(raw) // 8)}
    challenged = 0
    for r in raw:
        a = r["output"]
        conf, label = a.get("confidence", 1.0), a["label"]
        # challenge the uncertain AND the rare (be paranoid about minority categories)
        da = None
        if conf < CHALLENGE_BELOW or label in rare:
            da = _devils_advocate(r["item"], label, CATS)
            challenged += 1
        if da and not da["agree"] and da["alt_label"] != label:
            r["signal"], r["signal_detail"] = "disagree", f'{label} vs {da["alt_label"]}'
            r["counter"] = da["argument"]
        elif conf < LOW_CONF:
            r["signal"], r["signal_detail"] = "low-conf", f"{conf:.2f}"
        elif label in rare:
            r["signal"], r["signal_detail"] = "rare", label
        else:
            r["signal"], r["signal_detail"] = "clean", ""
    raw.sort(key=lambda r: _SIGNAL_ORDER[r["signal"]])   # contested/hard first
    print(f"  challenged {challenged}/{len(raw)} with the devil's advocate.")

    items = [{"i": i, "input": r["input"], "output": r["output"],
              "signal": r["signal"], "signal_detail": r["signal_detail"], "counter": r.get("counter", ""),
              "decision": None, "gold": None, "committed": False} for i, r in enumerate(raw)]
    batch = {"specialist": "classify", "standard": STANDARDS.get("classify", {}),
             "dist": dict(dist), "items": items}
    _save("classify", batch)
    return batch


def _path(specialist: str) -> Path:
    return REVIEW_DIR / f"{specialist}.json"


def _save(specialist: str, batch: dict) -> None:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    _path(specialist).write_text(json.dumps(batch, indent=2, default=str))


def _load(specialist: str) -> dict:
    p = _path(specialist)
    if not p.exists():
        raise SystemExit(f"no pending batch for '{specialist}'. Generate one:\n"
                         f"  python -m engine.cli train {specialist} --generate 6")
    return json.loads(p.read_text())


# ---- the local server -------------------------------------------------------
def serve(specialist: str, port: int = 8765, open_browser: bool = True) -> None:
    batch = _load(specialist)                      # fail early if none

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):                 # quiet
            pass

        def _send(self, code, body, ctype="application/json"):
            data = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/" or self.path.startswith("/?"):
                self._send(200, PAGE, "text/html; charset=utf-8")
            elif self.path == "/api/batch":
                self._send(200, json.dumps(_load(specialist), default=str))
            else:
                self._send(404, "{}")

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or "{}")
            b = _load(specialist)
            if self.path == "/api/decision":
                it = b["items"][body["index"]]
                it["decision"] = body["decision"]              # approve | improve | skip
                it["gold"] = body.get("gold")
                _save(specialist, b)
                self._send(200, json.dumps({"ok": True, "saved": _saved_count(b)}))
            elif self.path == "/api/commit":
                committed = 0
                for it in b["items"]:
                    if it["decision"] in ("approve", "improve") and not it["committed"]:
                        save_example(specialist, it["input"], it["gold"] or it["output"])
                        it["committed"] = True
                        committed += 1
                _save(specialist, b)
                self._send(200, json.dumps({"ok": True, "committed": committed,
                                            "total_committed": sum(x["committed"] for x in b["items"])}))
            else:
                self._send(404, "{}")

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    n = len(batch["items"])
    print(f"engine train · {specialist} — {n} item(s) to review")
    print(f"  open  {url}")
    print("  approve / improve each, then Save examples. Ctrl-C here when done.")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
        httpd.shutdown()


def _saved_count(b: dict) -> int:
    return sum(1 for it in b["items"] if it["decision"] in ("approve", "improve"))


# ---- the page (self-contained; dark technical theme to match engine) ---------
PAGE = r"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>engine · train</title>
<style>
 :root{--bg:#1e242c;--panel:#28303a;--panel2:#313a45;--line:#3d4854;--ink:#f0f3f7;
       --mut:#aeb8c4;--brass:#d4b877;--green:#5cb287;--dim:#6b7683;--bad:#d97a6e;
       --read:#f6f6f2;--readink:#1a2029;--readline:#d6d9cf}
 *{box-sizing:border-box}
 html,body{height:100%}
 body{margin:0;background:var(--bg);color:var(--ink);overflow:hidden;
      font:13.5px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
 .wrap{height:100vh;max-width:1440px;margin:0 auto;padding:13px 20px 11px;
       display:flex;flex-direction:column;gap:9px}
 header{display:flex;align-items:baseline;gap:14px;flex:0 0 auto}
 h1{font-size:13px;letter-spacing:.16em;text-transform:uppercase;color:var(--brass);margin:0}
 .spec{color:var(--ink);font-weight:600}
 .count{margin-left:auto;color:var(--mut);font-size:12px}
 .dots{display:flex;gap:5px;flex-wrap:wrap;margin:0;flex:0 0 auto}
 .dot{width:11px;height:11px;border-radius:3px;background:#2b323c;cursor:pointer;transition:.15s}
 .dot.cur{outline:2px solid var(--brass);outline-offset:2px}
 .dot.approve{background:var(--green)} .dot.improve{background:var(--brass)}
 .dot.skip{background:var(--dim)}
 .grid3{flex:1;min-height:0;display:grid;grid-template-columns:0.95fr 1.5fr 1.05fr;gap:10px}
 .col{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:13px 15px;
      min-width:0;display:flex;flex-direction:column;min-height:0;overflow:hidden}
 .col.std{overflow:auto}                       /* the reference column scrolls as a whole */
 .col.std ul{margin:2px 0 15px;padding-left:18px;color:var(--ink)}
 .col.std li{margin:6px 0}
 .exlabel{color:var(--mut);font-size:11px;letter-spacing:.12em;text-transform:uppercase;margin:2px 0 6px}
 .exbox{margin:0 0 13px;background:var(--read);border:1px solid var(--readline);border-radius:6px;
        padding:10px 12px;font-size:12px;color:var(--readink);word-break:break-word}
 .exbox.gold{border-color:#b7c69f;box-shadow:inset 3px 0 0 var(--green)}
 @media(max-width:1000px){body{overflow:auto}.wrap{height:auto}.grid3{grid-template-columns:1fr}
   .col{overflow:visible}.col.std{overflow:visible}.itemtext{max-height:55vh}}
 .lbl{color:var(--mut);font-size:11px;letter-spacing:.13em;text-transform:uppercase;margin:0 0 8px}
 .chips{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
 .chip{background:var(--panel2);border:1px solid var(--line);border-radius:20px;padding:2px 10px;
       font-size:11px;color:var(--mut)}
 .crit{color:var(--mut);font-size:12px;margin:0 0 10px}
 .itemtext{flex:1;min-height:0;background:var(--read);color:var(--readink);border:1px solid var(--readline);
           border-radius:6px;padding:13px 14px;overflow:auto;word-break:break-word;line-height:1.55}
 .md .t{color:#0f141b;font-weight:700;font-size:14.5px;display:block;margin-bottom:9px;line-height:1.4}
 .md h4{margin:13px 0 3px;font-size:12px;color:#41474e;text-transform:uppercase;letter-spacing:.08em}
 .md p{margin:6px 0} .md .li{margin:3px 0 3px 4px}
 .md a{color:#3b6ea5;word-break:break-all}
 .md code{background:#e6e8df;border-radius:3px;padding:1px 4px;font-size:12px}
 .md pre.code{background:#ebede4;border:1px solid #d6d9cf;border-radius:5px;padding:9px 11px;margin:8px 0;
           max-height:150px;overflow:auto;white-space:pre;font-size:12px;color:#1a2029}
 /* signal — why this item was surfaced */
 .signal{display:none;border-radius:6px;padding:8px 12px;margin-bottom:10px;font-size:12px}
 .signal.show{display:block}
 .signal .why{font-weight:700;text-transform:uppercase;letter-spacing:.07em;font-size:11px}
 .signal .ctr{margin-top:5px;font-weight:400;font-style:italic;opacity:.9}
 .signal.disagree{background:#3a2f1c;border:1px solid var(--brass);color:#f2dfae}
 .signal.low-conf{background:#33301f;border:1px solid #857439;color:#ecdca6}
 .signal.rare{background:#1c322b;border:1px solid #3f7060;color:#a9e3d0}
 .signal.missed{background:#3a2320;border:1px solid var(--bad);color:#f2c6bd}
 .signal.flagged{background:#33301f;border:1px solid #857439;color:#ecdca6}
 /* output — readable judgment, JSON underneath */
 .preview{background:var(--read);color:var(--readink);border:1px solid var(--readline);border-radius:6px;padding:12px 14px;margin-bottom:10px}
 .orow{display:grid;grid-template-columns:88px 1fr;gap:10px;align-items:center;padding:4px 0}
 .orow+.orow{border-top:1px solid #e4e6dc}
 .ok{color:#5a6069;font-size:11px;letter-spacing:.09em;text-transform:uppercase}
 .pill{justify-self:start;background:#2c3542;color:#eef1f5;border-radius:20px;padding:3px 14px;font-weight:700}
 .obar{position:relative;height:8px;background:#dcdfd4;border-radius:5px;overflow:hidden}
 .obar i{position:absolute;inset:0 auto 0 0;background:var(--green);border-radius:5px}
 .conf{display:grid;grid-template-columns:88px 1fr 42px;gap:10px;align-items:center;padding:4px 0}
 .otext{color:#1a2029}
 .lbl2{color:var(--mut);font-size:11px;margin:0 0 5px}
 textarea{flex:1;width:100%;min-height:90px;background:var(--read);color:var(--readink);border:1px solid var(--readline);
          border-radius:6px;padding:11px 12px;font:inherit;line-height:1.5;resize:vertical}
 textarea:focus{outline:none;border-color:var(--brass);box-shadow:0 0 0 2px rgba(212,184,119,.25)}
 textarea.bad{border-color:var(--bad);box-shadow:0 0 0 2px rgba(217,122,110,.25)}
 .jsonerr{color:var(--bad);font-size:11px;height:14px;margin-top:5px}
 .bar{display:flex;align-items:center;gap:10px;margin-top:10px;flex:0 0 auto}
 button{background:var(--panel2);color:var(--ink);border:1px solid var(--line);border-radius:6px;
        padding:9px 16px;cursor:pointer;font:inherit}
 button:hover{border-color:var(--brass)}
 button.primary{background:var(--brass);color:#141414;border-color:var(--brass);font-weight:700}
 button.primary:disabled{opacity:.4;cursor:not-allowed}
 button.ghost{color:var(--mut)}
 .sp{flex:1}
 .kbd{color:var(--dim);font-size:11px}
 .commit{flex:0 0 auto;margin-top:0;display:flex;align-items:center;gap:12px;padding-top:9px;border-top:1px solid var(--line)}
 .toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#141a20;
        border:1px solid var(--brass);color:var(--ink);padding:10px 18px;border-radius:8px;
        opacity:0;transition:.25s;pointer-events:none}
 .toast.show{opacity:1}
 .done{color:var(--green)}
</style></head><body><div class="wrap">
 <header>
   <h1>engine train</h1><span class="spec" id="spec">·</span>
   <span class="count" id="count"></span>
 </header>
 <div class="dots" id="dots"></div>

 <div class="grid3">
   <section class="col std" id="std">
     <p class="lbl">the standard — what good looks like</p>
     <ul id="rubric"></ul>
     <p class="exlabel">reference exemplar — input</p>
     <div class="exbox md" id="exin"></div>
     <p class="exlabel">reference exemplar — output</p>
     <div class="exbox gold" id="exout"></div>
   </section>
   <section class="col">
     <p class="lbl">input the specialist saw</p>
     <div class="chips" id="cats"></div>
     <p class="crit" id="crit"></p>
     <div class="itemtext md" id="itemtext"></div>
   </section>
   <section class="col">
     <p class="lbl">its output — approve, or edit the JSON to improve</p>
     <div class="signal" id="signal"></div>
     <div class="preview" id="preview"></div>
     <p class="lbl2" id="lbl2txt">raw json — edit to correct</p>
     <textarea id="editor" spellcheck="false"></textarea>
     <div class="jsonerr" id="jsonerr"></div>
     <div class="bar">
       <button class="ghost" id="prev">◂ prev</button>
       <button class="ghost" id="skip">skip <span class="kbd">s</span></button>
       <div class="sp"></div>
       <button class="ghost" id="reset">revert edits</button>
       <button class="primary" id="save">save &amp; next <span class="kbd">⌘↵</span></button>
     </div>
   </section>
 </div>

 <div class="commit">
   <span id="progress" class="count"></span>
   <div class="sp"></div>
   <button class="primary" id="commit">save examples ▸</button>
 </div>
</div>
<div class="toast" id="toast"></div>
<script>
let B=null, idx=0, PROSE=null;
const PROSE_KEYS=["reply","post","text","draft","body","content","message"];
function proseField(o){
  if(!o||typeof o!=="object") return null;
  const cand=Object.keys(o).filter(k=>PROSE_KEYS.includes(k)&&typeof o[k]==="string");
  return cand.length?cand[0]:null;
}
const $=id=>document.getElementById(id);
const pretty=o=>JSON.stringify(o,null,2);
const esc=s=>String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
function inline(s){return esc(s).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>')
  .replace(/(https?:\/\/[^\s)]+)/g,'<a href="$1" target="_blank" rel="noopener">$1</a>');}
function mdRender(md){
  const lines=String(md).replace(/\r/g,'').split('\n'); let h="",code=false,buf=[],para=[];
  const flush=()=>{if(para.length){h+=`<p>${inline(para.join(' '))}</p>`;para=[];}};
  for(const ln of lines){
    if(ln.trim().startsWith('```')){ if(code){h+=`<pre class="code">${esc(buf.join('\n'))}</pre>`;buf=[];code=false;} else {flush();code=true;} continue;}
    if(code){buf.push(ln);continue;}
    const hd=ln.match(/^(#{1,6})\s+(.*)/);
    if(hd){flush();h+=`<h4>${esc(hd[2])}</h4>`;continue;}
    if(ln.trim()===''){flush();continue;}
    if(/^\s*[-*]\s+/.test(ln)){flush();h+=`<div class="li">• ${inline(ln.replace(/^\s*[-*]\s+/,''))}</div>`;continue;}
    para.push(ln);
  }
  if(code)h+=`<pre class="code">${esc(buf.join('\n'))}</pre>`; flush(); return h;
}
function textOf(item){
  if(item==null) return "";
  if(typeof item==="string") return mdRender(item);
  const t=item.title||item.name||"", body=item.body||item.text||item.content||"";
  return t? `<span class="t">${esc(t)}</span>${mdRender(body)}` : `<pre class="code">${esc(pretty(item))}</pre>`;
}
function renderOutput(o){
  if(o==null||typeof o!=="object"||Array.isArray(o)) return `<div class="otext">${esc(pretty(o))}</div>`;
  let h="";
  for(const [k,v] of Object.entries(o)){
    if(typeof v==="number" && v>=0 && v<=1 && /conf|score|prob|rank/i.test(k))
      h+=`<div class="conf"><span class="ok">${esc(k)}</span><span class="obar"><i style="width:${(v*100).toFixed(0)}%"></i></span><span class="otext">${v.toFixed(2)}</span></div>`;
    else if(k==="label"||k==="category"||k==="verdict"||k==="component")
      h+=`<div class="orow"><span class="ok">${esc(k)}</span><span class="pill">${esc(v)}</span></div>`;
    else
      h+=`<div class="orow"><span class="ok">${esc(k)}</span><span class="otext">${esc(typeof v==="object"?pretty(v):v)}</span></div>`;
  }
  return h;
}

async function load(){
  B=await (await fetch("/api/batch")).json();
  $("spec").textContent="· "+B.specialist;
  const s=B.standard||{};
  $("rubric").innerHTML=(s.rubric||[]).map(r=>`<li>${esc(r)}</li>`).join("");
  if(s.exemplar){const ei=s.exemplar.input;$("exin").innerHTML=textOf(ei&&ei.item!==undefined?ei.item:ei);$("exout").innerHTML=renderOutput(s.exemplar.output);}
  else $("std").style.display="none";
  render();
}
function render(){
  const it=B.items[idx];
  $("count").textContent=`${idx+1} / ${B.items.length}`;
  // input panel
  const inp=it.input||{};
  $("cats").innerHTML=((inp.categories||inp.components||[])).map(c=>`<span class="chip">${esc(c)}</span>`).join("");
  $("crit").textContent=inp.criteria?("criteria — "+inp.criteria):(inp.scoring?("scoring — "+inp.scoring):(inp.standard?("standard — "+inp.standard):""));
  if(inp.subject){                                   // verify: render the composite subject
    const s=inp.subject;
    $("itemtext").innerHTML=`<span class="t">${esc(s.issue_title||"")}</span>`+
      `<div class="chips" style="margin:8px 0 4px"><span class="chip">label: ${esc(s.classified_as||"?")}</span>`+
      `<span class="chip">route: ${esc(s.routed_to||"?")}</span></div>`+
      `<div class="exlabel" style="margin-top:10px">drafted reply</div>`+mdRender(s.draft_reply||"");
  } else {
    $("itemtext").innerHTML=textOf(inp.item!==undefined?inp.item:inp);
  }
  // signal — why this item was surfaced for you
  const sg=$("signal");
  if(it.signal&&it.signal!=="clean"){
    const w={disagree:"contested — argue the other side",'low-conf':"low confidence",rare:"rare category",
             missed:"verify MISSED a planted error",flagged:"verify failed a real subject — check its issues"}[it.signal]||it.signal;
    const ctr=it.counter?`<div class="ctr">${esc(it.counter)}</div>`:"";
    sg.className="signal show "+it.signal;
    sg.innerHTML=`<span class="why">⚠ ${w}</span> — ${esc(it.signal_detail||"")}${ctr}`;
  } else { sg.className="signal"; sg.innerHTML=""; }
  // editor: prose mode edits the text field directly; else raw JSON
  PROSE=proseField(it.output);
  const cur=it.gold!=null?it.gold:it.output;
  $("lbl2txt").textContent=PROSE?("the "+PROSE+" — edit to the voice"):"raw json — edit to correct";
  $("editor").value=PROSE?(cur[PROSE]||""):pretty(cur);
  validate();
  drawDots();
  updateProgress();
}
function drawDots(){
  $("dots").innerHTML="";
  B.items.forEach((it,i)=>{
    const d=document.createElement("div");
    d.className="dot "+(it.decision||"")+(i===idx?" cur":"");
    d.title=`${i+1}: ${it.decision||"pending"}`;
    d.onclick=()=>{idx=i;render();};
    $("dots").appendChild(d);
  });
}
function updateProgress(){
  const dec=B.items.filter(x=>x.decision).length;
  const kept=B.items.filter(x=>x.decision==="approve"||x.decision==="improve").length;
  const comm=B.items.filter(x=>x.committed).length;
  $("progress").innerHTML=`${dec}/${B.items.length} reviewed · ${kept} to keep`+
     (comm?` · <span class="done">${comm} saved</span>`:"");
}
function parsed(){ try{return [JSON.parse($("editor").value),null];}catch(e){return [null,e.message];} }
function validate(){
  if(PROSE){                                    // prose mode — no JSON, live markdown preview
    $("editor").classList.remove("bad"); $("jsonerr").textContent=""; $("save").disabled=false;
    $("preview").innerHTML=mdRender($("editor").value);
    return;
  }
  const [val,err]=parsed();
  $("editor").classList.toggle("bad",!!err);
  $("jsonerr").textContent=err?("invalid JSON — "+err):"";
  $("save").disabled=!!err;
  if(!err) $("preview").innerHTML=renderOutput(val);
}
async function decide(kind){
  const it=B.items[idx];
  let gold=it.output, decision=kind;
  if(kind!=="skip"){
    if(PROSE){ gold={...it.output,[PROSE]:$("editor").value}; }
    else { const [val,err]=parsed(); if(err){validate();return;} gold=val; }
    decision=(pretty(gold)===pretty(it.output))?"approve":"improve";
  }
  it.decision=decision; it.gold=(kind==="skip"?null:gold);
  await fetch("/api/decision",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({index:idx,decision,gold:it.gold})});
  if(idx<B.items.length-1){idx++;render();}
  else{render();toast(decision==="skip"?"skipped":"saved — last item");}
}
async function commit(){
  const r=await (await fetch("/api/commit",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"})).json();
  B=await (await fetch("/api/batch")).json();
  render();
  toast(r.committed?`wrote ${r.committed} example(s) → state/examples/${B.specialist}.jsonl`:"nothing new to save");
}
let tmo;
function toast(m){const t=$("toast");t.textContent=m;t.classList.add("show");clearTimeout(tmo);tmo=setTimeout(()=>t.classList.remove("show"),2600);}

$("editor").addEventListener("input",validate);
$("save").onclick=()=>decide("save");
$("skip").onclick=()=>decide("skip");
$("reset").onclick=()=>{const o=B.items[idx].output;$("editor").value=PROSE?(o[PROSE]||""):pretty(o);validate();};
$("prev").onclick=()=>{if(idx>0){idx--;render();}};
$("commit").onclick=commit;
document.addEventListener("keydown",e=>{
  const inEditor=document.activeElement===$("editor");
  if((e.metaKey||e.ctrlKey)&&e.key==="Enter"){e.preventDefault();decide("save");}
  else if(!inEditor&&e.key==="s"){e.preventDefault();decide("skip");}
  else if(!inEditor&&e.key==="ArrowRight"){if(idx<B.items.length-1){idx++;render();}}
  else if(!inEditor&&e.key==="ArrowLeft"){if(idx>0){idx--;render();}}
});
load();
</script></body></html>"""
