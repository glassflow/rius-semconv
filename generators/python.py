"""Emits the Python constants module (`_semconv_generated.py`).

Constants and tables only. The SDK's hand-written semconv.py re-exports this
module and keeps the helper functions (kind_attributes, compose_span_name,
request_attribute_key, ...), because logic is not registry data.

Output is shaped to pass `ruff format --check` and `ruff check` under the
Python SDK's configuration, so vendoring it needs no formatter exemption.
"""

from __future__ import annotations

from .registry import Registry, comment

LANG = "python"


def _literal(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _ref_or_literal(reg: Registry, key: str) -> str:
    const = reg.const_for_key(key, LANG)
    return const if const is not None else _literal(key)


def _member_lines(reg: Registry, members: list[dict], indent: str) -> list[str]:
    out = []
    for m in members:
        out.extend(comment(m.get("note"), "#", indent))
        out.append(f"{indent}{m['ref'] if 'ref' in m else _literal(m['key'])},")
    return out


def render(reg: Registry) -> str:
    pre = reg.preamble
    al = reg.allowlists
    out: list[str] = []
    public: list[str] = []

    out.append('"""' + pre["python"]["docstring"].rstrip("\n"))
    out.append('"""')
    out.append("")
    out.extend(comment(pre["notice"], "#"))
    out.extend(comment(pre["header"], "#"))
    out.append("")
    out.append("from __future__ import annotations")
    out.append("")
    out.append("from enum import Enum")
    if reg.table("otel_kind_by_kind", LANG) is not None:
        out.append("")
        out.append("from opentelemetry.trace import SpanKind as OtelSpanKind")

    # --- constants ---
    for row in reg.rows(LANG):
        if "section" in row or "rationale" in row:
            out.append("")
        out.extend(comment(row.get("section"), "#"))
        out.extend(comment(row.get("rationale"), "#"))
        out.append(f"{row['const']} = {_literal(row['key'])}")
        public.append(row["const"])

    # --- request parameters ---
    mp = reg.model_parameters
    out.append("")
    out.extend(comment(mp["doc"], "#"))
    out.append(f"{mp['const']}: dict[str, str] = {{")
    for spelling, target, note in reg.model_parameter_items():
        out.extend(comment(note, "#", "    "))
        out.append(f"    {_literal(spelling)}: {_ref_or_literal(reg, target)},")
    out.append("}")
    public.append(mp["const"])

    # --- allowlists ---
    pending = al["pending_identity"]
    out.append("")
    out.extend(comment(pending["doc"], "#"))
    out.append(f"{pending['const']} = frozenset(")
    out.append("    {")
    out.extend(_member_lines(reg, reg.members("pending_identity", LANG), "        "))
    out.append("    }")
    out.append(")")
    public.append(pending["const"])

    prefixes = al["pending_identity_prefixes"]
    out.extend(comment(prefixes["doc"], "#"))
    refs = prefixes["refs"]
    trailing = "," if len(refs) == 1 else ""
    out.append(f"{prefixes['const']} = ({', '.join(refs)}{trailing})")
    public.append(prefixes["const"])

    members = al["invocation_parameters_content_members"]
    out.append("")
    out.extend(comment(members["doc"], "#"))
    values = ", ".join(_literal(v) for v in members["values"])
    out.append(f"{members['const']} = ({values}{',' if len(members['values']) == 1 else ''})")
    public.append(members["const"])

    def member_set(section: str) -> None:
        block = al[section]
        out.append("")
        out.extend(comment(block["doc"], "#"))
        out.append(f"{block['const']} = frozenset(")
        out.append("    {")
        out.extend(_member_lines(reg, reg.members(section, LANG), "        "))
        out.append("    }")
        out.append(")")
        public.append(block["const"])

    def string_tuple(section: str) -> None:
        block = al[section]
        out.append("")
        out.extend(comment(block["doc"], "#"))
        out.append(f"{block['const']} = (")
        out.extend(f"    {_literal(v)}," for v in block["values"])
        out.append(")")
        public.append(block["const"])

    # Before CONTENT_ATTRIBUTES, which folds them in by name.
    for section in reg.included("content"):
        member_set(section)

    content = al["content"]
    out.append("")
    out.extend(comment(content["doc"], "#"))
    out.append(f"{content['const']} = frozenset(")
    out.append("    {")
    out.extend(_member_lines(reg, reg.members("content", LANG), "        "))
    out.append("    }")
    derived = content.get("derived")
    if derived:
        out.extend(comment(derived.get("note"), "#", "    "))
        out.append("    | {")
        out.append('        f"{prefix}{member}"')
        out.append(f"        for prefix in ({', '.join(derived['prefixes'])})")
        out.append(f"        for member in {derived['members']}")
        out.append("    }")
    for section in reg.included("content"):
        out.append(f"    | {al[section]['const']}")
    out.append(")")
    public.append(content["const"])

    string_tuple("content_prefixes")
    member_set("content_prefix_identity")
    string_tuple("content_suffixes")

    block = al["content_prefixed_suffixes"]
    out.append("")
    out.extend(comment(block["doc"], "#"))
    out.append(f"{block['const']} = (")
    for entry in block["values"]:
        suffixes = ", ".join(_literal(s) for s in entry["suffixes"])
        trailing = "," if len(entry["suffixes"]) == 1 else ""
        out.append(f"    ({_literal(entry['prefix'])}, ({suffixes}{trailing})),")
    out.append(")")
    public.append(block["const"])

    # --- span kinds ---
    sk = reg.taxonomy["span_kind"]
    out.append("")
    out.append("")
    out.append(f"class {sk['names'][LANG]}(str, Enum):")
    out.append('    """' + sk["doc"].rstrip("\n"))
    out.append("")
    for k in sk["values"]:
        out.append(f"    - ``{k['name']}``: {k['doc']}")
    out.append('    """')
    out.append("")
    for k in sk["values"]:
        out.append(f"    {k['name']} = {_literal(k['name'])}")
    public.append(sk["names"][LANG])
    out.append("")

    # --- tables ---
    kind_type = sk["names"][LANG]
    for name, key_fmt, value_fmt, annotation in (
        ("operation_by_kind", "kind", "literal", f"dict[{kind_type}, str]"),
        ("kind_by_operation", "literal", "kind", f"dict[str, {kind_type}]"),
        ("otel_kind_by_kind", "kind", "otel", f"dict[{kind_type}, OtelSpanKind]"),
        ("name_target_by_kind", "kind", "ref", f"dict[{kind_type}, str]"),
    ):
        table = reg.table(name, LANG)
        if table is None:
            continue
        ident = table["names"][LANG]
        out.append("")
        out.extend(comment(table["doc"], "#"))
        out.append(f"{ident}: {annotation} = {{")
        for k, v in table["map"].items():
            out.append(f"    {_fmt(k, key_fmt, kind_type)}: {_fmt(v, value_fmt, kind_type)},")
        out.append("}")
        if not ident.startswith("_"):
            public.append(ident)

    out.append("")
    out.append("__all__ = [")
    out.extend(f"    {_literal(name)}," for name in sorted(public))
    out.append("]")
    return "\n".join(out) + "\n"


def _fmt(value: str, how: str, kind_type: str) -> str:
    if how == "kind":
        return f"{kind_type}.{value}"
    if how == "otel":
        return f"OtelSpanKind.{value}"
    if how == "ref":
        return value
    return _literal(value)
