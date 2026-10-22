"""The loader and the registry linter.

Each lint rule gets one test that breaks the real registry in exactly one way
and asserts the linter names the break. The first test is the baseline: the
committed registry is clean.
"""

import pytest

from generators.registry import LANGS, Registry
from tools.check_registry import ROOT, ticket_ids


def lint(data):
    return Registry(data).lint()


def row(data, const):
    return next(r for r in data["attributes"]["attributes"] if r["const"] == const)


def assert_flags(data, fragment):
    errors = lint(data)
    assert any(fragment in e for e in errors), f"expected {fragment!r} in {errors}"


def test_committed_registry_is_clean(data):
    assert lint(data) == []


# --- source spellings and event attributes ----------------------------------


def test_source_spellings_are_not_generated_for_go(registry):
    assert "LLM_SYSTEM" in [r["const"] for r in registry.rows("python")]
    assert "LLM_SYSTEM" not in [r["const"] for r in registry.rows("go")]


@pytest.mark.parametrize("languages", [None, ["python", "go"]])
def test_a_source_spelling_is_never_generated_for_go(data, languages):
    # The backend declares its input spellings by hand in semconv.go; a
    # generated copy would declare the constant twice and fail to compile.
    source = row(data, "LLM_PROVIDER")
    if languages is None:
        del source["shipped_in"], source["divergence"]
    else:
        source["shipped_in"] = languages
    assert_flags(data, "LLM_PROVIDER: a source spelling is never generated for go")


@pytest.mark.parametrize("column", ["direction", "kinds", "category", "level"])
def test_a_source_spelling_takes_no_attribute_column(data, column):
    row(data, "LLM_PROVIDER")[column] = "read" if column == "direction" else "all"
    assert_flags(data, f"LLM_PROVIDER: a source spelling takes no {column}")


def test_a_source_spelling_that_is_not_a_usage_key_needs_a_rationale(data):
    del row(data, "LLM_PROVIDER")["rationale"]
    assert_flags(data, "LLM_PROVIDER: source spelling needs a rationale")


def test_a_usage_source_spelling_needs_a_decision(data):
    keys = data["usage_keys"]["keys"]
    data["usage_keys"]["keys"] = [e for e in keys if e.get("key") != "llm.token_count.total"]
    assert_flags(data, "LLM_TOKEN_COUNT_TOTAL: usage key llm.token_count.total has no decision")


def test_a_canonical_usage_key_is_not_a_source_spelling(data):
    entry = next(e for e in data["usage_keys"]["keys"] if e.get("key") == "llm.token_count.total")
    entry["decision"] = "canonical"
    assert_flags(data, "usage_keys.yaml decides llm.token_count.total is canonical")


def test_a_source_spelling_and_an_attribute_share_no_key(data):
    row(data, "TOOL_NAME")["key"] = "gen_ai.tool.name"
    assert_flags(data, "duplicate key gen_ai.tool.name (GEN_AI_TOOL_NAME, TOOL_NAME)")


def test_an_event_attribute_names_an_event_row(data):
    row(data, "EXCEPTION_MESSAGE")["event"] = "EXCEPTION_TYPE"
    assert_flags(data, "EXCEPTION_MESSAGE: event EXCEPTION_TYPE is not an event row")


def test_an_event_attribute_is_exempt_from_the_span_content_allowlist(data):
    assert row(data, "EXCEPTION_MESSAGE")["category"] == "content"
    del row(data, "EXCEPTION_MESSAGE")["event"]
    assert_flags(data, "EXCEPTION_MESSAGE: content but not on the content allowlist")


# --- filtering ---------------------------------------------------------------


def test_rows_default_to_every_language(registry):
    for lang in LANGS:
        assert "SESSION_ID" in [r["const"] for r in registry.rows(lang)]


def test_shipped_in_limits_a_row_to_its_languages(registry):
    assert "TRACER_NAME" in [r["const"] for r in registry.rows("python")]
    assert "TRACER_NAME" not in [r["const"] for r in registry.rows("go")]
    assert "LLM_INPUT_MESSAGES_PREFIX" in [r["const"] for r in registry.rows("typescript")]
    assert "LLM_INPUT_MESSAGES_PREFIX" not in [r["const"] for r in registry.rows("python")]


