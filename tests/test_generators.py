"""The generated modules: committed output current, and the emitted values
are the registry's.

Values are checked by EVALUATING the committed out/ files (Python exec, Node
for TypeScript, the Go compiler), not by grepping them, because the parity
tools compare evaluated values too. Rendering needs Weaver, so the tests that
render are skipped without it; CI runs them in the weaver job, which also
checks that generation is deterministic.
"""

import ast
import pathlib
import re
import shutil
import subprocess

import pytest

from conftest import ROOT, requires_go, requires_node, requires_weaver
from generators import generate
from generators.registry import Registry
from tools.parity import go_constants, python_surface, ts_surface

TICKET = re.compile(r"\b(?:RIUS|GLA2?)-\d+\b")
LANGS = ["python", "typescript", "go"]


def committed(registry, lang):
    return generate.output_path(ROOT / "out", registry, lang).read_text()


@pytest.fixture(scope="module")
def py_module(base_data):
    return python_surface(committed(Registry(base_data), "python"))


# --- freshness ---------------------------------------------------------------


@requires_weaver
def test_committed_output_is_current():
    """What CI's staleness step runs. Fails if out/ lags the registry."""
    assert generate.main(["--check"]) == 0


@requires_weaver
def test_check_detects_a_stale_file(tmp_path):
    assert generate.main(["--out", str(tmp_path)]) == 0
    stale = tmp_path / "python" / "_semconv_generated.py"
    stale.write_text(stale.read_text() + "# drift\n")
    assert generate.main(["--out", str(tmp_path), "--check"]) == 1


@requires_weaver
def test_output_follows_the_registry_before_model_is_rewritten(data):
    """generate renders from what tools/to_weaver.py would write now, not from
    the committed model/."""
    row = next(r for r in data["attributes"]["attributes"] if r["const"] == "TRACER_NAME")
    row["key"] = "rius-renamed"
    text = generate.render(Registry(data), ["python"])["python"]
    assert 'TRACER_NAME = "rius-renamed"' in text


def test_generation_refuses_a_registry_that_fails_lint(monkeypatch, data, tmp_path):
    data["attributes"]["attributes"][0]["divergence"] = ""
    monkeypatch.setattr(generate, "load_data", lambda: data)
    assert generate.main(["--out", str(tmp_path)]) == 2


@pytest.mark.parametrize("lang", LANGS)
def test_no_ticket_ids_in_output(base_data, lang):
    assert not TICKET.findall(committed(Registry(base_data), lang))


# --- Python ------------------------------------------------------------------


def test_python_constants(py_module):
    assert py_module["TRACER_NAME"] == "rius"
    assert py_module["GEN_AI_AGENT_VERSION"] == "gen_ai.agent.version"
    assert py_module["GEN_AI_MAIN_AGENT_ID"] == "gen_ai.main_agent.id"
    assert py_module["GEN_AI_MAIN_AGENT_NAME"] == "gen_ai.main_agent.name"
    assert py_module["GEN_AI_MAIN_AGENT_DESCRIPTION"] == "gen_ai.main_agent.description"
    # Deprecated, but still generated through the deprecation window.
    assert py_module["RIUS_MAIN_AGENT_NAME"] == "rius.main_agent.name"
    assert py_module["EXCEPTION_EVENT"] == "exception"
    assert py_module["RIUS_REQUEST_PREFIX"] == "rius.request."
    assert "SERVICE_NAME" not in py_module  # Go-only
    assert "GEN_AI_SYSTEM_INSTRUCTIONS" not in py_module  # planned


