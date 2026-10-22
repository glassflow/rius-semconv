"""Diff the Python SDK's control recording against the TypeScript SDK's.

    python tools/check_controls.py [fixtures-dir]

The control families (fixtures/rius-python, fixtures/rius-typescript) record
what each SDK itself exports for the same scenarios. Each SDK's conformance
test only checks that its own output is stable; this check compares the two
SDKs with each other, scenario by scenario and span by span: the resource,
each span's scope, name, kind, ids, times and status, every attribute, and
every event with its attributes.

It compares the newest recording of each family (by the version in the file
name). Every difference must be listed in fixtures/control_differences.json
with the reason it is a language difference and not a disagreement between the
SDKs. An entry matches a difference on `where` and `key`, and, when it has
them, on `scenarios` and on the exact `python` and `typescript` values (OTLP
JSON `AnyValue`s, `null` for absent). A side the entry gives no value for must
be present on both recordings: such an entry lets the values differ, never
lets one go missing. A difference no entry matches fails, and
so does an entry that matches nothing, so fixing a difference means deleting
its entry in the same change.

Exit 0 when the two controls agree up to the listed differences, 1 otherwise,
with one line per problem.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PYTHON = "rius-python"
TYPESCRIPT = "rius-typescript"
ALLOWLIST = "control_differences.json"
#: The span fields compared one by one; attributes and events are compared key by key.
SPAN_FIELDS = (
    "name",
    "kind",
    "traceId",
    "parentSpanId",
    "startTimeUnixNano",
    "endTimeUnixNano",
    "status",
    "flags",
    "traceState",
    "links",
    "droppedAttributesCount",
    "droppedEventsCount",
    "droppedLinksCount",
)


@dataclass(frozen=True)
class Difference:
    scenario: str
    span: str
    where: str
    key: str
    python: Any
    typescript: Any

    def __str__(self) -> str:
        return (
            f"{self.scenario} span {self.span}: {self.where} {self.key}: "
            f"python {json.dumps(self.python)}, typescript {json.dumps(self.typescript)}"
        )


def _version(name: str, family: str) -> tuple[int, ...]:
    match = re.fullmatch(re.escape(family) + r"-(\d+(?:\.\d+)*)\.json", name)
    if match is None:
        raise ValueError(f"{family}/{name}: recording name has no version")
    return tuple(int(part) for part in match.group(1).split("."))


def newest_recording(fixtures: Path, family: str) -> Path:
    """The family's recording with the highest version in its file name."""
    manifest = json.loads((fixtures / family / "manifest.json").read_text())
    names = sorted(manifest["recordings"], key=lambda name: _version(name, family))
    return fixtures / family / names[-1]


def _attributes(items: list[dict[str, Any]] | None) -> dict[str, Any]:
    return {item["key"]: item["value"] for item in items or []}


def _keyed(scenario: str, span: str, where: str, python: Any, typescript: Any) -> list[Difference]:
    a, b = _attributes(python), _attributes(typescript)
    return [
        Difference(scenario, span, where, key, a.get(key), b.get(key))
        for key in sorted(set(a) | set(b))
        if a.get(key) != b.get(key)
    ]


def _span_differences(scenario: str, python: dict, typescript: dict) -> list[Difference]:
    span_id = python["span"]["spanId"]
    out: list[Difference] = []
    for field in ("name", "version"):
        a, b = python["scope"].get(field), typescript["scope"].get(field)
        if a != b:
            out.append(Difference(scenario, span_id, "scope", field, a, b))
    a_span, b_span = python["span"], typescript["span"]
    for field in SPAN_FIELDS:
        if a_span.get(field) != b_span.get(field):
            out.append(
                Difference(scenario, span_id, "span", field, a_span.get(field), b_span.get(field))
            )
    out += _keyed(
        scenario, span_id, "attribute", a_span.get("attributes"), b_span.get("attributes")
    )
    a_events, b_events = a_span.get("events", []), b_span.get("events", [])
    if [e["name"] for e in a_events] != [e["name"] for e in b_events]:
        names = ([e["name"] for e in a_events], [e["name"] for e in b_events])
        out.append(Difference(scenario, span_id, "events", "names", *names))
        return out
    for a_event, b_event in zip(a_events, b_events, strict=True):
        where = f"event {a_event['name']}"
        if a_event.get("timeUnixNano") != b_event.get("timeUnixNano"):
            times = (a_event.get("timeUnixNano"), b_event.get("timeUnixNano"))
            out.append(Difference(scenario, span_id, where, "timeUnixNano", *times))
        out += _keyed(
            scenario, span_id, where, a_event.get("attributes"), b_event.get("attributes")
        )
    return out


