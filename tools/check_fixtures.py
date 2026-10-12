"""Check that every recorded fixture is complete and consistent.

    python tools/check_fixtures.py [fixtures-dir]

For every family directory under fixtures/ (any directory whose name does not
start with "_"):

- it has a manifest.json and a record script (record.py or record.mjs);
- every recording the manifest lists exists, and every recording file in the
  directory is listed;
- the scenarios in a recording are exactly the ones its manifest entry
  describes, and none is empty unless listed under `empty_scenarios`;
- its expected result exists, names the normalizer that produced it, covers
  the same scenarios, and keeps the recording's span ids and times, so a
  consumer can match each expected span to its raw span;
- no JSON file in it holds a traceback or a local path from the machine that
  recorded it.

Exit 0 when everything is consistent, 1 otherwise, with one line per problem.
Needs only the standard library.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
RECORD_SCRIPTS = ("record.py", "record.mjs")
EXPECTED_SUFFIX = ".expected.json"
SOURCES = {"python-sdk", "typescript-sdk", "sink"}
#: Text that only appears when a recording kept something from the recording
#: machine: a traceback or a stack frame, or a local path. Matched against the
#: file's JSON text, where a newline is the two characters backslash and n.
MACHINE_MARKERS = (
    "Traceback (most recent call last)",
    "\\n    at ",
    "site-packages",
    "/Users/",
    "/home/",
    "/private/tmp/",
)


def _machine_leaks(path: Path) -> list[str]:
    text = path.read_text()
    return [marker for marker in MACHINE_MARKERS if marker in text]


def _spans_by_id(scenario: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["span"]["spanId"]: entry["span"] for entry in scenario.get("spans", [])}


def _timeline(span: dict[str, Any]) -> tuple:
    return (
        span.get("traceId"),
        span.get("parentSpanId"),
        span.get("startTimeUnixNano"),
        span.get("endTimeUnixNano"),
    )


def _load(path: Path, errors: list[str]) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        errors.append(f"{path}: cannot read JSON ({exc})")
        return None


def check_family(family: Path) -> list[str]:
    errors: list[str] = []
    label = family.name
    manifest_path = family / "manifest.json"
    if not manifest_path.exists():
        return [f"{label}: no manifest.json"]
    if not any((family / script).exists() for script in RECORD_SCRIPTS):
        errors.append(f"{label}: no record script ({' or '.join(RECORD_SCRIPTS)})")
    manifest = _load(manifest_path, errors)
    if manifest is None:
        return errors
    if manifest.get("family") != label:
        errors.append(f"{label}: manifest names family {manifest.get('family')!r}")

    listed = manifest.get("recordings", {})
    on_disk = {p.name for p in recording_files(family)}
    for name in sorted(on_disk - set(listed)):
        errors.append(f"{label}: {name} is not listed in manifest.json")
    for path in sorted(family.glob("*.json")):
        for marker in _machine_leaks(path):
            errors.append(f"{label}/{path.name}: contains {marker!r} from the recording machine")

    for name, entry in listed.items():
        where = f"{label}/{name}"
        recording_path = family / name
        if not recording_path.exists():
            errors.append(f"{where}: listed in manifest.json but missing")
            continue
        for field in ("packages", "scenarios", "expected", "verified"):
            if field not in entry:
                errors.append(f"{where}: manifest entry has no {field}")
        if "python" not in entry and "node" not in entry:
            errors.append(f"{where}: manifest entry names no runtime (python or node)")
        recording = _load(recording_path, errors)
        if recording is None:
            continue
        raw = {s["scenario"]: s for s in recording.get("recordings", [])}
        described = set(entry.get("scenarios", {}))
        for scenario in sorted(set(raw) - described):
            errors.append(f"{where}: scenario {scenario} is not described in manifest.json")
        for scenario in sorted(described - set(raw)):
            errors.append(f"{where}: manifest describes {scenario}, which was not recorded")
        allowed_empty = set(entry.get("empty_scenarios", []))
        for scenario, data in raw.items():
            if not data.get("spans") and scenario not in allowed_empty:
                errors.append(f"{where}: scenario {scenario} recorded no spans")

        expected_entry = entry.get("expected", {})
        if expected_entry.get("source") not in SOURCES:
            errors.append(f"{where}: expected.source must be one of {sorted(SOURCES)}")
        expected_name = expected_entry.get("file", "")
        if not expected_name.endswith(EXPECTED_SUFFIX):
            errors.append(f"{where}: expected.file must end in {EXPECTED_SUFFIX}")
            continue
        expected_path = family / expected_name
        if not expected_path.exists():
            errors.append(f"{where}: expected result {expected_name} is missing")
            continue
        expected = _load(expected_path, errors)
        if expected is None:
            continue
        normalizer = expected.get("normalizer", {})
        for field in ("package", "version", "commit"):
            if not normalizer.get(field):
                errors.append(f"{label}/{expected_name}: normalizer has no {field}")
        produced = {s["scenario"]: s for s in expected.get("recordings", [])}
        if set(produced) != set(raw):
            errors.append(
                f"{label}/{expected_name}: scenarios differ from the recording "
                f"(missing {sorted(set(raw) - set(produced))}, "
                f"extra {sorted(set(produced) - set(raw))})"
            )
        for scenario in sorted(set(raw) & set(produced)):
            raw_spans = _spans_by_id(raw[scenario])
            out_spans = _spans_by_id(produced[scenario])
            if set(raw_spans) != set(out_spans):
                errors.append(f"{label}/{expected_name}: {scenario} has different span ids")
                continue
            for span_id, span in raw_spans.items():
                if _timeline(span) != _timeline(out_spans[span_id]):
                    errors.append(
                        f"{label}/{expected_name}: {scenario} span {span_id} changed its "
                        "trace, parent or times"
                    )
    return errors


#: JSON files in a family directory that are not recordings: its manifest, and
#: a Node family's package pins.
NOT_RECORDINGS = {"manifest.json", "package.json", "package-lock.json"}


def recording_files(family: Path) -> list[Path]:
    """The raw recordings in a family directory (not manifests, pins or expected results)."""
    return sorted(
        p
        for p in family.glob("*.json")
        if p.name not in NOT_RECORDINGS and not p.name.endswith(EXPECTED_SUFFIX)
    )


def families(fixtures: Path) -> list[Path]:
    return sorted(p for p in fixtures.iterdir() if p.is_dir() and not p.name.startswith("_"))


def check(fixtures: Path) -> list[str]:
    errors: list[str] = []
    for family in families(fixtures):
        errors += check_family(family)
    return errors


def main(argv: list[str]) -> int:
    fixtures = Path(argv[1]) if len(argv) > 1 else ROOT / "fixtures"
    errors = check(fixtures)
    for error in errors:
        print(error)
    found = families(fixtures)
    print(f"fixtures: {len(found)} famil{'y' if len(found) == 1 else 'ies'}, ", end="")
    print("clean" if not errors else f"{len(errors)} problem(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
