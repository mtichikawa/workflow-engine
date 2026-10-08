"""1B — move_examples relabels a specialist's exemplars from one scope to another (the primitive
behind moving WRITE's voice out of 'baseline' into a tailored scope). Pure, tmp-backed, no brain."""

import engine.examples as ex


def test_move_examples_relabels_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "EX_ROOT", tmp_path)
    monkeypatch.setattr(ex, "PRIVATE_ROOT", tmp_path / "private")
    ex.save_example("write", {"topic": "a"}, {"post": "x"}, scope_name="baseline")
    ex.save_example("write", {"topic": "b"}, {"post": "y"}, scope_name="baseline")

    moved = ex.move_examples("write", "baseline", "mike")

    assert moved == 2
    assert not ex.path("write", "baseline").exists()      # source drained
    assert ex.count_examples("write", "mike") == 2         # landed in the tailored scope


def test_move_examples_noop_when_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "EX_ROOT", tmp_path)
    monkeypatch.setattr(ex, "PRIVATE_ROOT", tmp_path / "private")
    assert ex.move_examples("write", "baseline", "mike") == 0


def test_reads_merge_public_then_private(tmp_path, monkeypatch):
    # a scope can be split across the public corpus and private/ — reads see both, public first
    monkeypatch.setattr(ex, "EX_ROOT", tmp_path / "public")
    monkeypatch.setattr(ex, "PRIVATE_ROOT", tmp_path / "private")
    ex.save_example("rank", {"item": "pub"}, {"score": 1}, scope_name="baseline")
    ex.save_example("rank", {"item": "priv"}, {"score": 2}, scope_name="baseline", private=True)

    assert [r["input"]["item"] for r in ex.load_examples("rank", ["baseline"])] == ["pub", "priv"]
    assert ex.count_examples("rank", "baseline") == 2
    assert ex.path("rank", "baseline", private=True).parent.parent == tmp_path / "private"


def test_public_clone_without_private_still_loads(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "EX_ROOT", tmp_path / "public")
    monkeypatch.setattr(ex, "PRIVATE_ROOT", tmp_path / "absent")
    ex.save_example("rank", {"item": "pub"}, {"score": 1}, scope_name="baseline")
    assert ex.count_examples("rank", "baseline") == 1