def test_planned_rows_are_skipped_unless_asked_for(data):
    row(data, "EXCEPTION_STACKTRACE")["status"] = "planned"
    assert "EXCEPTION_STACKTRACE" not in [r["const"] for r in Registry(data).rows("python")]
    planned = Registry(data, include_planned=True).rows("python")
    assert "EXCEPTION_STACKTRACE" in [r["const"] for r in planned]


def test_allowlist_members_honour_shipped_in(data):
    data["allowlists"]["content"]["attributes"].append(
        {"key": "only.in.python", "shipped_in": ["python"], "divergence": "test"}
    )
    registry = Registry(data)

    def content_keys(lang):
        return [m.get("key") for m in registry.members("content", lang)]

    assert "only.in.python" in content_keys("python")
    assert "only.in.python" not in content_keys("typescript")


def test_included_allowlists_fold_into_content(registry):
    assert registry.included("content") == ["third_party_content"]


def test_a_key_in_content_and_an_included_allowlist_is_flagged(data):
    data["allowlists"]["content"]["attributes"].append({"key": "langfuse.trace.input"})
    assert any("in both content and third_party_content" in e for e in lint(data))


def test_an_unknown_include_is_flagged(data):
    data["allowlists"]["content"]["includes"] = ["no_such_list"]
    assert any("no_such_list is not a member allowlist" in e for e in lint(data))


def test_a_prefix_identity_key_outside_every_content_prefix_is_flagged(data):
    data["allowlists"]["content_prefix_identity"]["attributes"].append({"key": "plain.key"})
    assert any("plain.key is under no content prefix" in e for e in lint(data))


def test_a_tool_definition_member_the_content_rule_misses_is_flagged(data):
    # The normalizers pull tool definitions out of the request bag by the
    # narrower list; each of those names must still be content as
    # gen_ai.request.<name> and rius.request.<name>.
    data["allowlists"]["invocation_parameters_content_members"]["values"].append("schemas")
    assert any("schemas is not in REQUEST_PARAMETERS_CONTENT_MEMBERS" in e for e in lint(data))


def test_a_credential_header_name_with_upper_case_is_flagged(data):
    # Consumers compare the lower-cased header name, so an upper-case entry
    # would never match anything.
    data["allowlists"]["credential_headers"]["values"].append("X-Auth")
    assert any("credential_headers: X-Auth is not lower case" in e for e in lint(data))


def test_a_credential_header_suffix_without_a_hyphen_is_flagged(data):
    # A suffix names a whole hyphen-separated word, so it starts with the hyphen.
    data["allowlists"]["credential_header_suffixes"]["values"].append("token")
    assert any("credential_header_suffixes: token does not start with '-'" in e for e in lint(data))


def test_a_header_segment_without_dots_is_flagged(data):
    data["allowlists"]["header_attribute_segments"]["values"].append("headers")
    assert any("header_attribute_segments: headers is not a .segment." in e for e in lint(data))


def test_derived_content_members_must_name_an_allowlist(data):
    data["allowlists"]["content"]["derived"]["members"] = "NO_SUCH_MEMBERS"
    assert any("content.derived: unknown members NO_SUCH_MEMBERS" in e for e in lint(data))


def test_table_shipped_in_limits_a_table(registry):
    assert registry.table("otel_kind_by_kind", "python") is not None
    assert registry.table("otel_kind_by_kind", "go") is None


# --- lint rules --------------------------------------------------------------


def test_duplicate_const_is_flagged(data):
    data["attributes"]["attributes"].append(dict(row(data, "SESSION_ID")))
    assert_flags(data, "duplicate const SESSION_ID")


def test_duplicate_key_is_flagged(data):
    clone = dict(row(data, "SESSION_ID"), const="SESSION_ID_AGAIN")
    data["attributes"]["attributes"].append(clone)
    assert_flags(data, "duplicate key session.id")


def test_shipped_in_needs_a_divergence(data):
    del row(data, "TRACER_NAME")["divergence"]
    assert_flags(data, "TRACER_NAME: shipped_in needs a divergence")


def test_shipped_in_rejects_unknown_languages(data):
    row(data, "TRACER_NAME")["shipped_in"] = ["python", "rust"]
    assert_flags(data, "unknown language rust")


def test_glassflow_namespace_is_forbidden(data):
    row(data, "WORKSPACE_ROUTE")["key"] = "glassflow.workspace"
    assert_flags(data, "glassflow.")


def test_rius_key_outside_rius_namespace_needs_an_exception(data):
    row(data, "RIUS_CONTEXT_SIZES")["key"] = "gen_ai.context.sizes"
    assert_flags(data, "RIUS_CONTEXT_SIZES: origin rius outside rius.*")


