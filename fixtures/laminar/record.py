"""Record real Laminar (lmnr) spans from an OpenHands run against a scripted
local model (no network, no API keys).

Usage: python record.py <recording.json> [<environment.json>]

Runs one OpenHands conversation per scenario in a child process, with tracing
configured only by the OTEL_* env vars a user would set. The child runs as
record.py from this directory, since lmnr names the resource after
sys.argv[0]. The child's model is a scripted OpenAI-compatible server in this
process, and its OTLP/HTTP exporter posts to a capture server in this process.
The captured protobuf spans go through ../_recording.py (spans_from_otlp, then
scenario_json), which writes them in OTLP/JSON form with deterministic ids and
times (see fixtures/README.md); they are then scrubbed of machine-specific
values and truncated (see manifest.json). Moved here from argus-core's sink
testdata, where the first recordings were made; the scenarios are unchanged.
"""

import gzip
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TASK = "Print 'hello from openhands' in the terminal, then finish."
MAX_STRING = 160
CREATED = 1767225600


def tool_named(tools, name):
    names = [t.get("name") or t["function"]["name"] for t in tools]
    if name not in names:
        raise SystemExit(f"{name} not in offered tools {names}")
    return name


def scripted_call(tools, done):
    if done == 0:
        return tool_named(tools, "terminal"), {
            "command": "echo hello from openhands",
            "summary": "Say hello",
            "security_risk": "LOW",
        }
    return tool_named(tools, "finish"), {
        "message": "Printed the greeting.",
        "summary": "Finish",
        "security_risk": "LOW",
    }


def chat_reply(request):
    done = sum(1 for m in request["messages"] if m.get("role") == "tool")
    name, arguments = scripted_call(request.get("tools") or [], done)
    call = {
        "id": f"call_{done + 1}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }
    return {
        "id": f"chatcmpl-rec-{done}",
        "object": "chat.completion",
        "created": CREATED,
        "model": request.get("model", "fake"),
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": None, "tool_calls": [call]},
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {
            "prompt_tokens": 1200 + 50 * done,
            "completion_tokens": 40,
            "total_tokens": 1240 + 50 * done,
        },
    }


def responses_reply(request):
    done = sum(1 for item in request["input"] if item.get("type") == "function_call_output")
    name, arguments = scripted_call(request.get("tools") or [], done)
    return {
        "id": f"resp_rec_{done}",
        "object": "response",
        "created_at": CREATED,
        "status": "completed",
        "model": request.get("model", "fake"),
        "output": [
            {
                "type": "function_call",
                "id": f"fc_rec_{done}",
                "call_id": f"call_{done + 1}",
                "name": name,
                "arguments": json.dumps(arguments),
                "status": "completed",
            }
        ],
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "usage": {
            "input_tokens": 1200 + 50 * done,
            "input_tokens_details": {"cached_tokens": 1024 * done},
            "output_tokens": 40,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": 1240 + 50 * done,
        },
    }


UNAUTHORIZED = {
    "error": {
        "message": "Incorrect API key provided: sk-fake.",
        "type": "invalid_request_error",
        "code": "invalid_api_key",
    }
}


class Model(BaseHTTPRequestHandler):
    mode = "chat"

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if Model.mode == "unauthorized":
            self.respond(401, UNAUTHORIZED)
        elif self.path.endswith("/responses"):
            self.respond(200, responses_reply(request))
        else:
            self.respond(200, chat_reply(request))

    def respond(self, status, body):
        out = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *args):
        pass


class Capture(BaseHTTPRequestHandler):
    spans = {}
    lock = threading.Lock()

    def do_POST(self):
        from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
            ExportTraceServiceRequest,
        )

        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        request = ExportTraceServiceRequest.FromString(body)
        with Capture.lock:
            for resource_spans in request.resource_spans:
                for scope_spans in resource_spans.scope_spans:
                    for span in scope_spans.spans:
                        Capture.spans[span.span_id] = (
                            resource_spans.resource,
                            scope_spans.scope,
                            span,
                        )
        self.send_response(200)
        self.send_header("Content-Type", "application/x-protobuf")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


