"""Media parts: the mapping in registry/media_parts.yaml, checked and rendered.

Three questions, three functions:

- `lint`: is the file well formed? Run by the registry linter with every
  other rule, so it needs no fixtures.
- `check_fixture_refs`: does every scenario a row names exist? A fixtures id
  is `<family>/<scenario>`: `<family>` is a directory under fixtures/ and
  `<scenario>` is a key of `recordings.<file>.scenarios` in that family's
  manifest.json. Run by tools/check_fixtures.py.
- `render_table`: the generated table, out/docs/media-parts.md.

`strip_raw_payload` is the reference implementation of `raw_payloads`: the
media tokens a normalizer replaces in a raw payload, replaced in place. Its
golden examples are in the file, and `lint` runs them. `is_data_url`,
`is_buffer` and `keyed_base64` are the detection rules on their own, which
tools/check_fixtures.py refuses in an expected result.
"""

from __future__ import annotations

import json
import pathlib
import re
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
    "d": ("type", "array_key", "mime_keys"),
    "e": (
        "keys",
        "sibling_keys",
        "parent_keys",
        "source_key",
        "source_type",
        "mime_keys",
        "mime_formats",
    ),
}
RAW_PAYLOAD_FIELDS = (
    "source_rule",
    "message_keys",
    "raw_keys",
    "strip_rule",
    "scope",
    "order",
    "json_candidate",
    "precedence",
    "spans",
    "byte_size",
    "regex_dialect",
    "reference",
    "replacement",
    "detection",
    "golden",
)
#: The prose rulings, rendered in this order.
RAW_PAYLOAD_PROSE = (
    "source_rule",
    "strip_rule",
    "scope",
    "order",
    "json_candidate",
    "precedence",
    "spans",
    "byte_size",
    "regex_dialect",
    "reference",
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
    for field in RAW_PAYLOAD_PROSE:
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
            groups = re.compile(rules["b"]["pattern"]).groups
        except re.error as exc:
            errors.append(f"{where} detection rule b pattern does not compile ({exc})")
        else:
            if groups != 2:
                errors.append(f"{where} detection rule b pattern needs 2 groups (mime, base64)")
    for entry in rules.get("e", {}).get("mime_formats") or []:
        if not entry.get("key") or "<value>" not in str(entry.get("mime", "")):
            errors.append(f"{where} detection rule e mime_formats need a key and a <value> mime")
    if not errors:
        errors += lint_golden(raw)
    return errors


def lint_golden(raw: dict) -> list[str]:
    """Every golden example is what strip does: exact output, exact tokens."""
    where = "media_parts: raw_payloads golden"
    errors: list[str] = []
    names: set[str] = set()
    for golden in raw.get("golden") or []:
        name = golden.get("name")
        if not name or name in names:
            errors.append(f"{where} needs a unique name, not {name!r}")
        names.add(name)
        if not all(isinstance(golden.get(f), str) for f in ("input", "output")):
            errors.append(f"{where} {name} needs an input and an output string")
            continue
        result = strip(raw, golden["input"])
        if result.text != golden["output"]:
            errors.append(f"{where} {name}: strip gives {result.text!r}")
        tokens = [t.as_dict(str(raw["replacement"]["unknown"])) for t in result.tokens]
        if tokens != golden.get("tokens"):
            errors.append(f"{where} {name}: strip finds tokens {tokens}")
    return errors


def is_message_key(raw: dict, key: str) -> bool:
    """Whether a key is a message key: exact, or under a prefix ending in a dot."""
    return any(
        key.startswith(m) if m.endswith(".") else key == m for m in raw.get("message_keys") or []
    )


# --- raw payloads ---------------------------------------------------------------
#
# strip_raw_payload is the reference implementation of raw_payloads: every
# span is on the original text, and only the tokens the rules find change.


def replacement(raw: dict, mime: str | None, byte_size: int | None) -> str:
    """The text a media token in a raw payload is replaced by."""
    unknown = str(raw["replacement"]["unknown"])
    return (
        str(raw["replacement"]["format"])
        .replace("<mime>", mime or unknown)
        .replace("<byte_size>", unknown if byte_size is None else str(byte_size))
    )


def _rules(raw: dict) -> dict[str, dict]:
    return {str(rule["id"]): rule for rule in raw["detection"]}


#: The whitespace byte_size removes, and the only whitespace a JSON candidate
#: trims and RFC 8259 allows between tokens.
ASCII_WHITESPACE = " \t\n\r"
_STANDARD = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")
_STANDARD_EXTRA = set("+/")
_URL_SAFE_EXTRA = set("-_")


def base64_size(value: str) -> int | None:
    """The decoded size of a base64 string, or None (unknown) when it is not
    valid base64: one alphabet, at most two trailing =, a length that is a
    multiple of 4. Space, tab, newline and carriage return are removed first."""
    text = "".join(ch for ch in value if ch not in ASCII_WHITESPACE)
    body = text.rstrip("=")
    padding = len(text) - len(body)
    chars = set(body)
    if padding > 2 or len(text) % 4 or not chars <= _STANDARD | _STANDARD_EXTRA | _URL_SAFE_EXTRA:
        return None
    if chars & _STANDARD_EXTRA and chars & _URL_SAFE_EXTRA:
        return None
    return len(text) * 3 // 4 - padding


@dataclass(frozen=True)
class Token:
    """A media token a strip replaced: its rule, mime type and size (None is
    unknown)."""

    rule: str
    mime: str | None
    byte_size: int | None

    def as_dict(self, unknown: str = "unknown") -> dict:
        """As a golden example lists it."""
        return {
            "rule": self.rule,
            "mime": self.mime or unknown,
            "byte_size": unknown if self.byte_size is None else self.byte_size,
        }


@dataclass(frozen=True)
class Stripped:
    """A stripped string and the tokens replaced in it, in document order."""

    text: str
    tokens: list[Token]


@dataclass(frozen=True)
class Span:
    """A data URL token inside a string: its boundaries, mime type and size."""

    start: int
    end: int
    mime: str | None
    byte_size: int | None


def data_url_spans(raw: dict, value: str) -> list[Span]:
    """Rule b: every data URL token in a string, wherever it sits."""
    return [
        Span(m.start(), m.end(), m.group(1) or None, base64_size(m.group(2)))
        for m in re.finditer(_rules(raw)["b"]["pattern"], value)
    ]


def is_data_url(raw: dict, value: str) -> bool:
    """Rule b: the string holds a data URL token."""
    return bool(data_url_spans(raw, value))


def strip_data_urls(raw: dict, value: str) -> str:
    """Rule b alone, on a string that is not JSON: each data URL token replaced
    in place, the text around it untouched."""
    out, last = [], 0
    for span in data_url_spans(raw, value):
        out += [value[last : span.start], replacement(raw, span.mime, span.byte_size)]
        last = span.end
    return "".join([*out, value[last:]])


def is_json_candidate(value: str) -> bool:
    """Starts with { or [ once leading ASCII whitespace is trimmed."""
    return value.lstrip(ASCII_WHITESPACE)[:1] in ("{", "[")


def _mime_key(rule: dict, obj: dict) -> str | None:
    for key in rule["mime_keys"]:
        if isinstance(obj.get(key), str) and obj[key]:
            return obj[key]
    return None


def is_buffer(raw: dict, value: dict) -> bool:
    """Rule d."""
    rule = _rules(raw)["d"]
    data = value.get(rule["array_key"])
    return value.get("type") == rule["type"] and isinstance(data, list) and bool(data)


def is_replacement(raw: dict, value: str) -> bool:
    """Whether a string is already a replacement: it starts with the format's
    text before <mime> and ends with its text after <byte_size>."""
    form = str(raw["replacement"]["format"])
    head, tail = form.split("<mime>")[0], form.split("<byte_size>")[-1]
    return len(value) >= len(head) + len(tail) and value.startswith(head) and value.endswith(tail)


def keyed_base64(raw: dict, value: dict, parent_key: str | None) -> list[str]:
    """Rule e: the keys of `value` that hold a base64 media string (never one
    that is already a replacement, so stripping twice changes nothing)."""
    rule = _rules(raw)["e"]
    context = (
        any(k in value for k in rule["sibling_keys"])
        or parent_key in rule["parent_keys"]
        or (parent_key == rule["source_key"] and value.get("type") == rule["source_type"])
    )
    if not context:
        return []
    return [
        k
        for k in rule["keys"]
        if isinstance(value.get(k), str) and value[k] and not is_replacement(raw, value[k])
    ]


def keyed_mime(raw: dict, value: dict, parent_key: str | None) -> str | None:
    """Rule e's mime type: a sibling mime key, else the first mime_formats entry
    whose sibling is set (and whose parent keys, if any, include the parent)."""
    rule = _rules(raw)["e"]
    mime = _mime_key(rule, value)
    if mime:
        return mime
    for entry in rule["mime_formats"]:
        sibling = value.get(entry["key"])
        if not isinstance(sibling, str) or not sibling:
            continue
        if "parent_keys" in entry and parent_key not in entry["parent_keys"]:
            continue
        return str(entry["mime"]).replace("<value>", sibling)
    return None


# A JSON document parsed with every value's span on the text it came from.


class _NotJson(ValueError):
    pass


@dataclass
class _Value:
    """A JSON value: its span on the text, its Python value, and for an
    object its members, for an array its items, for a string the raw span of
    each decoded character."""

    start: int
    end: int
    value: Any
    members: list[tuple[str, _Value]] | None = None
    items: list[_Value] | None = None
    chars: list[tuple[int, int]] | None = None


_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
_SHORT_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}
_HEX = set("0123456789abcdefABCDEF")


