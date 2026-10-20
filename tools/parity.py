"""Surface extraction and comparison for the parity checks.

Parity is checked on EVALUATED values, not on source text: the Python file is
executed, the TypeScript file is run through Node, and Go constants are read
from their literal declarations. Comments, formatting and whether a value is
spelled as a literal or as a reference to another constant are therefore
invisible, which is the point: those are the parts the generated file is free
to differ in.

Order is not invisible. Lists and tuples compare in order, and a mapping or an
enum whose entries are equal but listed in another order is REORDERED, which
fails: in the request-parameter map the first spelling listed wins, so two
tables with the same entries can still behave differently. Sets, and Go maps,
have no order to compare.

Normalized values are JSON-shaped so they compare with `==` and print well:
  set / frozenset / Set    -> {"__set__": [sorted members]}
  tuple                    -> {"__tuple__": [...]}   (kept distinct from list:
                              str.startswith needs a tuple)
  Python Enum class        -> {"__enum__": {name: value}}
  our SpanKind member      -> its value ("LLM"), which is also what a
                              TypeScript string enum member evaluates to
  OpenTelemetry SpanKind   -> its name ("CLIENT"), in both languages, via
                              the stubs below. The generated Python holds the
                              name itself, so it compares with the TypeScript
                              table and with an SDK copy that still holds the
                              OpenTelemetry member
"""

from __future__ import annotations

import contextlib
import enum
import json
import re
import shutil
import subprocess
import sys
import tempfile
import types
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

OTEL_KINDS = ("INTERNAL", "SERVER", "CLIENT", "PRODUCER", "CONSUMER")
MODULE = "semconv_under_test"


class ToolMissing(RuntimeError):
    """A language toolchain the check needs is not installed."""


# --- Python --------------------------------------------------------------------


@contextlib.contextmanager
def _otel_stub() -> Iterator[None]:
    """Swap in a minimal `opentelemetry.trace` for the duration of an exec, so
    the check needs no OpenTelemetry install and never sees a real one."""
    otel = types.ModuleType("opentelemetry")
    trace = types.ModuleType("opentelemetry.trace")

    class Span:  # noqa: D401 - a stand-in type, never instantiated
        pass

    trace.Span = Span
    trace.SpanKind = enum.Enum("SpanKind", {k: i for i, k in enumerate(OTEL_KINDS)})
    trace.SpanKind.__module__ = "opentelemetry.trace"
    otel.trace = trace
    saved = {k: sys.modules.get(k) for k in ("opentelemetry", "opentelemetry.trace")}
    sys.modules["opentelemetry"] = otel
    sys.modules["opentelemetry.trace"] = trace
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _exec_python(source: str) -> dict[str, Any]:
    module = types.ModuleType(MODULE)
    with _otel_stub():
        exec(compile(source, f"<{MODULE}>", "exec"), module.__dict__)  # noqa: S102
    return module.__dict__


