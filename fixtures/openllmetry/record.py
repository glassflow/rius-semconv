"""Record real OpenLLMetry spans against mocked providers (no network, no keys).

Usage: python record.py <recording.json> [<environment.json>]

Drives the openai and anthropic clients, instrumented by traceloop-sdk, through
an httpx.MockTransport. Each scenario's finished spans go through
../_recording.py, which writes them in OTLP/JSON form with deterministic ids and
times (see fixtures/README.md).
Moved here from the Rius backend's sink testdata, where the first recordings
were made; the scenarios and responses are unchanged.
"""

import contextlib
import json
import os
import sys
import warnings
from importlib.metadata import version
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["TRACELOOP_TELEMETRY"] = "false"
os.environ["TRACELOOP_TRACE_CONTENT"] = "true"
os.environ["OPENAI_API_KEY"] = "sk-test"
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"

# openai >= 3 and anthropic >= 1 moved to the httpx2 fork. Chosen by the openai
# version, not by which module imports: some environments hold both (traceloop
# 0.62.3 imports httpx itself, and 0.47.5's dependencies pull httpx2 in).
if int(version("openai").split(".")[0]) >= 3:
    import httpx2 as httpx

    HTTPX = "httpx2"
else:
    import httpx

    HTTPX = "httpx"
from _media import PNG_1X1, data_url  # noqa: E402
from _recording import ScriptedProvider, record_all  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

warnings.simplefilter("ignore")

from traceloop.sdk import Traceloop  # noqa: E402
from traceloop.sdk.decorators import agent, task, tool, workflow  # noqa: E402

exporter = InMemorySpanExporter()
# service.instance.id is pinned: recent OpenTelemetry SDKs set a random one.
init_kwargs = dict(
    app_name="openllmetry-recorder",
    exporter=exporter,
    disable_batch=True,
    telemetry_enabled=False,
    resource_attributes={"service.instance.id": "recorder"},
)
Traceloop.init(**init_kwargs)

import anthropic  # noqa: E402
import openai  # noqa: E402

OPENAI = "https://api.openai.com/v1/chat/completions"
ANTHROPIC = "https://api.anthropic.com/v1/messages"


class Router(ScriptedProvider):
    """The shared scripted provider, with the mock.post(url).mock(return_value=...)
    spelling these scenarios were written against."""

    def post(self, url):
        router = self

        class _Route:
            def mock(self, return_value):
                router.answer(url, return_value)

        return _Route()


router = Router(httpx)
transport = router.transport()
oa = openai.OpenAI(max_retries=0, http_client=httpx.Client(transport=transport))
an = anthropic.Anthropic(max_retries=0, http_client=httpx.Client(transport=transport))

WEATHER_TOOL_OPENAI = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the weather for a city",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}
WEATHER_TOOL_ANTHROPIC = {
    "name": "get_weather",
    "description": "Get the weather for a city",
    "input_schema": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
}


def oa_completion(message, finish="stop", usage=None):
    return {
        "id": "chatcmpl-rec1",
        "object": "chat.completion",
        "created": 1758700000,
        "model": "gpt-4o-2024-08-06",
        "system_fingerprint": "fp_rec",
        "choices": [{"index": 0, "message": message, "logprobs": None, "finish_reason": finish}],
        "usage": usage
        or {
            "prompt_tokens": 42,
            "completion_tokens": 7,
            "total_tokens": 49,
            "prompt_tokens_details": {"cached_tokens": 10, "audio_tokens": 0},
            "completion_tokens_details": {"reasoning_tokens": 0, "audio_tokens": 0},
        },
    }


def sse(chunks, anthropic_style=False):
    out = []
    for c in chunks:
        if anthropic_style:
            out.append(f"event: {c['type']}\ndata: {json.dumps(c)}\n\n")
        else:
            out.append(f"data: {json.dumps(c)}\n\n")
    if not anthropic_style:
        out.append("data: [DONE]\n\n")
    return "".join(out).encode()


def an_message(content, stop="end_turn"):
    return {
        "id": "msg_rec1",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-4-5-20250929",
        "content": content,
        "stop_reason": stop,
        "stop_sequence": None,
        "usage": {
            "input_tokens": 30,
            "output_tokens": 9,
            "cache_read_input_tokens": 5,
            "cache_creation_input_tokens": 3,
        },
    }


