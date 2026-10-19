"""registry/media_parts.yaml: the file's own rules, and its checks against the fixtures.

Each rule gets one test that breaks the real data in exactly one way and
asserts the break is named.
"""

from __future__ import annotations

import copy
import json
import re

import pytest

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
    assert len(rows) == 27
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


def test_anthropic_url_row_cites_no_openinference_fixture(base_data):
    (row,) = [
        r
        for r in base_data["media_parts"]["rows"]
        if r["source"] == "anthropic.messages" and "source.type = url" in r["shape"]
    ]
    assert row["fixtures"] == []
    assert row["reason"]


# --- the stripped_reason vocabulary -------------------------------------------


def test_stripped_reasons_are_exactly_the_two(data):
    assert set(data["media_parts"]["stripped_reasons"]) == {"not_captured", "redacted_upstream"}
    data["media_parts"]["stripped_reasons"]["too_big"] = "Too big."
    assert_flags(media_parts.lint(data["media_parts"]), "stripped_reasons must be exactly")


def test_missing_stripped_reason_fails(data):
    data["media_parts"]["stripped_reasons"].pop("redacted_upstream")
    assert_flags(media_parts.lint(data["media_parts"]), "stripped_reasons must be exactly")


# --- normalized: none ---------------------------------------------------------


def test_none_is_a_normalized_outcome(base_data):
    rows = [r for r in base_data["media_parts"]["rows"] if r["normalized"] == "none"]
    assert rows
    table = media_parts.render_table(base_data["media_parts"])
    assert "no part (raw payload stripped: `input.value`, `output.value`)" in table
    assert "| no part |" in table


def test_none_cannot_be_combined(data):
    data["media_parts"]["rows"][0]["normalized"] = ["none", "blob"]
    assert_flags(media_parts.lint(data["media_parts"]), "none stands alone")


def _outcomes_by_fixture(rows: list[dict], include_raw: bool = False) -> dict[str, set[frozenset]]:
    """fixture id -> the outcomes the rows citing it say it makes. Only the
    message-source rows, unless include_raw: raw_payload rows too."""
    out: dict[str, set[frozenset]] = {}
    for row in rows:
        if row.get("raw_payload") and not include_raw:
            continue
        for ref in row.get("fixtures") or []:
            out.setdefault(ref, set()).add(frozenset(media_parts.normalized_of(row)))
    return out


def test_no_fixture_proves_two_different_outcomes(base_data):
    """A scenario cited by two message-source rows must make the same kind of
    part in both: it cannot both produce a part and produce none. A raw_payload
    row is exempt: a scenario yields a stripped raw payload and a part from
    its message keys."""
    for ref, outcomes in _outcomes_by_fixture(base_data["media_parts"]["rows"]).items():
        if len(outcomes) > 1:
            listed = sorted(map(sorted, outcomes))
            assert not any(o == {"none"} for o in outcomes), f"{ref}: {listed}"


def test_the_check_catches_a_conflict(data):
    rows = data["media_parts"]["rows"]
    (oo,) = [r for r in rows if r["source"] == "openllmetry.openai"]
    oo["fixtures"] = ["openllmetry/image_https_url"]
    outcomes = _outcomes_by_fixture(rows)["openllmetry/image_https_url"]
    assert frozenset({"none"}) in outcomes and len(outcomes) > 1


def _raw_payload_keys(row: dict) -> list[str]:
    value = row.get("raw_payload")
    return list(value) if isinstance(value, list) else [value] if value else []


def test_raw_payload_rows(base_data):
    rows = base_data["media_parts"]["rows"]
    by_source = {
        (r["source"], r["shape"]): _raw_payload_keys(r) for r in rows if r.get("raw_payload")
    }
    assert by_source == {
        ("laminar.openhands", "ImageContent with image_urls in lmnr.span.input"): [
            "lmnr.span.input"
        ],
        (
            "openinference.llm",
            "media present only in input.value / output.value "
            "(audio input, audio output, PDF document)",
        ): ["input.value", "output.value"],
        ("vercel.ai", "file part with Buffer data in ai.prompt"): ["ai.prompt"],
    }
    (oo,) = [r for r in rows if r["source"] == "openllmetry.openai"]
    assert "raw_payload" not in oo