def test_em_dashes_are_forbidden_in_prose(data):
    # Every rationale and note is published on the docs site.
    row(data, "SESSION_ID")["rationale"] += "Grouping \u2014 the whole point.\n"
    data["model_parameters"]["groups"][0]["note"] += " \u2014 or not."
    errors = [e for e in lint(data) if "em dash in the registry" in e]
    i = data["attributes"]["attributes"].index(row(data, "SESSION_ID"))
    assert [e.split(":")[0] for e in errors] == [
        f"registry.attributes.attributes[{i}].rationale",
        "registry.model_parameters.groups[0].note",
    ], errors


def test_ticket_ids_are_forbidden_in_prose(data):
    row(data, "SESSION_ID")["rationale"] += "Settled in RIUS-917.\n"
    assert_flags(data, "ticket id RIUS-917")


def test_resource_rows_carry_no_category(data):
    row(data, "SERVICE_INSTANCE_ID")["category"] = "identity"
    assert_flags(data, "SERVICE_INSTANCE_ID: resource attributes take no category")


def test_span_attributes_need_a_category(data):
    del row(data, "SESSION_ID")["category"]
    assert_flags(data, "SESSION_ID: span attribute needs a category")


def test_unknown_enum_values_are_flagged(data):
    row(data, "SESSION_ID")["category"] = "secret"
    assert_flags(data, "SESSION_ID: category secret")


def test_identity_missing_from_pending_needs_a_reason(data):
    members = data["allowlists"]["pending_identity"]["attributes"]
    members[:] = [m for m in members if m.get("ref") != "SESSION_ID"]
    assert_flags(data, "SESSION_ID: identity but not pending")


def test_not_pending_reason_is_honoured(data):
    del row(data, "RIUS_SPAN_PENDING")["not_pending"]
    assert_flags(data, "RIUS_SPAN_PENDING: identity but not pending")


def test_prefix_covered_identity_needs_no_reason(data):
    # gen_ai.request.temperature is covered by the gen_ai.request. prefix.
    assert not [e for e in lint(data) if "GEN_AI_REQUEST_TEMPERATURE" in e]


def test_pending_members_must_be_identity(data):
    data["allowlists"]["pending_identity"]["attributes"].append({"ref": "INPUT_VALUE"})
    assert_flags(data, "INPUT_VALUE: pending member is content")


def test_content_attribute_must_be_on_the_content_allowlist(data):
    members = data["allowlists"]["content"]["attributes"]
    members[:] = [m for m in members if m.get("ref") != "INPUT_VALUE"]
    assert_flags(data, "INPUT_VALUE: content but not on the content allowlist")


def test_unknown_ref_is_flagged(data):
    data["allowlists"]["pending_identity"]["attributes"].append({"ref": "NO_SUCH_CONST"})
    assert_flags(data, "unknown const NO_SUCH_CONST")


def test_member_cannot_ship_where_its_row_does_not(data):
    data["allowlists"]["pending_identity"]["attributes"].append({"ref": "TRACER_NAME"})
    assert_flags(data, "TRACER_NAME is not generated for go")


def test_every_kind_is_mapped_or_explicitly_unmapped(data):
    del data["taxonomy"]["operation_by_kind"]["unmapped"]["CHAIN"]
    assert_flags(data, "operation_by_kind: CHAIN is neither mapped nor unmapped")


def test_taxonomy_maps_reject_unknown_kinds(data):
    data["taxonomy"]["kind_by_operation"]["map"]["made_up"] = "NOT_A_KIND"
    assert_flags(data, "kind_by_operation: unknown kind NOT_A_KIND")


def test_name_targets_must_be_constants(data):
    data["taxonomy"]["name_target_by_kind"]["map"]["TOOL"] = "gen_ai.tool.name"
    assert_flags(data, "name_target_by_kind: unknown const gen_ai.tool.name")


def test_model_parameter_spellings_are_unique(data):
    data["model_parameters"]["groups"][1]["spellings"].append("model")
    assert_flags(data, "duplicate spelling model")


def test_model_parameter_targets_live_under_gen_ai_request(data):
    data["model_parameters"]["groups"][0]["target"] = "rius.request.model"
    assert_flags(data, "target rius.request.model is not under gen_ai.request.")