class _Parser:
    """Strict RFC 8259: no NaN, Infinity, comments or trailing commas."""

    def __init__(self, text: str):
        self.text = text
        self.i = 0

    def document(self) -> _Value:
        self.space()
        value = self.value()
        self.space()
        if self.i != len(self.text):
            raise _NotJson("trailing text")
        return value

    def space(self) -> None:
        while self.i < len(self.text) and self.text[self.i] in ASCII_WHITESPACE:
            self.i += 1

    def peek(self) -> str:
        return self.text[self.i] if self.i < len(self.text) else ""

    def expect(self, ch: str) -> None:
        if self.peek() != ch:
            raise _NotJson(f"expected {ch!r} at {self.i}")
        self.i += 1

    def value(self) -> _Value:
        ch = self.peek()
        if ch == "{":
            return self.object()
        if ch == "[":
            return self.array()
        if ch == '"':
            return self.string()
        for word, val in (("true", True), ("false", False), ("null", None)):
            if self.text.startswith(word, self.i):
                start, self.i = self.i, self.i + len(word)
                return _Value(start, self.i, val)
        match = _NUMBER.match(self.text, self.i)
        if not match:
            raise _NotJson(f"no value at {self.i}")
        self.i = match.end()
        return _Value(match.start(), match.end(), json.loads(match.group()))

    def object(self) -> _Value:
        start = self.i
        self.expect("{")
        members: list[tuple[str, _Value]] = []
        self.space()
        if self.peek() == "}":
            self.i += 1
        else:
            while True:
                self.space()
                key = self.string()
                self.space()
                self.expect(":")
                self.space()
                members.append((key.value, self.value()))
                self.space()
                if self.peek() == ",":
                    self.i += 1
                    continue
                self.expect("}")
                break
        # Duplicate keys: the last one counts, as in every JSON parser here.
        return _Value(start, self.i, {k: v.value for k, v in members}, members=members)

    def array(self) -> _Value:
        start = self.i
        self.expect("[")
        items: list[_Value] = []
        self.space()
        if self.peek() == "]":
            self.i += 1
        else:
            while True:
                self.space()
                items.append(self.value())
                self.space()
                if self.peek() == ",":
                    self.i += 1
                    continue
                self.expect("]")
                break
        return _Value(start, self.i, [v.value for v in items], items=items)

    def string(self) -> _Value:
        start = self.i
        self.expect('"')
        out: list[str] = []
        chars: list[tuple[int, int]] = []
        text = self.text
        while True:
            if self.i >= len(text):
                raise _NotJson("unterminated string")
            ch, at = text[self.i], self.i
            if ch == '"':
                self.i += 1
                break
            if ch < " ":
                raise _NotJson("control character in string")
            if ch != "\\":
                out.append(ch)
                self.i += 1
            else:
                kind = text[self.i + 1 : self.i + 2]
                if kind in _SHORT_ESCAPES:
                    out.append(_SHORT_ESCAPES[kind])
                    self.i += 2
                elif kind == "u":
                    code = self.hex4(self.i + 2)
                    self.i += 6
                    if 0xD800 <= code < 0xDC00 and text.startswith("\\u", self.i):
                        low = self.hex4(self.i + 2)
                        if 0xDC00 <= low < 0xE000:
                            code = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)
                            self.i += 6
                    out.append(chr(code))
                else:
                    raise _NotJson(f"bad escape at {self.i}")
            chars.append((at, self.i))
        return _Value(start, self.i, "".join(out), chars=chars)

    def hex4(self, at: int) -> int:
        digits = self.text[at : at + 4]
        if len(digits) != 4 or not set(digits) <= _HEX:
            raise _NotJson(f"bad \\u escape at {at}")
        return int(digits, 16)


