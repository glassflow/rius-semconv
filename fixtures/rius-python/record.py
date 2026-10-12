"""Record what the rius Python SDK itself exports: its native spans and its MCP wrapper.

Usage: python record.py <recording.json> [<environment.json>]

A control family. Every other family records a third-party instrumentor's raw
spans; this one records spans the SDK already normalized on the way out, so
normalizing them again must change nothing. The recording is what reaches the
SDK's exporter (init(span_exporter=...)), which is what goes on the wire.

Native scenarios use the public API (observe, start_as_current_span,
start_as_current_generation, session, user). MCP scenarios call tools on an
in-process MCP server through the SDK's ClientSession wrapper. No network, no
API keys, no model calls: a generation's output and usage are whatever the
scenario sets.

mcp 2.x traces itself (scope mcp-python-sdk): with the server in-process, its
server/discover, tools/call and tools/list spans reach the same exporter. They
are the mcp library's spans, not the SDK's, so only spans from the SDK's own
scope are recorded.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import sys
import time
from collections.abc import Callable
from pathlib import Path

# The SDK measures time to first chunk with time.time_ns() and writes the
# measured seconds into a span attribute, which would differ on every run. A
# clock that advances one millisecond per reading keeps the value real in
# shape and identical across recordings. It is installed before OpenTelemetry
# is imported, since the SDK's tracer binds time_ns at import: spans and the
# first-token event then read the same clock, so attribute and event agree.
_ticks = itertools.count(1)
time.time_ns = lambda: 1_700_000_000_000_000_000 + next(_ticks) * 1_000_000

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
import rius  # noqa: E402
from _recording import ScriptedProvider, record_all  # noqa: E402
from mcp import Client  # noqa: E402
from mcp.server import MCPServer  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)
from rius import SpanKind  # noqa: E402

PACKAGES = ["glassflow-rius", "mcp", "opentelemetry-api", "opentelemetry-sdk"]

#: The SDK's tracer scope; the only spans this family records.
SDK_SCOPE = "rius"


class SDKSpans(InMemorySpanExporter):
    """The in-memory exporter, read back with only the SDK's own spans."""

    def get_finished_spans(self):  # type: ignore[no-untyped-def]
        return tuple(
            span
            for span in super().get_finished_spans()
            if span.instrumentation_scope is not None
            and span.instrumentation_scope.name == SDK_SCOPE
        )


# The failing MCP tool logs its traceback server-side; the result is what matters.
logging.getLogger("mcp").setLevel(logging.CRITICAL)

exporter = SDKSpans()
client = rius.init(
    endpoint="http://127.0.0.1:9",  # never reached: span_exporter replaces the OTLP exporter
    api_key="recorder",
    service_name="rius-recorder",
    agent_name="weather-agent",
    span_exporter=exporter,
    instruments=["mcp"],
    heartbeat=False,
    partial_spans=False,
)

SCENARIOS: dict[str, Callable[[], None]] = {}


def scenario(fn: Callable[[], None]) -> Callable[[], None]:
    def run() -> None:
        fn()
        # The SDK exports through a batch processor: flush before the
        # recorder reads the exporter.
        client.flush()

    SCENARIOS[fn.__name__] = run
    return fn


MESSAGES = [
    {"role": "system", "content": "Answer in one word."},
    {"role": "user", "content": "Capital of France?"},
]

WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Current weather for a city.",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}


@scenario
def generation_chat() -> None:
    with rius.start_as_current_generation(
        model="gpt-4o-mini",
        provider="openai",
        input=MESSAGES,
        model_parameters={"temperature": 0.2, "max_tokens": 64, "seed": 7},
    ) as gen:
        gen.set_output([{"role": "assistant", "content": "Paris."}])
        gen.set_response_model("gpt-4o-mini-2024-07-18")
        gen.set_response_id("chatcmpl-rec1")
        gen.set_finish_reasons("stop")
        gen.set_usage(
            input_tokens=42, output_tokens=9, cache_read_input_tokens=16, reasoning_output_tokens=3
        )


