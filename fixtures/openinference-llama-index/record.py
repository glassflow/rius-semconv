"""Record openinference-instrumentation-llama-index spans against a scripted OpenAI.

Usage: python record.py <recording.json> [<environment.json>]

Drives llama-index-llms-openai, instrumented by OpenInference's LlamaIndex
instrumentor ONLY, through an in-process mock transport that answers every
request with realistic OpenAI JSON. No network, no API keys, no rius SDK.

llama-index-llms-openai still pins openai 2.x, which uses plain httpx (not the
httpx2 fork the other OpenAI-based families use).
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

import httpx  # noqa: E402
import openai  # noqa: E402
from llama_index.core.llms import ChatMessage, MessageRole  # noqa: E402
from llama_index.core.tools import FunctionTool  # noqa: E402
from llama_index.llms.openai import OpenAI  # noqa: E402
from openinference.instrumentation.llama_index import LlamaIndexInstrumentor  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)

PACKAGES = [
    "openinference-instrumentation-llama-index",
    "openinference-instrumentation",
    "openinference-semantic-conventions",
    "llama-index-core",
    "llama-index-llms-openai",
    "openai",
    "httpx",
    "opentelemetry-api",
    "opentelemetry-sdk",
]

CHAT = "https://api.openai.com/v1/chat/completions"
MODEL = "gpt-4o-mini"

exporter = InMemorySpanExporter()
provider = TracerProvider(resource=recorder_resource())
provider.add_span_processor(SimpleSpanProcessor(exporter))
LlamaIndexInstrumentor().instrument(tracer_provider=provider)

script = ScriptedProvider(httpx)


def llm(**kwargs) -> OpenAI:
    return OpenAI(
        model=kwargs.pop("model", MODEL),
        max_retries=0,
        http_client=httpx.Client(transport=script.transport()),
        **kwargs,
    )


def get_weather(city: str) -> str:
    """Current weather for a city."""
    return f"sunny in {city}"


WEATHER = FunctionTool.from_defaults(fn=get_weather)

USAGE = {
    "prompt_tokens": 42,
    "completion_tokens": 9,
    "total_tokens": 51,
    "prompt_tokens_details": {"cached_tokens": 16, "audio_tokens": 0},
    "completion_tokens_details": {"reasoning_tokens": 3, "audio_tokens": 0},
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
    llm(temperature=0.2, max_tokens=64).chat(
        [
            ChatMessage(role=MessageRole.SYSTEM, content="Answer in one word."),
            ChatMessage(role=MessageRole.USER, content="Capital of France?"),
        ]
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
    for _ in llm().stream_chat([ChatMessage(role=MessageRole.USER, content="Capital of France?")]):
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
    llm().chat_with_tools([WEATHER], user_msg="Weather in Paris?")


@scenario
def tool_response() -> None:
    script.answer(
        CHAT,
        httpx.Response(200, json=completion({"role": "assistant", "content": "Sunny, 22C."})),
    )
    llm().chat_with_tools(
        [WEATHER],
        chat_history=[
            ChatMessage(role=MessageRole.USER, content="Weather in Paris?"),
            ChatMessage(
                role=MessageRole.ASSISTANT,
                content=None,
                additional_kwargs={"tool_calls": [TOOL_CALL]},
            ),
            ChatMessage(
                role=MessageRole.TOOL,
                content="sunny, 22C",
                additional_kwargs={"tool_call_id": "call_rec1", "name": "get_weather"},
            ),
        ],
    )


@scenario
def error() -> None:
    # LlamaIndex rejects an unknown model name before any request is sent, so
    # the failure comes from the provider instead: a revoked key.
    script.answer(
        CHAT,
        httpx.Response(
            401,
            json={
                "error": {
                    "message": "Incorrect API key provided.",
                    "type": "invalid_request_error",
                    "param": None,
                    "code": "invalid_api_key",
                }
            },
        ),
    )
    try:
        llm().chat([ChatMessage(role=MessageRole.USER, content="hi")])
    except openai.AuthenticationError:
        pass
    else:
        raise AssertionError("the scripted 400 did not raise")


if __name__ == "__main__":
    record_all(SCENARIOS, exporter, script, PACKAGES, sys.argv[1:])
