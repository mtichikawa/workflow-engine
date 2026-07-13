"""1B — move_examples relabels a specialist's exemplars from one scope to another (the primitive
behind moving WRITE's voice out of 'baseline' into a tailored scope). Pure, tmp-backed, no brain."""

import engine.examples as ex


def test_move_examples_relabels_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "EX_ROOT", tmp_path)
    ex.save_example("write", {"topic": "a"}, {"post": "x"}, scope_name="baseline")
    ex.save_example("write", {"topic": "b"}, {"post": "y"}, scope_name="baseline")

    moved = ex.move_examples("write", "baseline", "mike")

    assert moved == 2
    assert not ex.path("write", "baseline").exists()      # source drained
    assert ex.count_examples("write", "mike") == 2         # landed in the tailored scope


def test_move_examples_noop_when_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "EX_ROOT", tmp_path)
    assert ex.move_examples("write", "baseline", "mike") == 0