def _norm_py(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        if type(value).__module__ == "opentelemetry.trace":
            return value.name
        return value.value
    if isinstance(value, (set, frozenset)):
        return {"__set__": sorted(_norm_py(v) for v in value)}
    if isinstance(value, tuple):
        return {"__tuple__": [_norm_py(v) for v in value]}
    if isinstance(value, list):
        return [_norm_py(v) for v in value]
    if isinstance(value, dict):
        return {_norm_py(k): _norm_py(v) for k, v in value.items()}
    return value


def python_surface(source: str, *, raw: bool = False) -> dict[str, Any]:
    """name -> normalized value, for every module-level DATA name.

    Functions, imported names and dunders are skipped; Enum classes defined in
    the module are data. `raw=True` returns the executed globals instead.
    """
    namespace = _exec_python(source)
    if raw:
        return namespace
    out: dict[str, Any] = {}
    for name, value in namespace.items():
        if name.startswith("__") or name == "annotations":
            continue
        if isinstance(value, type):
            if issubclass(value, enum.Enum) and value.__module__ == MODULE:
                out[name] = {"__enum__": {m.name: m.value for m in value}}
            continue
        if callable(value) or isinstance(value, types.ModuleType):
            continue
        out[name] = _norm_py(value)
    return out


# --- TypeScript ----------------------------------------------------------------

# Values match the Python stub's normalized form, so the two languages compare.
_TS_API_STUB = "export const SpanKind = {" + ", ".join(f'{k}: "{k}"' for k in OTEL_KINDS) + "};\n"
# The real values of the constants the SDK imports; kept deliberately short.
_TS_SEMCONV_STUB = (
    'export const ATTR_SERVICE_NAME = "service.name";\n'
    'export const ATTR_SERVICE_VERSION = "service.version";\n'
)
_TS_DUMP = """
const m = await import("./mod.ts");
const norm = (v) =>
  v instanceof Set ? { __set__: [...v].map(norm).sort() }
  : Array.isArray(v) ? v.map(norm)
  : v && typeof v === "object"
    ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, norm(x)]))
    : v;
const out = {};
for (const [k, v] of Object.entries(m)) {
  if (typeof v === "function") continue;
  out[k] = norm(v);
}
process.stdout.write(JSON.stringify(out));
"""
_TS_PRIVATE_CONST = re.compile(r"^const ([A-Za-z_$][A-Za-z0-9_$]*)\b", re.M)
_PRIVATE_ALIAS = "__private__"


def node_binary() -> str:
    node = shutil.which("node")
    if node is None:
        raise ToolMissing("node is required for the TypeScript check (Node >= 22.7)")
    return node


def ts_surface(source: str) -> dict[str, tuple[Any, bool]]:
    """name -> (normalized value, is_exported), for every top-level const,
    enum and exported value. Unexported top-level consts are exported under
    an alias for the evaluation only, so tables like OPERATION_BY_KIND can be
    compared even while the SDK keeps them private."""
    node = node_binary()
    private = _TS_PRIVATE_CONST.findall(source)
    patched = source
    if private:
        aliases = ", ".join(f"{n} as {_PRIVATE_ALIAS}{n}" for n in private)
        patched += f"\nexport {{ {aliases} }};\n"
    with tempfile.TemporaryDirectory() as tmp:
        root = __import__("pathlib").Path(tmp)
        (root / "package.json").write_text('{"type": "module"}\n')
        for pkg, body in (("api", _TS_API_STUB), ("semantic-conventions", _TS_SEMCONV_STUB)):
            d = root / "node_modules" / "@opentelemetry" / pkg
            d.mkdir(parents=True)
            (d / "package.json").write_text(
                json.dumps({"name": f"@opentelemetry/{pkg}", "type": "module", "main": "index.js"})
            )
            (d / "index.js").write_text(body)
        (root / "mod.ts").write_text(patched)
        (root / "dump.mjs").write_text(_TS_DUMP)
        result = subprocess.run(
            [node, "--experimental-transform-types", "--no-warnings", "dump.mjs"],
            cwd=root,
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        raise RuntimeError(f"node could not evaluate the TypeScript source:\n{result.stderr}")
    raw = json.loads(result.stdout)
    out: dict[str, tuple[Any, bool]] = {}
    for name, value in raw.items():
        if name.startswith(_PRIVATE_ALIAS):
            out[name[len(_PRIVATE_ALIAS) :]] = (value, False)
        else:
            out[name] = (value, True)
    return out


# --- Go ------------------------------------------------------------------------

_GO_BLOCK = re.compile(r"^const \($(.*?)^\)", re.M | re.S)
_GO_SINGLE = re.compile(r'^const ([A-Za-z_]\w*)\s*=\s*"((?:[^"\\]|\\.)*)"', re.M)
_GO_ENTRY = re.compile(r'^\s*([A-Za-z_]\w*)\s*=\s*"((?:[^"\\]|\\.)*)"', re.M)


def go_constants(source: str) -> dict[str, str]:
    """Untyped string constants, from `const X = "..."` and `const ( ... )`.
    The backend's semconv package declares nothing else as a constant."""
    out = dict(_GO_SINGLE.findall(source))
    for block in _GO_BLOCK.findall(source):
        out.update(_GO_ENTRY.findall(block))
    return {k: json.loads(f'"{v}"') for k, v in out.items()}


# --- comparisons ----------------------------------------------------------------


@dataclass
class Report:
    changed: list[str] = field(default_factory=list)
    not_in_sdk: list[str] = field(default_factory=list)
    uncovered_public: list[str] = field(default_factory=list)
    uncovered_private: list[str] = field(default_factory=list)
    reordered: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.changed or self.not_in_sdk or self.uncovered_public or self.reordered)


def _ordered(value: Any) -> Any:
    """`value` with every mapping turned into its (key, value) pairs in order,
    so that `==` sees the order too."""
    if isinstance(value, dict):
        return [[k, _ordered(v)] for k, v in value.items()]
    if isinstance(value, list):
        return [_ordered(v) for v in value]
    return value


def compare(
    reference: dict[str, Any], generated: dict[str, Any], *, private: Callable[[str], bool]
) -> Report:
    """Generated module vs the SDK's hand-written file.

    changed           same name, different value
    not_in_sdk        the registry emits it, the SDK does not have it
    uncovered_public  the SDK exports a data name the registry does not cover
    uncovered_private the SDK has a private data name the registry does not
                      cover; reported, not failed, since a private table can
                      legitimately be logic's own business
    reordered         same entries, listed in a different order
    """
    report = Report()
    for name in sorted(generated):
        if name not in reference:
            report.not_in_sdk.append(name)
        elif reference[name] != generated[name]:
            report.changed.append(name)
        elif _ordered(reference[name]) != _ordered(generated[name]):
            report.reordered.append(name)
    for name in sorted(set(reference) - set(generated)):
        (report.uncovered_private if private(name) else report.uncovered_public).append(name)
    return report


@dataclass
class GoReport:
    changed: list[str] = field(default_factory=list)
    renamed: list[tuple[str, str]] = field(default_factory=list)
    unclassified: list[str] = field(default_factory=list)
    generated_only: list[str] = field(default_factory=list)
    classified: list[str] = field(default_factory=list)
    stale_gaps: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.changed or self.renamed or self.unclassified)


