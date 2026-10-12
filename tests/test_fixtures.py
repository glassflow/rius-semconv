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
