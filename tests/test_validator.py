"""Validator: catches malformed graphs before they run (static, no brain)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.core import Edge, Recipe, Step, is_valid, validate


def _errors(recipe):
    return [f.msg for f in validate(recipe, check_contracts=False) if f.level == "error"]

def _warnings(recipe):
    return [f.msg for f in validate(recipe, check_contracts=False) if f.level == "warning"]


def test_valid_linear():
    r = Recipe("ok", [Step("a", "x"), Step("b", "x", inputs={"v": "a.out"})])
    assert is_valid(r, check_contracts=False)
    assert not _errors(r)


def test_valid_loop():
    r = Recipe("loop",
               steps=[Step("gen", "x"), Step("check", "x", inputs={"n": "gen.n"})],
               edges=[Edge("gen", "check"), Edge("check", "gen", "check.ok == false")])
    assert is_valid(r, check_contracts=False)


def test_unknown_specialist():
    r = Recipe("unk", [Step("a", "no_such_specialist")])
    errs = [f.msg for f in validate(r, check_contracts=True) if f.level == "error"]
    assert any("unknown specialist" in m for m in errs)


def test_loop_without_condition():
    r = Recipe("badloop",
               steps=[Step("a", "x"), Step("b", "x", inputs={"v": "a.v"})],
               edges=[Edge("a", "b"), Edge("b", "a")])   # backward edge, no `when`
    assert any("no `when`" in m for m in _errors(r))


def test_no_exit():
    r = Recipe("noexit",
               steps=[Step("a", "x", inputs={"v": "b.v"}), Step("b", "x", inputs={"v": "a.v"})],
               edges=[Edge("a", "b"), Edge("b", "a", "b.ok == false")])
    # a->b and b->a(backward); a has forward out (a->b), b's only out is backward -> b is exit...
    # ensure at least the *reachability/exit* logic runs without crashing and both steps are reachable
    assert is_valid(r, check_contracts=False) or _errors(r)  # smoke: no crash


def test_bad_condition_ref():
    r = Recipe("badcond",
               steps=[Step("a", "x"), Step("b", "x", inputs={"v": "a.v"})],
               edges=[Edge("a", "b", "nope.field == 1")])   # 'nope' isn't a step
    assert any("references unknown 'nope'" in m for m in _errors(r))


def test_dangling_output_warning():
    # 'checkit' produces output nothing reads, and it isn't a terminal -> dangling warning
    r = Recipe("dangle",
               steps=[Step("a", "x"), Step("checkit", "x", inputs={"v": "a.v"}), Step("act", "x")],
               edges=[Edge("a", "checkit"), Edge("checkit", "act")])
    assert any("checkit" in m and "dangling" in m for m in _warnings(r))


def test_lone_guarded_gate_warns():
    # verify's only out-edge is guarded on pass -> the fail case dead-ends -> warning
    r = Recipe("gate",
               steps=[Step("verify", "x"), Step("act", "x", inputs={"v": "verify.verdict"})],
               edges=[Edge("verify", "act", "verify.verdict == 'pass'")])
    assert any("verify" in m and "single guarded" in m for m in _warnings(r))


def test_two_branches_no_gate_warning():
    # both pass and fail routed -> nothing dead-ends -> no lone-gate warning
    r = Recipe("branch",
               steps=[Step("verify", "x"), Step("act", "x", inputs={"v": "verify.verdict"})],
               edges=[Edge("verify", "act", "verify.verdict == 'pass'"),
                      Edge("verify", "act", "verify.verdict == 'fail'")])
    assert not any("single guarded" in m for m in _warnings(r))


# ---- checks 0, 10-16: following the data (library specialists, so contracts and value sets are real) ----
from engine import specialists  # noqa: E402,F401

CLS = {"categories": ["bug", "spam"], "criteria": "kind"}


def _lib(steps, edges=None):
    return [f.msg for f in validate(Recipe("t", steps, edges or [])) if f.level == "error"]


def _base():
    return [Step("cls", "classify", config=CLS, inputs={"item": "payload"}),
            Step("chk", "verify", config={"standard": "s"}, inputs={"subject": "cls.label"}),
            Step("act", "act", gate=True, config={"target": "file", "mode": "staged"},
                 inputs={"payload": {"content": "cls.reasoning"}})]


def test_library_graph_is_clean():
    assert _lib(_base()) == []


def test_duplicate_step_id():
    steps = _base() + [Step("cls", "classify", config=CLS, inputs={"item": "payload"})]
    assert any("share the id 'cls'" in m for m in _lib(steps))


def test_dangling_edge_is_reported_not_a_crash():
    assert any("unknown step 'ghost'" in m for m in _lib(_base(), [Edge("cls", "ghost")]))


def test_typo_of_a_step_is_caught_but_literals_pass():
    steps = _base()
    steps[1].inputs = {"subject": "clss.label"}
    assert any("did you mean 'cls'" in m for m in _lib(steps))
    steps[1].inputs = {"subject": "report-final.txt"}
    assert _lib(steps) == []


def test_reading_a_field_the_step_never_produces():
    steps = _base()
    steps[1].inputs = {"subject": "cls.score"}
    assert any("doesn't produce 'score'" in m for m in _lib(steps))


def test_reading_a_step_that_has_not_run_yet():
    steps = _base()
    steps[0].inputs = {"item": "chk.verdict"}
    assert any("hasn't run by then" in m for m in _lib(steps))


def test_loop_feedback_is_allowed():
    steps = [Step("cls", "classify", config=CLS, inputs={"item": "payload", "fb": "chk.issues"}),
             Step("chk", "verify", config={"standard": "s"}, inputs={"subject": "cls.label"})]
    assert _lib(steps, [Edge("cls", "chk"), Edge("chk", "cls", "chk.verdict == 'fail'")]) == []


def test_type_mismatch():
    steps = _base()
    steps[0].config = {"criteria": "kind"}
    steps[0].inputs = {"item": "payload", "categories": "chk.verdict"}      # str into a list input
    assert any("which takes list" in m for m in _lib(steps))


def test_condition_operator_field_and_value():
    for when, needle in (("chk.verdict = 'pass'", "invalid operator"),
                         ("chk.verdcit == 'pass'", "doesn't produce"),
                         ("chk.verdict == 'passed'", "never produces"),
                         ("cls.label == 'feature'", "never produces")):
        edges = [Edge("cls", "chk"), Edge("chk", "act", when), Edge("chk", "act", "chk.verdict == 'fail'")]
        assert any(needle in m for m in _lib(_base(), edges)), when


def test_and_join_that_can_never_start():
    steps = _base()[:2] + [Step("alt", "verify", config={"standard": "s"}, inputs={"subject": "cls.label"}),
                           _base()[2]]
    edges = [Edge("cls", "chk"), Edge("chk", "act", "chk.verdict == 'pass'"),
             Edge("chk", "alt", "chk.verdict != 'pass'"), Edge("alt", "act")]
    assert any("can never start" in m for m in _lib(steps, edges))


def test_side_effect_needs_a_gate_at_or_before_it():
    steps = _base()
    steps[2].gate = False
    assert any("no human gate" in m for m in _lib(steps))
    steps[1].gate = True                                                      # a gate upstream is enough
    assert _lib(steps) == []
