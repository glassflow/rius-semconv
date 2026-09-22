"""Emits semconv.ts."""

from __future__ import annotations

from .registry import Registry, comment

TAIL = """
/** The OpenTelemetry `SpanKind` field a span of taxonomy `kind` should carry. */
export function otelSpanKind(kind: SpanKind): OtelSpanKind {
  return OTEL_KIND_BY_KIND[kind];
}

/**
 * Identity attributes for a span of `kind`, for setting AT CREATION.
 * Set at creation so pending-span snapshots can classify the span.
 *
 * `name` is the span name. The GenAI execute-tool convention requires
 * `gen_ai.tool.name`, and for a local tool the span name IS the tool name,
 * so a TOOL span with a name gets it here rather than relying on every
 * caller to remember.
 */
export function kindAttributes(kind: SpanKind, name?: string): Record<string, string> {
  const attributes: Record<string, string> = { [OPENINFERENCE_SPAN_KIND]: kind };
  const operation = OPERATION_BY_KIND[kind];
  if (operation !== undefined) attributes[GEN_AI_OPERATION_NAME] = operation;
  if (kind === SpanKind.TOOL && name !== undefined) attributes[GEN_AI_TOOL_NAME] = name;
  return attributes;
}
"""


def _member(entry: dict, out: list[str]) -> None:
    out.extend(comment(entry.get("note"), "//", "  "))
    if "ref" in entry:
        out.append(f"  {entry['ref']},")
    else:
        out.append(f'  "{entry["key"]}",')


def render(reg: Registry, preamble: dict) -> str:
    out: list[str] = []
    out.extend(comment(preamble["header"], "//"))
    out.append("")
    out.append(preamble["typescript"]["imports"].rstrip("\n"))

    for entry in reg.symbols():
        if "section" in entry:
            out.append("")
            out.extend(comment(entry["section"], "//"))
        out.extend(comment(entry.get("rationale"), "//"))
        out.append(f'export const {entry["const"]} = "{entry["key"]}";')

    pending = reg.allowlist("pending_identity")
    out.append("")
    out.extend(comment(pending["doc"], "//"))
    out.append("export const PENDING_IDENTITY_ATTRIBUTES: ReadonlySet<string> = new Set([")
    for e in pending["attributes"]:
        _member(e, out)
    out.append("]);")
    for e in pending["prefixes"]:
        out.extend(comment(e.get("note"), "//"))
    refs = ", ".join(e["ref"] for e in pending["prefixes"])
    out.append(f"export const PENDING_IDENTITY_PREFIXES: readonly string[] = [{refs}];")

    content = reg.allowlist("content")
    out.append("")
    out.extend(comment(content["doc"], "//"))
    out.append("export const CONTENT_ATTRIBUTES: ReadonlySet<string> = new Set([")
    for e in content["attributes"]:
        _member(e, out)
    out.append("]);")

    for spec in reg.partial_content():
        entry = spec["entry"]
        out.append("")
        out.extend(comment(entry.get("rationale"), "//"))
        out.append(f'export const {entry["const"]} = "{entry["key"]}";')
        out.extend(comment(spec["doc"], "//"))
        members = ", ".join(f'"{m}"' for m in spec["members"])
        out.append(
            f'export const {spec["members_const"]}: readonly string[] = [{members}];'
        )

    for const, block in (
        ("CONTENT_ATTRIBUTE_PREFIXES", reg.allowlists["content"]["prefixes"]),
        ("CONTENT_ATTRIBUTE_SUFFIXES", reg.allowlists["content"]["suffixes"]),
    ):
        out.append("")
        out.extend(comment(block["doc"], "//"))
        out.append(f"export const {const}: readonly string[] = [")
        for value in block["values"]:
            out.append(f'  "{value}",')
        out.append("];")

    kinds = reg.span_kinds()
    out.append("")
    out.extend(comment(reg.taxonomy["span_kind"]["doc"], "//"))
    out.append("export enum SpanKind {")
    for k in kinds:
        out.append(f'  {k["name"]} = "{k["value"]}", // {k["doc"]}')
    out.append("}")

    out.append("")
    out.extend(comment(reg.taxonomy["operation_by_kind"]["doc"], "//"))
    out.append("const OPERATION_BY_KIND: Partial<Record<SpanKind, string>> = {")
    for kind, operation in reg.operation_by_kind().items():
        out.append(f'  [SpanKind.{kind}]: "{operation}",')
    out.append("};")

    out.append("")
    out.extend(comment(reg.taxonomy["otel_kind_by_kind"]["doc"], "//"))
    out.append("const OTEL_KIND_BY_KIND: Record<SpanKind, OtelSpanKind> = {")
    for kind, otel in reg.otel_kind_by_kind().items():
        out.append(f"  [SpanKind.{kind}]: OtelSpanKind.{otel},")
    out.append("};")

    return "\n".join(out) + TAIL
