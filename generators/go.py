"""Emits semconv.go.

Go names are derived from the Python constant name unless the row overrides
them with `go:`. The derivation is intentionally boring: SNAKE_CASE ->
PascalCase with a small initialism table, so a reviewer can predict the name
from the registry without running the generator.
"""

from __future__ import annotations

from .registry import Registry, comment

INITIALISMS = {
    "ID": "ID",
    "GEN": "Gen",
    "AI": "AI",
    "MCP": "MCP",
    "LLM": "LLM",
    "URL": "URL",
    "SDK": "SDK",
    "TTL": "TTL",
}


def go_name(const: str, override: str | None = None) -> str:
    if override:
        return override
    parts = const.split("_")
    out = []
    for part in parts:
        out.append(INITIALISMS.get(part, part.capitalize()))
    return "".join(out)


def render(reg: Registry, preamble: dict) -> str:
    out: list[str] = []

    def ref_name(const: str) -> str:
        """Resolve an allowlist `ref` through the registry so a `go:` override
        on the row is honoured here too."""
        return go_name(const, reg.const(const).get("go"))

    out.extend(comment(preamble["go"]["docstring"], "//"))
    out.append("//")
    out.extend(comment(preamble["header"], "//"))
    out.append(f'package {preamble["go"]["package"]}')
    out.append("")

    out.append("const (")
    first = True
    for entry in reg.symbols():
        if "section" in entry:
            if not first:
                out.append("")
            out.extend(comment(entry["section"], "//", "\t"))
        first = False
        out.extend(comment(entry.get("rationale"), "//", "\t"))
        out.append(f'\t{go_name(entry["const"], entry.get("go"))} = "{entry["key"]}"')

    out.append("")
    out.append("\t// Span kind values (openinference.span.kind).")
    for k in reg.span_kinds():
        kn = INITIALISMS.get(k["name"], k["name"].capitalize())
        out.append(f'\tSpanKind{kn} = "{k["value"]}" // {k["doc"]}')
    out.append(")")

    # Allowlists as package-level vars: Go has no const sets.
    pending = reg.allowlist("pending_identity")
    out.append("")
    out.extend(comment(pending["doc"], "//"))
    out.append("var PendingIdentityAttributes = map[string]struct{}{")
    for e in pending["attributes"]:
        out.extend(comment(e.get("note"), "//", "\t"))
        lit = ref_name(e["ref"]) if "ref" in e else f'"{e["key"]}"'
        out.append(f"\t{lit}: {{}},")
    out.append("}")
    out.append("")
    for e in pending["prefixes"]:
        out.extend(comment(e.get("note"), "//"))
    refs = ", ".join(ref_name(e["ref"]) for e in pending["prefixes"])
    out.append(f"var PendingIdentityPrefixes = []string{{{refs}}}")

    content = reg.allowlist("content")
    out.append("")
    out.extend(comment(content["doc"], "//"))
    out.append("var ContentAttributes = map[string]struct{}{")
    for e in content["attributes"]:
        out.extend(comment(e.get("note"), "//", "\t"))
        lit = ref_name(e["ref"]) if "ref" in e else f'"{e["key"]}"'
        out.append(f"\t{lit}: {{}},")
    out.append("}")

    for spec in reg.partial_content():
        entry = spec["entry"]
        out.append("")
        out.extend(comment(spec["doc"], "//"))
        members = ", ".join(f'"{m}"' for m in spec["members"])
        out.append(f'var {go_name(spec["members_const"])} = []string{{{members}}}')

    for name, block in (
        ("ContentAttributePrefixes", reg.allowlists["content"]["prefixes"]),
        ("ContentAttributeSuffixes", reg.allowlists["content"]["suffixes"]),
    ):
        out.append("")
        out.extend(comment(block["doc"], "//"))
        out.append(f"var {name} = []string{{")
        for value in block["values"]:
            out.append(f'\t"{value}",')
        out.append("}")

    out.append("")
    out.extend(comment(reg.taxonomy["operation_by_kind"]["doc"], "//"))
    out.append("var OperationByKind = map[string]string{")
    for kind, operation in reg.operation_by_kind().items():
        out.append(f'\tSpanKind{INITIALISMS.get(kind, kind.capitalize())}: "{operation}",')
    out.append("}")

    out.append("")
    out.append("// The reverse direction, for normalizing foreign traffic that carries")
    out.append("// gen_ai.operation.name but no openinference.span.kind.")
    out.append("var KindByOperation = map[string]string{")
    for operation, kind in reg.taxonomy["kind_by_operation"]["map"].items():
        out.append(f'\t"{operation}": SpanKind{INITIALISMS.get(kind, kind.capitalize())},')
    out.append("}")
    out.append("")
    return "\n".join(out)