def test_raw_payload_only_on_a_none_row(data):
    data["media_parts"]["rows"][0]["raw_payload"] = "input.value"
    assert_flags(media_parts.lint(data["media_parts"]), "raw_payload only on a none row")


def test_raw_payload_must_be_a_raw_key(data):
    (row,) = [r for r in data["media_parts"]["rows"] if r["source"] == "laminar.openhands"]
    row["raw_payload"] = "gen_ai.input.messages"
    assert_flags(media_parts.lint(data["media_parts"]), "raw_payload gen_ai.input.messages")


def test_raw_payload_is_rendered(base_data):
    table = media_parts.render_table(base_data["media_parts"])
    assert "no part (raw payload stripped: `ai.prompt`)" in table


def test_openinference_raw_only_media_makes_no_part(base_data):
    rows = base_data["media_parts"]["rows"]
    (row,) = [r for r in rows if r["source"] == "openinference.llm" and r["normalized"] == "none"]
    assert sorted(row["fixtures"]) == sorted(
        [
            "openinference-openai/input_audio",
            "openinference-openai/audio_output",
            "openinference-js-openai/input_audio",
            "openinference-js-openai/audio_output",
            "openinference-anthropic/document_pdf",
            "openinference-js-anthropic/document_pdf",
        ]
    )


def test_openllmetry_data_url_makes_no_part(base_data):
    rows = base_data["media_parts"]["rows"]
    (row,) = [r for r in rows if r["source"] == "openllmetry.openai"]
    assert row["normalized"] == "none"
    assert row["fixtures"] == ["openllmetry/image_base64"]
    (data_url,) = [
        r
        for r in rows
        if r["source"] == "openai.chat" and r["shape"].startswith("image_url.url = data")
    ]
    assert "openllmetry" not in data_url["paths"]


def test_laminar_input_is_a_raw_payload(base_data):
    media = base_data["media_parts"]
    (row,) = [r for r in media["rows"] if r["source"] == "laminar.openhands"]
    assert row["normalized"] == "none"
    assert "InputValue" in row["note"]
    assert "lmnr.span.input" in media["raw_payloads"]["raw_keys"]
    assert "lmnr.span.input" not in media["raw_payloads"]["message_keys"]


def test_openinference_path_only_where_an_openinference_fixture_proves_it(base_data):
    for row in base_data["media_parts"]["rows"]:
        cited = any(f.startswith("openinference-") for f in row["fixtures"])
        assert ("openinference" in row["paths"]) == cited, media_parts.row_name(row)


# --- the source rule: parts come from message keys only ----------------------


def _scenario_spans(ref: str) -> list[dict]:
    import json

    family, _, scenario = ref.partition("/")
    spans = []
    for path in sorted((FIXTURES / family).glob("*.json")):
        if path.name in {"manifest.json", "package.json", "package-lock.json"}:
            continue
        if path.name.endswith((".expected.json", ".expected-row.json")):
            continue
        for recording in json.loads(path.read_text())["recordings"]:
            if recording["scenario"] == scenario:
                spans += [entry["span"] for entry in recording["spans"]]
    assert spans, ref
    return spans


def _media_in_message_keys(ref: str, raw: dict) -> bool:
    """Whether a message key (raw_payloads.message_keys) of a recorded
    scenario carries a media part, flattened or as JSON."""
    import json

    for span in _scenario_spans(ref):
        for attribute in span.get("attributes") or []:
            key = attribute["key"]
            if not media_parts.is_message_key(raw, key):
                continue
            value = attribute["value"].get("stringValue", "")
            if re.search(r"\.(image|audio|file|document)\.", key) or (
                key.endswith("message_content.type") and value in MEDIA_KINDS
            ):
                return True
            try:
                parsed = json.loads(value)
            except ValueError:
                continue
            if _holds_media_part(parsed):
                return True
    return False


