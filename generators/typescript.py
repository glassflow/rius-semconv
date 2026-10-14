"""Emits the TypeScript constants module (`semconv.generated.ts`).

Constants and tables only. The SDK's hand-written semconv.ts re-exports this
module and keeps the helper functions (kindAttributes, composeSpanName,
requestAttributeKey, ...), because logic is not registry data.

Output is shaped to pass `biome check` under the TypeScript SDK's
configuration (100 columns, double quotes, trailing commas), so vendoring it
needs no lint exemption. Arrays that fit on one line are emitted on one line,
the way biome's formatter prints them.
"""

from __future__ import annotations

import json
import re

from .registry import Registry, comment

LANG = "typescript"
WIDTH = 100
IDENT = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


def _literal(value: str) -> str:
    return json.dumps(value)


def _prop(key: str) -> str:
    return key if IDENT.match(key) else _literal(key)


def _ref_or_literal(reg: Registry, key: str) -> str:
    const = reg.const_for_key(key, LANG)
    return const if const is not None else _literal(key)


def _deprecated_doc(rationale: str | None) -> list[str]:
    """A deprecated constant's rationale as JSDoc ending in an @deprecated tag,
    so editors strike the constant through. The rationale's opening
    `Deprecated: ...` line, which names the successor, becomes the tag."""
    lines = (rationale or "").rstrip("\n").split("\n") if rationale else []
    tag = "@deprecated"
    if lines and lines[0].startswith("Deprecated: "):
        tag = f"{tag} {lines.pop(0).removeprefix('Deprecated: ')}"
    body = [f" * {line}".rstrip() for line in lines]
    return ["/**", *body, *([" *"] if body else []), f" * {tag}", " */"]


def _array(head: str, items: list[str], tail: str = ";") -> list[str]:
    """`head[items]tail` on one line when it fits, else one item per line."""
    flat = f"{head}[{', '.join(items)}]{tail}"
    if len(flat) <= WIDTH:
        return [flat]
    return [f"{head}[", *(f"  {i}," for i in items), f"]{tail}"]


def _set(head: str, members: list[dict], extra: list[str] | None = None) -> list[str]:
    out = [f"{head}new Set(["]
    for m in members:
        out.extend(comment(m.get("note"), "//", "  "))
        out.append(f"  {m['ref'] if 'ref' in m else _literal(m['key'])},")
    out.extend(extra or [])
    out.append("]);")
    return out


