"""Record pydantic-ai's own OpenTelemetry spans against a scripted OpenAI.

Usage: python record.py <recording.json> [<environment.json>]

pydantic-ai instruments itself (no OpenInference): an agent run is an
invoke_agent span, each model request a chat span, each tool call an
execute_tool span. Agents run against OpenAIChatModel over an in-process mock
transport answering with realistic OpenAI JSON. No network, no API keys, no
rius SDK. Instrumentation settings are pydantic-ai's defaults, so agent-run
spans carry their usage under gen_ai.aggregated_usage.*.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path

# pydantic-ai measures time to first chunk with time.perf_counter() and writes
# the measured seconds into a span attribute, which would differ on every run.
# A clock that advances one millisecond per reading keeps the value real in
# shape (a positive duration) and identical across recordings. Nothing else in
# the recording path reads perf_counter: OpenTelemetry uses time_ns.
_ticks = itertools.count()
time.perf_counter = lambda: next(_ticks) / 1000

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx2 as httpx  # noqa: E402  (openai >= 3 uses the httpx2 fork)
from _media import PNG_1X1  # noqa: E402
from _recording import ScriptedProvider, record_all, recorder_resource, sse  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)
from pydantic_ai import Agent, BinaryContent  # noqa: E402
from pydantic_ai.exceptions import ModelHTTPError  # noqa: E402
from pydantic_ai.models.instrumented import InstrumentationSettings  # noqa: E402
from pydantic_ai.models.openai import OpenAIChatModel  # noqa: E402
from pydantic_ai.providers.openai import OpenAIProvider  # noqa: E402

PACKAGES = [
    "pydantic-ai-slim",
    "openai",
    "httpx2",
    "opentelemetry-api",
    "opentelemetry-sdk",
]

CHAT = "https://api.openai.com/v1/chat/completions"

exporter = InMemorySpanExporter()
provider = TracerProvider(resource=recorder_resource())
provider.add_span_processor(SimpleSpanProcessor(exporter))
# Every agent, the documented way (pydantic-ai 2.x has no per-agent `instrument=`).
Agent.instrument_all(InstrumentationSettings(tracer_provider=provider))

script = ScriptedProvider(httpx)


def model(name: str = "gpt-4o-mini") -> OpenAIChatModel:
    return OpenAIChatModel(
        name,
        provider=OpenAIProvider(
            api_key="sk-test",
            http_client=httpx.AsyncClient(transport=script.transport()),
        ),
    )


def agent(**kwargs) -> Agent:
    return Agent(
        model(kwargs.pop("model_name", "gpt-4o-mini")),
        name="weather_agent",
        **kwargs,
    )


USAGE = {
    "prompt_tokens": 42,
    "completion_tokens": 9,
    "total_tokens": 51,
    "prompt_tokens_details": {"cached_tokens": 16, "audio_tokens": 0},
    "completion_tokens_details": {"reasoning_tokens": 3, "audio_tokens": 0},
}


def completion(message: dict, finish_reason: str = "stop", rid: str = "chatcmpl-rec1") -> dict:
    return {
        "id": rid,
        "object": "chat.completion",
        "created": 1700000000,
        "model": "gpt-4o-mini-2024-07-18",
        "system_fingerprint": "fp_rec",
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": USAGE,
    }


SCENARIOS: dict[str, Callable[[], None]] = {}


def scenario(fn: Callable[[], None]) -> Callable[[], None]:
    SCENARIOS[fn.__name__] = fn
    return fn


@scenario
def chat() -> None:
    script.answer(
        CHAT, httpx.Response(200, json=completion({"role": "assistant", "content": "Paris."}))
    )
    agent(system_prompt="Answer in one word.").run_sync(
        "Capital of France?", model_settings={"temperature": 0.2, "max_tokens": 64}
    )


@scenario
def chat_stream() -> None:
    def chunk(delta: dict, finish: str | None = None, usage: dict | None = None) -> dict:
        body = {
            "id": "chatcmpl-rec2",
            "object": "chat.completion.chunk",
            "created": 1700000000,
            "model": "gpt-4o-mini-2024-07-18",
            "choices": [] if usage else [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        if usage:
            body["usage"] = usage
        return body

    body = sse(
        [
            (None, chunk({"role": "assistant", "content": ""})),
            (None, chunk({"content": "Par"})),
            (None, chunk({"content": "is."})),
            (None, chunk({}, "stop")),
            (None, chunk({}, usage=USAGE)),
            (None, "[DONE]"),
        ]
    )
    script.answer(
        CHAT, httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)
    )

    async def run() -> None:
        async with agent().run_stream("Capital of France?") as result:
            async for _ in result.stream_text():
                pass

    asyncio.run(run())


@scenario
def agent_tools() -> None:
    # Two model requests in one run: the first asks for the tool, the second
    # answers with its result. Usage is on each chat span, and summed on the
    # agent-run span under gen_ai.aggregated_usage.*.
    tool_call = {
        "id": "call_rec1",
        "type": "function",
        "function": {"name": "get_weather", "arguments": json.dumps({"city": "Paris"})},
    }
    script.answer(
        CHAT,
        httpx.Response(
            200,
            json=completion(
                {"role": "assistant", "content": None, "tool_calls": [tool_call]},
                finish_reason="tool_calls",
            ),
        ),
        httpx.Response(
            200,
            json=completion({"role": "assistant", "content": "Sunny, 22C."}, rid="chatcmpl-rec2"),
        ),
    )
    weather = agent()

    @weather.tool_plain
    def get_weather(city: str) -> str:
        """Current weather for a city."""
        return "sunny, 22C"

    weather.run_sync("Weather in Paris?")


@scenario
def error() -> None:
    script.answer(
        CHAT,
        httpx.Response(
            400,
            json={
                "error": {
                    "message": "The model `gpt-nope` does not exist.",
                    "type": "invalid_request_error",
                    "param": None,
                    "code": "model_not_found",
                }
            },
        ),
    )
    try:
        agent(model_name="gpt-nope").run_sync("hi")
    except ModelHTTPError:
        pass
    else:
        raise AssertionError("the scripted 400 did not raise")


@scenario
def image_binary() -> None:
    script.answer(
        CHAT,
        httpx.Response(200, json=completion({"role": "assistant", "content": "A tiny image."})),
    )
    agent().run_sync(
        ["What is in this image?", BinaryContent(data=PNG_1X1, media_type="image/png")]
    )


if __name__ == "__main__":
    record_all(SCENARIOS, exporter, script, PACKAGES, sys.argv[1:])
