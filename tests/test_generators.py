"""The three generators: deterministic, committed output current, and the
emitted values are the registry's.

Values are checked by EVALUATING the generated code (Python exec, Node for
TypeScript, the Go compiler), not by grepping it, because the parity tools
compare evaluated values too.
"""

import pathlib
import re
import shutil
import subprocess

import pytest

from conftest import ROOT, requires_go, requires_node
from generators import generate
from generators.registry import Registry
from tools.parity import go_constants, python_surface, ts_surface

TICKET = re.compile(r"\b(?:RIUS|GLA2?)-\d+\b")


def render(registry, lang):
    return generate.TARGETS[lang].render(registry)


@pytest.fixture(scope="module")
def py_module(base_data):
    return python_surface(render(Registry(base_data), "python"))


# --- determinism and freshness ----------------------------------------------


@pytest.mark.parametrize("lang", ["python", "typescript", "go"])
def test_rendering_is_deterministic(base_data, lang):
    if lang == "go" and shutil.which("gofmt") is None:
        pytest.skip("needs gofmt")
    first = render(Registry(base_data), lang)
    second = render(Registry(base_data), lang)
    assert first == second


def test_committed_output_is_current():
    """What CI's staleness job runs. Fails if out/ lags the registry."""
    assert generate.main(["--check"]) == 0


def test_check_detects_a_stale_file(tmp_path):
    assert generate.main(["--out", str(tmp_path)]) == 0
    stale = tmp_path / "python" / "_semconv_generated.py"
    stale.write_text(stale.read_text() + "# drift\n")
    assert generate.main(["--out", str(tmp_path), "--check"]) == 1


def test_generation_refuses_a_registry_that_fails_lint(monkeypatch, base_data, tmp_path):
    import copy

    broken = copy.deepcopy(base_data)
    broken["attributes"]["attributes"][0]["divergence"] = ""
    monkeypatch.setattr(generate, "load_data", lambda: broken)
    assert generate.main(["--out", str(tmp_path)]) == 2


@pytest.mark.parametrize("lang", ["python", "typescript", "go"])
def test_no_ticket_ids_in_output(base_data, lang):
    if lang == "go" and shutil.which("gofmt") is None:
        pytest.skip("needs gofmt")
    assert not TICKET.findall(render(Registry(base_data), lang))


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
    assert "TELEMETRY_DISTRO_NAME" not in py_module  # planned


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


def test_python_tables(py_module):
    assert py_module["_OPERATION_BY_KIND"]["LLM"] == "chat"
    assert "CHAIN" not in py_module["_OPERATION_BY_KIND"]
    assert py_module["_KIND_BY_OPERATION"]["plan"] == "CHAIN"
    assert py_module["_OPERATION_BY_KIND"]["RERANKER"] == "rerank"
    assert py_module["_KIND_BY_OPERATION"]["rerank"] == "RERANKER"
    assert py_module["_OTEL_KIND_BY_KIND"]["TOOL"] == "OtelSpanKind.INTERNAL"
    assert py_module["_NAME_TARGET_BY_KIND"]["RETRIEVER"] == "gen_ai.data_source.id"
    params = py_module["GEN_AI_REQUEST_PARAMETERS"]
    assert params["maxOutputTokens"] == "gen_ai.request.max_tokens"
    assert "top_logprobs" not in params
    assert py_module["SpanKind"] == {
        "__enum__": {
            k: k for k in ["AGENT", "LLM", "TOOL", "RETRIEVER", "EMBEDDING", "RERANKER", "CHAIN"]
        }
    }


def test_python_all_lists_exactly_the_public_names(base_data):
    namespace = {}
    source = render(Registry(base_data), "python")
    surface = python_surface(source)
    exec_globals = python_surface(source, raw=True)
    namespace.update(exec_globals)
    public = {n for n in surface if not n.startswith("_")}
    assert set(namespace["__all__"]) == public


def test_python_include_planned_adds_planned_rows(base_data):
    surface = python_surface(render(Registry(base_data, include_planned=True), "python"))
    assert surface["TELEMETRY_DISTRO_NAME"] == "telemetry.distro.name"


# --- TypeScript --------------------------------------------------------------


@requires_node
def test_typescript_values(base_data):
    surface = ts_surface(render(Registry(base_data), "typescript"))
    values = {name: value for name, (value, _public) in surface.items()}
    assert values["TRACER_NAME"] == "rius"
    assert values["SERVICE_VERSION"] == "service.version"  # via ATTR_SERVICE_VERSION
    content = values["CONTENT_ATTRIBUTES"]["__set__"]
    assert "llm.invocation_parameters" in content
    assert "rius.request.tools" in content
    assert "langfuse.trace.input" in content  # folded in from the third-party list
    assert values["CONTENT_ATTRIBUTE_PREFIXED_SUFFIXES"] == [
        ["llm.request.functions.", [".description", ".parameters", ".arguments"]]
    ]
    assert len(values["PENDING_IDENTITY_ATTRIBUTES"]["__set__"]) == 17
    assert values["OTEL_KIND_BY_KIND"]["LLM"] == "OtelSpanKind.CLIENT"
    assert values["SpanKind"]["RETRIEVER"] == "RETRIEVER"


def test_typescript_aliases_upstream_constant(base_data):
    source = render(Registry(base_data), "typescript")
    assert 'import { ATTR_SERVICE_VERSION } from "@opentelemetry/semantic-conventions";' in source
    assert "export const SERVICE_VERSION = ATTR_SERVICE_VERSION;" in source


def test_typescript_is_biome_clean_when_biome_is_available(base_data, tmp_path):
    """Optional: runs the TypeScript SDK's own formatter when a checkout with
    node_modules sits next to this repo, so a vendored file never trips the
    SDK's lint job."""
    sdk = ROOT.parent / "rius-sdk-typescript"
    biome = sdk / "node_modules" / ".bin" / "biome"
    if not biome.exists():
        pytest.skip("no rius-sdk-typescript checkout with node_modules alongside")
    target = sdk / "src" / "__rius_semconv_probe__.ts"
    target.write_text(render(Registry(base_data), "typescript"))
    try:
        result = subprocess.run(
            [str(biome), "check", str(target)], cwd=sdk, capture_output=True, text=True
        )
    finally:
        target.unlink()
    assert result.returncode == 0, result.stdout + result.stderr


# --- Go ----------------------------------------------------------------------


def test_go_header_and_names(base_data):
    if shutil.which("gofmt") is None:
        pytest.skip("needs gofmt")
    source = render(Registry(base_data), "go")
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
    (pkg / "semconv_generated.go").write_text(render(Registry(base_data), "go"))
    (tmp_path / "main.go").write_text(
        "package main\n\n"
        'import (\n\t"fmt"\n\n\t"example.com/probe/semconv"\n)\n\n'
        "func main() {\n"
        "\t_, pending := semconv.PendingIdentityAttributes[semconv.RiusSpanPending]\n"
        "\t_, bag := semconv.ContentAttributes[semconv.LLMInvocationParameters]\n"
        "\tfmt.Println(len(semconv.PendingIdentityAttributes), pending, bag,\n"
        '\t\tsemconv.KindByOperation["plan"], semconv.OperationByKind[semconv.SpanKindRetriever],\n'
        '\t\tsemconv.GenAIRequestParameters["n"])\n'
        "}\n"
    )
    out = subprocess.run(
        ["go", "run", "."], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout
    expected = ["17", "false", "true", "CHAIN", "retrieval", "gen_ai.request.choice.count"]
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
