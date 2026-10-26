"""registry/usage_keys.yaml: the file's own rules, and its checks against the fixtures.

Like test_registry.py, each rule gets one test that breaks the real data in
exactly one way and asserts the break is named. The baseline tests come
first: the committed file is clean and every recorded usage key is decided.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from conftest import ROOT
from generators import usage_keys
from generators.registry import Registry
from tools import check_usage_keys

FIXTURES = ROOT / "fixtures"


@pytest.fixture(scope="module")
def recorded(base_data):
    """The real fixtures, scanned once."""
    return usage_keys.scan(base_data["usage_keys"], FIXTURES)


def entry(data: dict, name: str) -> dict:
    return next(e for e in data["usage_keys"]["keys"] if usage_keys.entry_name(e) == name)


def lint(data: dict) -> list[str]:
    return Registry(data).lint()


def assert_flags(errors: list[str], fragment: str) -> None:
    assert any(fragment in e for e in errors), f"expected {fragment!r} in {errors}"


# --- baseline ----------------------------------------------------------------


def test_committed_usage_keys_lint_clean(data):
    assert lint(data) == []


def test_every_recorded_usage_key_is_decided(base_data, recorded):
    assert usage_keys.check(base_data["usage_keys"], recorded) == []


def test_the_cli_passes_on_the_committed_fixtures(capsys):
    assert check_usage_keys.main([]) == 0
    assert "all decided" in capsys.readouterr().out


def test_the_scan_sees_raw_and_produced_keys(recorded):
    assert "openinference-openai" in recorded.recorded["llm.token_count.prompt"]
    # Only ever added by a normalizer, never recorded raw.
    assert "rius.aggregated_usage.input_tokens" not in recorded.recorded
    assert "vercel-ai-otel" in recorded.produced["rius.aggregated_usage.input_tokens"]


def test_each_normalizer_is_observed(recorded):
    seen = {obs.normalizer for obs in recorded.observations}
    assert seen == {"python", "typescript", "sink"}


# --- the file's own rules ------------------------------------------------------


def test_an_entry_needs_a_key_or_a_prefix(data):
    entry(data, "llm.cost.total")["prefix"] = "llm.cost."
    assert_flags(lint(data), "needs exactly one of key or prefix")


def test_an_entry_is_listed_once(data):
    data["usage_keys"]["keys"].append(
        {"key": "llm.cost.total", "decision": "ignored", "reason": "x"}
    )
    assert_flags(lint(data), "llm.cost.total: listed twice")


def test_the_decision_is_known(data):
    entry(data, "llm.cost.total")["decision"] = "maybe"
    assert_flags(lint(data), "decision must be one of")


def test_an_unread_key_needs_a_reason(data):
    entry(data, "llm.cost.total")["reason"] = " "
    assert_flags(lint(data), "llm.cost.total: a ignored key needs a reason")


def test_a_canonical_key_is_in_the_registry(data):
    data["usage_keys"]["keys"].append({"key": "gen_ai.usage.made_up", "decision": "canonical"})
    assert_flags(lint(data), "canonical, but not a registry attribute or prefix")


def test_a_mapped_target_is_a_canonical_usage_key(data):
    entry(data, "llm.token_count.prompt")["target"] = "gen_ai.request.max_tokens"
    assert_flags(lint(data), "is not a canonical usage key")


def test_a_mapped_target_is_a_registry_attribute(data):
    entry(data, "llm.token_count.prompt")["target"] = "gen_ai.usage.made_up"
    assert_flags(lint(data), "target gen_ai.usage.made_up is not a registry attribute")


def test_a_mapped_key_names_who_maps_it(data):
    entry(data, "llm.token_count.prompt")["mapped_by"] = []
    assert_flags(lint(data), "mapped_by names no normalizer")


def test_mapped_by_names_known_normalizers(data):
    entry(data, "llm.token_count.prompt")["mapped_by"] = ["python", "rust"]
    assert_flags(lint(data), "unknown normalizer rust")


def test_only_a_mapped_key_has_a_target(data):
    entry(data, "llm.cost.total")["target"] = "gen_ai.usage.input_tokens"
    assert_flags(lint(data), "target is only for mapped keys")


def test_no_ticket_ids_in_the_reasons(data):
    entry(data, "llm.cost.total")["reason"] = "See RIUS-1."
    assert_flags(lint(data), "ticket id RIUS-1")


# --- decisions -----------------------------------------------------------------


def test_an_exact_key_wins_over_a_prefix(base_data):
    data = base_data["usage_keys"]
    assert usage_keys.decision_for(data, "pydantic_ai.cache.hit_ratio")["decision"] == "not_usage"
    assert usage_keys.decision_for(data, "gen_ai.usage.input_tokens")["decision"] == "canonical"
    assert usage_keys.decision_for(data, "no.such.usage_key") is None


def test_match_is_case_insensitive(base_data):
    assert usage_keys.is_usage_key(base_data["usage_keys"], "ai.usage.promptTokens")
    assert usage_keys.is_usage_key(base_data["usage_keys"], "llm.cost.total")
    assert not usage_keys.is_usage_key(base_data["usage_keys"], "gen_ai.request.model")


# --- checks against the fixtures ------------------------------------------------


def test_an_undecided_usage_key_fails(data, recorded):
    data["usage_keys"]["keys"].remove(entry(data, "llm.cost.total"))
    assert_flags(
        usage_keys.check(data["usage_keys"], recorded),
        "llm.cost.total: usage key with no decision",
    )


def test_a_new_key_in_a_recording_fails(base_data, tmp_path):
    copy = tmp_path / "fixtures"
    shutil.copytree(FIXTURES / "openinference-openai", copy / "openinference-openai")
    path = copy / "openinference-openai" / "openinference-openai-0.1.65.json"
    recording = json.loads(path.read_text())
    recording["recordings"][0]["spans"][0]["span"]["attributes"].append(
        {"key": "llm.token_count.prompt_details.brand_new", "value": {"intValue": "1"}}
    )
    path.write_text(json.dumps(recording))
    data = base_data["usage_keys"]
    errors = usage_keys.check(data, usage_keys.scan(data, copy))
    assert_flags(errors, "llm.token_count.prompt_details.brand_new: usage key with no decision")


def test_a_key_in_an_event_counts(base_data, tmp_path):
    copy = tmp_path / "fixtures"
    shutil.copytree(FIXTURES / "openinference-openai", copy / "openinference-openai")
    path = copy / "openinference-openai" / "openinference-openai-0.1.65.json"
    recording = json.loads(path.read_text())
    recording["recordings"][0]["spans"][0]["span"]["events"] = [
        {
            "name": "final_chunk",
            "timeUnixNano": "1700000000000000000",
            "attributes": [{"key": "chunk.usage.tokens", "value": {"intValue": "3"}}],
        }
    ]
    path.write_text(json.dumps(recording))
    data = base_data["usage_keys"]
    errors = usage_keys.check(data, usage_keys.scan(data, copy))
    assert_flags(errors, "chunk.usage.tokens: usage key with no decision")


def test_a_normalizer_that_maps_a_key_not_listed_fails(data, recorded):
    entry(data, "llm.token_count.prompt")["mapped_by"] = ["typescript", "sink"]
    assert_flags(
        usage_keys.check(data["usage_keys"], recorded),
        "python removed it, but mapped_by does not list python",
    )


def test_a_listed_normalizer_that_keeps_the_key_fails(data, recorded):
    entry(data, "gen_ai.usage.total_tokens").update(
        decision="mapped", target="gen_ai.usage.input_tokens", mapped_by=["sink"]
    )
    assert_flags(
        usage_keys.check(data["usage_keys"], recorded),
        "sink should map it to gen_ai.usage.input_tokens, but kept it",
    )


def test_a_key_that_is_not_usage_may_be_removed(data, recorded):
    # The TypeScript SDK maps ai.settings.maxOutputTokens (a request
    # parameter) to gen_ai.request.max_tokens; that is no usage mapping.
    assert entry(data, "ai.settings.maxOutputTokens")["decision"] == "not_usage"
    assert not usage_keys.check(data["usage_keys"], recorded)
    entry(data, "ai.settings.maxOutputTokens").update(decision="ignored")
    assert_flags(
        usage_keys.check(data["usage_keys"], recorded),
        "ai.settings.maxOutputTokens: typescript removed it, but mapped_by does not list",
    )


def test_a_mapping_must_leave_its_target(data, recorded):
    entry(data, "llm.token_count.prompt")["target"] = "gen_ai.usage.cache_write.input_tokens"
    assert_flags(
        usage_keys.check(data["usage_keys"], recorded),
        "python removed it without setting gen_ai.usage.cache_write.input_tokens",
    )


BREAKDOWNS = [
    "gen_ai.usage.cache_read.input_tokens",
    "gen_ai.usage.cache_write.input_tokens",
    "gen_ai.usage.reasoning.output_tokens",
    "gen_ai.usage.text.input_tokens",
    "gen_ai.usage.text.output_tokens",
    "gen_ai.usage.text.cache_read.input_tokens",
    "gen_ai.usage.image.input_tokens",
    "gen_ai.usage.image.output_tokens",
    "gen_ai.usage.image.cache_read.input_tokens",
    "gen_ai.usage.audio.input_tokens",
    "gen_ai.usage.audio.output_tokens",
    "gen_ai.usage.audio.cache_read.input_tokens",
]


def test_the_breakdowns_omit_zero_and_the_totals_do_not(base_data):
    omitted = [e["key"] for e in base_data["usage_keys"]["keys"] if e.get("omit_zero") is True]
    assert sorted(omitted) == sorted(BREAKDOWNS)
    data = base_data["usage_keys"]
    assert usage_keys.omits_zero(data, "rius.aggregated_usage.cache_read.input_tokens")
    assert not usage_keys.omits_zero(data, "gen_ai.usage.input_tokens")
    assert not usage_keys.omits_zero(data, "rius.aggregated_usage.input_tokens")


def test_omit_zero_is_only_true(data):
    entry(data, "gen_ai.usage.cache_read.input_tokens")["omit_zero"] = "yes"
    assert_flags(lint(data), "omit_zero is true or absent")


def test_omit_zero_is_only_for_a_canonical_usage_key(data):
    entry(data, "llm.token_count.prompt")["omit_zero"] = True
    assert_flags(lint(data), "llm.token_count.prompt: omit_zero is only for a canonical")


def test_a_mapped_zero_may_leave_no_target_when_the_target_omits_zero(data, recorded):
    # openinference-openai records llm.token_count.prompt_details.audio at 0;
    # the normalizer drops the zero it maps, and the source with it.
    assert not usage_keys.check(data["usage_keys"], recorded)
    entry(data, "gen_ai.usage.audio.input_tokens").pop("omit_zero")
    assert_flags(
        usage_keys.check(data["usage_keys"], recorded),
        "python removed it without setting gen_ai.usage.audio.input_tokens",
    )


def test_a_zero_left_on_an_omitted_key_fails(data, tmp_path):
    copy = tmp_path / "fixtures"
    shutil.copytree(FIXTURES / "openinference-openai", copy / "openinference-openai")
    expected = next((copy / "openinference-openai").glob("*.expected.json"))
    payload = json.loads(expected.read_text())
    span = payload["recordings"][0]["spans"][0]["span"]
    span["attributes"].append(
        {"key": "gen_ai.usage.cache_read.input_tokens", "value": {"intValue": "0"}}
    )
    expected.write_text(json.dumps(payload))
    assert_flags(
        usage_keys.check(data["usage_keys"], usage_keys.scan(data["usage_keys"], copy)),
        "gen_ai.usage.cache_read.input_tokens: python left it at 0",
    )


def _pydantic_ai_copy(tmp_path: Path) -> tuple[Path, Path, dict]:
    copy = tmp_path / "fixtures"
    shutil.copytree(FIXTURES / "pydantic-ai", copy / "pydantic-ai")
    expected = copy / "pydantic-ai" / "pydantic-ai-2.55.0.expected.json"
    return copy, expected, json.loads(expected.read_text())


def test_a_dropped_breakdown_that_was_not_zero_fails(data, tmp_path):
    # pydantic-ai records gen_ai.usage.cache_read.input_tokens at 16: a
    # normalizer whose zero test also caught a count would drop it.
    copy, expected, payload = _pydantic_ai_copy(tmp_path)
    key = "gen_ai.usage.cache_read.input_tokens"
    dropped = 0
    for scenario in payload["recordings"]:
        for wrapped in scenario["spans"]:
            attributes = wrapped["span"]["attributes"]
            kept = [a for a in attributes if a["key"] != key]
            dropped += len(attributes) - len(kept)
            wrapped["span"]["attributes"] = kept
    assert dropped == 5
    expected.write_text(json.dumps(payload))
    assert_flags(
        usage_keys.check(data["usage_keys"], usage_keys.scan(data["usage_keys"], copy)),
        f"{key}: python dropped it, but it was not 0",
    )


def test_a_breakdown_moved_aside_is_not_dropped(data, tmp_path):
    copy, expected, payload = _pydantic_ai_copy(tmp_path)
    for scenario in payload["recordings"]:
        for wrapped in scenario["spans"]:
            for a in wrapped["span"]["attributes"]:
                if a["key"] == "gen_ai.usage.cache_read.input_tokens":
                    a["key"] = "rius.aggregated_usage.cache_read.input_tokens"
    expected.write_text(json.dumps(payload))
    assert not usage_keys.check(data["usage_keys"], usage_keys.scan(data["usage_keys"], copy))


def test_a_zero_left_on_an_event_fails(data, tmp_path):
    copy = tmp_path / "fixtures"
    shutil.copytree(FIXTURES / "openinference-openai", copy / "openinference-openai")
    expected = next((copy / "openinference-openai").glob("*.expected.json"))
    payload = json.loads(expected.read_text())
    payload["recordings"][0]["spans"][0]["span"]["events"] = [
        {
            "name": "final_chunk",
            "timeUnixNano": "1700000000000000000",
            "attributes": [
                {"key": "gen_ai.usage.reasoning.output_tokens", "value": {"intValue": "0"}}
            ],
        }
    ]
    expected.write_text(json.dumps(payload))
    assert_flags(
        usage_keys.check(data["usage_keys"], usage_keys.scan(data["usage_keys"], copy)),
        "gen_ai.usage.reasoning.output_tokens: python left it at 0",
    )


def test_a_mapped_zero_on_an_event_may_leave_no_target(data, tmp_path):
    # The recorded llm.token_count.prompt_details.audio is 0 on an event
    # instead of the span: still a zero, so dropping it with its source is fine.
    copy = tmp_path / "fixtures"
    shutil.copytree(FIXTURES / "openinference-openai", copy / "openinference-openai")
    path = copy / "openinference-openai" / "openinference-openai-0.1.65.json"
    recording = json.loads(path.read_text())
    key = "llm.token_count.prompt_details.audio"
    moved = 0
    for scenario in recording["recordings"]:
        for wrapped in scenario["spans"]:
            span = wrapped["span"]
            on_span = [a for a in span["attributes"] if a["key"] == key]
            if not on_span:
                continue
            span["attributes"] = [a for a in span["attributes"] if a["key"] != key]
            span.setdefault("events", []).append(
                {"name": "usage", "timeUnixNano": "1700000000000000000", "attributes": on_span}
            )
            moved += 1
    assert moved
    path.write_text(json.dumps(recording))
    assert not usage_keys.check(data["usage_keys"], usage_keys.scan(data["usage_keys"], copy))


def test_a_key_at_0_in_one_place_and_a_count_in_another_is_no_zero():
    key = "gen_ai.usage.cache_read.input_tokens"
    span = {
        "attributes": [{"key": key, "value": {"intValue": "4"}}],
        "events": [{"attributes": [{"key": key, "value": {"intValue": "0"}}]}],
    }
    assert usage_keys._zero_keys(span) == set()
    span["attributes"][0]["value"] = {"intValue": "0"}
    assert usage_keys._zero_keys(span) == {key}


@pytest.mark.parametrize(
    ("value", "zero"),
    [
        ({"intValue": "0"}, True),
        ({"intValue": 0}, True),
        ({"doubleValue": 0.0}, True),
        ({"stringValue": "0"}, True),
        ("0", True),
        ({"intValue": "3"}, False),
        ({"doubleValue": 0.5}, False),
        ({"boolValue": False}, False),
        ({"stringValue": "lots"}, False),
        ("", False),
    ],
)
def test_what_reads_as_zero(value, zero):
    assert usage_keys._is_zero(value) is zero


# --- the table ------------------------------------------------------------------


def test_the_table_lists_every_entry(base_data, recorded):
    table = usage_keys.render_table(base_data["usage_keys"], recorded)
    for e in base_data["usage_keys"]["keys"]:
        assert f"`{usage_keys.entry_name(e)}`" in table


def test_the_table_says_who_maps_what(base_data, recorded):
    table = usage_keys.render_table(base_data["usage_keys"], recorded)
    row = next(line for line in table.splitlines() if "`gen_ai.usage.prompt_tokens`" in line)
    assert row.split(" | ")[1:4] == ["keeps", "keeps", "→ `gen_ai.usage.input_tokens`"]


def test_the_committed_table_is_current(base_data, recorded):
    planned = frozenset(
        a["key"]
        for a in base_data["attributes"]["attributes"]
        if a.get("status") == "planned" and "key" in a
    )
    table = usage_keys.render_table(base_data["usage_keys"], recorded, planned)
    assert (ROOT / "out" / "docs" / "usage-keys.md").read_text() == table


def test_a_prefix_lists_only_the_keys_it_decides(base_data, recorded):
    prefix = entry(base_data, "pydantic_ai.cache.*")
    families = usage_keys._families(base_data["usage_keys"], prefix, recorded.recorded)
    assert families == ["pydantic-ai"]


def test_fixtures_dir_is_scanned_not_hardcoded(tmp_path, base_data):
    empty = tmp_path / "fixtures"
    empty.mkdir()
    result = usage_keys.scan(base_data["usage_keys"], Path(empty))
    assert not result.recorded and not result.observations


def test_a_mapped_target_may_have_moved_aside():
    # A wrapper span that repeats a call's usage keeps it under
    # rius.aggregated_usage.*: the key was mapped, then the family moved.
    after = {"rius.aggregated_usage.input_tokens": 42}
    assert usage_keys._target_set("gen_ai.usage.input_tokens", after)
    assert not usage_keys._target_set("gen_ai.usage.output_tokens", after)
    assert not usage_keys._target_set("gen_ai.usage.input_tokens", {})


# --- producers (the Weaver registry's normalizer inputs) ----------------------


def test_every_foreign_usage_key_has_a_producer(base_data):
    data = base_data["usage_keys"]
    assert usage_keys.producer_for(data, "llm.token_count.prompt") == "openinference"
    assert usage_keys.producer_for(data, "llm.usage.total_tokens") == "openllmetry"
    assert usage_keys.producer_for(data, "gen_ai.usage.prompt_tokens") is None


def test_a_foreign_key_without_a_producer_is_flagged(data):
    data["usage_keys"]["keys"].append(
        {"key": "acme.token_count", "decision": "ignored", "reason": "test"}
    )
    assert any("no producers prefix covers it" in e for e in lint(data))


def test_a_producer_cannot_claim_gen_ai(data):
    data["usage_keys"]["producers"]["vercel"]["prefixes"].append("gen_ai.usage.")
    assert any("claims gen_ai.usage., in gen_ai.*" in e for e in lint(data))


def test_an_unknown_value_type_is_flagged(data):
    entry(data, "llm.cost.total")["type"] = "boolean"
    assert any("llm.cost.total: type must be one of" in e for e in lint(data))


def test_a_string_value_type_is_accepted(data):
    entry(data, "llm.cost.total")["type"] = "string"
    assert not [e for e in lint(data) if "type must be one of" in e]


MODALITY_USAGE_KEYS = [
    f"gen_ai.usage.{modality}.{suffix}"
    for modality in ("text", "image", "audio")
    for suffix in ("input_tokens", "output_tokens", "cache_read.input_tokens")
]


@pytest.mark.parametrize("key", MODALITY_USAGE_KEYS)
def test_modality_keys_are_canonical(key):
    found = usage_keys.decision_for(Registry.load().usage_keys, key)
    assert found is not None and found["decision"] == "canonical"


def test_a_planned_key_is_marked_in_the_table(base_data, recorded):
    key = "gen_ai.usage.audio.input_tokens"
    table = usage_keys.render_table(base_data["usage_keys"], recorded, frozenset({key}))
    row = next(line for line in table.splitlines() if f"`{key}`" in line)
    assert "Planned, not emitted yet." in row
