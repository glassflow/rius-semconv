"""Shared helpers for the recorders under fixtures/<family>/record.py.

A recorder drives a real instrumentor against a scripted provider in-process
(no network, no API keys), captures the finished spans with an in-memory
exporter, and hands each scenario's spans to `scenario_json`. That turns them
into the OTLP/JSON form (the protobuf JSON mapping of
opentelemetry.proto.trace.v1.Span) every consumer can parse with its own OTLP
types, made deterministic so a re-recording in the pinned environment is
byte-identical:

- ids: each distinct trace id becomes 1, 2, ... and each span id 1, 2, ...,
  numbered in start order, so parent links survive;
- times: every timestamp in the scenario (span starts and ends, event times)
  is replaced by its rank in the scenario's timeline, one millisecond apart
  from a fixed base, so ordering and nesting survive and the first-token
  event still lands after its span's start;
- an exception event's stack trace, which names machine paths, is elided.

This module is imported by recorders running in their own pinned virtualenv,
so it depends only on opentelemetry-sdk, opentelemetry-exporter-otlp-proto-common
and protobuf, which every such environment already holds.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from importlib.metadata import version
from pathlib import Path
from typing import Any

from google.protobuf.json_format import MessageToDict
from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan

#: 2023-11-14T22:13:20Z. Any fixed value works; this one is easy to spot.
BASE_TIME_NS = 1_700_000_000_000_000_000
TICK_NS = 1_000_000

STACKTRACE = "exception.stacktrace"
ELIDED = "<stacktrace elided>"


def recorder_resource() -> Resource:
    """The resource every recorder's provider uses.

    service.instance.id is pinned: the OpenTelemetry SDK (1.45 and later) sets
    a random UUID otherwise, and the recording would differ on every run.
    """
    return Resource.create({"service.name": "rius-recorder", "service.instance.id": "recorder"})


def _hex(value: int, width: int) -> str:
    return format(value, f"0{width}x")


def scenario_json(
    name: str, spans: Sequence[ReadableSpan], *, canonicalize: bool = True
) -> dict[str, Any]:
    """One scenario: its resource and its spans, in start order.

    With `canonicalize` (recording), ids and times are renumbered as the module
    docstring describes. Without it (writing an expected result from replayed
    spans), the spans' own ids and times are kept as they are: they are already
    canonical, and renumbering would shift every later time whenever
    normalization drops an event.
    """
    if not spans:
        return {"scenario": name, "resource": {"attributes": []}, "spans": []}
    ordered = sorted(enumerate(spans), key=lambda pair: (pair[1].start_time or 0, pair[0]))
    ordered_spans = [span for _, span in ordered]

    trace_ids: dict[int, str] = {}
    span_ids: dict[int, str] = {}
    for span in ordered_spans:
        context = span.get_span_context()
        if canonicalize:
            trace_ids.setdefault(context.trace_id, _hex(len(trace_ids) + 1, 32))
            span_ids.setdefault(context.span_id, _hex(len(span_ids) + 1, 16))
        else:
            trace_ids[context.trace_id] = _hex(context.trace_id, 32)
            span_ids[context.span_id] = _hex(context.span_id, 16)

    stamps = sorted(
        {span.start_time for span in ordered_spans if span.start_time is not None}
        | {span.end_time for span in ordered_spans if span.end_time is not None}
        | {event.timestamp for span in ordered_spans for event in span.events}
    )
    if canonicalize:
        rank = {stamp: str(BASE_TIME_NS + i * TICK_NS) for i, stamp in enumerate(stamps)}
    else:
        rank = {stamp: str(stamp) for stamp in stamps}

    request = encode_spans(ordered_spans)
    resource_spans = request.resource_spans
    resource = MessageToDict(resource_spans[0].resource) if resource_spans else {}
    resource["attributes"] = sorted(resource.get("attributes", []), key=lambda a: a["key"])

    encoded: dict[int, tuple[dict, dict]] = {}
    for rs in resource_spans:
        for ss in rs.scope_spans:
            scope = {"name": ss.scope.name, "version": ss.scope.version}
            for pb in ss.spans:
                span_id = int.from_bytes(pb.span_id, "big")
                encoded[span_id] = (scope, MessageToDict(pb))

    out = []
    for span in ordered_spans:
        context = span.get_span_context()
        scope, d = encoded[context.span_id]
        d["traceId"] = trace_ids[context.trace_id]
        d["spanId"] = span_ids[context.span_id]
        parent = span.parent
        if parent is not None and parent.span_id in span_ids:
            d["parentSpanId"] = span_ids[parent.span_id]
        else:
            d.pop("parentSpanId", None)
        d.pop("flags", None)
        d["startTimeUnixNano"] = rank[span.start_time]
        d["endTimeUnixNano"] = rank[span.end_time]
        d["attributes"] = sorted(d.get("attributes", []), key=lambda a: a["key"])
        for event, source in zip(d.get("events", []), span.events, strict=True):
            event["timeUnixNano"] = rank[source.timestamp]
            for attr in event.get("attributes", []):
                if attr["key"] == STACKTRACE:
                    attr["value"] = {"stringValue": ELIDED}
            event["attributes"] = sorted(event.get("attributes", []), key=lambda a: a["key"])
        out.append({"scope": scope, "span": d})
    return {"scenario": name, "resource": resource, "spans": out}


def write_recording(path: Path, recordings: list[dict[str, Any]]) -> None:
    with open(path, "w") as f:
        json.dump({"recordings": recordings}, f, indent=2, ensure_ascii=False)
        f.write("\n")


def environment(packages: Sequence[str]) -> dict[str, Any]:
    """The pins a recording was made with, for its manifest entry."""
    return {
        "python": sys.version.split()[0],
        "packages": {package: version(package) for package in packages},
    }
