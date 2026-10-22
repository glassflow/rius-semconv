"""tools/check_controls.py: the two SDKs' controls agree up to reviewed differences."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tools.check_controls import ALLOWLIST, PYTHON, ROOT, TYPESCRIPT, check, newest_recording


@pytest.fixture
def fixtures(tmp_path: Path) -> Path:
    """A copy of both control families and the allowlist, free to break."""
    for family in (PYTHON, TYPESCRIPT):
        shutil.copytree(
            ROOT / "fixtures" / family,
            tmp_path / family,
            ignore=shutil.ignore_patterns("node_modules"),
        )
    shutil.copy(ROOT / "fixtures" / ALLOWLIST, tmp_path / ALLOWLIST)
    return tmp_path


def edit(path: Path, change) -> None:
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data))


def attribute(span: dict, key: str) -> dict:
    return next(a for a in span["attributes"] if a["key"] == key)


def test_committed_controls_agree():
    assert check(ROOT / "fixtures") == []


def test_compares_the_newest_recording_of_each_family(fixtures: Path):
    assert newest_recording(fixtures, PYTHON).name != f"{PYTHON}-1.0.0.json"
    assert newest_recording(fixtures, TYPESCRIPT).name != f"{TYPESCRIPT}-1.0.0.json"


def test_an_unlisted_attribute_difference_fails(fixtures: Path):
    def change(data):
        span = data["recordings"][0]["spans"][0]["span"]
        attribute(span, "gen_ai.request.model")["value"] = {"stringValue": "other"}

    edit(newest_recording(fixtures, TYPESCRIPT), change)
    problems = check(fixtures)
    assert len(problems) == 1
    assert "attribute gen_ai.request.model" in problems[0]


def test_an_attribute_only_one_sdk_writes_fails(fixtures: Path):
    def change(data):
        span = data["recordings"][0]["spans"][0]["span"]
        span["attributes"] = [a for a in span["attributes"] if a["key"] != "gen_ai.response.id"]

    edit(newest_recording(fixtures, PYTHON), change)
    problems = check(fixtures)
    assert len(problems) == 1
    assert "gen_ai.response.id" in problems[0] and "python null" in problems[0]


def test_a_listed_key_with_other_values_fails(fixtures: Path):
    def change(data):
        scenario = next(s for s in data["recordings"] if s["scenario"] == "generation_error")
        attribute(scenario["spans"][0]["span"], "error.type")["value"] = {"stringValue": "X"}

    edit(newest_recording(fixtures, TYPESCRIPT), change)
    problems = check(fixtures)
    assert any("not listed" in p and "error.type" in p for p in problems)
    assert any("matches no difference" in p and "error.type" in p for p in problems)


def test_a_stale_entry_fails(fixtures: Path):
    def change(data):
        data["differences"].append(
            {"where": "attribute", "key": "input.value", "reason": "no longer differs"}
        )

    edit(fixtures / ALLOWLIST, change)
    problems = check(fixtures)
    assert len(problems) == 1
    assert "matches no difference" in problems[0] and "input.value" in problems[0]


def test_an_entry_without_a_reason_fails(fixtures: Path):
    def change(data):
        data["differences"][0]["reason"] = " "

    edit(fixtures / ALLOWLIST, change)
    assert any("has no reason" in p for p in check(fixtures))


def test_span_structure_is_compared(fixtures: Path):
    def change(data):
        span = data["recordings"][0]["spans"][0]["span"]
        span["name"] = "renamed"
        span["status"] = {"code": "STATUS_CODE_ERROR"}

    edit(newest_recording(fixtures, TYPESCRIPT), change)
    problems = check(fixtures)
    assert any("span name" in p for p in problems)
    assert any("span status" in p for p in problems)


def test_event_attributes_are_compared(fixtures: Path):
    def change(data):
        scenario = next(s for s in data["recordings"] if s["scenario"] == "generation_error")
        event = scenario["spans"][0]["span"]["events"][0]
        attribute(event, "exception.message")["value"] = {"stringValue": "other"}

    edit(newest_recording(fixtures, TYPESCRIPT), change)
    problems = check(fixtures)
    assert len(problems) == 1
    assert "event exception exception.message" in problems[0]


def test_a_missing_scenario_fails(fixtures: Path):
    def change(data):
        data["recordings"] = [s for s in data["recordings"] if s["scenario"] != "chain"]

    edit(newest_recording(fixtures, TYPESCRIPT), change)
    assert any("chain" in p and "scenario recorded" in p for p in check(fixtures))


def test_an_entry_without_values_does_not_allow_a_missing_attribute(fixtures: Path):
    """telemetry.sdk.version may differ between the SDKs, but it must be
    there: an entry without values never covers a key one side lost."""

    def change(data):
        resource = data["recordings"][0]["resource"]
        resource["attributes"] = [
            a for a in resource["attributes"] if a["key"] != "telemetry.sdk.version"
        ]

    edit(newest_recording(fixtures, TYPESCRIPT), change)
    problems = check(fixtures)
    assert len(problems) == 1
    assert "not listed" in problems[0] and "telemetry.sdk.version" in problems[0]
    assert "typescript null" in problems[0]


def test_an_entry_without_values_does_not_allow_a_missing_scope_version(fixtures: Path):
    def change(data):
        for scenario in data["recordings"]:
            for entry in scenario["spans"]:
                entry["scope"].pop("version", None)

    edit(newest_recording(fixtures, PYTHON), change)
    assert any("scope version" in p and "python null" in p for p in check(fixtures))
