"""Media parts: the mapping in registry/media_parts.yaml, checked and rendered.

Three questions, three functions:

- `lint`: is the file well formed? Run by the registry linter with every
  other rule, so it needs no fixtures.
- `check_fixture_refs`: does every scenario a row names exist? A fixtures id
  is `<family>/<scenario>`: `<family>` is a directory under fixtures/ and
  `<scenario>` is a key of `recordings.<file>.scenarios` in that family's
  manifest.json. Run by tools/check_fixtures.py.
- `render_table`: the generated table, out/docs/media-parts.md.

`media_tokens` applies the `raw_payloads.detection` rules to a value: the
media tokens a normalizer replaces in a raw payload, and the ones
tools/check_fixtures.py refuses in an expected result.
"""

from __future__ import annotations

import json
import pathlib
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

#: none: no part is made (the media is only in a raw payload, or was dropped).
NONE = "none"
NORMALIZED = {"blob", "uri", "file", "text", "generic", NONE}
#: Exactly the stripped_reason vocabulary.
STRIPPED_REASONS = {"not_captured", "redacted_upstream"}
#: The detection rules raw_payloads must define, and the fields each needs.
DETECTION_FIELDS = {
    "b": ("pattern",),
    "d": ("type", "array_key"),
    "e": ("keys", "sibling_keys", "parent_keys", "source_key", "source_type"),
}
RAW_PAYLOAD_FIELDS = (
    "source_rule",
    "message_keys",
    "raw_keys",
    "strip_rule",
    "replacement",
    "detection",
)
DIRECTIONS = {"input", "output"}
PATHS = {"passthrough", "openinference", "openllmetry", "laminar", "vercel", "native"}
#: The modality column's extra value: the modality rule (MIME type first).
FROM_MIME = "from_mime"


def row_name(row: dict) -> str:
    return f"media_parts: {row.get('source')} {row.get('shape')}:"


def normalized_of(row: dict) -> list[str]:
    value = row.get("normalized")
    return list(value) if isinstance(value, list) else [value]


def raw_payload_of(row: dict) -> list[str]:
    """The raw payload keys a none row describes; empty for any other row."""
    value = row.get("raw_payload")
    if not value:
        return []
    return [str(v) for v in value] if isinstance(value, list) else [str(value)]


# --- the file ----------------------------------------------------------------


def lint(data: dict) -> list[str]:
    """Every rule the file itself must satisfy. Empty list = clean."""
    errors: list[str] = []
    modalities = set(data.get("modalities") or [])
    if not modalities:
        errors.append("media_parts: modalities must list at least one modality")
    reasons = data.get("stripped_reasons") or {}
    for reason, meaning in reasons.items():
        if not str(meaning).strip():
            errors.append(f"media_parts: stripped_reasons {reason} needs a description")
    if set(reasons) != STRIPPED_REASONS:
        errors.append(f"media_parts: stripped_reasons must be exactly {sorted(STRIPPED_REASONS)}")
    errors += lint_raw_payloads(data.get("raw_payloads"))
    seen: set[tuple] = set()
    for row in data.get("rows") or []:
        label = row_name(row)
        for field in ("source", "shape"):
            if not str(row.get(field, "")).strip():
                errors.append(f"{label} needs a {field}")
        key = (row.get("source"), row.get("shape"), row.get("direction"))
        if key in seen:
            errors.append(f"{label} listed twice")
        seen.add(key)
        if row.get("direction") not in DIRECTIONS:
            errors.append(f"{label} direction must be one of {sorted(DIRECTIONS)}")
        normalized = normalized_of(row)
        if any(n not in NORMALIZED for n in normalized):
            errors.append(f"{label} normalized must be one of {sorted(NORMALIZED)}")
        if NONE in normalized and len(normalized) > 1:
            errors.append(f"{label} normalized {NONE} stands alone")
        raw_keys = set((data.get("raw_payloads") or {}).get("raw_keys") or [])
        payload_keys = raw_payload_of(row)
        if payload_keys and normalized != [NONE]:
            errors.append(f"{label} raw_payload only on a none row")
        for key in payload_keys:
            if key not in raw_keys:
                errors.append(f"{label} raw_payload {key} is not one of raw_payloads.raw_keys")
        modality = row.get("modality")
        if modality is None:
            if normalized not in (["text"], [NONE]):
                errors.append(f"{label} needs a modality")
        elif modality != FROM_MIME and modality not in modalities:
            errors.append(f"{label} modality must be one of {[*sorted(modalities), FROM_MIME]}")
        paths = row.get("paths") or []
        if not paths:
            errors.append(f"{label} paths must name at least one path")
        for path in paths:
            if path not in PATHS:
                errors.append(f"{label} unknown path {path}; use one of {sorted(PATHS)}")
        fixtures = row.get("fixtures")
        if not isinstance(fixtures, list):
            errors.append(f"{label} fixtures must be a list (empty when none is recorded)")
            continue
        for ref in fixtures:
            family, _, scenario = str(ref).partition("/")
            if not family or not scenario:
                errors.append(f"{label} fixtures must be <family>/<scenario>, not {ref!r}")
        if not fixtures and not str(row.get("reason", "")).strip():
            errors.append(f"{label} needs fixtures or a reason")
    return errors