def test_multi_meaning_key_needs_when_on_each_span_placement(data):
    placements = row(data, "GEN_AI_AGENT_NAME")["placements"]
    del placements[1]["when"]
    assert_flags(data, "GEN_AI_AGENT_NAME: span placement needs `when`")


@pytest.mark.parametrize("field", ["const", "key"])
def test_required_fields(data, field):
    del row(data, "SESSION_ID")[field]
    assert_flags(data, f"missing {field}")


# --- Weaver fields ------------------------------------------------------------


def retired(data, key):
    return next(r for r in data["attributes"]["retired"] if r["key"] == key)


@pytest.mark.parametrize("field", ["brief", "stability", "examples"])
def test_own_attributes_need_the_weaver_fields(data, field):
    del row(data, "RIUS_SPAN_PENDING")[field]
    assert_flags(data, f"RIUS_SPAN_PENDING: missing {field}")


def test_an_event_needs_no_examples(data):
    assert "examples" not in row(data, "GEN_AI_FIRST_TOKEN_EVENT")
    row(data, "GEN_AI_FIRST_TOKEN_EVENT")["examples"] = ["x"]
    assert_flags(data, "an event takes no examples")


def test_an_otel_row_takes_no_brief(data):
    row(data, "GEN_AI_TOOL_NAME")["brief"] = "Name of the tool."
    assert_flags(data, "GEN_AI_TOOL_NAME: brief on a referenced upstream key")


def test_a_row_upstream_defines_takes_no_brief(data):
    row(data, "SESSION_ID")["brief"] = "The session."
    assert_flags(data, "SESSION_ID: brief on a referenced upstream key")


def test_an_openinference_key_no_registry_defines_needs_a_brief(data):
    del row(data, "INPUT_VALUE")["brief"]
    assert_flags(data, "INPUT_VALUE: missing brief")


def test_an_unknown_upstream_is_flagged(data):
    row(data, "SESSION_ID")["upstream"] = "openinference"
    assert_flags(data, "SESSION_ID: upstream openinference is not one of")


def test_an_upstream_divergence_needs_another_type(data):
    row(data, "GEN_AI_REQUEST_TOP_K")["upstream_divergence"] = {"type": "int", "note": "x"}
    assert_flags(data, "upstream_divergence type must be a type other than the row's")


def test_an_upstream_divergence_needs_a_note(data):
    row(data, "GEN_AI_REQUEST_TOP_K")["upstream_divergence"] = {"type": "double"}
    assert_flags(data, "upstream_divergence needs a note")


def test_only_upstream_keys_diverge_from_upstream(data):
    row(data, "RIUS_SPAN_PENDING")["upstream_divergence"] = {"type": "int", "note": "x"}
    assert_flags(data, "upstream_divergence only goes on a referenced upstream key")


def passthrough(data, key):
    return next(r for r in data["attributes"]["passthrough"] if r["key"] == key)


def test_a_passthrough_key_is_upstream(data):
    passthrough(data, "gen_ai.conversation.id")["origin"] = "openinference"
    assert_flags(data, "only upstream (origin: otel) keys pass through")


def test_a_passthrough_key_has_no_row(data):
    passthrough(data, "gen_ai.conversation.id")["key"] = "session.id"
    assert_flags(data, "has a row in attributes; keep it in one place")


def test_a_passthrough_key_needs_a_rationale(data):
    del passthrough(data, "gen_ai.conversation.id")["rationale"]
    assert_flags(data, "needs a rationale saying who writes and reads it")


def test_a_brief_is_one_line(data):
    row(data, "RIUS_SPAN_PENDING")["brief"] = "Two\nlines."
    assert_flags(data, "brief must be one line")


def test_a_brief_ends_with_a_full_stop(data):
    row(data, "RIUS_SPAN_PENDING")["brief"] = "No full stop"
    assert_flags(data, "brief must end with a full stop")


def test_an_unknown_stability_is_flagged(data):
    row(data, "RIUS_SPAN_PENDING")["stability"] = "experimental"
    assert_flags(data, "stability experimental is not one of")


@pytest.mark.parametrize(
    "const,example",
    [("RIUS_SPAN_PENDING", "true"), ("RIUS_AGGREGATED_USAGE_PREFIX", 1.5), ("WORKSPACE_ROUTE", 1)],
)
def test_examples_must_have_the_row_type(data, const, example):
    row(data, const)["examples"] = [example]
    assert_flags(data, f"{const}: example {example!r} is not a")