MEDIA_KINDS = {"image", "image_url", "input_audio", "audio", "file", "document", "blob", "uri"}


def _holds_media_part(value) -> bool:
    if isinstance(value, dict):
        if value.get("type") in MEDIA_KINDS:
            return True
        return any(_holds_media_part(v) for v in value.values())
    if isinstance(value, list):
        return any(_holds_media_part(v) for v in value)
    return False


def test_every_part_row_is_proved_by_a_message_key(base_data):
    """R7: a fixture proving a part must carry the media in a message key,
    never only in a raw payload such as input.value."""
    media = base_data["media_parts"]
    for row in media["rows"]:
        if not set(media_parts.normalized_of(row)) & {"blob", "uri", "file"}:
            continue
        for ref in row["fixtures"]:
            assert _media_in_message_keys(ref, media["raw_payloads"]), (
                f"{media_parts.row_name(row)} {ref} has no media in a message key"
            )


def test_a_scenario_proving_only_no_part_has_no_media_in_message_keys(base_data):
    media = base_data["media_parts"]
    outcomes = _outcomes_by_fixture(media["rows"], include_raw=True)
    for ref, kinds in outcomes.items():
        if kinds == {frozenset({"none"})}:
            assert not _media_in_message_keys(ref, media["raw_payloads"]), ref


# --- raw payloads -------------------------------------------------------------


def test_raw_payloads_name_the_raw_keys(base_data):
    raw = base_data["media_parts"]["raw_payloads"]
    assert set(raw["raw_keys"]) >= {
        "input.value",
        "output.value",
        "lmnr.span.input",
        "lmnr.span.output",
        "ai.prompt",
        "pydantic_ai.all_messages",
        "InputValue",
        "OutputValue",
    }
    assert {rule["id"] for rule in raw["detection"]} == {"b", "d", "e"}


def test_raw_payloads_need_detection_rules(data):
    data["media_parts"]["raw_payloads"]["detection"] = [
        r for r in data["media_parts"]["raw_payloads"]["detection"] if r["id"] != "e"
    ]
    assert_flags(media_parts.lint(data["media_parts"]), "detection must define rules")


def test_raw_key_cannot_be_a_message_key(data):
    raw = data["media_parts"]["raw_payloads"]
    raw["message_keys"].append("input.value")
    assert_flags(media_parts.lint(data["media_parts"]), "both a message key and a raw key")


def test_replacement_names_mime_and_size(data):
    data["media_parts"]["raw_payloads"]["replacement"]["format"] = "[stripped]"
    assert_flags(media_parts.lint(data["media_parts"]), "replacement format")


def test_replacement_renders(base_data):
    raw = base_data["media_parts"]["raw_payloads"]
    assert media_parts.replacement(raw, "image/png", 67) == "[stripped image/png 67 bytes]"
    assert media_parts.replacement(raw, None, None) == "[stripped unknown unknown bytes]"


def test_docs_render_raw_payloads(base_data):
    table = media_parts.render_table(base_data["media_parts"])
    assert "## Raw payloads" in table
    assert "`input.value`" in table
    assert "[stripped image/png 67 bytes]" in table


def test_shape_cell_is_code(base_data):
    table = media_parts.render_table(base_data["media_parts"])
    assert "`image_url.url = data:<mime>;base64,...`" in table