def serve(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server.server_address[1]


SCENARIOS = {
    "chat_tool_calls": {"mode": "chat", "api_mode": "chat"},
    "llm_error": {"mode": "unauthorized", "api_mode": "chat"},
    "responses_api_wrapper_only": {"mode": "chat", "api_mode": "responses"},
    "agent_metadata": {
        "mode": "chat",
        "api_mode": "chat",
        "metadata": {"agent.name": "billing-agent"},
    },
}


def run_agent(api_mode, model_port, metadata):
    from openhands.sdk import LLM, Agent, Conversation, Tool
    from openhands.tools.file_editor import FileEditorTool
    from openhands.tools.terminal import TerminalTool

    llm = LLM(
        usage_id="agent",
        model="openai/fake",
        base_url=f"http://127.0.0.1:{model_port}/v1",
        api_key="sk-fake",
        api_mode=api_mode,
        num_retries=0,
    )
    agent = Agent(llm=llm, tools=[Tool(name=TerminalTool.name), Tool(name=FileEditorTool.name)])
    observability = {"observability_metadata": metadata} if metadata else {}
    conversation = Conversation(
        agent=agent, workspace=tempfile.mkdtemp(prefix="oh-rius-"), **observability
    )
    conversation.send_message(TASK)
    try:
        conversation.run()
    except Exception as error:
        print("conversation failed:", type(error).__name__, file=sys.stderr)


def record_scenario(name, model_port, capture_port):
    Model.mode = SCENARIOS[name]["mode"]
    Capture.spans = {}
    env = {
        **os.environ,
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": f"http://127.0.0.1:{capture_port}/v1/traces",
        "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL": "http/protobuf",
        "OPENHANDS_SUPPRESS_BANNER": "1",
        "LITELLM_LOCAL_MODEL_COST_MAP": "True",
    }
    metadata = json.dumps(SCENARIOS[name].get("metadata", {}))
    child = [
        sys.executable,
        "record.py",
        "--agent",
        SCENARIOS[name]["api_mode"],
        str(model_port),
        metadata,
    ]
    here = os.path.dirname(os.path.abspath(__file__))
    subprocess.run(child, env=env, cwd=here, check=True, stdout=subprocess.DEVNULL)
    from _recording import spans_from_otlp

    return spans_from_otlp(list(Capture.spans.values()))


TEMP_DIR = re.compile(r"(/private)?/var/folders/[^\s\"'\\]+?/oh-rius-[a-z0-9_]+")
MACHINE_PATH = re.compile(r"(/Users|/home|/opt)/[^\s\"'\\]+")
ADDRESS = re.compile(r" at 0x[0-9a-f]+>")
MACHINE_NAME = re.compile(r'"(username|hostname)":"[^"]*"')


class Scrubber:
    """Machine-specific values: the workspace temp dir, local paths, object
    addresses, user and host names. UUIDs are numbered by the shared encoder."""

    def text(self, value):
        value = TEMP_DIR.sub("/workspace", value)
        value = MACHINE_PATH.sub("<path>", value)
        value = ADDRESS.sub(" at 0x0>", value)
        return MACHINE_NAME.sub(r'"\1":"<\1>"', value)


def truncate(value):
    if len(value) <= MAX_STRING:
        return value
    return value[:MAX_STRING] + f"...<{len(value) - MAX_STRING} chars truncated>"


def shorten(value):
    try:
        decoded = json.loads(value)
    except ValueError:
        return truncate(value)
    if not isinstance(decoded, (dict, list)):
        return truncate(value)
    return json.dumps(shorten_json(decoded), ensure_ascii=False, separators=(",", ":"))


def shorten_json(value):
    if isinstance(value, dict):
        return {k: shorten_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [shorten_json(v) for v in value]
    if isinstance(value, str):
        return truncate(value)
    return value


def scrub(tree, scrubber):
    if isinstance(tree, dict):
        return {k: scrub(v, scrubber) for k, v in tree.items()}
    if isinstance(tree, list):
        return [scrub(v, scrubber) for v in tree]
    if isinstance(tree, str):
        return scrubber.text(tree)
    return tree


PACKAGES = [
    "openhands-sdk",
    "openhands-tools",
    "lmnr",
    "litellm",
    "opentelemetry-sdk",
    "opentelemetry-exporter-otlp-proto-http",
]


def shorten_attributes(scenario):
    """Truncate every string attribute (and every string inside a JSON-valued
    one) to MAX_STRING: the OpenHands system prompt and tool descriptions are
    several KB each."""
    for entry in scenario["spans"]:
        for attr in entry["span"].get("attributes", []):
            if "stringValue" in attr["value"]:
                attr["value"]["stringValue"] = shorten(attr["value"]["stringValue"])
    return scenario


def main(argv):
    from _recording import environment, scenario_json, write_recording

    model_port, capture_port = serve(Model), serve(Capture)
    recorded = []
    for name in SCENARIOS:
        spans = record_scenario(name, model_port, capture_port)
        scenario = scrub(scenario_json(name, spans), Scrubber())
        recorded.append(shorten_attributes(scenario))
    write_recording(Path(argv[0]), recorded)
    env = json.dumps(environment(PACKAGES), indent=2)
    if len(argv) > 1:
        Path(argv[1]).write_text(env + "\n")
    else:
        print(env)


if __name__ == "__main__":
    if sys.argv[1] == "--agent":
        run_agent(sys.argv[2], int(sys.argv[3]), json.loads(sys.argv[4]))
    else:
        main(sys.argv[1:])