def lint_raw_payloads(raw: Any) -> list[str]:
    """The raw_payloads section: the source rule, the strip rule, the
    replacement and the detection rules."""
    where = "media_parts: raw_payloads"
    if not isinstance(raw, dict):
        return [f"{where} must be a mapping"]
    errors = [f"{where} needs {field}" for field in RAW_PAYLOAD_FIELDS if not raw.get(field)]
    for field in ("source_rule", "strip_rule"):
        if field in raw and not isinstance(raw[field], str):
            errors.append(f"{where} {field} must be prose")
    for key in sorted(set(raw.get("raw_keys") or [])):
        if is_message_key(raw, key):
            errors.append(f"{where} {key} is both a message key and a raw key")
    replacement = raw.get("replacement") or {}
    form = str(replacement.get("format", ""))
    if "<mime>" not in form or "<byte_size>" not in form:
        errors.append(f"{where} replacement format must name <mime> and <byte_size>")
    if not str(replacement.get("unknown", "")).strip():
        errors.append(f"{where} replacement needs the unknown value")
    for token in replacement.get("tokens") or []:
        for field in ("token", "replaced", "mime", "byte_size"):
            if not str(token.get(field, "")).strip():
                errors.append(f"{where} replacement token {token.get('token')!r} needs {field}")
    rules = {str(rule.get("id")): rule for rule in raw.get("detection") or []}
    if set(rules) != set(DETECTION_FIELDS):
        errors.append(f"{where} detection must define rules {sorted(DETECTION_FIELDS)}")
    for rule_id, fields in DETECTION_FIELDS.items():
        rule = rules.get(rule_id)
        if rule is None:
            continue
        for field in ("name", "description", *fields):
            if not rule.get(field):
                errors.append(f"{where} detection rule {rule_id} needs {field}")
    if rules.get("b", {}).get("pattern"):
        try:
            re.compile(rules["b"]["pattern"])
        except re.error as exc:
            errors.append(f"{where} detection rule b pattern does not compile ({exc})")
    return errors


def is_message_key(raw: dict, key: str) -> bool:
    """Whether a key is a message key: exact, or under a prefix ending in a dot."""
    return any(
        key.startswith(m) if m.endswith(".") else key == m for m in raw.get("message_keys") or []
    )


# --- raw payloads ---------------------------------------------------------------


@dataclass(frozen=True)
class Token:
    """A media token: the rule that found it and the path to it."""

    rule: str
    path: tuple


def replacement(raw: dict, mime: str | None, byte_size: int | None) -> str:
    """The string a media token in a raw payload is replaced by."""
    unknown = str(raw["replacement"]["unknown"])
    return (
        str(raw["replacement"]["format"])
        .replace("<mime>", mime or unknown)
        .replace("<byte_size>", unknown if byte_size is None else str(byte_size))
    )


