"""Record openinference-instrumentation-langchain spans against a scripted OpenAI.

Usage: python record.py <recording.json> [<environment.json>]

Drives langchain-openai's ChatOpenAI, instrumented by OpenInference's LangChain
instrumentor ONLY, through an in-process mock transport that answers every
request with realistic OpenAI JSON. No network, no API keys, no rius SDK.

Only the LangChain instrumentor is enabled, so each scenario shows LangChain's
own spans. With the openai instrumentor enabled as well, every model call would
also get a sibling ChatCompletion span; that combination is its own family.
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

import httpx2 as httpx  # noqa: E402  (openai >= 3, under langchain-openai, uses httpx2)
import openai  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage  # noqa: E402
from langchain_core.prompts import ChatPromptTemplate  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402
from openinference.instrumentation.langchain import LangChainInstrumentor  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)

PACKAGES = [
    "openinference-instrumentation-langchain",
    "openinference-instrumentation",
    "openinference-semantic-conventions",
    "langchain-core",
    "langchain-openai",
    "openai",
    "httpx2",
    "opentelemetry-api",
    "opentelemetry-sdk",
]

CHAT = "https://api.openai.com/v1/chat/completions"
MODEL = "gpt-4o-mini"

exporter = InMemorySpanExporter()
provider = TracerProvider(resource=recorder_resource())
provider.add_span_processor(SimpleSpanProcessor(exporter))
LangChainInstrumentor().instrument(tracer_provider=provider)

script = ScriptedProvider(httpx)


def llm(**kwargs) -> ChatOpenAI:
    return ChatOpenAI(
        model=MODEL,
        max_retries=0,
        http_client=httpx.Client(transport=script.transport()),
        **kwargs,
    )


@tool
def get_weather(city: str) -> str:
    """Current weather for a city."""
    return f"sunny in {city}"


USAGE = {
    "prompt_tokens": 42,
    "completion_tokens": 9,
    "total_tokens": 51,
    "prompt_tokens_details": {"cached_tokens": 16, "audio_tokens": 0},
    "completion_tokens_details": {"reasoning_tokens": 3, "audio_tokens": 0},
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


TOOL_CALL = {
    "id": "call_rec1",
    "type": "function",
    "function": {"name": "get_weather", "arguments": json.dumps({"city": "Paris"})},
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
    llm(temperature=0.2, max_tokens=64).invoke(
        [SystemMessage("Answer in one word."), HumanMessage("Capital of France?")]
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
    for _ in llm(stream_usage=True).stream([HumanMessage("Capital of France?")]):
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
    llm().bind_tools([get_weather], tool_choice="auto").invoke([HumanMessage("Weather in Paris?")])


@scenario
def tool_response() -> None:
    script.answer(
        CHAT,
        httpx.Response(200, json=completion({"role": "assistant", "content": "Sunny, 22C."})),
    )
    llm().bind_tools([get_weather]).invoke(
        [
            HumanMessage("Weather in Paris?"),
            AIMessage(
                "",
                tool_calls=[{"id": "call_rec1", "name": "get_weather", "args": {"city": "Paris"}}],
            ),
            ToolMessage("sunny, 22C", tool_call_id="call_rec1"),
        ]
    )


@scenario
def chain() -> None:
    script.answer(
        CHAT, httpx.Response(200, json=completion({"role": "assistant", "content": "Paris."}))
    )
    prompt = ChatPromptTemplate.from_messages(
        [("system", "Answer in one word."), ("human", "Capital of {country}?")]
    )
    (prompt | llm()).invoke({"country": "France"})


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
        ChatOpenAI(
            model="gpt-nope",
            max_retries=0,
            http_client=httpx.Client(transport=script.transport()),
        ).invoke([HumanMessage("hi")])
    except openai.BadRequestError:
        pass
    else:
        raise AssertionError("the scripted 400 did not raise")


if __name__ == "__main__":
    record_all(SCENARIOS, exporter, script, PACKAGES, sys.argv[1:])