SCENARIOS = {}


def scenario(fn):
    SCENARIOS[fn.__name__] = fn
    return fn


# ---- openai -----------------------------------------------------------------


@scenario
def openai_chat(mock):
    mock.post(OPENAI).mock(
        return_value=httpx.Response(200, json=oa_completion({"role": "assistant", "content": "yo"}))
    )
    oa.chat.completions.create(
        model="gpt-4o",
        temperature=0.1,
        max_tokens=64,
        messages=[{"role": "system", "content": "be terse"}, {"role": "user", "content": "hi"}],
    )


@scenario
def openai_chat_stream(mock):
    base = {
        "id": "chatcmpl-rec2",
        "object": "chat.completion.chunk",
        "created": 1758700000,
        "model": "gpt-4o-2024-08-06",
    }
    chunks = [
        {
            **base,
            "choices": [
                {"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}
            ],
        },
        {**base, "choices": [{"index": 0, "delta": {"content": "y"}, "finish_reason": None}]},
        {**base, "choices": [{"index": 0, "delta": {"content": "o"}, "finish_reason": None}]},
        {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        {
            **base,
            "choices": [],
            "usage": {"prompt_tokens": 12, "completion_tokens": 2, "total_tokens": 14},
        },
    ]
    mock.post(OPENAI).mock(
        return_value=httpx.Response(
            200, content=sse(chunks), headers={"content-type": "text/event-stream"}
        )
    )
    stream = oa.chat.completions.create(
        model="gpt-4o",
        stream=True,
        stream_options={"include_usage": True},
        messages=[{"role": "user", "content": "hi"}],
    )
    for _ in stream:
        pass


@scenario
def openai_tool_call(mock):
    mock.post(OPENAI).mock(
        return_value=httpx.Response(
            200,
            json=oa_completion(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_abc",
                            "type": "function",
                            "function": {"name": "get_weather", "arguments": '{"city":"Paris"}'},
                        }
                    ],
                },
                finish="tool_calls",
            ),
        )
    )
    oa.chat.completions.create(
        model="gpt-4o",
        tools=[WEATHER_TOOL_OPENAI],
        tool_choice="auto",
        messages=[{"role": "user", "content": "weather in Paris?"}],
    )


@scenario
def openai_tool_response(mock):
    mock.post(OPENAI).mock(
        return_value=httpx.Response(
            200, json=oa_completion({"role": "assistant", "content": "It is sunny in Paris."})
        )
    )
    oa.chat.completions.create(
        model="gpt-4o",
        tools=[WEATHER_TOOL_OPENAI],
        messages=[
            {"role": "user", "content": "weather in Paris?"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_abc",
                        "type": "function",
                        "function": {"name": "get_weather", "arguments": '{"city":"Paris"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_abc", "content": "sunny, 22C"},
        ],
    )


@scenario
def openai_error(mock):
    mock.post(OPENAI).mock(
        return_value=httpx.Response(
            400,
            json={
                "error": {
                    "message": "Invalid model",
                    "type": "invalid_request_error",
                    "param": "model",
                    "code": "model_not_found",
                }
            },
        )
    )
    with contextlib.suppress(openai.BadRequestError):
        oa.chat.completions.create(model="gpt-nope", messages=[{"role": "user", "content": "hi"}])


@scenario
def openai_embeddings(mock):
    mock.post("https://api.openai.com/v1/embeddings").mock(
        return_value=httpx.Response(
            200,
            json={
                "object": "list",
                "data": [{"object": "embedding", "index": 0, "embedding": [0.1, -0.2, 0.3]}],
                "model": "text-embedding-3-small",
                "usage": {"prompt_tokens": 4, "total_tokens": 4},
            },
        )
    )
    oa.embeddings.create(model="text-embedding-3-small", input="hello world")


# ---- anthropic --------------------------------------------------------------


@scenario
def anthropic_chat(mock):
    mock.post(ANTHROPIC).mock(
        return_value=httpx.Response(200, json=an_message([{"type": "text", "text": "yo"}]))
    )
    an.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=64,
        system="be terse",
        messages=[{"role": "user", "content": "hi"}],
    )


@scenario
def anthropic_chat_stream(mock):
    events = [
        {
            "type": "message_start",
            "message": {
                **an_message([]),
                "stop_reason": None,
                "usage": {
                    "input_tokens": 12,
                    "output_tokens": 1,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
            },
        },
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "y"}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "o"}},
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
            "usage": {"output_tokens": 2},
        },
        {"type": "message_stop"},
    ]
    mock.post(ANTHROPIC).mock(
        return_value=httpx.Response(
            200,
            content=sse(events, anthropic_style=True),
            headers={"content-type": "text/event-stream"},
        )
    )
    stream = an.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=64,
        stream=True,
        messages=[{"role": "user", "content": "hi"}],
    )
    for _ in stream:
        pass