@pytest.mark.parametrize(
    ("value", "rules"),
    [
        ("data:image/png;base64,iVBORw0KGgo=", {"b"}),
        ({"type": "Buffer", "data": [1, 2]}, {"d"}),
        ({"type": "Buffer", "data": []}, set()),
        ({"source": {"type": "base64", "media_type": "image/png", "data": "iVBO"}}, {"e"}),
        ({"source": {"type": "base64", "data": "iVBO"}}, {"e"}),
        ({"input_audio": {"data": "UklGRg==", "format": "wav"}}, {"e"}),
        ({"inline_data": {"data": "UklGRg=="}}, {"e"}),
        ({"b64_json": "iVBO", "format": "png"}, set()),
        ({"b64_json": "iVBO", "output_format": "png"}, {"e"}),
        ({"data": "QUFB", "mediaType": ""}, set()),
        ({"data": "QUFB", "mediaType": None}, set()),
        ({"mediaType": "image/png", "data": ["QUFB", ""]}, {"e"}),
        ({"data": "hello"}, set()),
        ({"result": {"data": "x"}}, set()),
        ({"data": "", "media_type": "image/png"}, set()),
        ('{"audio": {"data": "UklGRg=="}}', {"e"}),
        ({"type": "blob", "mime_type": "image/png", "content": "iVBO"}, {"e"}),
        ({"type": "text", "content": "iVBO"}, set()),
        ({"type": "blob", "content": "[stripped image/png 3 bytes]"}, set()),
    ],
)
def test_detection_rules(base_data, value, rules):
    raw = base_data["media_parts"]["raw_payloads"]
    assert {t.rule for t in media_parts.media_tokens(raw, value)} == rules


# --- rule (b): a data URL token anywhere in a string -------------------------


def test_data_url_in_prose_is_a_token(base_data):
    raw = base_data["media_parts"]["raw_payloads"]
    url = "data:image/png;base64,iVBORw0KGgo="
    text = f"look at {url} please"
    (span,) = media_parts.data_url_spans(raw, text)
    assert text[span.start : span.end] == url
    assert span.mime == "image/png"
    assert {t.rule for t in media_parts.media_tokens(raw, text)} == {"b"}


def test_data_url_replacement_leaves_the_prose_intact(base_data):
    raw = base_data["media_parts"]["raw_payloads"]
    text = 'see "data:audio/wav;base64,UklGRg==", then data:;base64,AAAA.'
    assert media_parts.strip_data_urls(raw, text) == (
        'see "[stripped audio/wav 4 bytes]", then [stripped unknown 3 bytes].'
    )


def test_whole_string_data_url_is_the_special_case(base_data):
    raw = base_data["media_parts"]["raw_payloads"]
    assert (
        media_parts.strip_data_urls(raw, "data:image/png;base64,iVBORw0KGgo=")
        == "[stripped image/png 8 bytes]"
    )


def test_a_url_data_url_is_not_a_token(base_data):
    raw = base_data["media_parts"]["raw_payloads"]
    assert media_parts.data_url_spans(raw, "data:None;url,None") == []


def test_data_url_pattern_needs_its_three_groups(data):
    (rule,) = [r for r in data["media_parts"]["raw_payloads"]["detection"] if r["id"] == "b"]
    rule["pattern"] = "data:([^;]*);base64,(x)"
    assert_flags(media_parts.lint(data["media_parts"]), "pattern needs 3 groups")


@pytest.mark.parametrize(
    ("text", "mime"),
    [
        ("data:image/png;base64,AAAA", "image/png"),
        ("Data:image/png;base64,AAAA", "image/png"),
        ("data:image/png;name=a.png;charset=x;base64,AAAA", "image/png"),
        ("data:application/vnd.ms-excel;base64,AAAA", "application/vnd.ms-excel"),
        ("data:;base64,AAAA", None),
        ("data:image;base64,AAAA", None),
        ("data:image/png\\x;base64,AAAA", None),
        ("data:a/b/c;base64,AAAA", None),
    ],
)
def test_data_url_mime_is_a_token_or_unknown(base_data, text, mime):
    raw = base_data["media_parts"]["raw_payloads"]
    (span,) = media_parts.data_url_spans(raw, text)
    assert (span.start, span.end, span.mime) == (0, len(text), mime)


