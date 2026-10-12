"""fixtures/_replay.py is the exact inverse of fixtures/_recording.py.

Every consumer decodes recordings to feed its normalizer, and the Python SDK's
conformance test decodes them with this module. If decoding lost anything (an
attribute type, an event, a parent link, a time), a normalizer would be tested
against a span the instrumentor never produced.
"""

from __future__ import annotations

import json
import sys

import pytest

from tools.check_fixtures import ROOT, families, recording_files

sys.path.insert(0, str(ROOT / "fixtures"))

from _recording import scenario_json  # noqa: E402
from _replay import scenario_spans  # noqa: E402

RECORDINGS = [path for family in families(ROOT / "fixtures") for path in recording_files(family)]
# Sink-only families' expected results are rows, not spans: they have no
# OTLP/JSON expected file to round-trip.
SPAN_EXPECTED = [
    path for path in RECORDINGS if path.with_name(path.stem + ".expected.json").exists()
]


@pytest.mark.parametrize("path", RECORDINGS, ids=lambda p: p.name)
def test_every_recording_round_trips(path):
    for recording in json.loads(path.read_text())["recordings"]:
        decoded = scenario_spans(recording)
        assert scenario_json(recording["scenario"], decoded, canonicalize=False) == recording


@pytest.mark.parametrize("path", SPAN_EXPECTED, ids=lambda p: p.name)
def test_every_expected_result_round_trips(path):
    expected = path.with_name(path.stem + ".expected.json")
    for recording in json.loads(expected.read_text())["recordings"]:
        decoded = scenario_spans(recording)
        assert scenario_json(recording["scenario"], decoded, canonicalize=False) == recording
