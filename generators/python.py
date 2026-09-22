"""Emits semconv.py.

One template, read top to bottom. The only clever part is `_blank`: a blank
line goes before a row that opens a section, and nowhere else.
"""

from __future__ import annotations

from .registry import Registry, comment

TAIL = '''

def otel_span_kind(kind: SpanKind) -> OtelSpanKind:
    """The OpenTelemetry ``SpanKind`` field a span of taxonomy ``kind`` should carry."""
    return _OTEL_KIND_BY_KIND[kind]


def kind_attributes(kind: SpanKind, name: str | None = None) -> dict[str, str]:
    """Identity attributes for a span of ``kind``, for setting at CREATION.

    Pending snapshots (pending.py) are built at ``on_start``, so taxonomy set
    via ``set_attribute`` afterwards is invisible to them; passing these at
    span creation is what makes a pending span classifiable.

    ``name`` is the span name. The GenAI execute-tool convention requires
    ``gen_ai.tool.name``, and for a local tool the span name IS the tool
    name, so a TOOL span with a name gets it here rather than relying on
    every caller to remember.
    """
    attributes = {OPENINFERENCE_SPAN_KIND: kind.value}
    operation = _OPERATION_BY_KIND.get(kind)
    if operation is not None:
        attributes[GEN_AI_OPERATION_NAME] = operation
    if kind is SpanKind.TOOL and name is not None:
        attributes[GEN_AI_TOOL_NAME] = name
    return attributes


def set_span_kind(span: Span, kind: SpanKind) -> None:
    """Stamp a span with its OpenInference kind and (if applicable) gen_ai operation."""
    span.set_attribute(OPENINFERENCE_SPAN_KIND, kind.value)
    operation = _OPERATION_BY_KIND.get(kind)
    if operation is not None:
        span.set_attribute(GEN_AI_OPERATION_NAME, operation)
'''


def _member(entry: dict, out: list[str]) -> None:
    """One member of a frozenset/tuple literal: `ref` -> identifier, `key` -> string."""
    out.extend(comment(entry.get("note"), "#", "        "))
    if "ref" in entry:
        out.append(f"        {entry['ref']},")
    else:
        out.append(f'        "{entry["key"]}",')


def render(reg: Registry, preamble: dict) -> str:
    out: list[str] = []

    out.append('"""' + preamble["python"]["docstring"].rstrip("\n"))
    out.append('"""')
    out.append("")
    out.extend(comment(preamble["header"], "#"))
    out.append("")
    out.append(preamble["python"]["imports"].rstrip("\n"))
    out.append("")

    # --- constants ---
    for entry in reg.symbols():
        if "section" in entry or entry.get("blank_before"):
            out.append("")
        if "section" in entry:
            out.extend(comment(entry["section"], "#"))
        out.extend(comment(entry.get("rationale"), "#"))
        out.append(f'{entry["const"]} = "{entry["key"]}"')

    # --- pending allowlist ---
    pending = reg.allowlist("pending_identity")
    out.append("")
    out.extend(comment(pending["doc"], "#"))
    out.append("PENDING_IDENTITY_ATTRIBUTES = frozenset(")
    out.append("    {")
    for e in pending["attributes"]:
        _member(e, out)
    out.append("    }")
    out.append(")")
    for e in pending["prefixes"]:
        out.extend(comment(e.get("note"), "#"))
    refs = ", ".join(e["ref"] for e in pending["prefixes"])
    trailing = "," if len(pending["prefixes"]) == 1 else ""
    out.append(f"PENDING_IDENTITY_PREFIXES = ({refs}{trailing})")

    # --- content allowlist ---
    content = reg.allowlist("content")
    out.append("")
    out.extend(comment(content["doc"], "#"))
    out.append("CONTENT_ATTRIBUTES = frozenset(")
    out.append("    {")
    for e in content["attributes"]:
        _member(e, out)
    out.append("    }")
    out.append(")")

    # --- partially sensitive bags ---
    for spec in reg.partial_content():
        entry = spec["entry"]
        out.append("")
        out.extend(comment(entry.get("rationale"), "#"))
        out.append(f'{entry["const"]} = "{entry["key"]}"')
        out.extend(comment(spec["doc"], "#"))
        members = ", ".join(f'"{m}"' for m in spec["members"])
        out.append(f'{spec["members_const"]} = ({members})')

    # --- prefixes / suffixes ---
    for const, block in (
        ("CONTENT_ATTRIBUTE_PREFIXES", reg.allowlists["content"]["prefixes"]),
        ("CONTENT_ATTRIBUTE_SUFFIXES", reg.allowlists["content"]["suffixes"]),
    ):
        out.append("")
        out.extend(comment(block["doc"], "#"))
        out.append(f"{const} = (")
        for value in block["values"]:
            out.append(f'    "{value}",')
        out.append(")")

    # --- span kind enum ---
    kinds = reg.span_kinds()
    out.append("")
    out.append("")
    out.append("class SpanKind(str, Enum):")
    out.append(
        '    """Observation kind. Values are OpenInference '
        "``openinference.span.kind`` values."
    )
    out.append("")
    for k in kinds:
        out.append(f'    - ``{k["name"]}``: {k["doc"]}')
    out.append('    """')
    out.append("")
    for k in kinds:
        out.append(f'    {k["name"]} = "{k["value"]}"')

    # --- maps ---
    out.append("")
    out.append("")
    out.extend(comment(reg.taxonomy["operation_by_kind"]["doc"], "#"))
    out.append("_OPERATION_BY_KIND: dict[SpanKind, str] = {")
    for kind, operation in reg.operation_by_kind().items():
        out.append(f'    SpanKind.{kind}: "{operation}",')
    out.append("}")

    out.append("")
    out.append("")
    out.extend(comment(reg.taxonomy["otel_kind_by_kind"]["doc"], "#"))
    out.append("_OTEL_KIND_BY_KIND: dict[SpanKind, OtelSpanKind] = {")
    for kind, otel in reg.otel_kind_by_kind().items():
        out.append(f"    SpanKind.{kind}: OtelSpanKind.{otel},")
    out.append("}")

    out.append("")
    return "\n".join(out) + TAIL
