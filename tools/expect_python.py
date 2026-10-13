"""Write a recording's expected result from the Python SDK's normalizer.

    python tools/expect_python.py --sdk-commit <sha> fixtures/<family>/<recording>.json ...

For every recording given, replays each scenario's spans (fixtures/_replay.py),
exports them through the rius SDK's NormalizingSpanExporter, and writes what
comes out next to the recording as <recording>.expected.json, in the same
OTLP/JSON form with the same ids and times.

The Python SDK is the reference implementation, so its output is the expected
result for every family it covers. Run this in a virtualenv holding
glassflow-rius installed from the commit named by --sdk-commit, for example:

    uv pip install "glassflow-rius @ git+https://github.com/glassflow/rius-sdk-python@<sha>"

The commit and the installed version are written into the expected file, so a
reviewer can see which normalizer produced it. Review the result by hand before
committing it: this tool records what the SDK does, not what it should do.
"""

from __future__ import annotations

import argparse
import json
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fixtures"))

from _recording import scenario_json  # noqa: E402
from _replay import scenario_spans  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)

PACKAGE = "glassflow-rius"


def expected_path(recording: Path) -> Path:
    return recording.with_name(recording.stem + ".expected.json")


def normalized_spans(spans: list[Any]) -> Any:
    """``spans`` through the SDK's exporter, after the processors that decide
    from end order have seen them.

    A live provider calls those processors at every span start and end, and
    the exporter reads what they learned (whether a LiteLLM span's child
    already recorded the call's usage). A replay drives them the same way:
    every start, then every end in the order the spans finished, so a parent
    is still open when its child ends. SDK versions without such processors
    are replayed through the exporter alone.
    """
    from rius.normalization import NormalizingSpanExporter

    sink = InMemorySpanExporter()
    try:
        from rius.aggregated_usage import WrappedCallTracker
    except ImportError:
        NormalizingSpanExporter(sink).export(spans)
        return sink.get_finished_spans()
    wrapped_calls = WrappedCallTracker()
    for span in sorted(spans, key=lambda s: s.start_time or 0):
        wrapped_calls.on_start(span)
    for span in sorted(spans, key=lambda s: s.end_time or 0):
        wrapped_calls.on_end(span)
    NormalizingSpanExporter(sink, wrapped_calls=wrapped_calls).export(spans)
    return sink.get_finished_spans()


def expect(recording: Path, sdk_commit: str) -> Path:
    data = json.loads(recording.read_text())
    out = []
    for scenario in data["recordings"]:
        finished = normalized_spans(scenario_spans(scenario))
        out.append(scenario_json(scenario["scenario"], finished, canonicalize=False))
    path = expected_path(recording)
    document = {
        "normalizer": {"package": PACKAGE, "version": version(PACKAGE), "commit": sdk_commit},
        "recordings": out,
    }
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--sdk-commit", required=True, help="rius-sdk-python commit installed")
    parser.add_argument("recordings", nargs="+", type=Path)
    args = parser.parse_args()
    for recording in args.recordings:
        print(f"wrote {expect(recording, args.sdk_commit)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