def test_python_allowlists(py_module):
    pending = py_module["PENDING_IDENTITY_ATTRIBUTES"]["__set__"]
    assert len(pending) == 17
    assert "rius.span.pending" not in pending
    assert py_module["PENDING_IDENTITY_PREFIXES"] == {
        "__tuple__": ["gen_ai.request.", "rius.request."]
    }
    content = py_module["CONTENT_ATTRIBUTES"]["__set__"]
    assert "llm.invocation_parameters" in content
    assert {"gen_ai.request.tools", "rius.request.functions"} <= set(content)
    # A model parameter that carries the prompt itself is content under
    # either request namespace, or a caller passing it through model
    # parameters exports it verbatim with content capture off.
    # The provider spellings (Gemini, Bedrock, Cohere, wrapper libraries) and
    # structured-output schemas count too: rius.request.<key> keeps the
    # caller's spelling, so each spelling must be listed.
    prompt_members = [
        "system",
        "messages",
        "prompt",
        "input",
        "instructions",
        "contents",
        "system_instruction",
        "systemInstruction",
        "system_prompt",
        "systemPrompt",
        "toolConfig",
        "preamble",
        "chat_history",
        "message",
        "documents",
        "response_format",
        "json_schema",
    ]
    for member in prompt_members:
        assert {f"gen_ai.request.{member}", f"rius.request.{member}"} <= set(content)
    assert py_module["REQUEST_PARAMETERS_CONTENT_MEMBERS"] == {
        "__tuple__": [
            "system",
            "messages",
            "prompt",
            "input",
            "instructions",
            "tools",
            "functions",
            "contents",
            "system_instruction",
            "systemInstruction",
            "system_prompt",
            "systemPrompt",
            "toolConfig",
            "preamble",
            "chat_history",
            "message",
            "documents",
            "response_format",
            "json_schema",
        ]
    }
    # The tool-definition members stay what the normalizers pull out of the bag.
    assert py_module["INVOCATION_PARAMETERS_CONTENT_MEMBERS"] == {
        "__tuple__": ["tools", "functions"]
    }
    # Scalar knobs stay identity.
    assert "gen_ai.request.model" not in content
    assert "rius.request.reasoning_effort" not in content
    # The Vercel AI SDK's speech input, human-in-the-loop decisions and
    # provider metadata carry content too.
    assert {
        "ai.request.text",
        "ai.decision.questions",
        "ai.decision.state",
        "ai.decision.answers",
        "ai.response.providerMetadata",
        "ai.settings.context",
    } <= set(content)
    assert "ai.settings.context." in py_module["CONTENT_ATTRIBUTE_PREFIXES"]["__tuple__"]
    # A summary restates the conversation; its size does not.
    assert "rius.compaction.summary.text" in content
    assert "rius.compaction.summary.bytes" not in content


CREDENTIAL_HEADER_NAMES = [
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api-key",
    "x-goog-api-key",
    "apikey",
    "x-apikey",
    "ocp-apim-subscription-key",
    "helicone-auth",
]
CREDENTIAL_HEADER_NAME_SUFFIXES = ["-token", "-secret", "-api-key"]


def _drops(header, names, suffixes):
    # The rule HEADER_ATTRIBUTE_SEGMENTS documents for consumers.
    name = header.lower().replace("_", "-")
    return name in names or name.endswith(tuple(suffixes))


def test_python_credential_headers(py_module):
    # Dropped whatever capture_content and mask say: not content, a secret.
    assert py_module["CREDENTIAL_HEADER_NAMES"] == {"__tuple__": CREDENTIAL_HEADER_NAMES}
    assert py_module["CREDENTIAL_HEADER_NAME_SUFFIXES"] == {
        "__tuple__": CREDENTIAL_HEADER_NAME_SUFFIXES
    }
    assert py_module["HEADER_ATTRIBUTE_SEGMENTS"] == {"__tuple__": [".headers.", ".header."]}


@pytest.mark.parametrize(
    ("header", "dropped"),
    [
        ("x-portkey-api-key", True),
        ("x-litellm-api-key", True),
        ("X_LiteLLM_API_Key", True),
        ("ocp-apim-subscription-key", True),
        ("x-apikey", True),
        ("x-auth-token", True),
        # A suffix matches a whole word, and -api-key is not a bare -key.
        ("idempotency-key", False),
        ("x-ratelimit-remaining-tokens", False),
        ("max-tokens", False),
        ("content-type", False),
    ],
)
def test_credential_header_rule(py_module, header, dropped):
    names = py_module["CREDENTIAL_HEADER_NAMES"]["__tuple__"]
    suffixes = py_module["CREDENTIAL_HEADER_NAME_SUFFIXES"]["__tuple__"]
    assert _drops(header, names, suffixes) is dropped