def _rules(raw: dict) -> dict[str, dict]:
    return {str(rule["id"]): rule for rule in raw["detection"]}


def is_data_url(raw: dict, value: str) -> bool:
    """Rule b."""
    return re.search(_rules(raw)["b"]["pattern"], value) is not None


def is_buffer(raw: dict, value: dict) -> bool:
    """Rule d."""
    rule = _rules(raw)["d"]
    data = value.get(rule["array_key"])
    return value.get("type") == rule["type"] and isinstance(data, list) and bool(data)


def keyed_base64(raw: dict, value: dict, parent_key: str | None) -> list[str]:
    """Rule e: the keys of `value` that hold a base64 media string."""
    rule = _rules(raw)["e"]
    context = (
        any(k in value for k in rule["sibling_keys"])
        or parent_key in rule["parent_keys"]
        or (parent_key == rule["source_key"] and value.get("type") == rule["source_type"])
    )
    if not context:
        return []
    return [k for k in rule["keys"] if isinstance(value.get(k), str) and value[k]]


def media_tokens(
    raw: dict, value: Any, parent_key: str | None = None, path: tuple = ()
) -> Iterator[Token]:
    """Every media token rules b, d and e find in a value. A string holding
    JSON is parsed and searched too (its tokens' paths go through it)."""
    if isinstance(value, dict):
        if is_buffer(raw, value):
            yield Token("d", path)
            return
        keyed = keyed_base64(raw, value, parent_key)
        for key in keyed:
            yield Token("e", (*path, key))
        for key, child in value.items():
            if key not in keyed:
                yield from media_tokens(raw, child, key, (*path, key))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from media_tokens(raw, child, parent_key, (*path, i))
    elif isinstance(value, str):
        if is_data_url(raw, value):
            yield Token("b", path)
        elif value.lstrip()[:1] in ("{", "["):
            try:
                parsed = json.loads(value)
            except ValueError:
                return
            yield from media_tokens(raw, parsed, None, path)


# --- the fixtures ------------------------------------------------------------


def recorded_scenarios(fixtures: pathlib.Path) -> dict[str, set[str]]:
    """family -> every scenario its manifest.json describes."""
    out: dict[str, set[str]] = {}
    for manifest_path in sorted(fixtures.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text())
        out[manifest_path.parent.name] = {
            scenario
            for entry in manifest.get("recordings", {}).values()
            for scenario in entry.get("scenarios", {})
        }
    return out


def check_fixture_refs(data: dict, fixtures: pathlib.Path) -> list[str]:
    """A row naming a scenario that was never recorded fails, naming both."""
    recorded = recorded_scenarios(fixtures)
    errors: list[str] = []
    for row in data.get("rows") or []:
        for ref in row.get("fixtures") or []:
            family, _, scenario = str(ref).partition("/")
            if family not in recorded:
                errors.append(f"{row_name(row)} fixtures {ref}: no family {family} under fixtures/")
            elif scenario not in recorded[family]:
                errors.append(
                    f"{row_name(row)} fixtures {ref}: {family} has no scenario {scenario}"
                )
    return errors


# --- the table ---------------------------------------------------------------


def _one_line(text: object) -> str:
    """One table-safe line, for a code span."""
    return re.sub(r"\s+", " ", str(text or "")).strip().replace("|", "\\|")


def _prose(text: object) -> str:
    """One table-safe line of prose: `<`, `>`, `*` and `__` would otherwise be
    read as HTML or emphasis."""
    line = _one_line(text).replace("<", "&lt;").replace(">", "&gt;").replace("*", "\\*")
    return line.replace("__", "\\_\\_")


#: How the table writes `normalized: none`; a raw_payload row names its keys.
NONE_LABEL = "no part"
RAW_PAYLOAD_LABEL = "no part (raw payload stripped: {keys})"


def _becomes(row: dict) -> str:
    keys = raw_payload_of(row)
    if keys:
        return RAW_PAYLOAD_LABEL.format(keys=_code_list(keys))
    return " / ".join(NONE_LABEL if n == NONE else n for n in normalized_of(row))