def test_a_rename_must_point_at_an_attribute_row(data):
    retired(data, "glassflow.span.pending")["deprecated"]["renamed_to"] = "rius.nope"
    assert_flags(data, "renamed_to rius.nope is not an attribute row")


def _deprecated(data, const):
    return row(data, const)["deprecated"]


def test_a_replacement_outside_this_registry_must_be_an_upstream_row(data):
    _deprecated(data, "RIUS_MAIN_AGENT_NAME")["replaced_by"] = "gen_ai.nope"
    assert_flags(data, "replaced_by gen_ai.nope is not an upstream attribute row")


def test_a_replacement_only_goes_with_reason_uncategorized(data):
    retired(data, "glassflow.span.pending")["deprecated"]["replaced_by"] = "gen_ai.main_agent.name"
    assert_flags(data, "replaced_by only goes with reason uncategorized")


def test_a_deprecation_needs_a_note(data):
    del retired(data, "glassflow.span.pending")["deprecated"]["note"]
    assert_flags(data, "deprecated needs a note")


def test_an_unknown_deprecation_reason_is_flagged(data):
    retired(data, "glassflow.span.pending")["deprecated"]["reason"] = "gone"
    assert_flags(data, "reason gone is not one of")


def test_a_retired_key_is_not_also_a_row(data):
    retired(data, "glassflow.span.pending")["key"] = "rius.span.pending"
    assert_flags(data, "still a row in attributes")


def test_retired_keys_are_never_generated(registry):
    for lang in LANGS:
        assert "glassflow.span.pending" not in [r["key"] for r in registry.rows(lang)]


def test_upstream_equivalent_names_an_upstream_key(data):
    row(data, "RIUS_MAIN_AGENT_VERSION")["upstream_equivalent"] = "rius.other"
    assert_flags(data, "upstream_equivalent must name an upstream key")


def test_a_deprecated_row_takes_no_upstream_equivalent(data):
    # upstream_equivalent says "planned move, not deprecated"; once the row is
    # deprecated the deprecation note names the successor instead.
    row(data, "RIUS_MAIN_AGENT_ID")["upstream_equivalent"] = "gen_ai.main_agent.id"
    assert_flags(data, "deprecated row takes no upstream_equivalent")


# --- ticket ids outside the registry ------------------------------------------


def test_committed_fixtures_and_tools_cite_no_ticket_ids():
    assert ticket_ids(ROOT) == []


def test_a_ticket_id_in_fixtures_or_tools_is_flagged(tmp_path):
    (tmp_path / "fixtures" / "family").mkdir(parents=True)
    (tmp_path / "fixtures" / "family" / "record.py").write_text("x = 1\n# see RIUS-917\n")
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "helper.mts").write_text("// GLA2-12 and GLA-3\n")
    assert ticket_ids(tmp_path) == [
        "fixtures/family/record.py:2: ticket id RIUS-917; write the reason",
        "tools/helper.mts:1: ticket id GLA2-12; write the reason",
        "tools/helper.mts:1: ticket id GLA-3; write the reason",
    ]


def test_installed_packages_are_not_scanned(tmp_path):
    vendored = tmp_path / "fixtures" / "family" / "node_modules" / "pkg"
    vendored.mkdir(parents=True)
    (vendored / "CHANGELOG.md").write_text("Fixed RIUS-1\n")
    assert ticket_ids(tmp_path) == []


# --- media parts and per-modality usage -------------------------------------


@pytest.mark.parametrize("modality", ["text", "image", "audio"])
@pytest.mark.parametrize("suffix", ["input_tokens", "output_tokens", "cache_read.input_tokens"])
def test_modality_usage_rows_are_shipped_otel_ints(data, modality, suffix):
    key = f"gen_ai.usage.{modality}.{suffix}"
    r = next(r for r in data["attributes"]["attributes"] if r["key"] == key)
    assert (r["origin"], r.get("status", "shipped"), r["type"]) == ("otel", "shipped", "int")


def test_context_sizes_documents_media_entries(data):
    import json

    r = row(data, "RIUS_CONTEXT_SIZES")
    for word in ("blob / uri / file", "modality", "byte_size"):
        assert word in r["rationale"]
    media = [
        part
        for example in r["examples"]
        for side in ("input_messages", "output_messages")
        for message in json.loads(example).get(side, [])
        for part in message["parts"]
        if part["type"] == "blob"
    ]
    assert media, "no example carries a blob entry"
    for part in media:
        assert part["modality"] == "image" and "byte_size" in part and "bytes" not in part