def test_python_tables(py_module):
    assert py_module["_OPERATION_BY_KIND"]["LLM"] == "chat"
    assert "CHAIN" not in py_module["_OPERATION_BY_KIND"]
    assert py_module["_KIND_BY_OPERATION"]["plan"] == "CHAIN"
    assert py_module["_KIND_BY_OPERATION"]["compaction"] == "CHAIN"
    assert py_module["_OPERATION_BY_KIND"]["RERANKER"] == "rerank"
    assert py_module["_KIND_BY_OPERATION"]["rerank"] == "RERANKER"
    assert py_module["_OTEL_KIND_BY_KIND"]["TOOL"] == "INTERNAL"
    assert py_module["_NAME_TARGET_BY_KIND"]["RETRIEVER"] == "gen_ai.data_source.id"
    params = py_module["GEN_AI_REQUEST_PARAMETERS"]
    assert params["maxOutputTokens"] == "gen_ai.request.max_tokens"
    assert "top_logprobs" not in params
    assert py_module["SpanKind"] == {
        "__enum__": {
            k: k for k in ["AGENT", "LLM", "TOOL", "RETRIEVER", "EMBEDDING", "RERANKER", "CHAIN"]
        }
    }


def test_python_module_needs_nothing_but_python_3_9(base_data):
    # The coding-agent plugin vendors this file, and it has no dependencies
    # and supports Python 3.9.
    source = committed(Registry(base_data), "python")
    tree = ast.parse(source, feature_version=(3, 9))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= {"__future__", "enum"}


def test_python_all_lists_exactly_the_public_names(base_data):
    namespace = {}
    source = committed(Registry(base_data), "python")
    surface = python_surface(source)
    exec_globals = python_surface(source, raw=True)
    namespace.update(exec_globals)
    public = {n for n in surface if not n.startswith("_")}
    assert set(namespace["__all__"]) == public


@requires_weaver
def test_python_include_planned_adds_planned_rows(base_data):
    reg = Registry(base_data, include_planned=True)
    surface = python_surface(generate.render(reg, ["python"])["python"])
    assert surface["GEN_AI_SYSTEM_INSTRUCTIONS"] == "gen_ai.system_instructions"


# --- TypeScript --------------------------------------------------------------


@requires_node
def test_typescript_values(base_data):
    surface = ts_surface(committed(Registry(base_data), "typescript"))
    values = {name: value for name, (value, _public) in surface.items()}
    assert values["TRACER_NAME"] == "rius"
    assert values["SERVICE_VERSION"] == "service.version"  # via ATTR_SERVICE_VERSION
    content = values["CONTENT_ATTRIBUTES"]["__set__"]
    assert "llm.invocation_parameters" in content
    assert "rius.request.tools" in content
    assert {"gen_ai.request.system", "rius.request.messages", "ai.decision.state"} <= set(content)
    assert values["REQUEST_PARAMETERS_CONTENT_MEMBERS"][0] == "system"
    assert "langfuse.trace.input" in content  # folded in from the third-party list
    assert values["CONTENT_ATTRIBUTE_PREFIXED_SUFFIXES"] == [
        ["llm.request.functions.", [".description", ".parameters", ".arguments"]]
    ]
    assert len(values["PENDING_IDENTITY_ATTRIBUTES"]["__set__"]) == 17
    assert values["OTEL_KIND_BY_KIND"]["LLM"] == "CLIENT"
    assert values["SpanKind"]["RETRIEVER"] == "RETRIEVER"
    assert values["CREDENTIAL_HEADER_NAMES"] == CREDENTIAL_HEADER_NAMES
    assert values["CREDENTIAL_HEADER_NAME_SUFFIXES"] == CREDENTIAL_HEADER_NAME_SUFFIXES
    assert values["HEADER_ATTRIBUTE_SEGMENTS"] == [".headers.", ".header."]


def test_typescript_aliases_upstream_constant(base_data):
    source = committed(Registry(base_data), "typescript")
    assert 'import { ATTR_SERVICE_VERSION } from "@opentelemetry/semantic-conventions";' in source
    assert "export const SERVICE_VERSION = ATTR_SERVICE_VERSION;" in source


def test_typescript_marks_a_deprecated_constant_with_a_jsdoc_tag(base_data):
    # A line comment gives editors nothing to strike through; @deprecated does.
    source = committed(Registry(base_data), "typescript")
    block = source.split('export const RIUS_MAIN_AGENT_NAME = "rius.main_agent.name";')[0]
    doc = block[block.rindex("/**") :]
    assert " * @deprecated moved to gen_ai.main_agent.name.\n */\n" in doc
    assert "Deprecated:" not in doc
    assert " * Named the agent this process is" in doc