@scenario
def anthropic_tool_call(mock):
    mock.post(ANTHROPIC).mock(
        return_value=httpx.Response(
            200,
            json=an_message(
                [
                    {"type": "text", "text": "Let me check."},
                    {
                        "type": "tool_use",
                        "id": "toolu_abc",
                        "name": "get_weather",
                        "input": {"city": "Paris"},
                    },
                ],
                stop="tool_use",
            ),
        )
    )
    an.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=64,
        tools=[WEATHER_TOOL_ANTHROPIC],
        messages=[{"role": "user", "content": "weather in Paris?"}],
    )


@scenario
def anthropic_tool_response(mock):
    mock.post(ANTHROPIC).mock(
        return_value=httpx.Response(
            200, json=an_message([{"type": "text", "text": "It is sunny in Paris."}])
        )
    )
    an.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=64,
        tools=[WEATHER_TOOL_ANTHROPIC],
        messages=[
            {"role": "user", "content": "weather in Paris?"},
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_abc",
                        "name": "get_weather",
                        "input": {"city": "Paris"},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_abc", "content": "sunny, 22C"}
                ],
            },
        ],
    )


@scenario
def anthropic_error(mock):
    mock.post(ANTHROPIC).mock(
        return_value=httpx.Response(
            400,
            json={
                "type": "error",
                "error": {"type": "invalid_request_error", "message": "model: not found"},
            },
        )
    )
    with contextlib.suppress(anthropic.BadRequestError):
        an.messages.create(
            model="claude-nope", max_tokens=64, messages=[{"role": "user", "content": "hi"}]
        )


# ---- traceloop decorators: the span-kind taxonomy ---------------------------


@scenario
def traceloop_decorators(mock):
    mock.post(OPENAI).mock(
        return_value=httpx.Response(
            200, json=oa_completion({"role": "assistant", "content": "22C"})
        )
    )

    @tool(name="get_weather")
    def get_weather(city):
        return f"sunny in {city}"

    @task(name="summarize")
    def summarize(text):
        oa.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": text}])
        return "ok"

    @agent(name="weather_agent")
    def weather_agent(q):
        get_weather("Paris")
        return summarize(q)

    @workflow(name="weather_workflow")
    def run(q):
        return weather_agent(q)

    run("weather?")


PACKAGES = [
    "traceloop-sdk",
    "opentelemetry-instrumentation-openai",
    "opentelemetry-instrumentation-anthropic",
    "opentelemetry-semantic-conventions-ai",
    "opentelemetry-api",
    "opentelemetry-sdk",
    "openai",
    "anthropic",
    HTTPX,
]


# ---- images -----------------------------------------------------------------


def ask_about_image(mock, url):
    mock.post(OPENAI).mock(
        return_value=httpx.Response(
            200, json=oa_completion({"role": "assistant", "content": "A tiny image."})
        )
    )
    oa.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is in this image?"},
                    {"type": "image_url", "image_url": {"url": url}},
                ],
            }
        ],
    )


@scenario
def image_base64(mock):
    ask_about_image(mock, data_url("image/png", PNG_1X1))


@scenario
def image_https_url(mock):
    ask_about_image(mock, "https://example.com/cat.png")


if __name__ == "__main__":
    runs = {name: (lambda fn=fn: fn(router)) for name, fn in SCENARIOS.items()}
    record_all(runs, exporter, router, PACKAGES, sys.argv[1:])
