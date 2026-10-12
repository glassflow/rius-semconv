"""Show what a normalizer did to each span of a recording, for hand review.

    python tools/review_expected.py fixtures/<family>/<recording>.json [--unchanged]

For every scenario and span, prints the attribute keys the expected result
removed (-), added (+, with a short value) and changed (~), the event names if
they changed, and with --unchanged the keys it left alone, which is where an
unmapped key hides. Needs only the standard library.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

WIDTH = 80


def _value(v: dict[str, Any]) -> Any:
    if "arrayValue" in v:
        return [_value(x) for x in v["arrayValue"].get("values", [])]
    return next(iter(v.values()), None)


def _attributes(span: dict[str, Any]) -> dict[str, Any]:
    return {a["key"]: _value(a["value"]) for a in span.get("attributes", [])}


def _short(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value)
    return text if len(text) <= WIDTH else text[: WIDTH - 3] + "..."


def review(recording: Path, unchanged: bool) -> list[str]:
    raw = {s["scenario"]: s for s in json.loads(recording.read_text())["recordings"]}
    expected_path = recording.with_name(recording.stem + ".expected.json")
    expected = json.loads(expected_path.read_text())
    lines = [f"# {recording.name}  (normalizer: {expected.get('normalizer')})"]
    for scenario in expected["recordings"]:
        name = scenario["scenario"]
        before = {e["span"]["spanId"]: e["span"] for e in raw[name]["spans"]}
        lines.append(f"\n== {name}")
        for entry in scenario["spans"]:
            after = entry["span"]
            source = before[after["spanId"]]
            a, b = _attributes(source), _attributes(after)
            lines.append(
                f"  [{after['spanId'][-2:]}] {source['name']}  ({len(a)} -> {len(b)} keys)"
            )
            lines += [f"    - {k}" for k in sorted(set(a) - set(b))]
            lines += [f"    + {k} = {_short(b[k])}" for k in sorted(set(b) - set(a))]
            lines += [
                f"    ~ {k}: {_short(a[k])} -> {_short(b[k])}"
                for k in sorted(set(a) & set(b))
                if a[k] != b[k]
            ]
            events_before = [e["name"] for e in source.get("events", [])]
            events_after = [e["name"] for e in after.get("events", [])]
            if events_before != events_after:
                lines.append(f"    events: {events_before} -> {events_after}")
            if source.get("name") != after.get("name"):
                lines.append(f"    name: {source.get('name')} -> {after.get('name')}")
            if unchanged:
                kept = sorted(k for k in set(a) & set(b) if a[k] == b[k])
                lines.append(f"    unchanged: {', '.join(kept)}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("recordings", nargs="+", type=Path)
    parser.add_argument("--unchanged", action="store_true", help="also list untouched keys")
    args = parser.parse_args()
    for recording in args.recordings:
        print("\n".join(review(recording, args.unchanged)))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