def test_a_long_data_url_without_base64_is_linear(base_data):
    # The parameter group never overlaps the mime group, so this returns at once.
    raw = base_data["media_parts"]["raw_payloads"]
    assert media_parts.data_url_spans(raw, "data:x" + "a" * 200_000) == []
    assert media_parts.data_url_spans(raw, "data:x" + ";a" * 100_000) == []


def test_in_text_example_is_what_the_rule_does(base_data):
    raw = base_data["media_parts"]["raw_payloads"]
    example = raw["replacement"]["in_text"]
    assert media_parts.strip_data_urls(raw, example["before"]) == example["after"]


# --- strip_raw_payload: the golden examples ------------------------------------

GOLDEN = Registry.load().media_parts["raw_payloads"]["golden"]

#: The cases the contract must pin, by golden name.
REQUIRED_GOLDEN = {
    "anthropic_base64_image_pretty_printed",
    "openai_input_audio_wav",
    "vercel_buffer_in_ai_prompt",
    "data_url_in_prose",
    "data_url_in_json_string",
    "keyed_data_url_rule_e_wins",
    "truncated_json_rule_b_only",
    "json_nested_in_a_json_string",
    "nested_json_with_escapes_a_reencoder_would_not_write",
    "invalid_base64_under_keyed_data",
    "unicode_space_before_brace_is_not_json",
    "gemini_inline_data_camel_case",
    "openai_responses_image_generation_result",
    "stripping_twice_changes_nothing",
    "pydantic_ai_blob_part_in_all_messages",
    "depth_64_parses",
    "depth_65_is_rule_b_only",
    "duplicate_keys_strip_every_member",
    "mime_key_list_order_wins",
    "string_array_under_a_keyed_key",
    "a_null_sibling_is_not_context",
    "format_is_ignored_outside_an_audio_parent",
    "format_under_input_audio",
    "uppercase_data_url_scheme",
    "data_url_with_parameters",
    "a_sibling_mime_that_is_not_a_token_is_unknown",
}


def test_golden_covers_the_required_cases():
    assert {g["name"] for g in GOLDEN} >= REQUIRED_GOLDEN


@pytest.mark.parametrize("golden", GOLDEN, ids=[g["name"] for g in GOLDEN])
def test_golden(base_data, golden):
    raw = base_data["media_parts"]["raw_payloads"]
    result = media_parts.strip(raw, golden["input"])
    assert result.text == golden["output"]
    assert media_parts.strip_raw_payload(raw, golden["input"]) == golden["output"]
    assert [t.as_dict() for t in result.tokens] == golden["tokens"]


@pytest.mark.parametrize("golden", GOLDEN, ids=[g["name"] for g in GOLDEN])
def test_stripping_is_idempotent(base_data, golden):
    raw = base_data["media_parts"]["raw_payloads"]
    assert media_parts.strip(raw, golden["output"]) == media_parts.Stripped(golden["output"], [])


def test_a_wrong_golden_fails_lint(data):
    data["media_parts"]["raw_payloads"]["golden"][0]["output"] = "{}"
    errors = media_parts.lint(data["media_parts"])
    assert_flags(errors, "golden anthropic_base64_image_pretty_printed")


def test_golden_tokens_are_checked(data):
    data["media_parts"]["raw_payloads"]["golden"][1]["tokens"] = []
    assert_flags(media_parts.lint(data["media_parts"]), "golden openai_input_audio_wav")


def test_golden_rendered(base_data):
    table = media_parts.render_table(base_data["media_parts"])
    assert "### Golden examples" in table
    for golden in GOLDEN:
        assert f"`{golden['name']}`" in table


def test_the_prose_rulings_are_required(data):
    del data["media_parts"]["raw_payloads"]["precedence"]
    assert_flags(media_parts.lint(data["media_parts"]), "raw_payloads needs precedence")


