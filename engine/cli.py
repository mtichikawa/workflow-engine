"""engine — run a recipe, approve gates, inspect the board.

    python -m engine.cli run triage  --repo psf/requests --limit 8 [--auto]
    python -m engine.cli run content --topic "..." --brief "..." [--auto]
    python -m engine.cli approve <run_id> [item step]
    python -m engine.cli board <run_id>
"""

from __future__ import annotations

import argparse
import time

from . import specialists  # noqa: F401  (registers the library)
from .core import Board, Dispatcher, Tracer, get
from .recipes import RECIPES


def _run(args) -> None:
    recipe = RECIPES[args.recipe]
    run_id = f"{args.recipe}-{int(time.time())}"
    board = Board(recipe=recipe.name, run_id=run_id)

    # ---- intake: fill the hopper ----------------------------------------
    if args.recipe == "triage":
        issues = _safe_fetch("github", {"repo": args.repo, "limit": args.limit})
        for it in issues:
            board.add_item(it["id"], it)
        print(f"intake: {len(issues)} issues from {args.repo}\n")
    elif args.recipe == "review":
        prs = _safe_fetch("github_pr", {"repo": args.repo, "limit": args.limit})
        for pr in prs:
            board.add_item(pr["id"], pr)
        print(f"intake: {len(prs)} open PRs from {args.repo}\n")
    elif args.recipe == "content":
        slug = "".join(c if c.isalnum() else "-" for c in args.topic.lower())[:40].strip("-")
        board.add_item("topic", {"topic": args.topic, "brief": args.brief,
                                 "source": args.source, "limit": args.limit, "slug": f"{slug}.txt"})
        print(f"intake: 1 topic -> {args.topic!r}\n")
    elif args.recipe == "refine":
        slug = "".join(c if c.isalnum() else "-" for c in args.topic.lower())[:40].strip("-")
        board.add_item("topic", {"topic": args.topic, "brief": args.brief, "sources": [],
                                 "slug": f"{slug}.txt"})
        print(f"intake: 1 topic -> {args.topic!r} (draft→verify→revise loop)\n")

    if not _validate_or_abort(recipe):
        return
    Dispatcher(recipe, board, Tracer(run_id), concurrency=args.concurrency).run(auto_approve=args.auto)
    _record_runs(board, recipe)
    _report(board, run_id)


def _approve(args) -> None:
    board = Board.load(args.run_id)
    recipe = RECIPES[board.recipe]
    disp = Dispatcher(recipe, board, Tracer(args.run_id))
    gated = board.with_status("gated")
    targets = [(args.item, args.step)] if args.item else [(c.item_id, c.step_id) for c in gated]
    for item_id, step_id in targets:
        disp.approve(item_id, step_id)
    disp.run(auto_approve=False)     # let any freed downstream work run
    _report(board, args.run_id)


def _board(args) -> None:
    board = Board.load(args.run_id)
    _report(board, args.run_id)


def _compose(args) -> None:
    from .composer import compose
    from .specialists import CAPABILITIES
    res = compose(args.use_case, draft=args.draft)
    drafted = res.get("drafted", [])
    print(f"\nComposed recipe for: {args.use_case!r}\n")
    for s in res["steps"]:
        name = s["specialist"]
        if name in res["missing"]:
            tag = "NEW! "
        elif name in drafted:
            tag = "DRFT "
        elif name in CAPABILITIES:
            tag = "reuse"
        else:
            tag = "domn "
        print(f"  {tag}  {name:<14}{'  [GATE]' if s.get('gate') else ''}")
    if res["gaps"]:
        print("\nGaps the Composer identified:")
        for g in res["gaps"]:
            print(f"  · {g.get('name')}: {g.get('why', '')}")
            print(f"      input {g.get('input')} -> output {g.get('output')}")
    if res.get("edges"):
        print("\nedges (control flow):")
        for e in res["edges"]:
            w = f"   when {e['when']}" if e.get("when") else ""
            print(f"    {e['from']} -> {e['to']}{w}")
    if drafted:
        print(f"\nDRAFTED {len(drafted)} provisional specialist(s): {', '.join(drafted)}")
        print("  (untrusted — no eval yet; it runs, but validate it via the gate before relying on it)")
    for f in res.get("findings", []):
        print(f"  validator [{f.level}]: {f.msg}")
    print(f"\nrunnable:  {res['runnable']}")
    if args.run and res["runnable"]:
        run_id = f"composed-{int(time.time())}"
        board = Board(recipe="composed", run_id=run_id)
        board.add_item("item", {"text": args.input, "topic": args.input, "message": args.input,
                                "source": "hn", "limit": 5})
        print("\n--- running the composed recipe ---")
        Dispatcher(res["recipe"], board, Tracer(run_id)).run(auto_approve=args.auto)
        _record_runs(board, res["recipe"])
        _report(board, run_id)
    elif args.run:
        print("not runnable yet — fill the gap(s) above, then it composes cleanly.")


