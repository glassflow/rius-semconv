"""Print what a `weaver registry live-check --format json` report found.

    python tools/live_check_findings.py <live_check.json>

One line per distinct violation (the findings that fail the run), with how
many samples raised it, then a count of every finding by level and id. The
exit code is Weaver's to set (`--fail-on violation`); this always exits 0.
"""

from __future__ import annotations

import collections
import json
import pathlib
import sys


def findings(node):
    """Every finding in the report, wherever a sample nests it."""
    if isinstance(node, dict):
        yield from (node.get("live_check_result") or {}).get("all_advice", [])
        for v in node.values():
            yield from findings(v)
    elif isinstance(node, list):
        for v in node:
            yield from findings(v)


def summarize(report: dict) -> list[str]:
    violations: collections.Counter[str] = collections.Counter()
    counts: collections.Counter[tuple[str, str]] = collections.Counter()
    for f in findings(report["samples"]):
        counts[(f["level"], f["id"])] += 1
        if f["level"] == "violation":
            violations[
                f"{f['id']}: {f['message']} (in {f.get('signal_name') or 'a resource'})"
            ] += 1
    lines = [f"{n:4}x {v}" for v, n in sorted(violations.items())]
    lines.append(f"{sum(violations.values())} violation(s)")
    lines += [f"  {level:12} {id_:28} {n}" for (level, id_), n in sorted(counts.items())]
    return lines


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    for line in summarize(json.loads(pathlib.Path(argv[0]).read_text())):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