@pytest.mark.parametrize(
    "text",
    [
        '[NaN, {"source": {"type": "base64", "data": "iVBORw0KGgo="}}]',
        '{"source": {"type": "base64", "data": "iVBORw0KGgo="}} // comment',
        '{"source": {"type": "base64", "data": "iVBORw0KGgo="},}',
    ],
)
def test_not_rfc_8259_json_gets_rule_b_only(base_data, text):
    raw = base_data["media_parts"]["raw_payloads"]
    assert media_parts.strip_raw_payload(raw, text) == text


def test_ascii_whitespace_before_json_is_trimmed(base_data):
    raw = base_data["media_parts"]["raw_payloads"]
    text = ' \t\r\n{"source": {"type": "base64", "data": "iVBORw0KGgo="}} \n'
    assert media_parts.strip_raw_payload(raw, text) == (
        ' \t\r\n{"source": {"type": "base64", "data": "[stripped unknown 8 bytes]"}} \n'
    )


def test_buffer_inside_a_replaced_buffer_is_not_visited(base_data):
    raw = base_data["media_parts"]["raw_payloads"]
    text = '{"type":"Buffer","data":[1,2],"x":{"type":"Buffer","data":[3]}}'
    result = media_parts.strip(raw, text)
    assert result.text == '"[stripped unknown 2 bytes]"'
    assert [t.rule for t in result.tokens] == ["d"]


def test_a_mime_that_is_not_a_token_never_reaches_the_replacement(base_data):
    raw = base_data["media_parts"]["raw_payloads"]
    # A mime type with a backslash, inside a JSON string, and one level deeper.
    text = '{"a":"data:x\\\\y;base64,AAAA","b":"[\\"data:x\\\\\\\\y;base64,AAAA\\"]"}'
    assert media_parts.strip_raw_payload(raw, text) == (
        '{"a":"[stripped unknown 3 bytes]","b":"[\\"[stripped unknown 3 bytes]\\"]"}'
    )


# --- the depth limit -----------------------------------------------------------


def _nest(depth: int, inner: str) -> str:
    """`inner` inside depth - 1 arrays (inner is one more level)."""
    return "[" * (depth - 1) + inner + "]" * (depth - 1)


SOURCE = '{"source":{"type":"base64","data":"QUFB"}}'


def test_a_nested_document_continues_the_depth(base_data):
    raw = base_data["media_parts"]["raw_payloads"]
    # The string sits inside 2 levels (the object and the array), so a nested
    # document can be 62 deep: SOURCE is 2 levels, under 60 arrays.
    for arrays, stripped in ((60, True), (61, False)):
        nested = "[" * arrays + SOURCE + "]" * arrays
        text = json.dumps({"a": [nested]})
        tokens = media_parts.strip(raw, text).tokens
        assert [t.rule for t in tokens] == (["e"] if stripped else []), arrays


def test_a_deep_candidate_parses_only_to_the_limit():
    assert media_parts.parse_json_candidate(_nest(media_parts.MAX_DEPTH, "[]")) is not None
    assert media_parts.parse_json_candidate(_nest(media_parts.MAX_DEPTH + 1, "[]")) is None
    assert media_parts.parse_json_candidate("[[]]", depth=63) is None
    assert media_parts.parse_json_candidate("[]", depth=63) == []


@pytest.mark.parametrize(
    "text",
    [
        "[" * 200_000,
        "[" * 200_000 + "]" * 200_000,
        '{"a":' * 100_000 + "1" + "}" * 100_000,
        json.dumps({"a": "[" * 50_000 + "]" * 50_000}),
        "[" + "1" * 10_000 + "]",
    ],
    ids=["unclosed", "closed", "objects", "nested_string", "huge_number"],
)
def test_no_input_raises(base_data, text):
    raw = base_data["media_parts"]["raw_payloads"]
    assert media_parts.strip_raw_payload(raw, text) == text


# --- members: duplicates, siblings, mime order ---------------------------------


