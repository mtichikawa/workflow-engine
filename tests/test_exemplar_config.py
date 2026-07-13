"""1A — config-agnostic vs config-keyed exemplar retrieval. A config-keyed specialist (classify)
only injects exemplars from a matching config; a free-form one (respond) injects across configs.
Pure — uses fewshot.using() to supply the exemplar pool, no brain."""

from engine import fewshot


def test_config_key_extracts_config_fields():
    k = fewshot._config_key({"item": "x", "categories": ["a", "b"], "criteria": "type"})
    assert "categories" in k and "criteria" in k and '"x"' not in k   # content excluded


def test_config_keyed_retrieval_filters_by_config():
    same = {"item": "the login button is broken", "categories": ["bug", "feature"], "criteria": "type"}
    other = {"item": "the login button is broken", "categories": ["billing", "other"], "criteria": "type"}
    pool = [{"input": same, "output": {"label": "bug"}},
            {"input": other, "output": {"label": "other"}}]     # identical content, different config
    with fewshot.using("classify", pool):
        got = fewshot.retrieve("classify", dict(same))
    # only the matching-config exemplar is eligible — the other config's label would be invalid here
    assert len(got) == 1 and got[0]["input"]["categories"] == ["bug", "feature"]


def test_free_form_retrieval_ignores_config():
    a = {"message": "how do I reset my password", "tone": "formal"}
    b = {"message": "how do I reset my password", "tone": "casual"}
    pool = [{"input": a, "output": {"reply": "..."}},
            {"input": b, "output": {"reply": "..."}}]           # different config (tone)
    with fewshot.using("respond", pool):
        got = fewshot.retrieve("respond", {"message": "how do I reset my password", "tone": "formal"})
    assert len(got) == 2   # craft transfers across configs — both eligible
