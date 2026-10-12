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
- every UUID in a string value (frameworks write per-run ids into JSON
  payloads) becomes a placeholder numbered by first appearance.

This module is imported by recorders running in their own pinned virtualenv,
so it depends only on opentelemetry-sdk, opentelemetry-exporter-otlp-proto-common
and protobuf, which every such environment already holds.
"""

from __future__ import annotations

import json
import re
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


class ScriptedProvider:
    """A mock-transport handler: canned responses per URL, every request answered locally.

    Each scripted response answers exactly one request, in order, so an agent
    that calls the same endpoint twice (a tool call, then the final answer) is
    scripted with two responses. Takes the httpx module the client under test
    uses: openai >= 3 and anthropic >= 1 moved to the httpx2 fork, other
    clients still use httpx.
    """

    def __init__(self, httpx: Any) -> None:
        self.httpx = httpx
        self.responses: dict[str, list[Any]] = {}
        self.called: set[str] = set()

    def answer(self, url: str, *responses: Any) -> None:
        self.responses.setdefault(url, []).extend(responses)

    def reset(self) -> None:
        self.responses.clear()
        self.called.clear()

    def all_called(self) -> bool:
        """Every scripted response was used: none is left over."""
        return all(not queue for queue in self.responses.values())

    def transport(self) -> Any:
        return self.httpx.MockTransport(self)

    def intercept_all(self) -> None:
        """Answer every request any client in this process sends, from the script.

        For libraries that build their HTTP clients internally (LiteLLM keeps
        a module-level client per provider) and offer no clean injection point:
        passing `client=` would also end up in the span, serialized into the
        request-parameters bag. Replaces the real transport, so nothing can
        reach the network either.
        """
        self.httpx.HTTPTransport.handle_request = lambda _transport, request: self(request)

    def __call__(self, request: Any) -> Any:
        url = str(request.url).split("?")[0]
        if not self.responses.get(url):
            raise AssertionError(f"unscripted request: {url}")
        self.called.add(url)
        canned = self.responses[url].pop(0)
        return self.httpx.Response(
            canned.status_code, headers=canned.headers, content=canned.content
        )


def sse(events: Sequence[tuple[str | None, dict[str, Any] | str]]) -> bytes:
    """A server-sent-events body. Each item is (event name or None, data)."""
    out = []
    for name, data in events:
        if name is not None:
            out.append(f"event: {name}\n")
        payload = data if isinstance(data, str) else json.dumps(data)
        out.append(f"data: {payload}\n\n")
    return "".join(out).encode()


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
    scenario = {"scenario": name, "resource": resource, "spans": out}
    return _scrub_uuids(scenario) if canonicalize else scenario


_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def _scrub_uuids(scenario: dict[str, Any]) -> dict[str, Any]:
    """Replace every UUID in the scenario's string values with a placeholder.

    Frameworks mint ids per run and write them into attribute values, often
    inside a JSON string (LangChain's lc_run--<uuid>). Each distinct UUID
    becomes 00000000-0000-0000-0000-<n>, numbered by first appearance, so a
    repeated id stays recognisably the same id.
    """
    seen: dict[str, str] = {}

    def placeholder(match: re.Match[str]) -> str:
        found = match.group(0).lower()
        if found not in seen:
            seen[found] = f"00000000-0000-0000-0000-{len(seen) + 1:012d}"
        return seen[found]

    def walk(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v) for v in value]
        if isinstance(value, str):
            return _UUID.sub(placeholder, value)
        return value

    return walk(scenario)


def write_recording(path: Path, recordings: list[dict[str, Any]]) -> None:
    with open(path, "w") as f:
        json.dump({"recordings": recordings}, f, indent=2, ensure_ascii=False)
        f.write("\n")


def record_all(
    scenarios: dict[str, Any],
    exporter: Any,
    script: ScriptedProvider,
    packages: Sequence[str],
    argv: Sequence[str],
) -> None:
    """Run every scenario, write the recording, and report the environment.

    `argv` is `[<recording.json>, <environment.json>?]`. Each scenario starts
    from an empty exporter and an empty script, and must use every response it
    scripted, so a scenario that silently stopped calling the provider fails.
    """
    recordings = []
    for name, run in scenarios.items():
        exporter.clear()
        script.reset()
        run()
        leftover = {url: len(queue) for url, queue in script.responses.items() if queue}
        assert script.all_called(), f"{name}: scripted responses never requested: {leftover}"
        recordings.append(scenario_json(name, exporter.get_finished_spans()))
    write_recording(Path(argv[0]), recordings)
    env = json.dumps(environment(packages), indent=2)
    if len(argv) > 1:
        Path(argv[1]).write_text(env + "\n")
    else:
        print(env)


def environment(packages: Sequence[str]) -> dict[str, Any]:
    """The pins a recording was made with, for its manifest entry."""
    return {
        "python": sys.version.split()[0],
        "packages": {package: version(package) for package in packages},
    }
