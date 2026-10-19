"""tools/check_fixtures.py: each check fires on the problem it is for."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tools.check_fixtures import ROOT, check, check_family, families

FAMILY = "openinference-openai"
RECORDING = "openinference-openai-0.1.65.json"
EXPECTED = "openinference-openai-0.1.65.expected.json"


@pytest.fixture
def family(tmp_path: Path) -> Path:
    """A copy of a real family, free to break."""
    target = tmp_path / FAMILY
    shutil.copytree(ROOT / "fixtures" / FAMILY, target)
    return target


def edit(path: Path, change) -> None:
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data))


def test_committed_fixtures_are_clean():
    assert check(ROOT / "fixtures") == []


def test_families_skip_underscored_helpers():
    names = [p.name for p in families(ROOT / "fixtures")]
    assert FAMILY in names
    assert not any(name.startswith("_") for name in names)


def test_a_copied_family_is_clean(family):
    assert check_family(family) == []


def test_missing_manifest(family):
    (family / "manifest.json").unlink()
    assert check_family(family) == [f"{FAMILY}: no manifest.json"]


def test_missing_record_script(family):
    (family / "record.py").unlink()
    assert any("no record script" in e for e in check_family(family))


def test_unlisted_recording(family):
    shutil.copy(family / RECORDING, family / "openinference-openai-9.9.9.json")
    assert any("9.9.9.json is not listed" in e for e in check_family(family))


def test_listed_recording_missing(family):
    (family / RECORDING).unlink()
    assert any("listed in manifest.json but missing" in e for e in check_family(family))


def test_undescribed_scenario(family):
    edit(
        family / "manifest.json",
        lambda m: m["recordings"][RECORDING]["scenarios"].pop("embeddings"),
    )
    assert any("embeddings is not described" in e for e in check_family(family))


def test_empty_scenario_needs_an_allowance(family):
    def empty(data):
        data["recordings"][0]["spans"] = []

    edit(family / RECORDING, empty)
    edit(family / EXPECTED, empty)
    assert any("recorded no spans" in e for e in check_family(family))

    edit(
        family / "manifest.json",
        lambda m: m["recordings"][RECORDING].__setitem__("empty_scenarios", ["chat"]),
    )
    assert check_family(family) == []


def test_missing_expected(family):
    (family / EXPECTED).unlink()
    assert any(f"{EXPECTED} is missing" in e for e in check_family(family))


def test_expected_needs_a_normalizer_commit(family):
    edit(family / EXPECTED, lambda d: d["normalizer"].pop("commit"))
    assert any("normalizer has no commit" in e for e in check_family(family))


def test_expected_must_keep_ids_and_times(family):
    def shift(data):
        span = data["recordings"][0]["spans"][0]["span"]
        span["endTimeUnixNano"] = str(int(span["endTimeUnixNano"]) + 1)

    edit(family / EXPECTED, shift)
    assert any("changed its trace, parent or times" in e for e in check_family(family))


def test_expected_must_cover_the_same_scenarios(family):
    edit(family / EXPECTED, lambda d: d["recordings"].pop())
    assert any("scenarios differ from the recording" in e for e in check_family(family))


def test_expected_source_is_named(family):
    edit(
        family / "manifest.json",
        lambda m: m["recordings"][RECORDING]["expected"].__setitem__("source", "guess"),
    )
    assert any("expected.source must be one of" in e for e in check_family(family))


def test_a_traceback_with_local_paths_is_a_leak(family):
    def leak(data):
        status = data["recordings"][0]["spans"][0]["span"].setdefault("status", {})
        status["message"] = (
            'Error("boom")Traceback (most recent call last):\n'
            '  File "/Users/someone/venv/lib/python3.13/site-packages/x.py", line 1'
        )

    edit(family / RECORDING, leak)
    problems = [e for e in check_family(family) if "from the recording machine" in e]
    assert len(problems) == 3
    assert all(e.startswith(f"{FAMILY}/{RECORDING}: ") for e in problems)


def test_a_node_stack_frame_is_a_leak(family):
    def leak(data):
        status = data["recordings"][0]["spans"][0]["span"].setdefault("status", {})
        status["message"] = "Error: boom\n    at f (file:///srv/app.js:1:1)"

    edit(family / RECORDING, leak)
    assert any("'\\\\n    at '" in e for e in check_family(family))


SINK_FAMILY = "openllmetry"
SINK_RECORDING = "openllmetry-0.62.3.json"
SINK_ROWS = "openllmetry-0.62.3.expected-row.json"


@pytest.fixture
def sink_family(tmp_path: Path) -> Path:
    """A copy of a real sink-only family, whose expected result is rows."""
    target = tmp_path / SINK_FAMILY
    shutil.copytree(ROOT / "fixtures" / SINK_FAMILY, target)
    return target


def test_a_sink_family_is_clean(sink_family):
    assert check_family(sink_family) == []


def test_row_files_are_not_recordings(sink_family):
    assert not any(e.endswith("is not listed in manifest.json") for e in check_family(sink_family))


def test_a_sink_expected_result_must_be_rows(sink_family):
    edit(
        sink_family / "manifest.json",
        lambda m: m["recordings"][SINK_RECORDING]["expected"].__setitem__(
            "file", "openllmetry-0.62.3.expected.json"
        ),
    )
    assert any("must end in .expected-row.json" in e for e in check_family(sink_family))


def test_rows_need_a_commit(sink_family):
    edit(sink_family / SINK_ROWS, lambda d: d["normalizer"].pop("commit"))
    assert any("normalizer has no commit" in e for e in check_family(sink_family))


def test_rows_must_cover_the_recorded_spans(sink_family):
    edit(sink_family / SINK_ROWS, lambda d: d["recordings"][0]["rows"].pop())
    assert any("rows do not match the recorded span ids" in e for e in check_family(sink_family))


CONTROL_FAMILY = "rius-python"
CONTROL_EXPECTED = "rius-python-1.0.0.expected.json"


@pytest.fixture
def control_family(tmp_path: Path) -> Path:
    """A copy of a real control family: spans an SDK already normalized."""
    target = tmp_path / CONTROL_FAMILY
    shutil.copytree(ROOT / "fixtures" / CONTROL_FAMILY, target)
    return target


def test_a_control_family_is_clean(control_family):
    assert check_family(control_family) == []


def test_a_control_must_come_out_unchanged(control_family):
    def rename_model(data):
        attributes = data["recordings"][0]["spans"][0]["span"]["attributes"]
        for attribute in attributes:
            if attribute["key"] == "gen_ai.request.model":
                attribute["value"] = {"stringValue": "renamed"}

    edit(control_family / CONTROL_EXPECTED, rename_model)
    assert any("must come out unchanged" in e for e in check_family(control_family))


def _first_span_attr(path: Path, key: str, value: str) -> None:
    """Set a string attribute on the first expected span."""

    def change(data):
        attributes = data["recordings"][0]["spans"][0]["span"]["attributes"]
        attributes[:] = [a for a in attributes if a["key"] != key]
        attributes.append({"key": key, "value": {"stringValue": value}})

    edit(path, change)


def _media_errors(family: Path) -> list[str]:
    return [e for e in check_family(family) if "holds base64 media" in e]


def _messages(part: dict) -> str:
    return json.dumps([{"role": "user", "parts": [part]}])


def test_blob_content_inside_messages_json_is_caught(family):
    blob = {"type": "blob", "modality": "image", "content": "iVBORw0K"}
    _first_span_attr(family / EXPECTED, "gen_ai.input.messages", _messages(blob))
    errors = _media_errors(family)
    assert len(errors) == 1
    assert "attribute gen_ai.input.messages holds base64 media" in errors[0]


def test_empty_blob_content_is_still_content(family):
    blob = {"type": "blob", "modality": "image", "content": ""}
    _first_span_attr(family / EXPECTED, "gen_ai.input.messages", _messages(blob))
    assert _media_errors(family)


def test_data_url_is_caught(family):
    part = {"type": "text", "content": "see data:image/png;base64,AAAA"}
    _first_span_attr(family / EXPECTED, "gen_ai.input.messages", _messages(part))
    assert _media_errors(family)


def test_long_base64_run_is_caught(family):
    _first_span_attr(family / EXPECTED, "some.attribute", "A" * 4096)
    assert _media_errors(family)


def test_long_non_media_strings_are_not_base64(family):
    args = json.dumps({"query": "word " * 400})
    values = [
        "a" * 32 + "0123456789abcdef" * 2,
        "123e4567-e89b-12d3-a456-426614174000",
        args[:2000].ljust(2000, " "),
        "lorem ipsum " * 417,
    ]
    for i, value in enumerate(values):
        _first_span_attr(family / EXPECTED, f"some.attribute.{i}", value)
    assert _media_errors(family) == []


def _buffer_prompt(data: list[int]) -> str:
    part = {
        "type": "file",
        "data": {"type": "Buffer", "data": data},
        "mediaType": "image/png",
    }
    return json.dumps({"messages": [{"role": "user", "content": [part]}]})


def test_buffer_byte_array_is_caught(family):
    _first_span_attr(family / EXPECTED, "ai.prompt", _buffer_prompt([137, 80, 78, 71]))
    errors = _media_errors(family)
    assert len(errors) == 1
    assert "attribute ai.prompt holds base64 media" in errors[0]


def test_empty_buffer_is_not_media(family):
    _first_span_attr(family / EXPECTED, "ai.prompt", _buffer_prompt([]))
    assert _media_errors(family) == []


def test_base64_in_sink_rows_is_caught(sink_family):
    blob = {"type": "blob", "modality": "image", "content": "iVBORw0K"}

    def change(data):
        data["recordings"][0]["rows"][0]["InputMessages"] = _messages(blob)

    edit(sink_family / SINK_ROWS, change)
    errors = _media_errors(sink_family)
    assert len(errors) == 1
    assert "attribute InputMessages holds base64 media" in errors[0]


def test_recordings_may_hold_base64(family):
    blob = {"type": "blob", "modality": "image", "content": "iVBORw0K"}
    _first_span_attr(family / RECORDING, "gen_ai.input.messages", _messages(blob))
    assert not _media_errors(family)


def test_blob_in_an_event_attribute_is_caught(family):
    blob = {"type": "blob", "modality": "image", "content": "x"}

    def change(data):
        span = data["recordings"][0]["spans"][0]["span"]
        span["events"] = [
            {
                "timeUnixNano": "1",
                "name": "gen_ai.client.inference.operation.details",
                "attributes": [{"key": "payload", "value": {"stringValue": _messages(blob)}}],
            }
        ]

    edit(family / EXPECTED, change)
    errors = _media_errors(family)
    assert len(errors) == 1
    assert "event gen_ai.client.inference.operation.details attribute payload" in errors[0]


def test_anthropic_base64_source_in_input_value_is_caught(family):
    """Rule (e): `data` under a `source` with type base64, inside a JSON string."""
    image = {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": "iVBORw0KGgo="},
    }
    request = {"messages": [{"role": "user", "content": [image]}]}
    _first_span_attr(family / EXPECTED, "input.value", json.dumps(request))
    errors = _media_errors(family)
    assert len(errors) == 1
    assert "attribute input.value holds base64 media" in errors[0]


def test_openai_input_audio_is_caught(family):
    """Rule (e): `data` under the parent key input_audio."""
    part = {"type": "input_audio", "input_audio": {"data": "UklGRg==", "format": "wav"}}
    request = {"messages": [{"role": "user", "content": [part]}]}
    _first_span_attr(family / EXPECTED, "input.value", json.dumps(request))
    assert _media_errors(family)


def test_suite_payload_prefix_in_plain_text_is_caught(family):
    """Rule (f): the start of a payload fixtures/_media.py exports, anywhere."""
    from fixtures import _media

    prefix = _media.b64(_media.PNG_1X1)[:32]
    _first_span_attr(family / EXPECTED, "output.value", f"the image was {prefix} and so on")
    errors = _media_errors(family)
    assert len(errors) == 1
    assert "attribute output.value holds base64 media" in errors[0]


def test_data_key_without_media_context_is_not_media(family):
    _first_span_attr(family / EXPECTED, "input.value", json.dumps({"data": "hello"}))
    _first_span_attr(family / EXPECTED, "output.value", json.dumps({"result": {"data": "x"}}))
    assert _media_errors(family) == []


def test_a_blob_part_whose_content_is_the_replacement_is_media_only_in_a_message_key():
    from tools.check_fixtures import _holds_media

    replaced = {"type": "blob", "content": "[stripped image/png 8 bytes]"}
    for key in ("pydantic_ai.all_messages", "input.value", "InputValue", "some.attribute", None):
        assert not _holds_media(replaced, key=key), key
        assert _holds_media({"type": "blob", "content": "iVBORw0KGgo="}, key=key), key
        assert _holds_media({"type": "blob", "content": "[stripped image/png lots bytes]"}, key=key)
    for key in (
        "gen_ai.input.messages",
        "gen_ai.output.messages",
        "gen_ai.system_instructions",
        "llm.input_messages.0.message.contents",
        "InputMessages",
        "OutputMessages",
    ):
        assert _holds_media(replaced, key=key), key


REPLACED_BLOB = {"type": "blob", "modality": "image", "content": "[stripped image/png 3 bytes]"}


def test_a_replaced_blob_in_a_message_key_is_caught(family):
    _first_span_attr(family / EXPECTED, "gen_ai.input.messages", _messages(REPLACED_BLOB))
    errors = _media_errors(family)
    assert len(errors) == 1
    assert "attribute gen_ai.input.messages holds base64 media" in errors[0]


def test_a_replaced_blob_in_a_raw_payload_is_not_media(family):
    _first_span_attr(family / EXPECTED, "pydantic_ai.all_messages", _messages(REPLACED_BLOB))
    assert _media_errors(family) == []


def test_a_replaced_blob_in_a_tool_result_is_not_media(family):
    part = {"type": "blob", "mime_type": "image/png", "content": "[stripped image/png 8 bytes]"}
    _first_span_attr(family / EXPECTED, "gen_ai.tool.call.result", json.dumps([part]))
    assert _media_errors(family) == []


def test_a_replaced_blob_in_a_sink_column(sink_family):
    def change(data):
        row = data["recordings"][0]["rows"][0]
        row["InputValue"] = _messages(REPLACED_BLOB)
        row["SpanAttributes"]["pydantic_ai.all_messages"] = _messages(REPLACED_BLOB)

    edit(sink_family / SINK_ROWS, change)
    assert _media_errors(sink_family) == []

    def to_messages(data):
        data["recordings"][0]["rows"][0]["OutputMessages"] = _messages(REPLACED_BLOB)

    edit(sink_family / SINK_ROWS, to_messages)
    errors = _media_errors(sink_family)
    assert len(errors) == 1
    assert "attribute OutputMessages holds base64 media" in errors[0]
