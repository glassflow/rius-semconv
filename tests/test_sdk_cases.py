"""sdk_cases/: every file the SDKs vendor is well formed.

The SDKs run the cases; this only checks the shape both of their tests rely
on, so a malformed case fails here rather than as a confusing SDK test failure.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "sdk_cases"
FILES = ("values", "attributes", "messages", "masking", "env", "resource", "anthropic_error_type")
NAME = re.compile(r"[a-z0-9]+(_[a-z0-9]+)*")
NUMBERS = {"NaN", "Infinity", "-Infinity"}
ENV_FIELDS = {
    "endpoint",
    "service_name",
    "agent_name",
    "service_version",
    "disabled",
    "capture_content",
    "heartbeat",
    "partial_spans",
    "bridge_foreign_provider",
    "sample_rate",
    "heartbeat_interval",
    "partial_spans_delay",
}
#: Each file's fields: those every case must have, and those it may have.
FIELDS = {
    "values": ({"name", "value", "expected"}, set()),
    "attributes": ({"name", "value", "expected"}, set()),
    "messages": ({"name", "direction", "value", "messages", "context_sizes"}, set()),
    "masking": ({"name", "capture_content", "mask", "span", "expected"}, set()),
    "env": ({"name", "env", "expected"}, {"warns"}),
    "resource": ({"name", "otel_resource_attributes", "options", "expected", "absent"}, set()),
    "anthropic_error_type": ({"name", "scope", "attributes", "expected"}, set()),
}


def load(name: str) -> dict[str, Any]:
    return json.loads((CASES / f"{name}.json").read_text())


def tags(value: Any) -> list[str]:
    """Problems with the tagged forms in a value."""
    problems: list[str] = []
    if isinstance(value, dict):
        tagged = [key for key in value if key.startswith("$")]
        if tagged and len(value) != 1:
            problems.append(f"a tag must be the mapping's only key: {value}")
        elif "$bytes" in value:
            n = value["$bytes"]
            if not isinstance(n, int) or isinstance(n, bool) or n < 0:
                problems.append(f"$bytes takes a size: {value}")
        elif "$number" in value:
            if value["$number"] not in NUMBERS:
                problems.append(f"$number takes one of {sorted(NUMBERS)}: {value}")
        elif tagged:
            problems.append(f"unknown tag {tagged[0]}")
        for item in value.values():
            problems += tags(item)
    elif isinstance(value, list):
        for item in value:
            problems += tags(item)
    return problems


def test_the_directory_holds_exactly_the_documented_files():
    assert sorted(p.stem for p in CASES.glob("*.json")) == sorted(FILES)
    readme = (CASES / "README.md").read_text()
    for name in FILES:
        assert f"`{name}.json`" in readme


@pytest.mark.parametrize("name", FILES)
def test_cases_are_well_formed(name: str):
    data = load(name)
    assert set(data) == {"about", "cases"}
    assert data["about"].strip()
    assert data["cases"]
    required, optional = FIELDS[name]
    names = [case["name"] for case in data["cases"]]
    assert len(names) == len(set(names)), "case names must be unique"
    for case in data["cases"]:
        assert NAME.fullmatch(case["name"]), case["name"]
        assert required <= set(case) <= required | optional, case["name"]
        assert tags(case) == [], case["name"]


def test_messages_name_a_direction():
    for case in load("messages")["cases"]:
        assert case["direction"] in {"input", "output"}, case["name"]


def test_masks_are_ones_the_sdk_tests_build():
    for case in load("masking")["cases"]:
        mask = case["mask"]
        assert mask is None or len(mask) == 1, case["name"]
        if mask is not None:
            (kind,) = mask
            assert kind in {"returns", "format", "throws"}, case["name"]
            assert kind != "throws" or mask["throws"] is True, case["name"]
        assert set(case["expected"]) == {"attributes", "events", "status"}, case["name"]


def test_env_cases_name_known_fields_and_only_rius_variables():
    for case in load("env")["cases"]:
        assert set(case["expected"]) <= ENV_FIELDS, case["name"]
        assert all(name.startswith("RIUS_") for name in case["env"]), case["name"]
        assert all(isinstance(raw, str) for raw in case["env"].values()), case["name"]


def test_resource_options_are_names():
    for case in load("resource")["cases"]:
        assert set(case["options"]) <= {"service_name", "agent_name"}, case["name"]


def test_anthropic_error_type_cases_hold_an_error_type():
    for case in load("anthropic_error_type")["cases"]:
        attributes = case["attributes"]
        assert isinstance(attributes["error.type"], str), case["name"]
        assert set(attributes) <= {"error.type", "http.response.status_code"}, case["name"]
        assert isinstance(case["expected"], str), case["name"]
