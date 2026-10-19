"""Record openinference-instrumentation-anthropic spans against a scripted Anthropic.

Usage: python record.py <recording.json> [<environment.json>]

Drives the anthropic client, instrumented by OpenInference, through an
in-process mock transport that answers every request with realistic Anthropic
JSON. No network, no API keys, and no rius SDK: these are the raw spans.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _media import PDF_ONE_PAGE, PNG_1X1, b64  # noqa: E402
from _recording import ScriptedProvider, record_all, recorder_resource, sse  # noqa: E402

os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"

import anthropic  # noqa: E402
import httpx2 as httpx  # noqa: E402  (anthropic >= 1 uses the httpx2 fork)
from openinference.instrumentation.anthropic import AnthropicInstrumentor  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)

PACKAGES = [
    "openinference-instrumentation-anthropic",
    "openinference-instrumentation",
    "openinference-semantic-conventions",
    "anthropic",
    "httpx2",
    "opentelemetry-api",
    "opentelemetry-sdk",
]

MESSAGES = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"

exporter = InMemorySpanExporter()
provider = TracerProvider(resource=recorder_resource())
provider.add_span_processor(SimpleSpanProcessor(exporter))
AnthropicInstrumentor().instrument(tracer_provider=provider)

script = ScriptedProvider(httpx)
client = anthropic.Anthropic(max_retries=0, http_client=httpx.Client(transport=script.transport()))

WEATHER_TOOL = {
    "name": "get_weather",
    "description": "Current weather for a city",
    "input_schema": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
}

# Anthropic reports cache reads and writes beside input_tokens, not inside it,
# so both cache mappings and the input-total rule have something to work on.
USAGE = {
    "input_tokens": 26,
    "output_tokens": 9,
    "cache_read_input_tokens": 16,
    "cache_creation_input_tokens": 8,
}


def message(content: list[dict], stop_reason: str = "end_turn") -> dict:
    return {
        "id": "msg_rec1",
        "type": "message",
        "role": "assistant",
        "model": MODEL,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": USAGE,
    }


SCENARIOS: dict[str, Callable[[], None]] = {}


def scenario(fn: Callable[[], None]) -> Callable[[], None]:
    SCENARIOS[fn.__name__] = fn
    return fn


@scenario
def chat() -> None:
    script.answer(MESSAGES, httpx.Response(200, json=message([{"type": "text", "text": "Paris."}])))
    client.messages.create(
        model=MODEL,
        max_tokens=64,
        # anthropic 1.x dropped temperature/top_p/top_k from messages.create;
        # stop_sequences is the request knob left to map.
        stop_sequences=["\n\n"],
        system="Answer in one word.",
        messages=[{"role": "user", "content": "Capital of France?"}],
    )


@scenario
def chat_stream() -> None:
    start = message([], stop_reason=None)
    start["id"] = "msg_rec2"
    start["usage"] = {**USAGE, "output_tokens": 1}
    body = sse(
        [
            ("message_start", {"type": "message_start", "message": start}),
            (
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                },
            ),
            (
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "Par"},
                },
            ),
            (
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "is."},
                },
            ),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            (
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"output_tokens": 9},
                },
            ),
            ("message_stop", {"type": "message_stop"}),
        ]
    )
    script.answer(
        MESSAGES,
        httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body),
    )
    stream = client.messages.create(
        model=MODEL,
        max_tokens=64,
        stream=True,
        messages=[{"role": "user", "content": "Capital of France?"}],
    )
    for _ in stream:
        pass


@scenario
def tool_call() -> None:
    script.answer(
        MESSAGES,
        httpx.Response(
            200,
            json=message(
                [
                    {
                        "type": "tool_use",
                        "id": "toolu_rec1",
                        "name": "get_weather",
                        "input": {"city": "Paris"},
                    }
                ],
                stop_reason="tool_use",
            ),
        ),
    )
    client.messages.create(
        model=MODEL,
        max_tokens=64,
        tools=[WEATHER_TOOL],
        tool_choice={"type": "auto"},
        messages=[{"role": "user", "content": "Weather in Paris?"}],
    )


@scenario
def tool_response() -> None:
    script.answer(
        MESSAGES,
        httpx.Response(200, json=message([{"type": "text", "text": "Sunny, 22C."}])),
    )
    client.messages.create(
        model=MODEL,
        max_tokens=64,
        tools=[WEATHER_TOOL],
        messages=[
            {"role": "user", "content": "Weather in Paris?"},
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_rec1",
                        "name": "get_weather",
                        "input": {"city": "Paris"},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_rec1", "content": "sunny, 22C"}
                ],
            },
        ],
    )


@scenario
def error() -> None:
    script.answer(
        MESSAGES,
        httpx.Response(
            400,
            json={
                "type": "error",
                "error": {"type": "invalid_request_error", "message": "model: claude-nope"},
            },
        ),
    )
    try:
        client.messages.create(
            model="claude-nope", max_tokens=64, messages=[{"role": "user", "content": "hi"}]
        )
    except anthropic.BadRequestError:
        pass
    else:
        raise AssertionError("the scripted 400 did not raise")


def ask_about(block: dict, question: str) -> None:
    script.answer(
        MESSAGES, httpx.Response(200, json=message([{"type": "text", "text": "A tiny image."}]))
    )
    client.messages.create(
        model=MODEL,
        max_tokens=64,
        messages=[{"role": "user", "content": [{"type": "text", "text": question}, block]}],
    )


@scenario
def image_base64() -> None:
    ask_about(
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": b64(PNG_1X1)},
        },
        "What is in this image?",
    )


@scenario
def image_url() -> None:
    ask_about(
        {"type": "image", "source": {"type": "url", "url": "https://example.com/cat.png"}},
        "What is in this image?",
    )


@scenario
def document_pdf() -> None:
    ask_about(
        {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": b64(PDF_ONE_PAGE),
            },
        },
        "Summarize this document.",
    )


if __name__ == "__main__":
    record_all(SCENARIOS, exporter, script, PACKAGES, sys.argv[1:])
