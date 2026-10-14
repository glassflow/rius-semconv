"""tools/check_weaver_types.py, on hand-built resolved registries."""

from __future__ import annotations

from tools import check_weaver_types


def resolved(type_, ours, divergence=None):
    rius = {"type": ours}
    if divergence:
        rius["upstream_divergence"] = divergence
    attribute = {"key": "gen_ai.request.top_k", "type": type_, "annotations": {"rius": rius}}
    groups = [{"id": "rius.upstream", "attributes": [attribute]}]
    return {"registry": {"attribute_groups": groups}}


def test_matching_types_agree():
    assert check_weaver_types.check(resolved("int", "int")) == []


def test_upstream_any_accepts_every_type():
    assert check_weaver_types.check(resolved("any", "string")) == []


def test_an_enum_is_compared_by_its_value_type():
    enum = {"members": [{"id": "a", "value": "A"}]}
    assert check_weaver_types.check(resolved(enum, "string")) == []


def test_a_silent_divergence_is_flagged():
    (error,) = check_weaver_types.check(resolved("int", "double"))
    assert "the row says double, upstream says int" in error


def test_a_recorded_divergence_is_accepted():
    divergence = {"type": "int", "note": "x"}
    assert check_weaver_types.check(resolved("int", "double", divergence)) == []


def test_a_stale_divergence_is_flagged():
    (error,) = check_weaver_types.check(resolved("int", "int", {"type": "int", "note": "x"}))
    assert "drop it" in error
