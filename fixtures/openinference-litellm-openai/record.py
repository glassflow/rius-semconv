"""Record LiteLLM with BOTH the LiteLLM and the openai OpenInference instrumentors.

Usage: python record.py <recording.json> [<environment.json>]

The combination a LiteLLM app gets when both instrumentors are enabled, which
the rius SDK does when both packages are installed: LiteLLM calls the OpenAI
client for OpenAI models, so each such call is recorded twice, once on
LiteLLM's `completion` span and once on the openai instrumentor's
`ChatCompletion` span, both carrying the call's usage. Anthropic goes through
LiteLLM's own HTTP handler, so it gets no second span.

Same scripted providers and responses as ../openinference-litellm (every
httpx request answered by the script). No network, no API keys, no rius SDK.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _recording import ScriptedProvider, record_all, recorder_resource, sse  # noqa: E402

os.environ["OPENAI_API_KEY"] = "sk-test"
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"  # no cost-map download at import

import httpx  # noqa: E402
import litellm  # noqa: E402
from openinference.instrumentation.litellm import LiteLLMInstrumentor  # noqa: E402
from openinference.instrumentation.openai import OpenAIInstrumentor  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)

PACKAGES = [
    "openinference-instrumentation-litellm",
    "openinference-instrumentation-openai",
    "openinference-instrumentation",
    "openinference-semantic-conventions",
    "litellm",
    "openai",
    "httpx",
    "opentelemetry-api",
    "opentelemetry-sdk",
]

CHAT = "https://api.openai.com/v1/chat/completions"
MESSAGES = "https://api.anthropic.com/v1/messages"

exporter = InMemorySpanExporter()
provider = TracerProvider(resource=recorder_resource())
provider.add_span_processor(SimpleSpanProcessor(exporter))
LiteLLMInstrumentor().instrument(tracer_provider=provider)
OpenAIInstrumentor().instrument(tracer_provider=provider)

script = ScriptedProvider(httpx)
script.intercept_all()


USAGE = {
    "prompt_tokens": 42,
    "completion_tokens": 9,
    "total_tokens": 51,
    "prompt_tokens_details": {"cached_tokens": 16, "audio_tokens": 0},
    "completion_tokens_details": {"reasoning_tokens": 3, "audio_tokens": 0},
}

WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Current weather for a city",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}

TOOL_CALL = {
    "id": "call_rec1",
    "type": "function",
    "function": {"name": "get_weather", "arguments": json.dumps({"city": "Paris"})},
}


def completion(message: dict, finish_reason: str = "stop") -> dict:
    return {
        "id": "chatcmpl-rec1",
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
    litellm.completion(
        model="openai/gpt-4o-mini",
        temperature=0.2,
        max_tokens=64,
        messages=[
            {"role": "system", "content": "Answer in one word."},
            {"role": "user", "content": "Capital of France?"},
        ],
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
    stream = litellm.completion(
        model="openai/gpt-4o-mini",
        stream=True,
        stream_options={"include_usage": True},
        messages=[{"role": "user", "content": "Capital of France?"}],
    )
    for _ in stream:
        pass


@scenario
def tool_call() -> None:
    script.answer(
        CHAT,
        httpx.Response(
            200,
            json=completion(
                {"role": "assistant", "content": None, "tool_calls": [TOOL_CALL]},
                finish_reason="tool_calls",
            ),
        ),
    )
    litellm.completion(
        model="openai/gpt-4o-mini",
        tools=[WEATHER_TOOL],
        tool_choice="auto",
        messages=[{"role": "user", "content": "Weather in Paris?"}],
    )


@scenario
def anthropic_chat() -> None:
    script.answer(
        MESSAGES,
        httpx.Response(
            200,
            json={
                "id": "msg_rec1",
                "type": "message",
                "role": "assistant",
                "model": "claude-haiku-4-5-20251001",
                "content": [{"type": "text", "text": "Paris."}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {
                    "input_tokens": 26,
                    "output_tokens": 9,
                    "cache_read_input_tokens": 16,
                    "cache_creation_input_tokens": 8,
                },
            },
        ),
    )
    litellm.completion(
        model="anthropic/claude-haiku-4-5-20251001",
        max_tokens=64,
        messages=[{"role": "user", "content": "Capital of France?"}],
    )


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
        litellm.completion(
            model="openai/gpt-nope",
            messages=[{"role": "user", "content": "hi"}],
            num_retries=0,
        )
    except litellm.NotFoundError:
        # LiteLLM maps OpenAI's "does not exist" 400 to its own NotFoundError.
        pass
    else:
        raise AssertionError("the scripted 400 did not raise")


if __name__ == "__main__":
    record_all(SCENARIOS, exporter, script, PACKAGES, sys.argv[1:])