def differences(python: list[dict], typescript: list[dict]) -> list[Difference]:
    """Every difference between two control recordings' scenarios."""
    out: list[Difference] = []
    a_scenarios = {s["scenario"]: s for s in python}
    b_scenarios = {s["scenario"]: s for s in typescript}
    for name in sorted(set(a_scenarios) ^ set(b_scenarios)):
        out.append(
            Difference(name, "-", "scenario", "recorded", name in a_scenarios, name in b_scenarios)
        )
    for name in [s["scenario"] for s in python if s["scenario"] in b_scenarios]:
        a, b = a_scenarios[name], b_scenarios[name]
        out += _keyed(
            name,
            "-",
            "resource",
            a["resource"].get("attributes"),
            b["resource"].get("attributes"),
        )
        a_spans = {e["span"]["spanId"]: e for e in a["spans"]}
        b_spans = {e["span"]["spanId"]: e for e in b["spans"]}
        for span_id in sorted(set(a_spans) ^ set(b_spans)):
            out.append(
                Difference(
                    name, span_id, "span", "recorded", span_id in a_spans, span_id in b_spans
                )
            )
        for span_id in sorted(set(a_spans) & set(b_spans)):
            out += _span_differences(name, a_spans[span_id], b_spans[span_id])
    return out


def matches(entry: dict[str, Any], diff: Difference) -> bool:
    if entry["where"] != diff.where or entry["key"] != diff.key:
        return False
    if "scenarios" in entry and diff.scenario not in entry["scenarios"]:
        return False
    # A side the entry gives no value for must still be present: an entry
    # that lets a value differ never lets it go missing.
    for side, value in (("python", diff.python), ("typescript", diff.typescript)):
        if side in entry:
            if entry[side] != value:
                return False
        elif value is None:
            return False
    return True


def check(fixtures: Path) -> list[str]:
    """One line per difference no entry allows, per entry that allows nothing,
    and per entry without a reason."""
    problems: list[str] = []
    python_path = newest_recording(fixtures, PYTHON)
    typescript_path = newest_recording(fixtures, TYPESCRIPT)
    python = json.loads(python_path.read_text())["recordings"]
    typescript = json.loads(typescript_path.read_text())["recordings"]
    allowed: list[dict[str, Any]] = json.loads((fixtures / ALLOWLIST).read_text())["differences"]
    for index, entry in enumerate(allowed):
        if not str(entry.get("reason", "")).strip():
            problems.append(f"{ALLOWLIST} entry {index} ({entry.get('key')}) has no reason")
    used: set[int] = set()
    for diff in differences(python, typescript):
        hits = [index for index, entry in enumerate(allowed) if matches(entry, diff)]
        used.update(hits)
        if not hits:
            problems.append(f"not listed in {ALLOWLIST}: {diff}")
    for index, entry in enumerate(allowed):
        if index not in used:
            problems.append(
                f"{ALLOWLIST} entry {index} ({entry['where']} {entry['key']}) "
                f"matches no difference between {python_path.name} and {typescript_path.name}"
            )
    return problems


def main(argv: list[str]) -> int:
    fixtures = Path(argv[0]) if argv else ROOT / "fixtures"
    problems = check(fixtures)
    for problem in problems:
        print(problem)
    if problems:
        return 1
    print(
        f"controls agree: {newest_recording(fixtures, PYTHON).name} and "
        f"{newest_recording(fixtures, TYPESCRIPT).name}, up to the listed differences"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
