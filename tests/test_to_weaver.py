"""tools/to_weaver.py: the Weaver registry written from registry/.

The baseline test is that the committed model/ is what the converter writes;
the others pin the mapping decisions on the real registry.
"""

from __future__ import annotations

import pytest
import yaml

from conftest import ROOT
from tools import to_weaver


@pytest.fixture(scope="module")
def own(base_data):
    files = to_weaver.render(base_data)
    return yaml.safe_load(files[to_weaver.MODEL / "rius" / "registry.yaml"])


@pytest.fixture(scope="module")
def params(base_data):
    return yaml.safe_load(to_weaver.render(base_data)[to_weaver.PARAMS])["params"]


def attribute(own, key):
    return next(a for a in own["attributes"] if a["key"] == key)


def test_committed_model_is_current():
    assert to_weaver.main(["--check"]) == 0


def test_every_rius_row_is_defined(base_data, own):
    keys = {a["key"] for a in own["attributes"]}
    for r in base_data["attributes"]["attributes"]:
        if r.get("origin") == "rius" and r["symbol"] == "attribute":
            assert r["key"] in keys


def test_every_definition_has_a_stability_and_a_brief(own):
    for item in own["attributes"] + own["events"]:
        assert item["stability"] in {"development", "stable"}
        assert item["brief"]


def test_a_rius_prefix_becomes_a_template(own):
    assert attribute(own, "rius.aggregated_usage")["type"] == "template[int]"
    assert attribute(own, "rius.request")["type"] == "template[any]"


def test_json_becomes_any_and_keeps_its_wire_type(own):
    sizes = attribute(own, "rius.context.sizes")
    assert sizes["type"] == "any"
    assert sizes["annotations"]["rius"]["wire_type"] == "json"


def test_a_rename_is_kept_deprecated_and_excluded_from_code_generation(own):
    old = attribute(own, "glassflow.span.pending")
    assert old["deprecated"]["reason"] == "renamed"
    assert old["deprecated"]["renamed_to"] == "rius.span.pending"
    assert old["annotations"]["code_generation"] == {"exclude": True}


def test_an_upstream_equivalent_is_noted_not_deprecated(own):
    main_agent = attribute(own, "rius.main_agent.id")
    assert "gen_ai.main_agent.id" in main_agent["note"]
    assert "deprecated" not in main_agent


def test_the_rius_event_is_an_event(own):
    (event,) = own["events"]
    assert event["name"] == "gen_ai.first_token"
    assert event["requirement_level"] == "recommended"


def test_columns_without_a_weaver_field_ride_the_annotation(own):
    pending = attribute(own, "rius.span.pending")["annotations"]["rius"]
    assert pending["const"] == "RIUS_SPAN_PENDING"
    assert pending["category"] == "identity"
    assert "not_pending" in pending


def test_layout_keeps_every_row_in_order(base_data, params):
    consts = [r["const"] for r in base_data["attributes"]["attributes"]]
    assert [e["const"] for e in params["layout"]] == consts


def test_rows_weaver_cannot_define_stay_whole_in_the_layout(params):
    scope = next(e for e in params["layout"] if e["const"] == "TRACER_NAME")
    assert scope["key"] == "rius"
    assert scope["symbol"] == "scope"


def test_a_stale_file_fails_the_check(tmp_path, monkeypatch):
    rius = tmp_path / "model" / "rius"
    rius.mkdir(parents=True)
    (rius / "leftover.yaml").write_text("file_format: definition/2\n")
    monkeypatch.setattr(to_weaver, "OWNED_DIRS", (rius,))
    monkeypatch.setattr(to_weaver, "ROOT", tmp_path)
    monkeypatch.setattr(to_weaver, "MODEL", tmp_path / "model")
    monkeypatch.setattr(to_weaver, "PARAMS", tmp_path / "templates" / "params.yaml")
    assert to_weaver.main(["--check"]) == 1
    assert to_weaver.main([]) == 0
    assert not (rius / "leftover.yaml").exists()
    assert to_weaver.main(["--check"]) == 0


def test_lint_errors_write_nothing(monkeypatch, data):
    data["attributes"]["attributes"][0]["const"] = data["attributes"]["attributes"][1]["const"]
    monkeypatch.setattr(to_weaver, "load_data", lambda: data)
    assert to_weaver.main(["--check"]) == 1


def test_manifest_is_not_written_here():
    assert (ROOT / "model" / "manifest.yaml") not in to_weaver.render(to_weaver.load_data())