def _code_list(items: list) -> str:
    return ", ".join(f"`{item}`" for item in items)


def _render_raw_payloads(raw: dict) -> list[str]:
    replacement_ = raw["replacement"]
    lines = [
        "## Raw payloads",
        "",
        f"**Source rule.** {_prose(raw['source_rule'])}",
        "",
        "Message keys (a key ending in `.` is a prefix): " + _code_list(raw["message_keys"]) + ".",
        "",
        "Raw payloads, never mined for parts: " + _code_list(raw["raw_keys"]) + ".",
        "",
        f"**Strip rule.** {_prose(raw['strip_rule'])}",
        "",
        f'**Replacement.** The JSON string `"{replacement_["format"]}"`, with '
        f"`{replacement_['unknown']}` for a mime type or size that is not known: "
        + ", ".join(f'`"{e}"`' for e in replacement_.get("examples") or [])
        + ".",
        "",
        "| Token | Replaced | Mime | Byte size |",
        "| -- | -- | -- | -- |",
    ]
    for token in replacement_.get("tokens") or []:
        cells = [token["token"], token["replaced"], token["mime"], token["byte_size"]]
        lines.append("| " + " | ".join(_prose(c) for c in cells) + " |")
    lines += [
        "",
        "**Detection rules.** The normalizers strip, and tools/check_fixtures.py refuses",
        "in an expected result, every token these find (in a string holding JSON too):",
        "",
        "| Rule | Name | Matches | Parameters |",
        "| -- | -- | -- | -- |",
    ]
    for rule in raw["detection"]:
        params = [
            f"{key}: " + (_code_list(value) if isinstance(value, list) else f"`{value}`")
            for key, value in rule.items()
            if key not in ("id", "name", "description")
        ]
        cells = [f"({rule['id']})", _prose(rule["name"]), _prose(rule["description"])]
        lines.append("| " + " | ".join([*cells, "; ".join(params).replace("|", "\\|")]) + " |")
    lines.append("")
    return lines


def render_table(data: dict) -> str:
    """out/docs/media-parts.md: every source shape and what it becomes."""
    lines = [
        "<!-- Generated from registry/media_parts.yaml by `python -m generators.generate`.",
        "     Do not edit. -->",
        "",
        "# Media parts",
        "",
        "After normalization a media part is a `blob` (inline bytes, always stripped of",
        "`content`), a `uri` or a `file`. The modality is one of "
        + ", ".join(f"`{m}`" for m in data["modalities"])
        + ",",
        "taken from the MIME type when known (`from_mime`), else from the provider's",
        "part kind. A `blob` carries a `stripped_reason`:",
        "",
    ]
    for reason, meaning in data["stripped_reasons"].items():
        lines.append(f"- `{reason}`: {_prose(meaning)}")
    lines += [
        "",
        "*Fixtures* lists the recorded scenarios (`<family>/<scenario>`) that prove the",
        "row; a row with none says why in *Why*.",
        "",
    ]
    lines += _render_raw_payloads(data["raw_payloads"])
    for direction in ("input", "output"):
        rows = [r for r in data["rows"] if r["direction"] == direction]
        if not rows:
            continue
        header = ["Source", "Shape", "Becomes", "Modality", "Paths", "Fixtures", "Why"]
        lines += [f"## {direction.capitalize()}", ""]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + " -- |" * len(header))
        for row in rows:
            why = _prose(row.get("note"))
            if row.get("fixtures"):
                fixtures = ", ".join(f"`{f}`" for f in row["fixtures"])
            else:
                fixtures = "none"
                why = _prose(f"{row.get('reason')} {row.get('note') or ''}")
            cells = [
                f"`{row['source']}`",
                f"`{_one_line(row['shape'])}`",
                _becomes(row),
                row.get("modality", "-"),
                ", ".join(row["paths"]),
                fixtures,
                why,
            ]
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    return "\n".join(lines)
