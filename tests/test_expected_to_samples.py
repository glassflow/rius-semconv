"""tools/expected_to_samples.py and tools/live_check_findings.py.

Weaver itself runs in CI (the weaver job); these pin the conversion and the
allowlist rules without it.
"""

from __future__ import annotations

import json

import pytest

from tools import expected_to_samples as conv
from tools import live_check_findings


def expected(span_attributes, resource_attributes=(), events=()):
    span = {
        "traceId": "1",
        "spanId": "1",
        "name": "chat gpt-4o-mini",
        "kind": "SPAN_KIND_CLIENT",
        "attributes": list(span_attributes),
        "events": list(events),
    }
    return {
        "recordings": [
            {
                "scenario": "chat",
                "resource": {"attributes": list(resource_attributes)},
                "spans": [{"scope": {"name": "rius"}, "span": span}],
            }
        ]
    }


def attr(key, **value):
    return {"key": key, "value": value}


def run(tmp_path, doc, passthrough=(), defined=(), sidecar=(), check_unused=False):
    f = tmp_path / "x.expected.json"
    f.write_text(json.dumps(doc))
    entries = [{"prefix": p, "reason": "r"} for p in passthrough]
    return conv.convert([f], entries, set(defined), list(sidecar), check_unused)


def span_keys(samples):
    return [a["name"] for a in samples[1]["span"]["attributes"]]


def test_otlp_values_keep_their_types():
    assert conv.value({"intValue": "12"}) == (12, "int")
    assert conv.value({"doubleValue": 0.5}) == (0.5, "double")
    assert conv.value({"boolValue": False}) == (False, "boolean")
    assert conv.value({"stringValue": "a"}) == ("a", "string")
    array = {"arrayValue": {"values": [{"stringValue": "a"}, {"stringValue": "b"}]}}
    assert conv.value(array) == (["a", "b"], "string[]")


def test_an_empty_array_names_no_type():
    assert conv.value({"arrayValue": {}}) == ([], None)


def test_an_unsupported_value_fails_loudly():
    with pytest.raises(ValueError):
        conv.value({"kvlistValue": {}})


def test_a_recording_becomes_a_resource_and_its_spans(tmp_path):
    event = {"name": "exception", "attributes": [attr("exception.type", stringValue="E")]}
    doc = expected(
        [attr("gen_ai.usage.input_tokens", intValue="3")],
        [attr("service.name", stringValue="svc")],
        [event],
    )
    samples, errors = run(tmp_path, doc)
    assert errors == []
    assert samples[0] == {
        "resource": {"attributes": [{"name": "service.name", "value": "svc", "type": "string"}]}
    }
    span = samples[1]["span"]
    assert (span["name"], span["kind"]) == ("chat gpt-4o-mini", "client")
    assert span["attributes"] == [{"name": "gen_ai.usage.input_tokens", "value": 3, "type": "int"}]
    assert span["span_events"][0]["attributes"][0]["name"] == "exception.type"


def test_an_allowlisted_key_is_left_out(tmp_path):
    doc = expected([attr("logfire.msg", stringValue="m"), attr("rius.x", stringValue="v")])
    samples, _ = run(tmp_path, doc, passthrough=["logfire."])
    assert span_keys(samples) == ["rius.x"]


def test_an_allowlist_entry_never_hides_a_key_the_model_defines(tmp_path):
    doc = expected(
        [attr("ai.usage.promptTokens", intValue="1"), attr("ai.operationId", stringValue="o")]
    )
    samples, _ = run(tmp_path, doc, passthrough=["ai."], defined={"ai.usage.promptTokens"})
    assert span_keys(samples) == ["ai.usage.promptTokens"]


def test_a_template_counts_as_defined(tmp_path):
    doc = expected([attr("pydantic_ai.cache.hit_ratio", doubleValue=0.5)])
    samples, _ = run(tmp_path, doc, passthrough=["pydantic_ai."], defined={"pydantic_ai.cache."})
    assert span_keys(samples) == ["pydantic_ai.cache.hit_ratio"]


def test_sidecar_usage_inputs_are_left_out(tmp_path):
    doc = expected(
        [
            attr("gen_ai.usage.details.audio_tokens", intValue="1"),
            attr("gen_ai.aggregated_usage.input_tokens", intValue="1"),
            attr("gen_ai.usage.input_tokens", intValue="1"),
        ]
    )
    sidecar = ["gen_ai.usage.details.audio_tokens", "gen_ai.aggregated_usage."]
    samples, _ = run(tmp_path, doc, sidecar=sidecar)
    assert span_keys(samples) == ["gen_ai.usage.input_tokens"]


def test_an_unused_allowlist_entry_is_stale(tmp_path):
    doc = expected([attr("logfire.msg", stringValue="m")])
    _, errors = run(tmp_path, doc, passthrough=["logfire.", "llm."], check_unused=True)
    assert errors == ["passthrough.yaml: 'llm.' matches no key left out; drop it"]


def test_an_entry_without_a_reason_is_rejected(tmp_path):
    f = tmp_path / "passthrough.yaml"
    f.write_text("passthrough:\n  - prefix: llm.\n    reason: ' '\n")
    with pytest.raises(ValueError, match="reason"):
        conv.load_passthrough(f)


def test_the_real_fixtures_convert_and_every_entry_is_used(tmp_path):
    out = tmp_path / "samples.json"
    assert conv.main(["--out", str(out)]) == 0
    samples = json.loads(out.read_text())
    recordings = [r for f in conv.expected_files() for r in json.loads(f.read_text())["recordings"]]
    assert len(conv.expected_files()) >= 18
    assert sum("resource" in s for s in samples) == len(recordings)
    assert sum("span" in s for s in samples) == sum(len(r["spans"]) for r in recordings)


def test_the_real_model_defines_its_templates_as_prefixes():
    keys = conv.model_keys()
    assert {"pydantic_ai.cache.", "rius.aggregated_usage.", "gen_ai.request.model"} <= keys
    assert not [k for k in keys if "*" in k]


def test_findings_list_each_violation_and_count_every_level():
    finding = {
        "id": "missing_attribute",
        "level": "violation",
        "message": "Attribute 'rius.x' does not exist in the registry.",
        "signal_name": "chat",
    }
    info = {"id": "undefined_enum_variant", "level": "information", "message": "m"}
    attributes = [{"live_check_result": {"all_advice": [finding, info]}}] * 2
    report = {"samples": [{"span": {"attributes": attributes}}]}
    lines = live_check_findings.summarize(report)
    assert (
        lines[0]
        == "   2x missing_attribute: Attribute 'rius.x' does not exist in the registry. (in chat)"
    )
    assert lines[1] == "2 violation(s)"
    assert any("undefined_enum_variant" in line for line in lines[2:])