def compare_go(
    reference: dict[str, str], generated: dict[str, str], gaps: dict[str, dict]
) -> GoReport:
    """Generated canonical constants vs the backend's semconv.go.

    changed        same name, different value
    renamed        (generated, reference): one value under two names; the
                   registry's `go:` override must adopt the backend's name
    unclassified   in the backend only, and not explained in the gaps file
    generated_only new to the backend; harmless, added when it migrates
    classified     in the backend only, explained in the gaps file
    stale_gaps     gaps entries that no longer describe the backend
    """
    report = GoReport()
    by_value: dict[str, list[str]] = {}
    for name, value in reference.items():
        by_value.setdefault(value, []).append(name)
    for name in sorted(generated):
        if name in reference:
            if reference[name] != generated[name]:
                report.changed.append(name)
            continue
        others = [n for n in by_value.get(generated[name], []) if n not in generated]
        if others:
            report.renamed.extend((name, other) for other in sorted(others))
        else:
            report.generated_only.append(name)
    renamed_refs = {ref for _gen, ref in report.renamed}
    for name in sorted(set(reference) - set(generated) - renamed_refs):
        (report.classified if name in gaps else report.unclassified).append(name)
    report.stale_gaps = sorted(n for n in gaps if n not in reference or n in generated)
    return report


@dataclass
class CrossReport:
    differ: list[str] = field(default_factory=list)
    python_only: list[str] = field(default_factory=list)
    typescript_only: list[str] = field(default_factory=list)


def _cross_norm(value: Any) -> Any:
    """Collapse the Python-only distinctions a TypeScript value cannot have."""
    if isinstance(value, dict):
        if set(value) == {"__tuple__"}:
            return [_cross_norm(v) for v in value["__tuple__"]]
        if set(value) == {"__enum__"}:
            return _cross_norm(value["__enum__"])
        return {k: _cross_norm(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_cross_norm(v) for v in value]
    return value


def cross_compare(python: dict[str, Any], typescript: dict[str, tuple[Any, bool]]) -> CrossReport:
    """The two SDKs' hand-written files against each other, by name. A Python
    `_PRIVATE` name matches the TypeScript `PRIVATE` one."""
    report = CrossReport()
    ts = {name: value for name, (value, _exported) in typescript.items()}
    py = {name.lstrip("_"): (name, value) for name, value in python.items()}
    for bare, (name, value) in sorted(py.items()):
        if bare not in ts:
            report.python_only.append(name)
        elif _cross_norm(value) != _cross_norm(ts[bare]):
            report.differ.append(name)
    report.typescript_only = sorted(set(ts) - set(py))
    return report
