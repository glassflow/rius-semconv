"""registry/media_parts.yaml: the file's own rules, and its checks against the fixtures.

Each rule gets one test that breaks the real data in exactly one way and
asserts the break is named.
"""

from __future__ import annotations

import copy

from conftest import ROOT
from generators import media_parts
from generators.registry import Registry

FIXTURES = ROOT / "fixtures"


def assert_flags(errors: list[str], fragment: str) -> None:
    assert any(fragment in e for e in errors), f"expected {fragment!r} in {errors}"


def test_committed_file_is_clean(base_data):
    media = base_data["media_parts"]
    assert media_parts.lint(media) == []
    assert media_parts.check_fixture_refs(media, FIXTURES) == []


def test_every_row_has_a_source_shape_and_direction(base_data):
    rows = base_data["media_parts"]["rows"]
    assert len(rows) == 22
    assert {r["direction"] for r in rows} == {"input", "output"}


def test_unknown_normalized_type_fails(data):
    data["media_parts"]["rows"][0]["normalized"] = "image"
    assert_flags(media_parts.lint(data["media_parts"]), "normalized must be one of")


def test_unknown_modality_fails(data):
    data["media_parts"]["rows"][0]["modality"] = "picture"
    assert_flags(media_parts.lint(data["media_parts"]), "modality must be one of")


def test_unknown_direction_fails(data):
    data["media_parts"]["rows"][0]["direction"] = "sideways"
    assert_flags(media_parts.lint(data["media_parts"]), "direction must be one of")


def test_unknown_path_fails(data):
    data["media_parts"]["rows"][0]["paths"] = ["telepathy"]
    assert_flags(media_parts.lint(data["media_parts"]), "unknown path telepathy")


def test_empty_fixtures_need_a_reason(data):
    row = data["media_parts"]["rows"][0]
    row["fixtures"] = []
    row.pop("reason", None)
    assert_flags(media_parts.lint(data["media_parts"]), "needs fixtures or a reason")


def test_row_naming_an_unrecorded_scenario_fails(data):
    data["media_parts"]["rows"][0]["fixtures"] = ["openinference-openai/no_such"]
    errors = media_parts.check_fixture_refs(data["media_parts"], FIXTURES)
    assert len(errors) == 1
    assert "openinference-openai/no_such" in errors[0]
    assert errors[0].startswith("media_parts: ")


def test_row_naming_an_unknown_family_fails(data):
    data["media_parts"]["rows"][0]["fixtures"] = ["no-such-family/x"]
    errors = media_parts.check_fixture_refs(data["media_parts"], FIXTURES)
    assert len(errors) == 1
    assert "no-such-family/x" in errors[0]


def test_fixture_id_without_a_scenario_fails(data):
    data["media_parts"]["rows"][0]["fixtures"] = ["openinference-openai"]
    assert_flags(media_parts.lint(data["media_parts"]), "fixtures must be <family>/<scenario>")


def test_row_naming_a_recorded_scenario_passes(data):
    family = "openinference-openai"
    import json

    manifest = json.loads((FIXTURES / family / "manifest.json").read_text())
    scenario = next(iter(next(iter(manifest["recordings"].values()))["scenarios"]))
    data["media_parts"]["rows"][0]["fixtures"] = [f"{family}/{scenario}"]
    assert media_parts.check_fixture_refs(data["media_parts"], FIXTURES) == []


def test_table_lists_every_row(base_data):
    media = base_data["media_parts"]
    table = media_parts.render_table(media)
    for row in media["rows"]:
        assert row["shape"].replace("|", "\\|") in table


def test_registry_lint_includes_media_parts(data):
    data["media_parts"]["rows"][0]["normalized"] = "image"
    assert_flags(Registry(copy.deepcopy(data)).lint(), "normalized must be one of")


def test_no_ticket_ids(data):
    data["media_parts"]["rows"][0]["reason"] = "see RIUS-1"
    assert_flags(Registry(copy.deepcopy(data)).lint(), "ticket id RIUS-1")