def render(reg: Registry) -> str:
    pre = reg.preamble
    al = reg.allowlists
    sk = reg.taxonomy["span_kind"]
    kind_type = sk["names"][LANG]
    out: list[str] = []

    out.extend(comment(pre["notice"], "//"))
    out.extend(comment(pre["header"], "//"))
    out.append("")
    if reg.table("otel_kind_by_kind", LANG) is not None:
        out.append('import { SpanKind as OtelSpanKind } from "@opentelemetry/api";')
    aliases: dict[str, list[str]] = {}
    for row in reg.rows(LANG):
        if "ts_alias" in row:
            aliases.setdefault(row["ts_alias"]["from"], []).append(row["ts_alias"]["name"])
    for module in sorted(aliases):
        out.append(f"import {{ {', '.join(sorted(aliases[module]))} }} from {_literal(module)};")

    # --- constants ---
    for row in reg.rows(LANG):
        if "section" in row or "rationale" in row:
            out.append("")
        out.extend(comment(row.get("section"), "//"))
        if "deprecated" in row:
            out.extend(_deprecated_doc(row.get("rationale")))
        else:
            out.extend(comment(row.get("rationale"), "//"))
        value = row["ts_alias"]["name"] if "ts_alias" in row else _literal(row["key"])
        out.append(f"export const {row['const']} = {value};")

    # --- request parameters ---
    mp = reg.model_parameters
    out.append("")
    out.extend(comment(mp["doc"], "//"))
    out.append(f"export const {mp['const']}: Readonly<Record<string, string>> = {{")
    for spelling, target, note in reg.model_parameter_items():
        out.extend(comment(note, "//", "  "))
        out.append(f"  {_prop(spelling)}: {_ref_or_literal(reg, target)},")
    out.append("};")

    # --- allowlists ---
    pending = al["pending_identity"]
    out.append("")
    out.extend(comment(pending["doc"], "//"))
    out.extend(
        _set(
            f"export const {pending['const']}: ReadonlySet<string> = ",
            reg.members("pending_identity", LANG),
        )
    )

    prefixes = al["pending_identity_prefixes"]
    out.append("")
    out.extend(comment(prefixes["doc"], "//"))
    out.extend(_array(f"export const {prefixes['const']}: readonly string[] = ", prefixes["refs"]))

    members = al["invocation_parameters_content_members"]
    out.append("")
    out.extend(comment(members["doc"], "//"))
    out.extend(
        _array(
            f"export const {members['const']}: readonly string[] = ",
            [_literal(v) for v in members["values"]],
        )
    )

    def member_set(section: str) -> None:
        block = al[section]
        out.append("")
        out.extend(comment(block["doc"], "//"))
        out.extend(
            _set(
                f"export const {block['const']}: ReadonlySet<string> = ",
                reg.members(section, LANG),
            )
        )

    def string_array(section: str) -> None:
        block = al[section]
        out.append("")
        out.extend(comment(block["doc"], "//"))
        out.extend(
            _array(
                f"export const {block['const']}: readonly string[] = ",
                [_literal(v) for v in block["values"]],
            )
        )

    # Before CONTENT_ATTRIBUTES, which spreads them in by name.
    for section in reg.included("content"):
        member_set(section)

    content = al["content"]
    derived = content.get("derived")
    extra: list[str] = []
    if derived:
        extra.extend(comment(derived.get("note"), "//", "  "))
        extra.append(f"  ...[{', '.join(derived['prefixes'])}].flatMap((prefix) =>")
        extra.append(f"    {derived['members']}.map((member) => `${{prefix}}${{member}}`),")
        extra.append("  ),")
    for section in reg.included("content"):
        extra.append(f"  ...{al[section]['const']},")
    out.append("")
    out.extend(comment(content["doc"], "//"))
    out.extend(
        _set(
            f"export const {content['const']}: ReadonlySet<string> = ",
            reg.members("content", LANG),
            extra,
        )
    )

    string_array("content_prefixes")
    member_set("content_prefix_identity")
    string_array("content_suffixes")

    block = al["content_prefixed_suffixes"]
    out.append("")
    out.extend(comment(block["doc"], "//"))
    # The annotation is laid out the way biome formats it, which is what the
    # consumer's lint enforces.
    out.append(f"export const {block['const']}: readonly (readonly [")
    out.append("  string,")
    out.append("  readonly string[],")
    entries = [
        f"[{_literal(e['prefix'])}, [{', '.join(_literal(s) for s in e['suffixes'])}]]"
        for e in block["values"]
    ]
    out.extend(_array("])[] = ", entries))

    # --- span kinds ---
    out.append("")
    out.extend(comment(sk["doc"].replace("``", "`"), "//"))
    out.append(f"export enum {kind_type} {{")
    for k in sk["values"]:
        out.append(f"  {k['name']} = {_literal(k['name'])}, // {k['doc']}")
    out.append("}")

    # --- tables ---
    for name, key_fmt, value_fmt, annotation in (
        ("operation_by_kind", "kind", "literal", f"Partial<Record<{kind_type}, string>>"),
        ("kind_by_operation", "literal", "kind", f"Record<string, {kind_type}>"),
        ("otel_kind_by_kind", "kind", "otel", f"Record<{kind_type}, OtelSpanKind>"),
        ("name_target_by_kind", "kind", "ref", f"Partial<Record<{kind_type}, string>>"),
    ):
        table = reg.table(name, LANG)
        if table is None:
            continue
        out.append("")
        out.extend(comment(table["doc"], "//"))
        out.append(f"export const {table['names'][LANG]}: {annotation} = {{")
        for k, v in table["map"].items():
            key = f"[{kind_type}.{k}]" if key_fmt == "kind" else _prop(k)
            out.append(f"  {key}: {_fmt(v, value_fmt, kind_type)},")
        out.append("};")

    return "\n".join(out) + "\n"


def _fmt(value: str, how: str, kind_type: str) -> str:
    if how == "kind":
        return f"{kind_type}.{value}"
    if how == "otel":
        return f"OtelSpanKind.{value}"
    if how == "ref":
        return value
    return _literal(value)
