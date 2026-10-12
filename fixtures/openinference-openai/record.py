"""Record openinference-instrumentation-openai spans against a scripted OpenAI.

Usage: python record.py <out.json> [<environment.json>]

Drives the openai client, instrumented by OpenInference, through an in-process
mock transport that answers every request with realistic OpenAI JSON. No
network, no API keys. The rius SDK is NOT involved: these are the raw spans the
instrumentor produces, before any normalization.

Writes the recordings to <out.json>, and the Python version and package pins to
<environment.json> (or stdout) for the manifest.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _recording import (  # noqa: E402
    environment,
    recorder_resource,
    scenario_json,
    write_recording,
)

os.environ["OPENAI_API_KEY"] = "sk-test"

import httpx2 as httpx  # noqa: E402  (openai >= 3 uses the httpx2 fork)
import openai  # noqa: E402
from openinference.instrumentation.openai import OpenAIInstrumentor  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)

PACKAGES = [
    "openinference-instrumentation-openai",
    "openinference-instrumentation",
    "openinference-semantic-conventions",
    "openai",
    "httpx2",
    "opentelemetry-api",
    "opentelemetry-sdk",
]

CHAT = "https://api.openai.com/v1/chat/completions"
EMBEDDINGS = "https://api.openai.com/v1/embeddings"

exporter = InMemorySpanExporter()
provider = TracerProvider(resource=recorder_resource())
provider.add_span_processor(SimpleSpanProcessor(exporter))
OpenAIInstrumentor().instrument(tracer_provider=provider)


class Script:
    """The scripted provider: one canned response per URL, every request answered locally."""

    def __init__(self) -> None:
        self.responses: dict[str, httpx.Response] = {}
        self.called: set[str] = set()

    def answer(self, url: str, response: httpx.Response) -> None:
        self.responses[url] = response

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url).split("?")[0]
        if url not in self.responses:
            raise AssertionError(f"unscripted request: {url}")
        self.called.add(url)
        canned = self.responses[url]
        return httpx.Response(canned.status_code, headers=canned.headers, content=canned.content)


script = Script()
client = openai.OpenAI(
    max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(script))
)

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

# Usage with every detail OpenAI reports, so the cache-read and reasoning
# mappings have something to map.
USAGE = {
    "prompt_tokens": 42,
    "completion_tokens": 9,
    "total_tokens": 51,
    "prompt_tokens_details": {"cached_tokens": 16, "audio_tokens": 0},
    "completion_tokens_details": {
        "reasoning_tokens": 3,
        "audio_tokens": 0,
        "accepted_prediction_tokens": 0,
        "rejected_prediction_tokens": 0,
    },
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
    client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.2,
        max_tokens=64,
        messages=[
            {"role": "system", "content": "Answer in one word."},
            {"role": "user", "content": "Capital of France?"},
        ],
    )


@scenario
def chat_stream() -> None:
    def chunk(delta: dict, finish_reason: str | None = None, usage: dict | None = None) -> str:
        body = {
            "id": "chatcmpl-rec2",
            "object": "chat.completion.chunk",
            "created": 1700000000,
            "model": "gpt-4o-mini-2024-07-18",
            "system_fingerprint": "fp_rec",
            "choices": []
            if usage
            else [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
        }
        if usage:
            body["usage"] = usage
        return f"data: {json.dumps(body)}\n\n"

    sse = (
        chunk({"role": "assistant", "content": ""})
        + chunk({"content": "Par"})
        + chunk({"content": "is."})
        + chunk({}, "stop")
        + chunk({}, usage=USAGE)
        + "data: [DONE]\n\n"
    )
    script.answer(
        CHAT,
        httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse.encode()),
    )
    stream = client.chat.completions.create(
        model="gpt-4o-mini",
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
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_rec1",
                            "type": "function",
                            "function": {"name": "get_weather", "arguments": '{"city":"Paris"}'},
                        }
                    ],
                },
                finish_reason="tool_calls",
            ),
        ),
    )
    client.chat.completions.create(
        model="gpt-4o-mini",
        tools=[WEATHER_TOOL],
        tool_choice="auto",
        messages=[{"role": "user", "content": "Weather in Paris?"}],
    )


@scenario
def tool_response() -> None:
    script.answer(
        CHAT,
        httpx.Response(200, json=completion({"role": "assistant", "content": "Sunny, 22C."})),
    )
    client.chat.completions.create(
        model="gpt-4o-mini",
        tools=[WEATHER_TOOL],
        messages=[
            {"role": "user", "content": "Weather in Paris?"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_rec1",
                        "type": "function",
                        "function": {"name": "get_weather", "arguments": '{"city":"Paris"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_rec1", "content": "sunny, 22C"},
        ],
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
        client.chat.completions.create(
            model="gpt-nope", messages=[{"role": "user", "content": "hi"}]
        )
    except openai.BadRequestError:
        pass
    else:
        raise AssertionError("the scripted 400 did not raise")


@scenario
def embeddings() -> None:
    script.answer(
        EMBEDDINGS,
        httpx.Response(
            200,
            json={
                "object": "list",
                "model": "text-embedding-3-small",
                "data": [{"object": "embedding", "index": 0, "embedding": [0.25, -0.5, 0.125]}],
                "usage": {"prompt_tokens": 5, "total_tokens": 5},
            },
        ),
    )
    client.embeddings.create(model="text-embedding-3-small", input="Capital of France?")


def main(out_path: str, environment_path: str | None) -> None:
    recordings = []
    for name, run in SCENARIOS.items():
        exporter.clear()
        script.responses.clear()
        script.called.clear()
        run()
        assert script.called == set(script.responses), (name, script.called)
        recordings.append(scenario_json(name, exporter.get_finished_spans()))
    write_recording(Path(out_path), recordings)
    env = json.dumps(environment(PACKAGES), indent=2)
    if environment_path:
        Path(environment_path).write_text(env + "\n")
    else:
        print(env)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