def test_typescript_keeps_line_comments_on_a_current_constant(base_data):
    source = committed(Registry(base_data), "typescript")
    block = source.split('export const GEN_AI_MAIN_AGENT_ID = "gen_ai.main_agent.id";')[0]
    assert not block.rstrip().endswith("*/")
    assert "@deprecated" not in block.split("\n\n")[-1]


def test_typescript_is_biome_clean_when_biome_is_available(base_data, tmp_path):
    """Optional: runs the TypeScript SDK's own formatter when a checkout with
    node_modules sits next to this repo, so a vendored file never trips the
    SDK's lint job."""
    sdk = ROOT.parent / "rius-sdk-typescript"
    biome = sdk / "node_modules" / ".bin" / "biome"
    if not biome.exists():
        pytest.skip("no rius-sdk-typescript checkout with node_modules alongside")
    target = sdk / "src" / "__rius_semconv_probe__.ts"
    target.write_text(committed(Registry(base_data), "typescript"))
    try:
        result = subprocess.run(
            [str(biome), "check", str(target)], cwd=sdk, capture_output=True, text=True
        )
    finally:
        target.unlink()
    assert result.returncode == 0, result.stdout + result.stderr


# --- Go ----------------------------------------------------------------------


def test_go_header_and_names(base_data):
    source = committed(Registry(base_data), "go")
    assert source.startswith("// Code generated by rius-semconv. DO NOT EDIT.\n")
    consts = go_constants(source)
    assert consts["ServiceName"] == "service.name"
    assert consts["GenAIResponseFinishReason"] == "gen_ai.response.finish_reasons"
    assert consts["OpenInferenceSpanKind"] == "openinference.span.kind"
    assert consts["SpanKindLLM"] == "LLM"
    assert "TracerName" not in consts


@requires_go
def test_go_compiles_and_holds_the_tables(base_data, tmp_path):
    (tmp_path / "go.mod").write_text("module example.com/probe\n\ngo 1.21\n")
    pkg = tmp_path / "semconv"
    pkg.mkdir()
    (pkg / "semconv_generated.go").write_text(committed(Registry(base_data), "go"))
    (tmp_path / "main.go").write_text(
        "package main\n\n"
        'import (\n\t"fmt"\n\n\t"example.com/probe/semconv"\n)\n\n'
        "func main() {\n"
        "\t_, pending := semconv.PendingIdentityAttributes[semconv.RiusSpanPending]\n"
        "\t_, bag := semconv.ContentAttributes[semconv.LLMInvocationParameters]\n"
        '\t_, system := semconv.ContentAttributes[semconv.RiusRequestPrefix+"system"]\n'
        "\tfmt.Println(len(semconv.PendingIdentityAttributes), pending, bag, system,\n"
        '\t\tsemconv.KindByOperation["plan"], semconv.OperationByKind[semconv.SpanKindRetriever],\n'
        '\t\tsemconv.GenAIRequestParameters["n"],\n'
        "\t\tlen(semconv.CredentialHeaderNames), semconv.CredentialHeaderNames[0],\n"
        "\t\tsemconv.CredentialHeaderNameSuffixes[1], semconv.HeaderAttributeSegments[0])\n"
        "}\n"
    )
    out = subprocess.run(
        ["go", "run", "."], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout
    expected = [
        "17",
        "false",
        "true",
        "true",
        "CHAIN",
        "retrieval",
        "gen_ai.request.choice.count",
        "11",
        "authorization",
        "-secret",
        ".headers.",
    ]
    assert out.split() == expected


def test_python_is_ruff_clean_under_the_sdk_settings():
    """The Python SDK's ruff settings (line length 100, py310, E F I UP B SIM
    TID), applied in isolation so this repo's own config does not leak in."""
    ruff = shutil.which("ruff") or str(ROOT / ".venv" / "bin" / "ruff")
    if not pathlib.Path(ruff).exists():
        pytest.skip("needs ruff (pip install -r requirements-dev.txt)")
    target = ROOT / "out" / "python" / "_semconv_generated.py"
    common = ["--isolated", "--line-length", "100", "--target-version", "py310"]
    lint = [ruff, "check", *common, "--select", "E,F,I,UP,B,SIM,TID", str(target)]
    fmt = [ruff, "format", "--check", *common, str(target)]
    for cmd in (lint, fmt):
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