def _review_cmd(args) -> None:
    from .examples import write_review
    board = Board.load(args.run_id)
    if board.recipe not in RECIPES:
        print(f"review supports named recipes; '{board.recipe}' isn't one.")
        return
    path = write_review(board, RECIPES[board.recipe])
    n_items = len(board.with_status("gated"))
    print(f"wrote {path}  ({n_items} gated item(s))")
    print("edit any 'output' you'd correct, leave the good ones, set approve:false to skip an item, then:")
    print(f"  python -m engine.cli capture {args.run_id}")


def _capture_cmd(args) -> None:
    from .examples import capture, count_examples, load_review
    review = load_review(args.run_id)
    n, approved = capture(review)
    board = Board.load(args.run_id)
    recipe = RECIPES[board.recipe]
    disp = Dispatcher(recipe, board, Tracer(args.run_id))
    for item_id in approved:
        for c in board.cards_for(item_id):
            if c.status == "gated":
                disp.approve(item_id, c.step_id)
    disp.run(auto_approve=False)
    _record_runs(board, recipe)
    print(f"captured {n} labeled example(s) from {len(approved)} approved item(s); gates approved.")


def _examples_cmd(args) -> None:
    from .examples import count_examples
    from .specialists import CAPABILITIES, DOMAIN
    print("\n  specialist    examples")
    print("  " + "-" * 24)
    for name in CAPABILITIES + DOMAIN:
        c = count_examples(name)
        if c or not args.nonzero:
            print(f"  {name:<12}  {c}")


def _safe_fetch(source: str, params: dict) -> list:
    try:
        return get("fetch").run({"source": source, "params": params}, {})["items"]
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"intake: couldn't fetch from {source} {params.get('repo', '')} — {e}")


def _validate_or_abort(recipe) -> bool:
    from .core import validate
    findings = validate(recipe)
    for w in (f for f in findings if f.level == "warning"):
        print(f"  validator [warning]: {w.msg}")
    errs = [f for f in findings if f.level == "error"]
    if errs:
        print("VALIDATION FAILED — not running this recipe:")
        for e in errs:
            print(f"  [error] {e.msg}")
        return False
    return True


def _record_runs(board, recipe) -> None:
    from .registry import record_run
    for card in board.cards.values():
        if card.status in ("done", "gated"):
            record_run(recipe.step(card.step_id).specialist)


def _registry(args) -> None:
    from .registry import catalog, is_provisional
    print("\n  specialist    kind        runs   eval   does")
    print("  " + "-" * 72)
    for c in catalog():
        tr = c["track_record"]
        ev = f"{tr['eval']:.0%}" if tr["eval"] is not None else "  —"
        prov = "  [PROVISIONAL]" if is_provisional(c["name"]) else ""
        print(f"  {c['name']:<12}  {c['kind']:<9}  {tr['runs']:>4}  {ev:>5}   {c['does'][:34]}{prov}")


def _eval(args) -> None:
    from evals.suite import missing_evals, run
    from .registry import record_eval
    results = run([args.name] if args.name else None)
    for r in results:
        record_eval(r.specialist, r.score, r.kind)
    print("\n  specialist    kind       score")
    print("  " + "-" * 34)
    for r in sorted(results, key=lambda r: (r.kind, r.specialist)):
        print(f"  {r.specialist:<12}  {r.kind:<9}  {r.passed}/{r.total}  {r.score:.0%}")
    from evals.suite import provisional_without_eval
    miss = missing_evals()
    if miss:
        print(f"\n  CONVENTION VIOLATION — no eval for: {', '.join(miss)}")
        print("  (every trusted specialist must ship with an eval — see evals/suite.py)")
    else:
        print("\n  ✓ every trusted specialist has an eval.")
    prov = provisional_without_eval()
    if prov:
        print(f"  provisional (eval not required until promotion): {', '.join(prov)}")

    from evals.examples_eval import run_all
    rows = run_all()
    if rows:
        print("\n  examples-as-eval  (leave-one-out over curated golds)")
        print("  " + "-" * 46)
        for name, p, t in rows:
            print(f"  {name:<14} {p}/{t}  {p / t:.0%}")


