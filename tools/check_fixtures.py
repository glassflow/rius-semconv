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
- in a control family (manifest `"control": true`: spans an SDK already
  normalized), the expected result is the recording itself, since
  normalizing canonical spans must change nothing;
- an expected result holds no base64 or byte-array media (recordings may):
  (a) no blob part with content; (b) no data: URL; (c) no 4096-character
  base64 run; (d) no non-empty {"type": "Buffer", "data": [...]} byte array;
  (e) no base64 string under data, b64_json or result next to a media type,
  under input_audio, audio or inline_data, or in a base64 source; and (f) not
  the first 32 base64 characters of any payload fixtures/_media.py exports,
  anywhere in the file. Rules (b), (d) and (e) are read from
  registry/media_parts.yaml raw_payloads.detection, the rules the normalizers
  strip by;
- no JSON file in it holds a traceback or a local path from the machine that
  recorded it.

Then, across families: every scenario id a row of registry/media_parts.yaml
names (`<family>/<scenario>`) is a scenario some family's manifest describes.

Exit 0 when everything is consistent, 1 otherwise, with one line per problem.
Needs PyYAML, to read the registry.
"""

from __future__ import annotations

import functools
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from generators import media_parts  # noqa: E402
from generators.registry import Registry  # noqa: E402

RECORD_SCRIPTS = ("record.py", "record.mjs")
EXPECTED_SUFFIX = ".expected.json"
#: A sink-only family's expected result: the rows the sink stores, not spans.
ROWS_SUFFIX = ".expected-row.json"
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


#: A run this long of base64 characters is media, not an id or a tool argument.
BASE64_RUN = re.compile(r"[A-Za-z0-9+/=]{4096}")


#: How much of a suite payload's base64 form rule (f) looks for.
PAYLOAD_PREFIX = 32


@functools.cache
def raw_payloads() -> dict:
    """registry/media_parts.yaml raw_payloads: the detection rules (b), (d), (e)."""
    return Registry.load().media_parts["raw_payloads"]


@functools.cache
def payload_prefixes() -> dict[str, str]:
    """Rule (f): name -> the first base64 characters of each payload
    fixtures/_media.py exports."""
    spec = importlib.util.spec_from_file_location("_media", ROOT / "fixtures" / "_media.py")
    assert spec is not None and spec.loader is not None
    media = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(media)
    payloads = {
        "PNG_1X1": media.PNG_1X1,
        "WAV_SILENT": media.WAV_SILENT,
        "PDF_ONE_PAGE": media.PDF_ONE_PAGE,
        "big_png(32000)": media.big_png(32000),
    }
    return {name: media.b64(data)[:PAYLOAD_PREFIX] for name, data in payloads.items()}


def _holds_payload(text: str) -> bool:
    return any(prefix in text for prefix in payload_prefixes().values())


def _holds_media(value: Any, parent_key: str | None = None) -> bool:
    """Whether a value, or JSON nested in a string in it, holds base64 media."""
    raw = raw_payloads()
    if isinstance(value, dict):
        if value.get("type") == "blob" and "content" in value:  # (a)
            return True
        if media_parts.is_buffer(raw, value):  # (d)
            return True
        if media_parts.keyed_base64(raw, value, parent_key):  # (e)
            return True
        return any(_holds_media(v, k) for k, v in value.items())
    if isinstance(value, list):
        return any(_holds_media(v, parent_key) for v in value)
    if isinstance(value, str):
        if media_parts.is_data_url(raw, value):  # (b)
            return True
        if "data:" in value and ";base64," in value.split("data:", 1)[1]:  # (b), inside text
            return True
        if BASE64_RUN.search(value):  # (c)
            return True
        if _holds_payload(value):  # (f)
            return True
        if value.lstrip()[:1] in ("{", "["):
            try:
                return _holds_media(json.loads(value))
            except ValueError:
                return False
    return False


def _media_leaks(path: Path) -> list[str]:
    """Where an expected result holds base64 media: `<scenario> span <id> attribute <key>`."""
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return []  # reported as unreadable elsewhere
    leaks = []
    for recording in data.get("recordings", []):
        scenario = recording.get("scenario")
        scopes = [("resource", recording.get("resource"))]
        for entry in recording.get("spans") or []:
            span = entry.get("span", {})
            where = f"{scenario} span {span.get('spanId')}"
            scopes.append((where, span))
            scopes.append((where + " scope", entry.get("scope")))
            for event in span.get("events") or []:
                scopes.append((f"{where} event {event.get('name')}", event))
            for link in span.get("links") or []:
                scopes.append((f"{where} link", link))
        for where, holder in scopes:
            for attribute in (holder or {}).get("attributes") or []:
                if _holds_media(attribute.get("value")):
                    prefix = f"{scenario} {where}" if where == "resource" else where
                    leaks.append(f"{prefix} attribute {attribute.get('key')}")
        for row in recording.get("rows") or []:
            for column, value in row.items():
                if _holds_media(value):
                    leaks.append(f"{scenario} span {row.get('SpanID')} attribute {column}")
    return leaks


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

    for path in sorted(family.glob("*.expected*.json")):
        if path.name.endswith((EXPECTED_SUFFIX, ROWS_SUFFIX)):
            leaks = _media_leaks(path)
            for leak in leaks:
                errors.append(f"{label}/{path.name}: {leak} holds base64 media")
            if not leaks and _holds_payload(path.read_text()):  # (f), outside any attribute
                errors.append(f"{label}/{path.name}: holds base64 media from fixtures/_media.py")

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
        sink = expected_entry.get("source") == "sink"
        suffix = ROWS_SUFFIX if sink else EXPECTED_SUFFIX
        if not expected_name.endswith(suffix):
            errors.append(f"{where}: expected.file must end in {suffix}")
            continue
        expected_path = family / expected_name
        if not expected_path.exists():
            errors.append(f"{where}: expected result {expected_name} is missing")
            continue
        expected = _load(expected_path, errors)
        if expected is None:
            continue
        normalizer = expected.get("normalizer", {})
        for field in ("package", "commit") if sink else ("package", "version", "commit"):
            if not normalizer.get(field):
                errors.append(f"{label}/{expected_name}: normalizer has no {field}")
        if sink:
            errors += _check_rows(label, expected_name, raw, expected)
            continue
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
            if manifest.get("control") and produced[scenario] != raw[scenario]:
                errors.append(
                    f"{label}/{expected_name}: {scenario} differs from the recording, "
                    "but a control's spans are already canonical and must come out unchanged"
                )
    return errors


def _check_rows(label: str, name: str, raw: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    """A sink-only family's rows: one per recorded span, keyed by the same ids."""
    errors = []
    produced = {s["scenario"]: s for s in expected.get("recordings", [])}
    if set(produced) != set(raw):
        errors.append(
            f"{label}/{name}: scenarios differ from the recording "
            f"(missing {sorted(set(raw) - set(produced))}, "
            f"extra {sorted(set(produced) - set(raw))})"
        )
    for scenario in sorted(set(raw) & set(produced)):
        span_ids = set(_spans_by_id(raw[scenario]))
        row_ids = {row.get("SpanID") for row in produced[scenario].get("rows") or []}
        if span_ids != row_ids:
            errors.append(f"{label}/{name}: {scenario} rows do not match the recorded span ids")
    return errors


#: JSON files in a family directory that are not recordings: its manifest, and
#: a Node family's package pins.
NOT_RECORDINGS = {"manifest.json", "package.json", "package-lock.json"}


def recording_files(family: Path) -> list[Path]:
    """The raw recordings in a family directory (not manifests, pins or expected results)."""
    return sorted(
        p
        for p in family.glob("*.json")
        if p.name not in NOT_RECORDINGS
        and not p.name.endswith(EXPECTED_SUFFIX)
        and not p.name.endswith(ROWS_SUFFIX)
    )


def families(fixtures: Path) -> list[Path]:
    return sorted(p for p in fixtures.iterdir() if p.is_dir() and not p.name.startswith("_"))


def check(fixtures: Path) -> list[str]:
    errors: list[str] = []
    for family in families(fixtures):
        errors += check_family(family)
    errors += media_parts.check_fixture_refs(Registry.load().media_parts, fixtures)
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
