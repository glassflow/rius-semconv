"""tools/to_weaver.py: the Weaver registry written from registry/.

The baseline test is that the committed model/ is what the converter writes;
the others pin the mapping decisions on the real registry.
"""

from __future__ import annotations

import copy

import pytest
import yaml

from conftest import ROOT
from tools import to_weaver


@pytest.fixture(scope="module")
def own(base_data):
    files = to_weaver.render(base_data)
    return yaml.safe_load(files[to_weaver.MODEL / "rius" / "registry.yaml"])


@pytest.fixture(scope="module")
def files(base_data):
    return {
        p.relative_to(to_weaver.ROOT).as_posix(): yaml.safe_load(text)
        for p, text in to_weaver.render(base_data).items()
    }


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


def test_an_upstream_equivalent_is_noted_not_deprecated(base_data):
    data = copy.deepcopy(base_data)
    version = next(
        r for r in data["attributes"]["attributes"] if r["const"] == "RIUS_MAIN_AGENT_VERSION"
    )
    version["upstream_equivalent"] = "gen_ai.main_agent.version"
    own = yaml.safe_load(to_weaver.render(data)[to_weaver.MODEL / "rius" / "registry.yaml"])
    main_agent = attribute(own, "rius.main_agent.version")
    assert "gen_ai.main_agent.version" in main_agent["note"]
    assert "deprecated" not in main_agent


@pytest.mark.parametrize("field", ["id", "name", "description"])
def test_a_key_moved_into_the_genai_registry_is_deprecated_naming_its_successor(own, field):
    ours = attribute(own, f"rius.main_agent.{field}")
    assert ours["deprecated"]["reason"] == "uncategorized"
    assert "renamed_to" not in ours["deprecated"]
    assert f"gen_ai.main_agent.{field}" in ours["deprecated"]["note"]
    # The "planned move, not deprecated" line is for upstream_equivalent only.
    assert "is not deprecated" not in ours["note"]


def test_the_main_agent_version_has_no_upstream_twin_and_stays(own):
    assert "deprecated" not in attribute(own, "rius.main_agent.version")


def test_the_upstream_main_agent_keys_are_referenced_not_defined(files, own):
    groups = files["model/rius/upstream.yaml"]["attribute_groups"]
    (upstream,) = [g for g in groups if g["id"] == "rius.upstream"]
    refs = {a["ref"] for a in upstream["attributes"]}
    defined = {a["key"] for a in own["attributes"]}
    for field in ("id", "name", "description"):
        assert f"gen_ai.main_agent.{field}" in refs
        assert f"gen_ai.main_agent.{field}" not in defined


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


def refs(files, group_id):
    groups = files["model/rius/upstream.yaml"]["attribute_groups"]
    return {a["ref"]: a for g in groups if g["id"] == group_id for a in g["attributes"]}


def defined(files):
    return {
        a["key"]
        for path, doc in files.items()
        if path.startswith("model/")
        for a in doc.get("attributes", [])
    }


def test_no_upstream_key_is_defined_here(base_data, files):
    keys = defined(files)
    for r in base_data["attributes"]["attributes"]:
        if r.get("origin") == "otel" or "upstream" in r:
            assert r["key"] not in keys
    assert not [k for k in keys if k.startswith(("gen_ai.", "otel."))]


def test_every_upstream_row_is_a_ref(base_data, files):
    upstream = refs(files, "rius.upstream")
    for r in base_data["attributes"]["attributes"]:
        if r["symbol"] == "attribute" and (r.get("origin") == "otel" or "upstream" in r):
            assert r["key"] in upstream


def test_a_ref_carries_its_level_values_and_rationale(files):
    upstream = refs(files, "rius.upstream")
    assert upstream["mcp.method.name"]["requirement_level"] == "required"
    rius = upstream["mcp.method.name"]["annotations"]["rius"]
    assert rius["values"] == {"MCP_METHOD_TOOLS_CALL": "tools/call"}
    assert "rationale" in upstream["gen_ai.tool.call.id"]["annotations"]["rius"]


def test_a_ref_carries_its_wire_type(files):
    rius = refs(files, "rius.upstream")["gen_ai.request.top_k"]["annotations"]["rius"]
    assert rius["type"] == "int"
    assert "upstream_divergence" not in rius


def test_passthrough_keys_are_refs(files):
    assert "gen_ai.conversation.id" in refs(files, "rius.passthrough")


def test_openinference_keys_are_defined_with_their_enum(files):
    doc = files["model/inputs/openinference.yaml"]
    kind = next(a for a in doc["attributes"] if a["key"] == "openinference.span.kind")
    assert [m["value"] for m in kind["type"]["members"]][:2] == ["AGENT", "LLM"]
    groups = {g["id"]: [a["ref"] for a in g["attributes"]] for g in doc["attribute_groups"]}
    assert "input.value" in groups["rius.openinference"]
    assert "llm.invocation_parameters" in groups["rius.normalizer_input.openinference"]


def test_a_usage_prefix_becomes_a_template_weaver_can_match(files):
    # Weaver matches a template key by `<key>.`, so the key carries no `*`.
    doc = files["model/inputs/pydantic_ai.yaml"]
    cache = next(a for a in doc["attributes"] if a["key"] == "pydantic_ai.cache")
    assert cache["type"] == "template[any]"
    assert not [a for a in doc["attributes"] if "*" in a["key"]]


def test_every_decided_usage_key_names_its_target(base_data, files):
    inputs = [
        a
        for path, doc in files.items()
        if path.startswith("model/inputs/")
        for a in doc["attributes"]
        if "normalizer_input" in a["annotations"]["rius"]
    ]
    assert inputs
    for a in inputs:
        decision = a["annotations"]["rius"]["normalizer_input"]
        if decision["decision"] == "mapped":
            assert decision["target"]
            assert decision["target"] in a["brief"]


def test_gen_ai_usage_inputs_stay_in_the_sidecar(params):
    names = {e.get("key") or e.get("prefix") for e in params["normalizer_inputs"]}
    assert "gen_ai.usage.prompt_tokens" in names
    assert "gen_ai.aggregated_usage." in names


def test_the_main_agent_id_is_emitted_whenever_the_entity_is(files):
    groups = files["model/rius/upstream.yaml"]["attribute_groups"]
    (upstream,) = [g for g in groups if g["id"] == "rius.upstream"]
    (main_agent_id,) = [a for a in upstream["attributes"] if a["ref"] == "gen_ai.main_agent.id"]
    assert main_agent_id["requirement_level"] == {
        "conditionally_required": "always, whenever the main-agent entity is emitted"
    }