@scenario
def generation_stream() -> None:
    with rius.start_as_current_generation(
        model="claude-haiku-4-5", provider="anthropic", input=MESSAGES
    ) as gen:
        gen.record_first_token()
        gen.set_output([{"role": "assistant", "content": "Paris."}])
        gen.set_finish_reasons("end_turn")
        gen.set_usage(input_tokens=20, output_tokens=4)


@scenario
def generation_error() -> None:
    try:
        with rius.start_as_current_generation(model="gpt-nope", provider="openai", input=MESSAGES):
            raise RuntimeError("The model `gpt-nope` does not exist.")
    except RuntimeError:
        pass


@rius.observe(kind=SpanKind.TOOL)
def get_weather(city: str) -> str:
    return "sunny, 22C"


@rius.observe(kind=SpanKind.AGENT, agent_name="weather-agent")
def weather_agent(question: str) -> str:
    """An agent turn: a generation that asks for a tool, the tool, a generation that answers."""
    asked = [{"role": "user", "content": question}]
    tool_call = {
        "role": "assistant",
        "tool_calls": [
            {
                "id": "call_rec1",
                "type": "function",
                "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'},
            }
        ],
    }
    with rius.start_as_current_generation(
        model="gpt-4o-mini", provider="openai", input=asked, tools=[WEATHER_TOOL]
    ) as gen:
        gen.set_output([tool_call])
        gen.set_finish_reasons("tool_calls")
        gen.set_usage(input_tokens=60, output_tokens=12)
    result = get_weather("Paris")
    answered = [
        *asked,
        tool_call,
        {"role": "tool", "tool_call_id": "call_rec1", "content": result},
    ]
    with rius.start_as_current_generation(
        model="gpt-4o-mini", provider="openai", input=answered, tools=[WEATHER_TOOL]
    ) as gen:
        gen.set_output([{"role": "assistant", "content": "Sunny, 22C."}])
        gen.set_finish_reasons("stop")
        gen.set_usage(input_tokens=80, output_tokens=6)
    return "Sunny, 22C."


@scenario
def agent_tools() -> None:
    with rius.session("session-rec1"), rius.user("user-rec1"):
        weather_agent("Weather in Paris?")


@scenario
def retrieval() -> None:
    with rius.start_as_current_span(
        kind=SpanKind.RETRIEVER, data_source_id="product-kb", top_k=2, input="return policy"
    ) as obs:
        obs.set_retrieved_documents(
            [
                {"id": "doc-1", "content": "Returns are accepted within 30 days.", "score": 0.92},
                {"id": "doc-2", "content": "Refunds go to the original card.", "score": 0.81},
            ]
        )


@rius.observe
def plan_trip(city: str) -> dict:
    return {"city": city, "days": 2}


@scenario
def chain() -> None:
    plan_trip("Paris")


def mcp_server() -> MCPServer:
    server = MCPServer("weather-server")

    @server.tool()
    def forecast(city: str) -> str:
        """Tomorrow's forecast for a city."""
        return f"{city}: sunny, 24C"

    @server.tool()
    def broken(city: str) -> str:
        """Always fails."""
        raise ValueError("forecast service unavailable")

    return server


async def call_tools(*calls: tuple[str, dict]) -> None:
    async with Client(mcp_server()) as mcp:
        for name, arguments in calls:
            await mcp.session.call_tool(name, arguments)


@scenario
def mcp_tool_call() -> None:
    asyncio.run(call_tools(("forecast", {"city": "Paris"})))


@scenario
def mcp_tool_error() -> None:
    # A tool that raises comes back as an error RESULT (isError), not an
    # exception: the span ends ERROR with error.type tool_error.
    asyncio.run(call_tools(("broken", {"city": "Paris"})))


@scenario
def mcp_in_agent() -> None:
    @rius.observe(kind=SpanKind.AGENT, agent_name="forecast-agent")
    def forecast_agent() -> None:
        asyncio.run(call_tools(("forecast", {"city": "Paris"})))

    forecast_agent()


if __name__ == "__main__":
    # No provider is scripted: the SDK makes no HTTP calls of its own here.
    record_all(SCENARIOS, exporter, ScriptedProvider(httpx), PACKAGES, sys.argv[1:])
