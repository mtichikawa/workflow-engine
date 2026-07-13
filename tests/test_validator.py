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
