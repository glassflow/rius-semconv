"""registry/media_parts.yaml: the file's own rules, and its checks against the fixtures.

Each rule gets one test that breaks the real data in exactly one way and
asserts the break is named.
"""

from __future__ import annotations

import copy
import json
import random
import re
import shutil
import subprocess
import time

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
    assert len(rows) == 39
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
    assert "no part (raw payload stripped: `input.value`)" in table
    assert "no part (raw payload stripped: `output.value`)" in table
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
            "media present only in input.value (audio input, PDF document)",
        ): ["input.value"],
        (
            "openinference.llm",
            "media present only in output.value (audio output)",
        ): ["output.value"],
        ("vercel.ai", "file part with Buffer data in ai.prompt"): ["ai.prompt"],
        ("vercel.ai", "image part with base64 image in ai.prompt"): ["ai.prompt"],
        ("vercel.ai", "file / image part with v7 tagged data in ai.prompt"): ["ai.prompt"],
        (
            "rius.sdk",
            "byte object in a serialized value (Python bytes, bytearray, memoryview;"
            " TypeScript ArrayBuffer and its views, Buffer included)",
        ): ["input.value", "output.value"],
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
    by_direction = {
        r["direction"]: r
        for r in rows
        if r["source"] == "openinference.llm" and r["normalized"] == "none"
    }
    assert sorted(by_direction["input"]["fixtures"]) == sorted(
        [
            "openinference-openai/input_audio",
            "openinference-js-openai/input_audio",
            "openinference-anthropic/document_pdf",
            "openinference-js-anthropic/document_pdf",
        ]
    )
    assert sorted(by_direction["output"]["fixtures"]) == sorted(
        [
            "openinference-openai/audio_output",
            "openinference-js-openai/audio_output",
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
    """A fixture proving a part must carry the media in a message key, never
    only in a raw payload such as input.value."""
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


def test_data_url_pattern_needs_its_four_groups(data):
    (rule,) = [r for r in data["media_parts"]["raw_payloads"]["detection"] if r["id"] == "b"]
    rule["pattern"] = "data:([^;]*);base64,(x)"
    assert_flags(media_parts.lint(data["media_parts"]), "pattern needs 4 groups")


@pytest.mark.parametrize(
    ("text", "run"),
    [
        ("data:a/b;base64,QUFB\nQkJD", "QUFB\nQkJD"),
        ("data:a/b;base64,QUFB\r\nQkJD", "QUFB\r\nQkJD"),
        ("data:a/b;base64,QUFB\n \tQkJD=", "QUFB\n \tQkJD="),
        ("data:a/b;base64,\nQUFB", "\nQUFB"),
        ("data:a/b;base64,QUFB\n\nQkJD", "QUFB"),
        ("data:a/b;base64,QUFB\rQkJD", "QUFB"),
        ("data:a/b;base64,QUE=\nQkJD", "QUE="),
        ("data:a/b;base64,QUFB\n", "QUFB"),
        ("data:a/b;base64,QUFB\ndata:a/b;base64,QkJD", "QUFB"),
        ("data:a/b;base64,QUFBdata:a/b;base64,QkJD", "QUFB"),
    ],
)
def test_a_run_goes_on_over_a_line_break_but_never_into_the_next_data_url(base_data, text, run):
    raw = base_data["media_parts"]["raw_payloads"]
    span = media_parts.data_url_spans(raw, text)[0]
    assert text[span.start : span.end] == "data:a/b;base64," + run


@pytest.mark.parametrize(
    ("text", "run"),
    [
        ("data:a/b;base64,QUFB\\nQkJD", "QUFB\\nQkJD"),
        ("data:a/b;base64,QUFB\\r\\nQkJD", "QUFB\\r\\nQkJD"),
        ("data:a/b;base64,QUFB\\n> QkJD=", "QUFB\\n> QkJD="),
        ("data:a/b;base64,QUFB\\n\\nQkJD", "QUFB"),
        ("data:a/b;base64,QUFB\\rQkJD", "QUFB"),
        ("data:a/b;base64,QUFB\\tQkJD", "QUFB"),
        ("data:a/b;base64,QUE=\\nQkJD", "QUE="),
        ("data:a/b;base64,QUFB\\n", "QUFB"),
        ("data:a/b;base64,QUFB\nQkJD\\nQ0ND", "QUFB\nQkJD\\nQ0ND"),
        ("data:a/b;base64,QUFB\\nQkJD\nQ0ND", "QUFB\\nQkJD"),
        ("data:a/b;base64," + "A" * 77 + "\\nQkJD", "A" * 77),
        ("data:a/b;base64,QUFB\\ndata:a/b;base64,QkJD", "QUFB"),
    ],
)
def test_an_escaped_run_goes_on_over_an_escaped_line_break(base_data, text, run):
    raw = base_data["media_parts"]["raw_payloads"]
    span = media_parts.data_url_spans(raw, text, escaped=True)[0]
    assert text[span.start : span.end] == "data:a/b;base64," + run


@pytest.mark.parametrize(
    ("text", "size"),
    [
        ('{"u":"data:a/b;base64,QUFB\\nQkJD', 6),
        ('{"u":"data:a/b;base64,QUFB\\r\\n> QkJD', 6),
        ('{"u":"data:a/b;base64,QUFB\\nQkJD"}', 6),
    ],
)
def test_only_json_that_does_not_parse_takes_an_escaped_line_break(base_data, text, size):
    raw = base_data["media_parts"]["raw_payloads"]
    (token,) = media_parts.strip(raw, text).tokens
    assert token.byte_size == size
    # The same text outside a candidate keeps to the raw pattern.
    (token,) = media_parts.strip(raw, "x " + text).tokens
    assert token.byte_size == 3


@pytest.mark.parametrize(
    ("text", "mime", "size"),
    [
        ("data%3Aimage%2Fpng%3Bbase64%2CiVBORw0KGgo%3D", "image/png", 8),
        ("DATA%3aimage%2fpng%3bbase64%2civBORw0KGgo%3d", "image/png", 8),
        ("data%3Aimage/png%3Bbase64%2C%2B%2B%2B%2B////AA%3D%3D", "image/png", 7),
        ("data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CQUFB", "image/svg+xml", 3),
        ("data%3Aimage%2Fpng%3Bname%3Da.png%3Bbase64%2CQUFB", "image/png", 3),
        ("data%3A%3Bbase64%2CQUFB", None, 3),
        ("data%3Aimage%3Bbase64%2CQUFB", None, 3),
        ("data%3Aa%2Fb%2Fc%3Bbase64%2CQUFB", None, 3),
        ("data%3Aa%2Fb%3Bbase64%2CQUFB%3D%3D%3D", "a/b", None),
        ("data%3Aa%2Fb%3Bbase64%2C", "a/b", 0),
    ],
)
def test_a_percent_encoded_data_url_is_one_token(base_data, text, mime, size):
    raw = base_data["media_parts"]["raw_payloads"]
    (span,) = media_parts.data_url_spans(raw, text)
    end = len(text) - 3 if text.endswith("%3D%3D%3D") else len(text)
    assert (span.start, span.end, span.mime, span.byte_size) == (0, end, mime, size)


@pytest.mark.parametrize(
    ("text", "token"),
    [
        ("x data%3Aa%2Fb%3Bbase64%2CQUFB%0AQkJD", "data%3Aa%2Fb%3Bbase64%2CQUFB%0AQkJD"),
        ("data%3Aa%2Fb%3Bbase64%2CQUFB%0d%0aQkJD%0A ", "data%3Aa%2Fb%3Bbase64%2CQUFB%0d%0aQkJD%0A"),
        ("data%3Aa%2Fb%3Bbase64%2CQUFB%3D%0AQkJD", "data%3Aa%2Fb%3Bbase64%2CQUFB%3D"),
        ("data%3Aa%2Fb%3Bbase64%2CQUFB%20QkJD", "data%3Aa%2Fb%3Bbase64%2CQUFB"),
        ("data%3Aa%2Fb%3Bbase64%2CQUFB%0CQkJD", "data%3Aa%2Fb%3Bbase64%2CQUFB"),
        ("data%3Aa%2Fb%3Bbase64%2CQUFB%2C", "data%3Aa%2Fb%3Bbase64%2CQUFB"),
        ("data%3Aa%2Fb%3Bbase64%2CQUFB&w=1", "data%3Aa%2Fb%3Bbase64%2CQUFB"),
        (
            "data%3Aa%2Fb%3Bbase64%2CQUFBdata%3Aa%2Fb%3Bbase64%2CQkJD",
            "data%3Aa%2Fb%3Bbase64%2CQUFB",
        ),
        ("data%3Aa%2Fb%3Bbase64%2CQUFBdata:a/b;base64,QkJD", "data%3Aa%2Fb%3Bbase64%2CQUFB"),
        ("data%3Aa%2Cb%3Bbase64%2CQUFB", None),
        ("data%3Aa b%3Bbase64%2CQUFB", None),
        ("data%253Aa%3Bbase64%2CQUFB", None),
        ("data%3Aa%3Bbase64%2cQUFB", "data%3Aa%3Bbase64%2cQUFB"),
        ("data%3Aa%3BBASE64%2CQUFB", None),
    ],
)
def test_a_percent_encoded_data_url_ends_where_its_run_does(base_data, text, token):
    raw = base_data["media_parts"]["raw_payloads"]
    spans = media_parts.data_url_spans(raw, text)
    assert [text[s.start : s.end] for s in spans][:1] == ([token] if token else [])


@pytest.mark.parametrize(
    ("value", "kept"),
    [
        ("data%3Aimage%2Fpng%3Bbase64%2CiVBORw0KGgo%3D", True),
        ("data%3Aimage%2Fpng%3Bbase64%2CiVBORw0KGgo%3D\n", True),
        ("data%3Aimage%2Fpng%3Bbase64%2CiVBORw0KGgo%3D ", False),
        ("data%3Aimage%2Fpng%3Bbase64%2CiVBORw0KGgo%3D%0A", True),
        ("data%3Aimage%2Fpng%3Bbase64%2CiVBORw0KGgo%3D%0d%0A", True),
        ("data%3Aimage%2Fpng%3Bbase64%2CiVBORw0KGgo%3D%0A%0A", False),
        ("data%3Aimage%2Fpng%3Bbase64%2CiVBORw0KGgo%3D%0A\n", False),
        ("data:image/png;base64,iVBORw0KGgo=%0A", False),
        ("https://x/?u=data%3Aimage%2Fpng%3Bbase64%2CiVBORw0KGgo%3D", True),
        (" data%3Aimage%2Fpng%3Bbase64%2CiVBORw0KGgo%3D", False),
    ],
)
def test_a_url_key_keeps_a_whole_percent_encoded_data_url_for_rule_b(base_data, value, kept):
    raw = base_data["media_parts"]["raw_payloads"]
    assert media_parts.kept_url(raw, value) == kept


def test_data_url_percent_pattern_needs_its_five_groups(data):
    (rule,) = [r for r in data["media_parts"]["raw_payloads"]["detection"] if r["id"] == "b"]
    rule["percent_pattern"] = rule["pattern"]
    assert_flags(media_parts.lint(data["media_parts"]), "percent_pattern needs 5 groups")


def test_data_url_escaped_pattern_needs_its_five_groups(data):
    (rule,) = [r for r in data["media_parts"]["raw_payloads"]["detection"] if r["id"] == "b"]
    rule["escaped_pattern"] = rule["pattern"]
    assert_flags(media_parts.lint(data["media_parts"]), "escaped_pattern needs 5 groups")


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


#: Rule (b) is linear: 40 KB of near-matches takes milliseconds. The bound
#: leaves room for slow CI.
NEAR_MATCHES = {
    "data_colon": "data:" * 8_000,
    "data_a_semicolon": "data:a;" * 6_000,
    "blank_continuations": "data:a/b;base64,A" + "\n " * 20_000 + "!",
    "data_url_lines": "data:a/b;base64,A\n" * 2_000 + "!",
    "quoted_continuations": "data:a/b;base64,A" + "\n>" * 20_000 + "!",
    "lines_at_the_cap": "data:a/b;base64," + ("A" * 76 + "\n") * 500 + "!",
    "lines_past_the_cap": ("data:a/b;base64," + "A" * 77 + "\n") * 400 + "!",
    # JSON that does not parse, so escaped_pattern is tried.
    "escaped_blank_continuations": '{"a":"data:a/b;base64,A' + "\\n " * 20_000 + "!",
    "escaped_one_character_lines": '{"a":"data:a/b;base64,' + "A\\n" * 20_000 + "!",
    "escaped_lines_at_the_cap": '{"a":"data:a/b;base64,' + ("A" * 76 + "\\r\\n") * 500 + "!",
    "escaped_backslashes": '{"a":"data:a/b;base64,A' + "\\" * 40_000,
    "percent_schemes": "data%3A" * 6_000,
    "percent_headers_with_no_comma": "data%3A" + "%3Bbase64" * 4_000,
    "percent_tokens": "data%3Aa%3Bbase64%2C" * 2_000,
    "percent_escaped_run": "data%3Aa%2Fb%3Bbase64%2C" + "%2B" * 13_000 + "!",
    "percent_line_breaks": "data%3Aa%2Fb%3Bbase64%2C" + "A%0D%0A" * 6_000 + "!",
    "percent_wrapped_tokens": "data%3Aa%2Fb%3Bbase64%2CQUFB%0A" * 1_500,
}
TIME_BOUND = 0.5


#: The near matches that hold no token; the others are all tokens.
NO_TOKENS = {"data_colon", "data_a_semicolon", "percent_schemes", "percent_headers_with_no_comma"}


@pytest.mark.parametrize("name", NEAR_MATCHES)
def test_near_matches_strip_in_linear_time(base_data, name):
    raw = base_data["media_parts"]["raw_payloads"]
    text = NEAR_MATCHES[name]
    start = time.perf_counter()
    stripped = media_parts.strip_raw_payload(raw, text)
    assert time.perf_counter() - start < TIME_BOUND
    assert (stripped == text) == (name in NO_TOKENS)
    assert "base64" not in stripped or name in NO_TOKENS


@pytest.mark.parametrize("name", NEAR_MATCHES)
def test_near_matches_check_in_linear_time(name):
    from tools.check_fixtures import _holds_media

    _holds_media("", key="input.value")  # loads the registry and payloads once
    start = time.perf_counter()
    assert _holds_media(NEAR_MATCHES[name], key="input.value") == (name not in NO_TOKENS)
    assert time.perf_counter() - start < TIME_BOUND


def test_a_long_data_url_without_base64_is_linear(base_data):
    # The parameter group never overlaps the mime group, so this returns at once.
    raw = base_data["media_parts"]["raw_payloads"]
    assert media_parts.data_url_spans(raw, "data:x" + "a" * 200_000) == []
    assert media_parts.data_url_spans(raw, "data:x" + ";a" * 100_000) == []


@pytest.mark.parametrize("tail", [" ", "!", "\n!", "\n" + "A" * 77 + " "])
def test_a_whole_value_that_fails_is_linear(base_data, tail):
    # Anchored and checked at the end, a long run that does not reach the end
    # of the value fails at once, where fullmatch would try each way to share
    # a line between the capped run and the uncapped tail.
    raw = base_data["media_parts"]["raw_payloads"]
    value = "data:a/b;base64," + "A" * 400_000 + tail
    start = time.perf_counter()
    assert media_parts.whole_data_url(raw, value) is None
    assert not media_parts.kept_url(raw, value)
    assert time.perf_counter() - start < TIME_BOUND


@pytest.mark.parametrize(
    "value",
    [
        "data:a/b;base64,QUFB",
        "data:a/b;base64," + "A" * 76 + "\n" + "A" * 76 + "\nAAAA",
        "data:a/b;base64," + "A" * 77 + "\nAAAA",
        "data:a/b;base64,QUFB\n" + "A" * 80 + "\nAAAA",
        "data:a/b;base64,QUFB\n> QUFB",
        "data:a/b;base64,QUE=\nQUFB",
        "data:a/b;base64,QUFB\n\nQUFB",
    ],
)
def test_a_whole_value_is_what_fullmatch_says(base_data, value):
    raw = base_data["media_parts"]["raw_payloads"]
    expected = re.fullmatch(media_parts._rules(raw)["b"]["pattern"], value) is not None
    assert (media_parts.whole_data_url(raw, value) is not None) == expected


@pytest.mark.parametrize(
    ("tail", "kept"),
    [
        ("", True),
        ("\n", True),
        ("\r\n", True),
        ("\n\n", False),
        ("\r", False),
        (" \n", False),
        ("\n ", False),
        ("\n\r\n", False),
    ],
)
def test_a_url_key_takes_one_final_line_break(base_data, tail, kept):
    raw = base_data["media_parts"]["raw_payloads"]
    value = "data:image/png;base64,iVBORw0KGgo=" + tail
    assert (media_parts.whole_data_url(raw, value, line_break=True) is not None) == kept
    assert media_parts.kept_url(raw, value) == kept
    assert (media_parts.whole_data_url(raw, value) is not None) == (tail == "")


def test_in_text_example_is_what_the_rule_does(base_data):
    raw = base_data["media_parts"]["raw_payloads"]
    example = raw["replacement"]["in_text"]
    assert media_parts.strip_data_urls(raw, example["before"]) == example["after"]


# --- strip_raw_payload: the golden examples ------------------------------------

GOLDEN = Registry.load().media_parts["raw_payloads"]["golden"]

#: The cases the contract must pin, by golden name.
REQUIRED_GOLDEN = {
    "a_percent_encoded_data_url_in_prose",
    "a_percent_encoded_data_url_in_json_and_under_keys",
    "a_percent_encoded_run_ends_at_any_other_escape",
    "a_percent_encoded_data_url_wrapped_before_it_was_encoded",
    "an_escaped_run_ends_at_a_unicode_escape",
    "a_wrapped_data_url_in_json_that_does_not_parse",
    "an_escaped_line_break_outside_json_ends_the_run",
    "a_base64_data_url_that_ends_in_one_line_break_under_a_url_key",
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
    "a_replacement_holding_a_data_url_is_not_complete",
    "a_replacement_with_a_mime_that_is_not_a_token_is_a_token",
    "a_nested_document_has_no_enclosing_object",
    "a_replaced_buffer_is_not_context",
    "a_replaced_buffer_next_to_a_replacement_lookalike",
    "context_is_read_before_the_pass",
    "context_is_read_before_the_pass_in_any_order",
    "output_format_is_read_before_the_pass",
    "a_second_pass_after_the_candidate_starts_to_parse",
    "langchain_v1_base64_image",
    "langchain_v1_blocks_of_every_media_type",
    "a_base64_key_beside_a_mime_type",
    "a_base64_key_with_no_media_context",
    "a_typed_key_counts_when_any_type_member_qualifies",
    "bedrock_converse_image_bytes",
    "bedrock_converse_document_and_video_bytes",
    "bedrock_converse_audio_bytes",
    "bytes_outside_a_source_is_left_alone",
    "mistral_input_audio_string",
    "mistral_typescript_input_audio_string",
    "input_audio_string_with_no_type_is_left_alone",
    "the_new_shapes_stripped_twice_change_nothing",
    "vercel_image_part_base64_in_ai_prompt",
    "vercel_image_part_base64_without_a_media_type",
    "vercel_image_string_that_is_not_base64",
    "vercel_image_url_is_left_alone",
    "vercel_image_data_url_keeps_its_own_mime",
    "vercel_tagged_file_data_in_ai_prompt",
    "vercel_tagged_image_data",
    "vercel_tagged_data_url_and_link",
    "image_and_tagged_data_outside_their_parts_are_left_alone",
    "langchain_v0_base64_block_without_a_mime_type",
    "langchain_v0_base64_blocks_with_a_mime_type",
    "langchain_v0_blocks_with_no_base64_marker_are_left_alone",
    "the_vercel_and_langchain_v0_shapes_stripped_twice_change_nothing",
    "a_wrapped_base64_data_url_under_a_url_key_is_one_rule_b_token",
    "a_link_followed_by_a_data_url_under_a_url_key_is_replaced_whole",
    "a_url_led_by_whitespace_under_a_url_key_is_replaced_whole",
    "a_link_with_data_colon_in_its_path_under_a_url_key",
    "a_link_followed_by_a_wrapped_data_url_in_a_json_string",
    "a_wrapped_data_url_in_prose",
    "a_wrapped_uppercase_data_url_in_prose",
    "an_unpadded_run_takes_the_first_word_of_the_next_line",
    "a_long_data_url_at_a_line_end_keeps_the_lines_after_it",
    "a_tiny_data_url_at_a_line_end_takes_the_one_word_lines_after_it",
    "a_wrapped_data_url_in_a_quoted_reply",
    "a_data_url_never_runs_into_the_next",
    "a_whole_data_url_is_unchanged_by_the_continuation",
    "a_percent_encoded_data_url_under_a_url_key_is_replaced_whole",
    "a_broken_base64_run_under_a_url_key_is_replaced_whole",
    "tagged_data_outside_a_vercel_part_is_left_alone",
    "a_base64_marker_reaches_data_alone",
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
    if "second_output" in golden:
        second = media_parts.strip(raw, golden["output"])
        assert second.text == golden["second_output"]
        assert [t.as_dict() for t in second.tokens] == golden["second_tokens"]


def _parse_status_changes(text: str, once: str) -> bool:
    """The one class idempotence excludes: a candidate whose parse status
    differs after pass 1 (it did not parse and now does)."""
    return (media_parts.parse_json_candidate(text) is None) != (
        media_parts.parse_json_candidate(once) is None
    )


@pytest.mark.parametrize("golden", GOLDEN, ids=[g["name"] for g in GOLDEN])
def test_stripping_is_idempotent(base_data, golden):
    raw = base_data["media_parts"]["raw_payloads"]
    if _parse_status_changes(golden["input"], golden["output"]):
        assert golden["name"] == "a_second_pass_after_the_candidate_starts_to_parse"
        return
    assert media_parts.strip(raw, golden["output"]) == media_parts.Stripped(golden["output"], [])


#: What the random documents are made of: every key the rules read, values
#: that are or look like replacements, data URLs and base64.
FUZZ_KEYS = [
    "data", "content", "type", "mediaType", "mime_type", "media_type", "format",
    "output_format", "source", "audio", "input_audio", "inlineData", "b64_json", "result", "x",
]  # fmt: skip
FUZZ_STRINGS = [
    "QUFB", "iVBORw0KGgo=", "", "hi", "image/png", "wav", "png", "base64", "blob", "Buffer",
    "data:image/png;base64,QUFB", "DATA:a/b;x=1;base64,QQ==", "x data:a;b;base64,QQ== y",
    "data:", "data:a;", "[stripped image/png 3 bytes]", "[stripped unknown unknown bytes]",
    "[stripped a b 3 bytes]", "[stripped data:image/png;base64,QUFB 1 bytes]",
    "[stripped image/png lots bytes]", "[stripped [stripped image/png 3 bytes] 1 bytes]",
]  # fmt: skip
FUZZ_CASES = 6_000


def _fuzz_value(rng: random.Random, depth: int = 0):
    roll = rng.random()
    if depth > 4 or roll < 0.35:
        return rng.choice([*FUZZ_STRINGS, 1, None, True])
    if roll < 0.45:
        return json.dumps(_fuzz_value(rng, depth + 1))  # a nested document
    if roll < 0.55:
        return {"type": "Buffer", "data": rng.choice([[1], [1, 2, 3], []])}
    if roll < 0.7:
        return [_fuzz_value(rng, depth + 1) for _ in range(rng.randint(0, 3))]
    obj = {rng.choice(FUZZ_KEYS): _fuzz_value(rng, depth + 1) for _ in range(rng.randint(0, 4))}
    if rng.random() < 0.3:
        obj["type"] = rng.choice(["blob", "Buffer", "base64"])
    return obj


def test_stripping_twice_is_stripping_once_on_random_documents(base_data):
    """Seeded: structured documents mixing Buffers, mime keys, format and data
    URLs, compact and spaced, at the top level and as a JSON string inside."""
    raw = base_data["media_parts"]["raw_payloads"]
    rng = random.Random(20240601)
    failures = []
    for _ in range(FUZZ_CASES):
        separators = rng.choice([(",", ":"), (", ", ": ")])
        text = json.dumps(_fuzz_value(rng), separators=separators)
        once = media_parts.strip_raw_payload(raw, text)
        if _parse_status_changes(text, once):
            continue
        if media_parts.strip_raw_payload(raw, once) != once:
            failures.append(text)
    assert failures == [], f"{len(failures)} not idempotent, first: {failures[0]}"


def test_part_examples_follow_the_member_order(base_data):
    media = base_data["media_parts"]
    members = media["part_shapes"]["members"]
    examples = media["part_shapes"]["examples"]
    assert {json.loads(e["part"])["type"] for e in examples} == set(members)
    for example in examples:
        part = json.loads(example["part"])
        assert list(part) == [m for m in members[part["type"]] if m in part], example["name"]
        assert None not in part.values(), example["name"]


def test_rows_with_a_part_example_follow_the_member_order(base_data):
    """Any row that carries an example output follows the same order."""
    members = base_data["media_parts"]["part_shapes"]["members"]
    for row in base_data["media_parts"]["rows"]:
        for field in ("part", "example", "output"):
            if field in row:
                part = json.loads(row[field]) if isinstance(row[field], str) else row[field]
                assert list(part) == [m for m in members[part["type"]] if m in part]


IN_PLACE_EXAMPLES = Registry.load().media_parts["part_shapes"]["in_place_examples"]


@pytest.mark.parametrize("example", IN_PLACE_EXAMPLES, ids=[e["name"] for e in IN_PLACE_EXAMPLES])
def test_in_place_example_changes_only_the_part(base_data, example):
    """Only the part object is replaced, by what native_part makes of it."""
    before, after = example["input"], example["output"]
    start = after.index('{"type":')
    end = after.index("}", start) + 1
    assert after[:start] == before[: before.index('{"type"')]
    assert after[end:] == before[before.index("}", before.index('{"type"')) + 1 :]
    (message,) = json.loads(before)
    (part,) = message["parts"]
    rebuilt = media_parts.native_part(base_data["media_parts"], part)
    assert rebuilt is not None
    assert media_parts.part_text(rebuilt) == after[start:end]


def test_members_out_of_order_fail_lint(data):
    examples = data["media_parts"]["part_shapes"]["examples"]
    examples[0]["part"] = '{"modality":"image","type":"blob","stripped_reason":"not_captured"}'
    assert_flags(media_parts.lint(data["media_parts"]), "not in the order")


def test_a_null_member_fails_lint(data):
    examples = data["media_parts"]["part_shapes"]["examples"]
    examples[0]["part"] = (
        '{"type":"blob","modality":"image","byte_size":null,"stripped_reason":"not_captured"}'
    )
    assert_flags(media_parts.lint(data["media_parts"]), "as null")


def test_a_mime_that_is_not_a_token_fails_lint(data):
    examples = data["media_parts"]["part_shapes"]["examples"]
    examples[0]["part"] = (
        '{"type":"blob","modality":"image","mime_type":"a b","stripped_reason":"not_captured"}'
    )
    assert_flags(media_parts.lint(data["media_parts"]), "not a token/token MIME type")


def _example_of(data, kind):
    examples = data["media_parts"]["part_shapes"]["examples"]
    return next(e for e in examples if json.loads(e["part"])["type"] == kind)


def test_a_file_part_without_its_file_id_fails_lint(data):
    _example_of(data, "file")["part"] = '{"type":"file","modality":"document"}'
    assert_flags(media_parts.lint(data["media_parts"]), "has no file_id")


def test_a_uri_part_without_its_uri_fails_lint(data):
    _example_of(data, "uri")["part"] = '{"type":"uri","modality":"document"}'
    assert_flags(media_parts.lint(data["media_parts"]), "has no uri")


def test_a_bare_file_part_is_not_canonical(base_data):
    errors = media_parts.part_order_errors(base_data["media_parts"], {"type": "file"})
    assert_flags(errors, "has no modality")
    assert_flags(errors, "has no file_id")


def _blob(**members):
    return {"type": "blob", "modality": "image", **members, "stripped_reason": "not_captured"}


@pytest.mark.parametrize(
    ("part", "fragment"),
    [
        (_blob(byte_size=-1), "has byte_size -1"),
        (_blob(byte_size="8"), "has byte_size '8'"),
        (_blob(byte_size=2.5), "has byte_size 2.5"),
        (_blob(byte_size=8.0), "has byte_size 8.0"),
        (_blob(byte_size=True), "has byte_size True"),
        (_blob(byte_size=2**53), "has byte_size 9007199254740992"),
        ({"type": "uri", "modality": "image", "uri": {"href": "h"}}, "has uri {'href': 'h'}"),
        ({"type": "file", "modality": "image", "file_id": 5}, "has file_id 5"),
        ({"type": "file", "modality": "picture", "file_id": "f"}, "has modality 'picture'"),
        (
            {"type": "blob", "modality": "image", "stripped_reason": "gone"},
            "has stripped_reason 'gone'",
        ),
        (
            {"type": "uri", "modality": "image", "mime_type": "image", "uri": "u"},
            "has mime_type 'image'",
        ),
        ({"type": "uri", "modality": "image", "mime_type": 5, "uri": "u"}, "has mime_type 5"),
    ],
)
def test_a_part_with_a_wrong_value_is_not_canonical(base_data, part, fragment):
    assert_flags(media_parts.part_order_errors(base_data["media_parts"], part), fragment)


def test_the_stripped_reasons_come_from_the_contract(base_data):
    media = copy.deepcopy(base_data["media_parts"])
    media["stripped_reasons"] = {"redacted_upstream": "x"}
    errors = media_parts.part_order_errors(media, _blob())
    assert_flags(errors, "has stripped_reason 'not_captured'")


@pytest.mark.parametrize(
    "part",
    [
        _blob(mime_type="image/png", byte_size=0),
        _blob(byte_size=2**53 - 1),
        {"type": "uri", "modality": "video", "uri": ""},
        {"type": "file", "modality": "document", "file_id": ""},
    ],
)
def test_a_part_with_canonical_values_passes(base_data, part):
    assert media_parts.part_order_errors(base_data["media_parts"], part) == []


def _parts(value):
    """The parts of a message-key value: each message's parts, or the system
    instructions' list itself."""
    for item in value if isinstance(value, list) else []:
        if isinstance(item, dict) and isinstance(item.get("parts"), list):
            yield from item["parts"]
        elif isinstance(item, dict) and "role" not in item:
            yield item


def _expected_media_parts():
    message_keys = {"gen_ai.input.messages", "gen_ai.output.messages", "gen_ai.system_instructions"}
    for path in sorted(FIXTURES.glob("*/*.expected.json")):
        for recording in json.loads(path.read_text())["recordings"]:
            for span in recording["spans"]:
                for attribute in span["span"].get("attributes") or []:
                    if attribute["key"] not in message_keys:
                        continue
                    value = json.loads(attribute["value"]["stringValue"])
                    for part in _parts(value):
                        if isinstance(part, dict) and part.get("type") in ("blob", "uri", "file"):
                            yield f"{path.name} {recording['scenario']}", part


def test_every_media_part_in_an_expected_result_is_canonical(base_data):
    """No normalizer may leave a media part that is not canonical: a file
    without its modality and file_id, a uri without its uri, members out of
    order."""
    media = base_data["media_parts"]
    seen = list(_expected_media_parts())
    assert seen, "no expected result holds a media part"
    failures = [
        f"{where}: {part} {errors}"
        for where, part in seen
        if (errors := media_parts.part_order_errors(media, part))
    ]
    assert failures == []


def test_a_message_example_that_keeps_a_bare_file_part_fails_lint(data):
    example = data["media_parts"]["part_shapes"]["message_examples"][0]
    example["output"] = '[{"role":"user","parts":[{"type":"file"}]}]'
    assert_flags(media_parts.lint(data["media_parts"]), "has no file_id")


def test_a_message_example_needs_json(data):
    data["media_parts"]["part_shapes"]["message_examples"][0]["output"] = "["
    assert_flags(media_parts.lint(data["media_parts"]), "needs JSON input and output")


def test_message_examples_rendered(base_data):
    table = media_parts.render_table(base_data["media_parts"])
    for example in base_data["media_parts"]["part_shapes"]["message_examples"]:
        assert f"`{example['name']}`" in table


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
    (keyed,) = [r for r in raw["detection"] if r["id"] == "e"]
    patterns = (
        rule["pattern"],
        rule["escaped_pattern"],
        rule["percent_scheme"],
        rule["percent_pattern"],
    )
    for pattern in (*patterns, raw["replacement"]["mime_pattern"], keyed["url_scheme"]):
        assert "(?" not in pattern, "no lookaround, named group or inline flag"
        for match in re.finditer(r"\\(.)", pattern):
            assert match.group(1) in PORTABLE_ESCAPES, f"\\{match.group(1)} is not portable"
    assert rule["pattern"].startswith("[dD][aA][tT][aA]:")
    assert '([^;,:\\t\\n\\f\\r "]*)(;[^;,:\\t\\n\\f\\r "]*)*' in rule["pattern"]
    assert "[A-Za-z0-9+/_-]" in rule["pattern"]
    assert "([A-Za-z0-9+/_-]{0,76}(\\r{0,1}\\n[ \\t>]*[A-Za-z0-9+/_-]+)*" in rule["pattern"]
    assert "[A-Za-z0-9+/_-]*={0,2})" in rule["pattern"]
    assert "?" not in rule["pattern"] and "|" not in rule["pattern"]
    # escaped_pattern is pattern with one more continuation group, its escaped
    # break holding no group (a group there lowers V8's stack limit).
    continuation = "(\\r{0,1}\\n[ \\t>]*[A-Za-z0-9+/_-]+)*"
    escaped = "(\\\\r{0,1}\\\\{0,1}n[ \\t>]*[A-Za-z0-9+/_-]+)*"
    assert rule["escaped_pattern"] == rule["pattern"].replace(continuation, continuation + escaped)
    assert "?" not in rule["escaped_pattern"] and "|" not in rule["escaped_pattern"]
    # percent_pattern starts with percent_scheme; its header escapes never end
    # in C, so %2C ends the header.
    assert rule["percent_pattern"].startswith(rule["percent_scheme"])
    assert '(%[0-9A-Fa-f][0-9ABD-Fabd-f][^%;,:\\t\\n\\f\\r "]*)*)' in rule["percent_pattern"]
    assert (
        "([A-Za-z0-9+/_-]*(%[02][ABDFabdf][A-Za-z0-9+/_-]*)*(%3[dD]){0,2})"
        in rule["percent_pattern"]
    )
    assert "?" not in rule["percent_pattern"] and "|" not in rule["percent_pattern"]


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
        ("[stripped image/png; charset=x 0 bytes]", False),
        ("[stripped a b 3 bytes]", False),
        ("[stripped data:image/png;base64,iVBORw0KGgo= 1 bytes]", False),
        ("[stripped application/vnd.ms-excel 12 bytes]", True),
        ("[stripped unknown 3 bytes]", True),
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


# --- URLs under a typed key that keeps them ------------------------------------


@pytest.mark.parametrize(
    ("value", "url"),
    [
        ("https://example.com/a.png", True),
        ("gs://bucket/a.png", True),
        ("data:image/png;base64,QUFB", True),
        ("svn+ssh://host/x", True),
        ("iVBORw0KGgo=", False),
        ("1http://x", False),
        (" https://example.com", False),
        ("[stripped unknown 3 bytes]", False),
        ("", False),
    ],
)
def test_a_url_starts_with_a_scheme(base_data, value, url):
    raw = base_data["media_parts"]["raw_payloads"]
    assert media_parts.is_url(raw, value) is url


def test_a_url_in_an_array_under_image_is_left_to_rule_b(base_data):
    raw = base_data["media_parts"]["raw_payloads"]
    text = '{"type":"image","image":["https://example.com/a.png","QUFB"]}'
    assert media_parts.strip_raw_payload(raw, text) == (
        '{"type":"image","image":["https://example.com/a.png","[stripped unknown 3 bytes]"]}'
    )


def test_keeps_urls_wins_over_a_sibling(base_data):
    """Tagged data beside its own mediaType qualifies through the sibling too,
    but its key keeps URLs, so the link stays."""
    raw = base_data["media_parts"]["raw_payloads"]
    text = (
        '{"type":"file","data":{"type":"data","data":"https://example.com/a.pdf",'
        '"mediaType":"application/pdf"}}'
    )
    assert media_parts.strip_raw_payload(raw, text) == text


def test_a_tagged_data_reads_its_own_mime_first(base_data):
    raw = base_data["media_parts"]["raw_payloads"]
    text = (
        '{"type":"file","mediaType":"image/png",'
        '"data":{"type":"data","data":"QUFB","mediaType":"image/gif"}}'
    )
    tokens = [t.as_dict() for t in media_parts.strip(raw, text).tokens]
    assert tokens == [{"rule": "e", "mime": "image/gif", "byte_size": 3}]


def test_a_base64_marker_needs_its_exact_value(base_data):
    raw = base_data["media_parts"]["raw_payloads"]
    for marker in ('"Base64"', '"base64 "', "true", '["base64"]'):
        text = '{"source_type":' + marker + ',"data":"QUFB"}'
        assert media_parts.strip_raw_payload(raw, text) == text, marker


def test_a_rule_e_without_its_new_fields_fails_lint(data):
    (rule,) = [r for r in data["media_parts"]["raw_payloads"]["detection"] if r["id"] == "e"]
    del rule["url_scheme"]
    del rule["base64_markers"]
    errors = media_parts.lint(data["media_parts"])
    assert_flags(errors, "detection rule e needs url_scheme")
    assert_flags(errors, "detection rule e needs base64_markers")


# --- byte objects -------------------------------------------------------------

BYTE_OBJECTS = Registry.load().media_parts["raw_payloads"]["byte_objects"]
PYTHON_BYTE_OBJECTS = [e for e in BYTE_OBJECTS["examples"] if e["language"] == "python"]


@pytest.mark.parametrize(
    "example", PYTHON_BYTE_OBJECTS, ids=[e["name"] for e in PYTHON_BYTE_OBJECTS]
)
def test_python_byte_objects_serialize_to_their_output(base_data, example):
    """The reference serializer writes each Python example's value as its
    attribute value. The TypeScript examples are checked by the TypeScript
    SDK; here they are checked to be final (lint)."""
    raw = base_data["media_parts"]["raw_payloads"]
    value = eval(
        example["value"],
        {"__builtins__": {}, "bytearray": bytearray, "bytes": bytes, "memoryview": memoryview},
    )  # noqa: S307
    assert media_parts.serialize_value(raw, value) == example["output"]


def test_byte_objects_cover_both_languages():
    assert {e["language"] for e in BYTE_OBJECTS["examples"]} == set(
        media_parts.BYTE_OBJECT_LANGUAGES
    )


def test_a_released_memoryview_has_no_size(base_data):
    raw = base_data["media_parts"]["raw_payloads"]
    view = memoryview(b"abc")
    view.release()
    assert media_parts.serialize_value(raw, [view]) == '["[stripped unknown unknown bytes]"]'


def test_a_byte_object_example_without_a_marker_fails_lint(data):
    example = data["media_parts"]["raw_payloads"]["byte_objects"]["examples"][0]
    example["output"] = '{"image":"<bytes 4 bytes>"}'
    assert_flags(media_parts.lint(data["media_parts"]), "output holds no marker")


def test_a_byte_object_example_with_a_known_mime_fails_lint(data):
    example = data["media_parts"]["raw_payloads"]["byte_objects"]["examples"][0]
    example["output"] = '{"image":"[stripped image/png 4 bytes]"}'
    assert_flags(media_parts.lint(data["media_parts"]), "output holds no marker")


def test_a_byte_object_example_that_a_strip_changes_fails_lint(data):
    example = data["media_parts"]["raw_payloads"]["byte_objects"]["examples"][0]
    example["output"] = '{"image":"[stripped unknown 4 bytes]","x":"data:image/png;base64,QUFB"}'
    assert_flags(media_parts.lint(data["media_parts"]), "output is not final")


def test_a_byte_object_example_needs_a_language(data):
    data["media_parts"]["raw_payloads"]["byte_objects"]["examples"][0]["language"] = "go"
    assert_flags(media_parts.lint(data["media_parts"]), "language must be one of")


def test_byte_objects_are_required(data):
    del data["media_parts"]["raw_payloads"]["byte_objects"]
    assert_flags(media_parts.lint(data["media_parts"]), "raw_payloads needs byte_objects")


def test_byte_objects_rendered(base_data):
    table = media_parts.render_table(base_data["media_parts"])
    assert "### Byte objects" in table
    for example in BYTE_OBJECTS["examples"]:
        assert f"`{example['name']}`" in table


# --- LangChain v1 reference blocks and message example attributes ---------------


def test_langchain_v1_reference_rows_name_the_prompt_paths(base_data):
    rows = [
        r
        for r in base_data["media_parts"]["rows"]
        if r["source"] == "langchain.messages" and r["shape"].startswith("v1 ")
    ]
    assert len(rows) == 3
    for row in rows:
        assert {"openllmetry", "laminar"} <= set(row["paths"]), row["shape"]
    assert not any("not mapped yet" in str(r.get("note")) for r in rows)


def test_message_examples_cover_the_prompt_paths(base_data):
    examples = base_data["media_parts"]["part_shapes"]["message_examples"]
    sources = {e["source"] for e in examples}
    assert "gen_ai.prompt.0.content" in sources
    assert any((e.get("attributes") or {}).get("lmnr.span.type") == "LLM" for e in examples)


def test_message_example_attributes_must_be_strings(data):
    example = data["media_parts"]["part_shapes"]["message_examples"][0]
    example["attributes"] = {"gen_ai.prompt.0.role": 5}
    assert_flags(media_parts.lint(data["media_parts"]), "attributes must map keys to strings")


def test_a_generic_row_needs_no_modality(data):
    rows = data["media_parts"]["rows"]
    (row,) = [r for r in rows if r["normalized"] == "generic"]
    assert "modality" not in row
    assert media_parts.lint(data["media_parts"]) == []


def test_a_base64_marker_without_its_keys_fails_lint(data):
    (rule,) = [r for r in data["media_parts"]["raw_payloads"]["detection"] if r["id"] == "e"]
    del rule["base64_markers"][0]["keys"]
    assert_flags(
        media_parts.lint(data["media_parts"]),
        "detection rule e base64_markers need a key, a value and keys",
    )


@pytest.mark.parametrize(
    "value",
    [
        "data:image/png;base64,iVBO\\nRw0KGgo=",
        "data:image/png;base64,iVBO\\r\\nRw0KGgo=",
        "data:image/png;base64,iVBO Rw0KGgo=",
        "data:image/png;base64,iVBORw0KGgo=\\n",
        "data:image/png;base64,iVBORw0KGgo=\\r\\n",
        "data:image/png;base64,iVBORw0KGgo=\\n\\n",
        "data:image/png,%89PNG%0D%0A",
        "Data:image/png;charset=x,iVBORw0KGgo=",
        "data:image/png;base64,@@@iVBORw0KGgo=",
    ],
)
@pytest.mark.parametrize(
    "template",
    [
        '[{"type":"image","image":"%s"}]',
        '[{"type":"image","image":{"type":"data","data":"%s"}}]',
        '[{"type":"file","data":"%s","mediaType":"image/png"}]',
        '[{"type":"file","data":{"type":"data","data":"%s"},"mediaType":"image/png"}]',
    ],
)
def test_no_payload_survives_a_url_key(base_data, template, value):
    """A data: string under a key that keeps URLs loses every byte of its
    payload, tagged or not, whatever breaks rule (b)'s run."""
    raw = base_data["media_parts"]["raw_payloads"]
    out = media_parts.strip_raw_payload(raw, template % value)
    for fragment in ("Rw0KGgo", "iVBO", "%89PNG"):
        assert fragment not in out, out


# --- the v1 part examples and message examples, through the reference ----------

PART_EXAMPLES = Registry.load().media_parts["part_shapes"]["examples"]
V1_PART_EXAMPLES = [e for e in PART_EXAMPLES if e["name"].startswith("langchain_v1_")]
REQUIRED_PART_EXAMPLES = {
    "langchain_v1_image_by_url",
    "langchain_v1_image_by_url_kind_before_extension",
    "langchain_v1_file_by_url_with_only_an_extension",
    "langchain_v1_file_by_url_with_no_extension",
    "langchain_v1_audio_by_data_url",
    "langchain_v1_image_by_redacted_url",
    "langchain_v1_file_by_empty_url",
    "langchain_v1_image_by_file_id",
    "langchain_v1_video_by_empty_file_id",
    "langchain_v1_image_by_redacted_url_and_a_file_id",
    "langchain_v1_file_by_file_id",
    "langchain_v1_file_by_empty_file_id_is_a_native_file_part",
    "langchain_v1_file_by_empty_file_id_and_a_url",
    "langchain_v1_file_by_file_id_keeps_its_modality",
    "langchain_v1_file_by_redacted_file_id_and_base64",
    "langchain_v1_file_by_redacted_file_id_and_an_empty_url",
    "langchain_v1_file_with_a_file_id_that_is_not_a_string_and_a_url",
    "langchain_v1_text_plain_by_base64",
    "langchain_v1_image_by_a_url_led_by_whitespace",
    "langchain_v1_image_by_a_url_led_by_a_tab",
    "langchain_v1_file_by_an_https_url_led_by_a_space",
    "langchain_v1_image_by_a_data_url_with_a_trailing_space",
    "langchain_v1_image_by_a_wrapped_data_url",
    "langchain_v1_file_by_a_url_led_by_whitespace_and_an_empty_file_id",
    "langchain_v1_file_by_empty_file_id_and_empty_base64",
    "langchain_v1_file_by_empty_file_id_and_redacted_base64",
    "langchain_v1_image_by_redacted_base64",
    "langchain_v1_audio_by_empty_base64",
    "langchain_v1_file_by_a_relative_url",
    "langchain_v1_image_by_a_rooted_relative_url",
    "langchain_v1_image_by_a_link_followed_by_a_data_url",
    "uri_led_by_whitespace_holding_a_data_url",
}


def test_part_examples_cover_the_required_cases():
    assert {e["name"] for e in PART_EXAMPLES} >= REQUIRED_PART_EXAMPLES


@pytest.mark.parametrize("example", V1_PART_EXAMPLES, ids=[e["name"] for e in V1_PART_EXAMPLES])
def test_v1_part_examples_are_what_the_reference_makes(base_data, example):
    """Each v1 example names its block, and the reference makes exactly its
    part, byte for byte."""
    assert "block" in example, f"{example['name']} needs a block"
    part = media_parts.langchain_v1_part(base_data["media_parts"], json.loads(example["block"]))
    assert part is not None
    assert media_parts.part_text(part) == example["part"]


@pytest.mark.parametrize(
    "block",
    [
        '{"type":"file","file_id":5}',
        '{"type":"image","id":"x","source_type":"id"}',
        '{"type":"image","source_type":"base64","data":"QUFB"}',
        '{"type":"text-plain","url":"https://example.com/a.txt"}',
        '{"type":"text-plain","file_id":"file-abc","url":""}',
        '{"type":"text","text":"hi"}',
    ],
)
def test_v1_blocks_with_no_reference_make_no_part(base_data, block):
    assert media_parts.langchain_v1_part(base_data["media_parts"], json.loads(block)) is None


def test_a_v1_example_block_must_be_an_object(data):
    (example,) = [
        e
        for e in data["media_parts"]["part_shapes"]["examples"]
        if e["name"] == "langchain_v1_image_by_url"
    ]
    example["block"] = "[1]"
    assert_flags(media_parts.lint(data["media_parts"]), "block must be a JSON object")


PROVIDER_PART_EXAMPLES = [e for e in PART_EXAMPLES if "provider" in e]

#: A provider URI holding data: after a link, for every reader, the
#: whitespace-led, uppercase and percent-encoded forms, and the negatives.
REQUIRED_PROVIDER_EXAMPLES = {
    "image_url_by_a_link_followed_by_a_data_url",
    "image_url_by_a_url_led_by_whitespace",
    "image_url_by_a_wrapped_uppercase_data_url",
    "image_url_by_a_plain_link",
    "image_url_by_a_link_with_data_colon_in_its_path",
    "image_url_by_a_whole_data_url",
    "image_url_by_a_data_url_that_ends_in_one_line_break",
    "vercel_image_by_a_wrapped_data_url_that_ends_in_one_line_break",
    "image_url_by_a_data_url_that_ends_in_two_line_breaks",
    "image_url_by_a_whole_percent_encoded_data_url",
    "vercel_image_by_a_percent_encoded_data_url_that_ends_in_one_line_break",
    "image_url_by_a_partly_percent_encoded_data_url",
    "image_url_by_a_link_holding_a_percent_encoded_data_url",
    "input_image_by_a_link_followed_by_a_percent_encoded_data_url",
    "anthropic_url_source_by_a_link_followed_by_a_data_url",
    "anthropic_document_url_source_by_a_link_followed_by_a_data_url",
    "input_file_by_a_link_followed_by_a_data_url",
    "input_file_by_a_file_url_led_by_whitespace",
    "gemini_file_data_by_a_link_followed_by_a_data_url",
    "gemini_file_data_by_a_plain_link",
    "vercel_file_by_a_link_followed_by_a_data_url",
    "vercel_file_by_a_url_tag_holding_a_data_url_after_a_link",
    "vercel_image_by_a_link_followed_by_a_data_url",
    "openinference_image_url_by_a_link_followed_by_a_data_url",
    "openinference_image_url_by_a_data_url_with_a_media_type",
    "openinference_image_url_by_a_link_holding_a_data_url_with_a_media_type",
    "openinference_image_url_by_a_link_with_a_media_type",
    "image_url_that_is_empty",
    "vercel_file_by_url_with_no_media_type",
}


def test_provider_examples_cover_every_reader():
    assert {e["name"] for e in PROVIDER_PART_EXAMPLES} >= REQUIRED_PROVIDER_EXAMPLES


@pytest.mark.parametrize(
    "example", PROVIDER_PART_EXAMPLES, ids=[e["name"] for e in PROVIDER_PART_EXAMPLES]
)
def test_provider_part_examples_are_what_the_reference_makes(base_data, example):
    part = media_parts.provider_uri_part(base_data["media_parts"], json.loads(example["provider"]))
    assert part is not None
    assert media_parts.part_text(part) == example["part"]


@pytest.mark.parametrize(
    "item",
    [
        '{"type":"file","data":"iVBORw0KGgo="}',
        '{"type":"image","image":"iVBORw0KGgo="}',
        '{"type":"image","image":" https://example.com/a.png"}',
        '{"type":"image_url","image_url":{"url":5}}',
        '{"type":"image","source":{"type":"base64","data":"QUFB"}}',
        '{"type":"input_file","file_id":"file-abc"}',
        '{"type":"input_image","image_url":"__REDACTED__","file_id":"file-abc123"}',
        '{"type":"input_image","image_url":"","file_id":"file-abc123"}',
        '{"type":"input_file","file_url":"__REDACTED__","file_id":"file-abc"}',
        '{"type":"input_file","file_url":"","file_data":"data:application/pdf;base64,JVBERi0="}',
        '{"type":"text","text":"https://x/a.png data:image/png;base64,QUFB"}',
    ],
)
def test_items_that_point_at_nothing_by_uri(base_data, item):
    assert media_parts.provider_uri_part(base_data["media_parts"], json.loads(item)) is None


def test_a_provider_example_must_be_an_object(data):
    (example,) = [
        e
        for e in data["media_parts"]["part_shapes"]["examples"]
        if e["name"] == "image_url_by_a_plain_link"
    ]
    example["provider"] = "[1]"
    assert_flags(media_parts.lint(data["media_parts"]), "provider must be a JSON object")


NATIVE_PART_EXAMPLES = [e for e in PART_EXAMPLES if "native" in e]


def test_native_part_examples_cover_the_native_uri_holding_a_data_url():
    assert {e["name"] for e in NATIVE_PART_EXAMPLES} >= {
        "uri_led_by_whitespace_holding_a_data_url",
        "uri_that_is_a_data_url_and_one_final_line_break",
        "uri_that_is_a_percent_encoded_data_url",
    }


@pytest.mark.parametrize(
    "example", NATIVE_PART_EXAMPLES, ids=[e["name"] for e in NATIVE_PART_EXAMPLES]
)
def test_native_part_examples_are_what_the_reference_makes(base_data, example):
    part = media_parts.native_part(base_data["media_parts"], json.loads(example["native"]))
    assert part is not None
    assert media_parts.part_text(part) == example["part"]


@pytest.mark.parametrize(
    "part",
    [
        '{"type":"uri","uri":5}',
        '{"type":"file","file_id":null}',
        '{"type":"file","file_id":5}',
        '{"type":"text","content":"hi"}',
    ],
)
def test_native_parts_left_as_they_came(base_data, part):
    assert media_parts.native_part(base_data["media_parts"], json.loads(part)) is None


@pytest.mark.parametrize(
    ("part", "rebuilt"),
    [
        (
            '{"type":"file","file_id":"","url":"https://example.com/a.pdf"}',
            '{"type":"uri","modality":"document","uri":"https://example.com/a.pdf"}',
        ),
        (
            '{"type":"file","file_id":"x","url":"https://example.com/a.pdf"}',
            '{"type":"file","modality":"document","file_id":"x"}',
        ),
        (
            '{"type":"file","file_id":"","modality":"audio"}',
            '{"type":"file","modality":"audio","file_id":""}',
        ),
        (
            '{"type":"uri","modality":"picture","mime_type":"video/mp4","uri":"https://e/a.png"}',
            '{"type":"uri","modality":"video","mime_type":"video/mp4","uri":"https://e/a.png"}',
        ),
        (
            '{"type":"uri","modality":"audio","mime_type":"image/png","uri":"x data:y"}',
            '{"type":"blob","modality":"image","mime_type":"image/png","stripped_reason":"not_captured"}',
        ),
        (
            '{"type":"uri","uri":"data%3Aimage%2Fpng%2C"}',
            '{"type":"blob","modality":"image","mime_type":"image/png","stripped_reason":"redacted_upstream"}',
        ),
        (
            '{"type":"uri","mime_type":"audio/wav","uri":"data%3A%3Bbase64%2CQUFB%20"}',
            '{"type":"blob","modality":"audio","mime_type":"audio/wav","stripped_reason":"not_captured"}',
        ),
        (
            '{"type":"blob","content":"data%3Aimage%2Fpng%3Bbase64%2CQUFB"}',
            '{"type":"blob","modality":"image","mime_type":"image/png","byte_size":3,"stripped_reason":"not_captured"}',
        ),
        (
            '{"type":"uri","uri":"https://e/?u=data%3Aimage%2Fpng%3Bbase64%2CQUFB"}',
            '{"type":"uri","modality":"document","uri":"https://e/?u=data%3Aimage%2Fpng%3Bbase64%2CQUFB"}',
        ),
        (
            '{"type":"blob","stripped_reason":"lost","content":null,"byte_size":-1}',
            '{"type":"blob","modality":"document","stripped_reason":"redacted_upstream"}',
        ),
        (
            '{"type":"blob","stripped_reason":"not_captured","byte_size":8e0}',
            '{"type":"blob","modality":"document","byte_size":8,"stripped_reason":"not_captured"}',
        ),
    ],
)
def test_native_part_rebuilds(base_data, part, rebuilt):
    native = media_parts.native_part(base_data["media_parts"], json.loads(part))
    assert media_parts.part_text(native) == rebuilt


def test_a_native_example_must_be_an_object(data):
    (example,) = [
        e
        for e in data["media_parts"]["part_shapes"]["examples"]
        if e["name"] == "uri_led_by_whitespace_holding_a_data_url"
    ]
    example["native"] = "[1]"
    assert_flags(media_parts.lint(data["media_parts"]), "native must be a JSON object")


def test_an_empty_otlp_any_value_is_null():
    assert media_parts.otlp_value({}) is None


def test_a_duplicate_kvlist_key_keeps_every_member_in_wire_order(base_data):
    raw = base_data["media_parts"]["raw_payloads"]
    any_value = {
        "kvlistValue": {
            "values": [
                {"key": "k", "value": {"bytesValue": "YQ=="}},
                {"key": "k", "value": {"stringValue": "x"}},
            ]
        }
    }
    value = media_parts.otlp_attribute_value(raw, any_value)
    assert list(value.items()) == [("k", "[stripped unknown 1 bytes]"), ("k", "x")]


def _vercel_makes_no_part(part: dict) -> bool:
    """A Vercel file or image part whose payload is neither a string nor v7
    tagged data holding one, or a v7 text tag whose text is not a string."""
    payload = part.get("data" if part.get("type") == "file" else "image")
    if isinstance(payload, str):
        return False
    if isinstance(payload, dict) and payload.get("type") in ("data", "url"):
        return not isinstance(payload.get(payload["type"]), str)
    if isinstance(payload, dict) and payload.get("type") == "text":
        return not isinstance(payload.get("text"), str)
    return True


def _message_parts(media: dict, example: dict) -> list:
    """gen_ai.input.messages for a message example: a text block is a text
    part, a LangChain v1 block the reference's part, and a Vercel part that
    makes no part is dropped. Any other block is outside what the examples
    hold, and fails."""

    def parts(blocks: list) -> list:
        out = []
        for block in blocks:
            if block.get("type") == "text":
                out.append({"type": "text", "content": block["text"]})
            elif example["source"] == "ai.prompt.messages":
                assert block.get("type") in ("file", "image") and _vercel_makes_no_part(block)
            else:
                part = media_parts.langchain_v1_part(media, block)
                assert part is not None, block
                out.append(part)
        return out

    value = json.loads(example["input"])
    if example["source"] == "ai.prompt.messages":
        return [{"role": m["role"], "parts": parts(m["content"])} for m in value]
    (index,) = re.fullmatch(r"gen_ai\.prompt\.([0-9]+)\.content", example["source"]).groups()
    role = example["attributes"][f"gen_ai.prompt.{index}.role"]
    return [{"role": role, "parts": parts(value)}]


MESSAGE_EXAMPLES = Registry.load().media_parts["part_shapes"]["message_examples"]


@pytest.mark.parametrize("example", MESSAGE_EXAMPLES, ids=[e["name"] for e in MESSAGE_EXAMPLES])
def test_message_examples_are_what_the_reference_makes(base_data, example):
    messages = _message_parts(base_data["media_parts"], example)
    text = json.dumps(messages, separators=(",", ":"), ensure_ascii=False)
    assert text == example["output"]


# --- the TypeScript byte objects, through Node ----------------------------------

TYPESCRIPT_BYTE_OBJECTS = [e for e in BYTE_OBJECTS["examples"] if e["language"] == "typescript"]

# The TypeScript SDK's rule as a JSON.stringify replacer: it reads the
# holder's original property (so a Buffer's toJSON never runs) and tells a
# byte object by its tag, which holds across realms, or ArrayBuffer.isView.
BYTE_OBJECT_SCRIPT = r"""
const tag = (v) => Object.prototype.toString.call(v);
const isBytes = (v) =>
  tag(v) === "[object ArrayBuffer]" ||
  tag(v) === "[object SharedArrayBuffer]" ||
  ArrayBuffer.isView(v);
const replacer = function (key, value) {
  const original = this[key];
  return isBytes(original) ? `[stripped unknown ${original.byteLength} bytes]` : value;
};
const examples = JSON.parse(process.argv[1]);
const write = (e) => JSON.stringify((0, eval)("(" + e + ")"), replacer);
console.log(JSON.stringify(examples.map(write)));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_typescript_byte_objects_serialize_to_their_output():
    """N is the byte length (byteLength), never the item count."""
    values = [e["value"] for e in TYPESCRIPT_BYTE_OBJECTS]
    out = subprocess.run(
        [shutil.which("node"), "-e", BYTE_OBJECT_SCRIPT, json.dumps(values)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert json.loads(out) == [e["output"] for e in TYPESCRIPT_BYTE_OBJECTS]


def test_a_lone_surrogate_is_written_escaped(base_data):
    """As the Python SDK writes it, and JSON.stringify: raw UTF-8 cannot carry
    a lone surrogate, so it is its lower-case \\uXXXX escape."""
    raw = base_data["media_parts"]["raw_payloads"]
    value = {"a": "x\ud800y", "\udfff": b"ab", "b": "é"}
    assert media_parts.serialize_value(raw, value) == (
        '{"a":"x\\ud800y","\\udfff":"[stripped unknown 2 bytes]","b":"é"}'
    )


# --- byte objects as attribute values -------------------------------------------

ATTRIBUTE_VALUES = BYTE_OBJECTS["attribute_values"]["examples"]


REFERENCE_ATTRIBUTE_VALUES = [e for e in ATTRIBUTE_VALUES if e["language"] != "typescript"]
TYPESCRIPT_ATTRIBUTE_VALUES = [e for e in ATTRIBUTE_VALUES if e["language"] == "typescript"]


@pytest.mark.parametrize(
    "example", REFERENCE_ATTRIBUTE_VALUES, ids=[e["name"] for e in REFERENCE_ATTRIBUTE_VALUES]
)
def test_attribute_value_examples_are_what_the_reference_makes(base_data, example):
    """A byte object set as an attribute value is the bare marker, no quotes."""
    raw = base_data["media_parts"]["raw_payloads"]
    if example["language"] == "python":
        value = eval(
            example["value"],
            {"__builtins__": {}, "bytearray": bytearray, "bytes": bytes, "memoryview": memoryview},
        )  # noqa: S307
        assert media_parts.attribute_value(raw, value) == example["output"]
    else:
        any_value = json.loads(example["value"])
        assert media_parts.otlp_attribute_value(raw, any_value) == example["output"]


# The TypeScript SDK's attribute value rule: a byte object at any depth is the
# bare marker, and an array that cannot stay homogeneous is its JSON, written
# with the byte object replacer. OpenTelemetry JS holds no mapping and no
# nested array, nor an array that is not homogeneous, so a walked value that
# is one is the JSON of the value.
ATTRIBUTE_VALUE_SCRIPT = (
    BYTE_OBJECT_SCRIPT.split("const examples")[0]
    + r"""
const marker = (v) => `[stripped unknown ${v.byteLength} bytes]`;
const attributeValue = (v) => {
  if (isBytes(v)) return marker(v);
  if (Array.isArray(v)) {
    const out = v.map(attributeValue);
    const mixed = v.some(isBytes) && !out.every((e) => typeof e === "string");
    return mixed ? JSON.stringify(v, replacer) : out;
  }
  if (v !== null && typeof v === "object") {
    return Object.fromEntries(Object.entries(v).map(([k, e]) => [k, attributeValue(e)]));
  }
  return v;
};
const holdsBytes = (v) =>
  isBytes(v) || (v !== null && typeof v === "object" && Object.values(v).some(holdsBytes));
const primitive = (v) => v === null || typeof v !== "object";
// As @opentelemetry/core's isHomogeneousAttributeValueArray: null aside, all
// strings, all numbers or all booleans.
const homogeneous = (a) => {
  const types = new Set(a.filter((e) => e != null).map((e) => typeof e));
  return types.size <= 1 && [...types].every((t) => ["string", "number", "boolean"].includes(t));
};
const setValue = (v) => {
  const out = attributeValue(v);
  const held = Array.isArray(out) ? homogeneous(out) : primitive(out);
  return held || !holdsBytes(v) ? out : JSON.stringify(v, replacer);
};
const examples = JSON.parse(process.argv[1]);
console.log(JSON.stringify(examples.map((e) => setValue((0, eval)("(" + e + ")")))));
"""
)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_typescript_attribute_values_are_their_output():
    values = [e["value"] for e in TYPESCRIPT_ATTRIBUTE_VALUES]
    out = subprocess.run(
        [shutil.which("node"), "-e", ATTRIBUTE_VALUE_SCRIPT, json.dumps(values)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert json.loads(out) == [e["output"] for e in TYPESCRIPT_ATTRIBUTE_VALUES]


def test_attribute_values_cover_every_language():
    assert {e["language"] for e in ATTRIBUTE_VALUES} == set(media_parts.ATTRIBUTE_VALUE_LANGUAGES)


@pytest.mark.parametrize(
    ("value", "output"),
    [
        ([True, b"ab"], '[true,"[stripped unknown 2 bytes]"]'),
        ([None, b"ab"], '[null,"[stripped unknown 2 bytes]"]'),
        ([b"ab", [b"c"]], '["[stripped unknown 2 bytes]",["[stripped unknown 1 bytes]"]]'),
        ([b"ab", {"k": "v"}], '["[stripped unknown 2 bytes]",{"k":"v"}]'),
        ([1, [b"c"]], [1, ["[stripped unknown 1 bytes]"]]),
        ((b"ab", "x"), ["[stripped unknown 2 bytes]", "x"]),
        ([[1, b"c"]], ['[1,"[stripped unknown 1 bytes]"]']),
        ([1, [1, b"c"]], [1, '[1,"[stripped unknown 1 bytes]"]']),
        ({"k": [1, b"c"]}, {"k": '[1,"[stripped unknown 1 bytes]"]'}),
        ([1, "x"], [1, "x"]),
    ],
)
def test_only_an_array_holding_a_byte_object_and_a_non_string_is_json(base_data, value, output):
    raw = base_data["media_parts"]["raw_payloads"]
    assert media_parts.attribute_value(raw, value) == output


@pytest.mark.parametrize(
    ("text", "size"),
    [("QUJD", 3), ("QUI=", 2), ("QUI", 2), ("_-__", 3), ("/+//", 3), ("iVBORw0KGgo", 8), ("", 0)],
)
def test_an_otlp_bytes_value_decodes_either_alphabet_padded_or_not(text, size):
    assert len(media_parts.otlp_bytes(text)) == size


@pytest.mark.parametrize("text", ["Q", "+-AA", "QU!D"])
def test_an_otlp_bytes_value_that_is_not_base64_raises(text):
    with pytest.raises(ValueError):
        media_parts.otlp_bytes(text)


def test_an_attribute_value_with_no_marker_fails_lint(data):
    section = data["media_parts"]["raw_payloads"]["byte_objects"]["attribute_values"]
    section["examples"][0]["output"] = {"k": "plain", "n": [1]}
    assert_flags(media_parts.lint(data["media_parts"]), "must be a bare marker")


def test_a_quoted_attribute_value_marker_fails_lint(data):
    section = data["media_parts"]["raw_payloads"]["byte_objects"]["attribute_values"]
    section["examples"][0]["output"] = '"[stripped unknown 4 bytes]"'
    assert_flags(media_parts.lint(data["media_parts"]), "must be a bare marker")


def test_attribute_values_are_required(data):
    del data["media_parts"]["raw_payloads"]["byte_objects"]["attribute_values"]
    assert_flags(media_parts.lint(data["media_parts"]), "needs attribute_values with a rule")


@pytest.mark.parametrize(
    ("block", "modality"),
    [
        ('{"type":"file","file_id":"x","modality":"image"}', "image"),
        ('{"type":"file","file_id":"","modality":"audio"}', "audio"),
        ('{"type":"file","file_id":"x","modality":"picture","mime_type":"video/mp4"}', "video"),
        ('{"type":"image","file_id":"x","modality":"audio"}', "image"),
        ('{"type":"file","url":"https://example.com/a.wav","modality":"image"}', "audio"),
    ],
)
def test_only_a_native_file_part_reads_its_modality_member(base_data, block, modality):
    part = media_parts.langchain_v1_part(base_data["media_parts"], json.loads(block))
    assert part["modality"] == modality