def test_duplicate_mime_keys_take_the_first_valid_one(base_data):
    raw = base_data["media_parts"]["raw_payloads"]
    text = '{"media_type":"","media_type":"image/png","media_type":"image/gif","data":"QUFB"}'
    assert media_parts.strip_raw_payload(raw, text) == (
        '{"media_type":"","media_type":"image/png","media_type":"image/gif",'
        '"data":"[stripped image/png 3 bytes]"}'
    )


def test_an_invalid_mime_key_falls_through_to_the_next(base_data):
    raw = base_data["media_parts"]["raw_payloads"]
    text = '{"media_type":"not a mime","mimeType":"audio/wav","data":"QUFB"}'
    (token,) = media_parts.strip(raw, text).tokens
    assert token.mime == "audio/wav"


def test_a_format_that_is_not_a_token_is_unknown(base_data):
    raw = base_data["media_parts"]["raw_payloads"]
    text = '{"audio":{"data":"QUFB","format":"w a v"}}'
    (token,) = media_parts.strip(raw, text).tokens
    assert token.mime is None


def test_two_level_nesting_escapes_twice(base_data):
    raw = base_data["media_parts"]["raw_payloads"]
    inner = json.dumps({"source": {"type": "base64", "data": "iVBORw0KGgo="}})
    text = json.dumps({"outer": json.dumps({"inner": inner})})
    stripped = media_parts.strip_raw_payload(raw, text)
    decoded = json.loads(json.loads(json.loads(stripped)["outer"])["inner"])
    assert decoded == {"source": {"type": "base64", "data": "[stripped unknown 8 bytes]"}}


@pytest.mark.parametrize(
    ("value", "size"),
    [
        ("iVBORw0KGgo=", 8),
        ("UklGRg==", 4),
        ("AAAA", 3),
        ("-_-_", 3),
        (" AA\tAA\r\n", 3),
        ("", 0),
        ("+_AA", None),
        ("AAA", None),
        ("AA=A", None),
        ("A===", None),
        ("AA AA", None),
        ("hello", None),
    ],
)
def test_byte_size(value, size):
    assert media_parts.base64_size(value) == size


# --- the rule (b) pattern means the same in Python, JavaScript and Go ----------

#: The escapes all three engines read the same way.
PORTABLE_ESCAPES = set("tnfr") | set("\\/.-[]()+*?{}|^$")


def test_data_url_pattern_is_portable(base_data):
    raw = base_data["media_parts"]["raw_payloads"]
    (rule,) = [r for r in raw["detection"] if r["id"] == "b"]
    for pattern in (rule["pattern"], raw["replacement"]["mime_pattern"]):
        assert "(?" not in pattern, "no lookaround, named group or inline flag"
        for match in re.finditer(r"\\(.)", pattern):
            assert match.group(1) in PORTABLE_ESCAPES, f"\\{match.group(1)} is not portable"
    assert rule["pattern"].startswith("[dD][aA][tT][aA]:")
    assert '[^;,\\t\\n\\f\\r "]' in rule["pattern"]
    assert "[A-Za-z0-9+/_-]" in rule["pattern"]


def test_portability_check_bites():
    for bad in ("\\s", "\\d", "\\w", "(?<=x)", "\\1"):
        pattern = f"data:([^;,]*{bad});base64,(x)"
        bites = "(?" in pattern or any(
            m.group(1) not in PORTABLE_ESCAPES for m in re.finditer(r"\\(.)", pattern)
        )
        assert bites, bad


@pytest.mark.parametrize(
    ("value", "complete"),
    [
        ("[stripped image/png 67 bytes]", True),
        ("[stripped unknown unknown bytes]", True),
        ("[stripped image/png; charset=x 0 bytes]", True),
        ("[stripped image/png lots bytes]", False),
        ("[stripped  3 bytes]", False),
        ("[stripped image/png bytes]", False),
        ("[stripped image/png \u0663 bytes]", False),
        ("x[stripped image/png 3 bytes]", False),
    ],
)
def test_complete_replacement(base_data, value, complete):
    raw = base_data["media_parts"]["raw_payloads"]
    assert media_parts.is_replacement(raw, value) is complete