def _fit(args) -> None:
    """Compute + cache the empirical few-shot policy per specialist (learning-loop 1C): run the
    leave-one-out eval WITH and WITHOUT few-shot and keep it on only where it helps. `--samples N`
    votes across N runs to beat the CLI brain's non-determinism (2B')."""
    from evals.examples_eval import fewshot_fit, fit_all
    k = max(1, getattr(args, "samples", 1))
    print(f"\n  few-shot fit — does few-shot improve the leave-one-out eval?  ({k} sample(s))")
    print("  majority vote across samples; ties keep it on. a checker that does worse -> OFF, from data")
    print("  " + "-" * 66)
    rows = [(args.name, fewshot_fit(args.name, samples=k))] if args.name else fit_all(samples=k)
    for name, d in rows:
        if not d:
            print(f"  {name:<14} (skipped — no matcher / too few golds)")
            continue
        verdict = "few-shot ON" if d["helps"] else "few-shot OFF"
        spread = f"with {d['with']} vs without {d['without']}" if k > 1 else \
                 f"with {d['with'][0]}/{d['n']} vs without {d['without'][0]}/{d['n']}"
        print(f"  {name:<14} {spread}  (votes {d['votes']}, mean {d['with_mean']} vs {d['without_mean']})  -> {verdict}")
    print("\n  cached to the registry; fewshot.block() reads it at run time.")


def _train_cmd(args) -> None:
    from collections import Counter
    from .trainer import generate_batch, serve
    if args.generate:
        batch = generate_batch(args.name, args.generate, args.repo)
        sig = Counter(it["signal"] for it in batch["items"])
        print(f"\ngenerated {len(batch['items'])} items  ·  labels {batch.get('dist', {})}")
        print(f"  surfaced (hard first): {dict(sig)}")
        print("  disagree/low-conf/rare need your judgment; clean ones are near-duplicates to skim.")
    serve(args.name, port=args.port, open_browser=not args.no_open)


def _benchmark_cmd(args) -> None:
    from .autotest import run_benchmark
    print("\n  COMPOSER BENCHMARK — re-derive hand-built specialists from a description,")
    print("  score against their REAL human-labeled evals (non-circular ground truth).")
    print("  " + "-" * 66)
    originals = {"classify": "6/6", "rank": "3/3", "route": "3/3"}
    for r in run_benchmark():
        s = r["structural"]
        t = r["target"]
        print(f"  {t:<9} auto-written {r['score']:<5} ({r['pct']:.0%})   hand-built {originals.get(t,'?')}   "
              f"| structural_pass={s['structural_pass']} crashes={s['crashes']}")
    print("\n  (Consistency needs the API brain — the CLI brain ignores temperature. Genuinely")
    print("   novel specialists still require human validation; this proves it writes WORKING ones.)")


def _costs_cmd(args) -> None:
    from .costs import summary
    s = summary()
    print(f"\n  token usage  (state/token_log.jsonl)")
    print("  " + "-" * 46)
    print(f"  calls        {s['calls']:>12,}")
    print(f"  input tok    {s['in']:>12,}")
    print(f"  output tok   {s['out']:>12,}")
    print(f"  est API cost {'$%.4f' % s['est_usd']:>12}   (list price; CLI on Max bills $0 today)")
    if s["by_tag"] and len(s["by_tag"]) > 1:
        print("\n  by tag        calls    in tok    out tok   est $")
        for tag, t in sorted(s["by_tag"].items(), key=lambda kv: -kv[1]["est_usd"]):
            print(f"  {tag:<12} {t['calls']:>5}  {t['in']:>9,} {t['out']:>9,}  ${t['est_usd']:.4f}")


def _replay_cmd(args) -> None:
    from .replay import write_replay
    path = write_replay(args.run_id)
    print(f"wrote replay -> {path}  (open it in a browser and press play)")


def _view(args) -> None:
    from .view import write_view
    board = Board.load(args.run_id)
    step_ids = [s.id for s in RECIPES[board.recipe].steps]
    path = write_view(args.run_id, step_ids)
    print(f"wrote board view -> {path}")