def _parse(text: str) -> _Value | None:
    try:
        return _Parser(text).document()
    except (_NotJson, RecursionError):
        return None


def parse_json_candidate(text: str) -> Any:
    """A JSON candidate's value when it parses (strict RFC 8259), else None."""
    if not is_json_candidate(text):
        return None
    document = _parse(text)
    return None if document is None else document.value


def json_escape(text: str) -> str:
    """Text as it is written inside a JSON string: the minimal escapes
    JSON.stringify writes, and nothing else."""
    out = []
    for ch in text:
        code = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch in "\b\f\n\r\t":
            out.append({"\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}[ch])
        elif code < 0x20 or 0xD800 <= code < 0xE000:
            out.append(f"\\u{code:04x}")
        else:
            out.append(ch)
    return "".join(out)


#: An edit on a text: replace text[start:end] by the string.
_Edit = tuple[int, int, str]


def _strip_text(raw: dict, text: str, tokens: list[Token]) -> list[_Edit]:
    """The edits on a string's text (a raw attribute, or a JSON string's
    unescaped value): the JSON walk when it is a candidate that parses, else
    rule b alone."""
    if is_json_candidate(text):
        document = _parse(text)
        if document is not None:
            edits: list[_Edit] = []
            _walk(raw, document, None, None, tokens, edits)
            return edits
    edits = []
    for span in data_url_spans(raw, text):
        tokens.append(Token("b", span.mime, span.byte_size))
        edits.append((span.start, span.end, replacement(raw, span.mime, span.byte_size)))
    return edits


def _literal(raw: dict, mime: str | None, byte_size: int | None) -> str:
    return '"' + json_escape(replacement(raw, mime, byte_size)) + '"'


def _walk(
    raw: dict,
    node: _Value,
    parent_key: str | None,
    holder: dict | None,
    tokens: list[Token],
    edits: list[_Edit],
) -> None:
    """Rules d, then e, then b, on one value, in document order. `holder` is the
    nearest enclosing object (through arrays), for rule d's mime type."""
    rules = _rules(raw)
    if node.members is not None:
        obj = node.value
        if is_buffer(raw, obj):
            mime = _mime_key(rules["d"], holder or {})
            size = len(obj[rules["d"]["array_key"]])
            tokens.append(Token("d", mime, size))
            edits.append((node.start, node.end, _literal(raw, mime, size)))
            return
        keyed = set(keyed_base64(raw, obj, parent_key))
        # With duplicate keys only the last member is the value.
        last = {key: child for key, child in node.members}
        for key, child in node.members:
            if key in keyed and last[key] is child:
                mime = keyed_mime(raw, obj, parent_key)
                size = base64_size(child.value)
                tokens.append(Token("e", mime, size))
                edits.append((child.start, child.end, _literal(raw, mime, size)))
            else:
                _walk(raw, child, key, obj, tokens, edits)
    elif node.items is not None:
        for child in node.items:
            _walk(raw, child, parent_key, holder, tokens, edits)
    elif node.chars is not None:
        # A JSON string: strip its unescaped value, then map each edit back to
        # the raw characters and write it escaped for this level.
        for start, end, text in _strip_text(raw, node.value, tokens):
            raw_start = node.chars[start][0]
            raw_end = node.chars[end - 1][1] if end > start else raw_start
            edits.append((raw_start, raw_end, json_escape(text)))


def _apply(text: str, edits: list[_Edit]) -> str:
    out, last = [], 0
    for start, end, new in edits:
        out += [text[last:start], new]
        last = end
    return "".join([*out, text[last:]])


def strip(raw: dict, text: str) -> Stripped:
    """raw_payloads applied to one string value: the stripped string, and the
    tokens replaced in it, in document order."""
    tokens: list[Token] = []
    return Stripped(_apply(text, _strip_text(raw, text, tokens)), tokens)


def strip_raw_payload(raw: dict, text: str) -> str:
    """The reference implementation of raw_payloads: the string with every
    media token replaced in place and every other character unchanged."""
    return strip(raw, text).text


def media_tokens(raw: dict, value: Any) -> list[Token]:
    """The media tokens strip finds in a value: a string as it is, anything
    else as JSON."""
    text = value if isinstance(value, str) else json.dumps(value)
    return strip(raw, text).tokens


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
    read as HTML or emphasis. Code spans (between backticks) are left as they
    are."""
    parts = _one_line(text).split("`")
    for i in range(0, len(parts), 2):
        part = parts[i].replace("<", "&lt;").replace(">", "&gt;").replace("*", "\\*")
        parts[i] = part.replace("__", "\\_\\_")
    return "`".join(parts)


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


#: Rendered titles that are not the field name, capitalized.
PROSE_TITLES = {"json_candidate": "JSON candidates", "byte_size": "Byte size"}


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
    ]
    for field in RAW_PAYLOAD_PROSE[1:]:
        title = PROSE_TITLES.get(field, field.replace("_", " ").capitalize())
        lines += [f"**{title}.** {_prose(raw[field])}", ""]
    lines += [
        f"**Replacement.** The text `{replacement_['format']}`, with "
        f"`{replacement_['unknown']}` for a mime type or size that is not known: "
        + ", ".join(f"`{e}`" for e in replacement_.get("examples") or [])
        + ". Rules (d) and (e) write it as a JSON string literal, quotes included;"
        " rule (b) writes the bare text, inside the quotes already there in a JSON string.",
        "",
    ]
    if replacement_.get("in_text"):
        lines += [
            "A data URL inside other text: only the token is replaced, so "
            f"`{replacement_['in_text']['before']}` becomes "
            f"`{replacement_['in_text']['after']}`.",
            "",
        ]
    lines += [
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
            f"{key}: " + _param(value)
            for key, value in rule.items()
            if key not in ("id", "name", "description")
        ]
        cells = [f"({rule['id']})", _prose(rule["name"]), _prose(rule["description"])]
        lines.append("| " + " | ".join([*cells, "; ".join(params).replace("|", "\\|")]) + " |")
    lines += ["", "### Golden examples", ""]
    lines += [
        "Each normalizer must turn each input into exactly its output (`strip_raw_payload`",
        "in generators/media_parts.py does). Tokens are listed in document order.",
        "",
    ]
    for golden in raw.get("golden") or []:
        tokens = ", ".join(
            f"({t['rule']}) {t['mime']}, {t['byte_size']} bytes" for t in golden["tokens"]
        )
        lines += [f"#### `{golden['name']}`", ""]
        if golden.get("note"):
            lines += [_prose(golden["note"]), ""]
        lines += ["Input:", "", "```text", golden["input"], "```", ""]
        lines += ["Output:", "", "```text", golden["output"], "```", ""]
        lines += [f"Tokens: {tokens or 'none'}.", ""]
    return lines


def _param(value: Any) -> str:
    """A detection rule parameter, for the table."""
    if isinstance(value, list) and all(isinstance(v, dict) for v in value):
        return ", ".join(
            "`"
            + v["key"]
            + "` gives `"
            + v["mime"]
            + "`"
            + (" under " + _code_list(v["parent_keys"]) if v.get("parent_keys") else "")
            for v in value
        )
    return _code_list(value) if isinstance(value, list) else f"`{value}`"


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
