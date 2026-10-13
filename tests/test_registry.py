"""The loader and the registry linter.

Each lint rule gets one test that breaks the real registry in exactly one way
and asserts the linter names the break. The first test is the baseline: the
committed registry is clean.
"""

import pytest

from generators.registry import LANGS, Registry


def lint(data):
    return Registry(data).lint()


def row(data, const):
    return next(r for r in data["attributes"]["attributes"] if r["const"] == const)


def assert_flags(data, fragment):
    errors = lint(data)
    assert any(fragment in e for e in errors), f"expected {fragment!r} in {errors}"


def test_committed_registry_is_clean(data):
    assert lint(data) == []


# --- filtering ---------------------------------------------------------------


def test_rows_default_to_every_language(registry):
    for lang in LANGS:
        assert "SESSION_ID" in [r["const"] for r in registry.rows(lang)]


def test_shipped_in_limits_a_row_to_its_languages(registry):
    assert "TRACER_NAME" in [r["const"] for r in registry.rows("python")]
    assert "TRACER_NAME" not in [r["const"] for r in registry.rows("go")]
    assert "SERVICE_NAME" in [r["const"] for r in registry.rows("go")]
    assert "SERVICE_NAME" not in [r["const"] for r in registry.rows("python")]


def test_planned_rows_are_skipped_unless_asked_for(data):
    assert "TELEMETRY_DISTRO_NAME" not in [r["const"] for r in Registry(data).rows("python")]
    planned = Registry(data, include_planned=True).rows("python")
    assert "TELEMETRY_DISTRO_NAME" in [r["const"] for r in planned]


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
    data["allowlists"]["pending_identity"]["attributes"].append({"ref": "SERVICE_NAME"})
    assert_flags(data, "SERVICE_NAME is not generated for python")


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
