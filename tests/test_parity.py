"""The parity library: surface extraction per language, and the comparisons
check_parity.py reports. Small hand-written sources, so each rule is visible.
"""

from conftest import requires_node
from tools.parity import (
    compare,
    compare_go,
    cross_compare,
    go_constants,
    python_surface,
    ts_surface,
)

PY_REF = """
from __future__ import annotations
from collections.abc import Mapping
from enum import Enum
from opentelemetry.trace import Span
from opentelemetry.trace import SpanKind as OtelSpanKind

A = "a"
B = "b"
SET = frozenset({A, B})
PREFIXES = (A,)

class SpanKind(str, Enum):
    LLM = "LLM"
    TOOL = "TOOL"

_MAP: dict[SpanKind, OtelSpanKind] = {SpanKind.LLM: OtelSpanKind.CLIENT}
_HELPER_TABLE = {"x": 1}

def helper(span: Span, m: Mapping[str, str]) -> None:
    return None
"""


def test_python_surface_normalizes_containers_and_enums():
    s = python_surface(PY_REF)
    assert s["SET"] == {"__set__": ["a", "b"]}
    assert s["PREFIXES"] == {"__tuple__": ["a"]}
    assert s["SpanKind"] == {"__enum__": {"LLM": "LLM", "TOOL": "TOOL"}}
    assert s["_MAP"] == {"LLM": "OtelSpanKind.CLIENT"}
    assert "helper" not in s and "Span" not in s and "annotations" not in s


def test_python_surface_ignores_set_order():
    reordered = PY_REF.replace("frozenset({A, B})", "frozenset({B, A})")
    assert python_surface(reordered)["SET"] == python_surface(PY_REF)["SET"]


def test_compare_passes_on_identical_surfaces():
    ref = python_surface(PY_REF)
    gen = {k: v for k, v in ref.items() if k != "_HELPER_TABLE"}
    report = compare(ref, gen, private=lambda n: n.startswith("_"))
    assert report.ok
    assert report.uncovered_private == ["_HELPER_TABLE"]


def test_compare_flags_changed_missing_and_uncovered():
    ref = python_surface(PY_REF)
    gen = dict(ref)
    gen["A"] = "changed"
    gen["NEW"] = "new"
    del gen["B"]
    report = compare(ref, gen, private=lambda n: n.startswith("_"))
    assert not report.ok
    assert report.changed == ["A"]
    assert report.not_in_sdk == ["NEW"]
    assert report.uncovered_public == ["B"]


def test_compare_flags_a_reordered_table():
    """Same entries, different order: where the first listed entry wins (the
    request-parameter map), the order is part of the value."""
    gen = {
        "PARAMS": {"stop": "s", "stop_sequences": "s"},
        "KIND": {"__enum__": {"A": "A", "B": "B"}},
    }
    ref = {
        "PARAMS": {"stop_sequences": "s", "stop": "s"},
        "KIND": {"__enum__": {"B": "B", "A": "A"}},
    }
    report = compare(ref, gen, private=lambda n: n.startswith("_"))
    assert report.reordered == ["KIND", "PARAMS"]
    assert report.changed == []
    assert not report.ok


def test_compare_distinguishes_tuple_from_list():
    ref = python_surface(PY_REF)
    gen = dict(ref, PREFIXES=["a"])
    assert compare(ref, gen, private=lambda n: n.startswith("_")).changed == ["PREFIXES"]


TS_REF = """
import { type Attributes, SpanKind as OtelSpanKind } from "@opentelemetry/api";
import { ATTR_SERVICE_VERSION } from "@opentelemetry/semantic-conventions";
export const A = "a";
export const SERVICE_VERSION = ATTR_SERVICE_VERSION;
export const SET: ReadonlySet<string> = new Set([A, "b"]);
export enum SpanKind { LLM = "LLM" }
const MAP: Record<SpanKind, OtelSpanKind> = { [SpanKind.LLM]: OtelSpanKind.CLIENT };
export function f(x: Attributes): string { return A; }
"""


@requires_node
def test_ts_surface_evaluates_exports_and_private_consts():
    s = ts_surface(TS_REF)
    assert s["A"] == ("a", True)
    assert s["SERVICE_VERSION"] == ("service.version", True)
    assert s["SET"] == ({"__set__": ["a", "b"]}, True)
    assert s["SpanKind"] == ({"LLM": "LLM"}, True)
    assert s["MAP"] == ({"LLM": "OtelSpanKind.CLIENT"}, False)
    assert "f" not in s


GO_SRC = """
package semconv

const X = "x"

const (
\t// comment
\tA = "a" // trailing
\tB   = "b"
)

var M = map[string]string{"k": "v"}
"""


def test_go_constants_reads_blocks_and_single_consts():
    assert go_constants(GO_SRC) == {"X": "x", "A": "a", "B": "b"}


def test_compare_go_classifies_every_reference_only_name():
    ref = {"A": "a", "Legacy": "old.key", "Input": "llm.x", "Renamed": "b"}
    gen = {"A": "a", "B": "b", "New": "new"}
    gaps = {"Legacy": {"class": "legacy_spelling", "reason": "r"}, "Gone": {"class": "x"}}
    report = compare_go(ref, gen, gaps)
    assert not report.ok
    assert report.unclassified == ["Input"]
    assert report.renamed == [("B", "Renamed")]
    assert report.generated_only == ["New"]
    assert report.stale_gaps == ["Gone"]


def test_compare_go_passes_when_everything_is_classified():
    ref = {"A": "a", "Legacy": "old.key"}
    gen = {"A": "a", "New": "new"}
    gaps = {"Legacy": {"class": "legacy_spelling", "reason": "r"}}
    assert compare_go(ref, gen, gaps).ok


def test_compare_go_flags_a_changed_value():
    report = compare_go({"A": "a"}, {"A": "z"}, {})
    assert report.changed == ["A"] and not report.ok


def test_cross_compare_maps_private_names_and_containers():
    py = python_surface(PY_REF)
    ts = {
        "A": ("a", True),
        "B": ("different", True),
        "SET": ({"__set__": ["a", "b"]}, True),
        "PREFIXES": (["a"], True),
        "SpanKind": ({"LLM": "LLM", "TOOL": "TOOL"}, True),
        "MAP": ({"LLM": "OtelSpanKind.CLIENT"}, False),
        "TS_ONLY": ("t", True),
    }
    diff = cross_compare(py, ts)
    assert diff.differ == ["B"]
    assert diff.python_only == ["_HELPER_TABLE"]
    assert diff.typescript_only == ["TS_ONLY"]