def _report(board: Board, run_id: str) -> None:
    print(f"\n=== board {run_id} ===")
    for status, cards in board.snapshot().items():
        print(f"  {status:<8} {len(cards):>3}  {', '.join(cards[:6])}{' …' if len(cards) > 6 else ''}")
    flagged = [c for c in board.cards.values() if (c.coverage or {}).get("flag")]
    if flagged:
        print(f"\n{len(flagged)} card(s) fell back toward BASELINE (tailored coverage thin) — "
              "prime spots to add a tailored example:")
        for c in flagged[:8]:
            cov = c.coverage
            print(f"  [{cov['flag']}] {c.item_id}:{c.step_id}  "
                  f"tailored {cov['tailored']}/{cov['total']} slots (ratio {cov['ratio']})")

    gated = board.with_status("gated")
    if gated:
        print(f"\n{len(gated)} card(s) awaiting approval — staged (not sent):")
        for c in gated[:6]:
            print(f"  {c.item_id}:{c.step_id} -> {c.output.get('result') if c.output else None}")
        print(f"\napprove with:  python -m engine.cli approve {run_id}")


def main() -> None:
    p = argparse.ArgumentParser(prog="engine")
    p.add_argument("--scope", default=None, metavar="TENANT",
                   help="tenant scope for examples (default: baseline). Reads baseline+<scope>, "
                        "writes to <scope>. The multi-tenant seam.")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run"); r.set_defaults(fn=_run)
    r.add_argument("recipe", choices=list(RECIPES))
    r.add_argument("--repo", default="psf/requests")
    r.add_argument("--limit", type=int, default=8)
    r.add_argument("--topic", default="")
    r.add_argument("--brief", default="Write as a sharp, no-hype technical founder.")
    r.add_argument("--source", default="hn")
    r.add_argument("--auto", action="store_true", help="auto-approve gates (flow straight through)")
    r.add_argument("--concurrency", type=int, default=1, help="run ready cards in parallel (N workers)")

    a = sub.add_parser("approve"); a.set_defaults(fn=_approve)
    a.add_argument("run_id"); a.add_argument("item", nargs="?"); a.add_argument("step", nargs="?")

    b = sub.add_parser("board"); b.set_defaults(fn=_board)
    b.add_argument("run_id")

    v = sub.add_parser("view"); v.set_defaults(fn=_view)
    v.add_argument("run_id")

    rp = sub.add_parser("replay"); rp.set_defaults(fn=_replay_cmd)
    rp.add_argument("run_id")

    e = sub.add_parser("eval"); e.set_defaults(fn=_eval)

    f = sub.add_parser("fit"); f.add_argument("name", nargs="?")
    f.add_argument("--samples", type=int, default=1, help="runs to majority-vote over (beats CLI non-determinism)")
    f.set_defaults(fn=_fit)
    e.add_argument("name", nargs="?", help="one specialist, or omit for all")

    reg = sub.add_parser("registry"); reg.set_defaults(fn=_registry)

    co = sub.add_parser("costs"); co.set_defaults(fn=_costs_cmd)

    bm = sub.add_parser("benchmark"); bm.set_defaults(fn=_benchmark_cmd)

    rv = sub.add_parser("review"); rv.set_defaults(fn=_review_cmd)
    rv.add_argument("run_id")

    cap = sub.add_parser("capture"); cap.set_defaults(fn=_capture_cmd)
    cap.add_argument("run_id")

    ex = sub.add_parser("examples"); ex.set_defaults(fn=_examples_cmd)
    ex.add_argument("--nonzero", action="store_true", help="only specialists with examples")

    tr = sub.add_parser("train"); tr.set_defaults(fn=_train_cmd)
    tr.add_argument("name", help="specialist to build examples for")
    tr.add_argument("--generate", type=int, default=0, metavar="N", help="first generate a pool of ~N fresh inputs")
    tr.add_argument("--repo", default="auto", help="'auto' = diverse multi-repo pool, or pin one repo")
    tr.add_argument("--port", type=int, default=8765)
    tr.add_argument("--no-open", action="store_true", help="don't auto-open the browser")

    c = sub.add_parser("compose"); c.set_defaults(fn=_compose)
    c.add_argument("use_case")
    c.add_argument("--run", action="store_true", help="run it if composable from the library")
    c.add_argument("--input", default="", help="the work-item text to run on")
    c.add_argument("--auto", action="store_true")
    c.add_argument("--draft", action="store_true", help="draft provisional specialists for any gaps")

    from .drafting import load_drafted
    load_drafted()                      # make persisted provisional specialists available
    args = p.parse_args()
    if getattr(args, "scope", None):    # set the ambient tenant scope once, at the entry point
        from . import scope
        scope.set_scope(args.scope)
    args.fn(args)


if __name__ == "__main__":
    main()
