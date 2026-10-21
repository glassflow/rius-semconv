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
tools/check_fixtures.py refuses in an expected result. No input raises out of
`strip_raw_payload`: the parser's depth limit bounds every recursion.
"""

from __future__ import annotations

import base64
import json
import pathlib
import re
import string
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
        "blob_type",
        "blob_key",
        "typed_keys",
        "url_scheme",
        "source_bytes_keys",
        "base64_markers",
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
    "idempotence",
    "spans",
    "byte_size",
    "members",
    "regex_dialect",
    "implementers",
    "reference",
    "replacement",
    "detection",
    "golden",
    "byte_objects",
)
#: The prose rulings, rendered in this order.
RAW_PAYLOAD_PROSE = (
    "source_rule",
    "strip_rule",
    "scope",
    "order",
    "json_candidate",
    "precedence",
    "idempotence",
    "spans",
    "byte_size",
    "members",
    "regex_dialect",
    "implementers",
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
    errors += lint_part_shapes(data)
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
            if normalized not in (["text"], [NONE], ["generic"]):
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


#: The serialized member order of each normalized part type.
PART_MEMBERS = {
    "blob": ["type", "modality", "mime_type", "byte_size", "stripped_reason"],
    "uri": ["type", "modality", "mime_type", "uri"],
    "file": ["type", "modality", "mime_type", "file_id"],
}
#: The member each part type cannot do without, besides type and modality: a
#: file with no file_id or a uri with no uri points to nothing.
REQUIRED_MEMBER = {"blob": "stripped_reason", "uri": "uri", "file": "file_id"}
#: Members whose unknown value is omitted rather than written as null.
OMITTABLE = {"mime_type", "byte_size"}
#: The largest byte_size a part may carry: the largest integer a JSON number
#: holds exactly.
MAX_BYTE_SIZE = 2**53 - 1


def part_order_errors(data: dict, part: Any) -> list[str]:
    """What is wrong with one serialized part: members out of order, a null,
    a mime_type that is not a MIME token, an unknown modality or reason."""
    if not isinstance(part, dict):
        return ["is not an object"]
    kind = part.get("type")
    members = PART_MEMBERS.get(kind)
    if members is None:
        return [f"has type {kind!r}, not one of {sorted(PART_MEMBERS)}"]
    errors = []
    keys = list(part)
    if keys != [m for m in members if m in part] or set(keys) - set(members):
        errors.append(f"has members {keys}, not in the order {members}")
    errors += [f"writes {k} as null" for k, v in part.items() if v is None]
    for required in ("type", "modality", REQUIRED_MEMBER[kind]):
        if required not in part:
            errors.append(f"has no {required}")
    mime_pattern = ((data.get("raw_payloads") or {}).get("replacement") or {}).get("mime_pattern")
    mime = part.get("mime_type")
    if mime is not None and (
        not isinstance(mime, str) or (mime_pattern and not re.fullmatch(str(mime_pattern), mime))
    ):
        errors.append(f"has mime_type {mime!r}, which is not a token/token MIME type")
    if part.get("modality") not in set(data.get("modalities") or []):
        errors.append(f"has modality {part.get('modality')!r}")
    if kind == "blob" and part.get("stripped_reason") not in set(
        data.get("stripped_reasons") or []
    ):
        errors.append(f"has stripped_reason {part.get('stripped_reason')!r}")
    size = part.get("byte_size")
    if size is not None and (type(size) is not int or not 0 <= size <= MAX_BYTE_SIZE):
        errors.append(f"has byte_size {size!r}, which is not a whole number from 0 to 2^53 - 1")
    for member in ("uri", "file_id"):
        if member in part and part[member] is not None and not isinstance(part[member], str):
            errors.append(f"has {member} {part[member]!r}, which is not a string")
    return errors


def _json_objects(value: Any) -> list[dict]:
    """Every object in a parsed value, outermost first."""
    if isinstance(value, dict):
        return [value, *[o for v in value.values() for o in _json_objects(v)]]
    if isinstance(value, list):
        return [o for v in value for o in _json_objects(v)]
    return []


def lint_part_shapes(data: dict) -> list[str]:
    """The part_shapes section: the member order, the rules, the extension map
    and examples that follow the order."""
    where = "media_parts: part_shapes"
    shapes = data.get("part_shapes")
    if not isinstance(shapes, dict):
        return [f"{where} must be a mapping"]
    errors: list[str] = []
    if shapes.get("members") != PART_MEMBERS:
        errors.append(f"{where} members must be exactly {PART_MEMBERS}")
    modalities = set(data.get("modalities") or [])
    for modality, extensions in (shapes.get("extensions") or {}).items():
        if modality not in modalities:
            errors.append(f"{where} extensions: {modality} is not a modality")
        if not isinstance(extensions, list) or any(
            str(e) != str(e).lower() or not str(e) for e in extensions
        ):
            errors.append(f"{where} extensions {modality} must be lower case extensions")
    if not shapes.get("extensions"):
        errors.append(f"{where} needs extensions")
    if not shapes.get("rules"):
        errors.append(f"{where} needs rules")
    seen_types = set()
    for example in shapes.get("examples") or []:
        name = example.get("name")
        try:
            part = json.loads(str(example.get("part")))
        except ValueError:
            errors.append(f"{where} example {name} part is not JSON")
            continue
        if isinstance(part, dict):
            seen_types.add(part.get("type"))
        errors += [f"{where} example {name} {e}" for e in part_order_errors(data, part)]
        for field in ("block", "native", "provider"):
            if field not in example:
                continue
            try:
                source = json.loads(str(example[field]))
            except ValueError:
                source = None
            if not isinstance(source, dict):
                errors.append(f"{where} example {name} {field} must be a JSON object")
    for example in shapes.get("in_place_examples") or []:
        name = example.get("name")
        try:
            before, after = json.loads(example["input"]), json.loads(example["output"])
        except (KeyError, ValueError):
            errors.append(f"{where} in_place example {name} needs JSON input and output")
            continue
        parts = [p for p in _json_objects(after) if p.get("type") in PART_MEMBERS]
        if not parts:
            errors.append(f"{where} in_place example {name} output holds no part")
        for part in parts:
            errors += [
                f"{where} in_place example {name} {e}" for e in part_order_errors(data, part)
            ]
        if (
            _json_objects(before) == _json_objects(after)
            or "{" + '"type":' not in example["output"]
        ):
            errors.append(f"{where} in_place example {name} must rebuild a part, compactly")
    if not shapes.get("in_place_examples"):
        errors.append(f"{where} needs an in_place example")
    for example in shapes.get("message_examples") or []:
        name = example.get("name")
        try:
            json.loads(example["input"])
            after = json.loads(example["output"])
        except (KeyError, ValueError):
            errors.append(f"{where} message example {name} needs JSON input and output")
            continue
        attributes = example.get("attributes", {})
        if not isinstance(attributes, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in attributes.items()
        ):
            errors.append(f"{where} message example {name} attributes must map keys to strings")
        for part in _json_objects(after):
            if part.get("type") in PART_MEMBERS:
                errors += [
                    f"{where} message example {name} {e}" for e in part_order_errors(data, part)
                ]
    if seen_types != set(PART_MEMBERS):
        errors.append(f"{where} needs an example of each of {sorted(PART_MEMBERS)}")
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
    try:
        re.compile(str(replacement.get("mime_pattern", "")))
    except re.error as exc:
        errors.append(f"{where} replacement mime_pattern does not compile ({exc})")
    if not replacement.get("mime_pattern"):
        errors.append(f"{where} replacement needs a mime_pattern")
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
            if groups != 4:
                errors.append(
                    f"{where} detection rule b pattern needs 4 groups"
                    " (mime, parameters, base64, continuation)"
                )
    for marker in rules.get("e", {}).get("base64_markers") or []:
        if (
            not marker.get("key")
            or not isinstance(marker.get("value"), str)
            or not marker.get("keys")
        ):
            errors.append(f"{where} detection rule e base64_markers need a key, a value and keys")
    for entry in rules.get("e", {}).get("mime_formats") or []:
        if not entry.get("key") or "<value>" not in str(entry.get("mime", "")):
            errors.append(f"{where} detection rule e mime_formats need a key and a <value> mime")
    if not errors:
        errors += lint_byte_objects(raw)
        errors += lint_golden(raw)
    return errors


#: The languages a byte_objects example is written in, and their names.
BYTE_OBJECT_LANGUAGES = {"python": "Python", "typescript": "TypeScript"}
#: The languages an attribute_values example is written in.
ATTRIBUTE_VALUE_LANGUAGES = {
    "python": "Python",
    "typescript": "TypeScript",
    "otlp": "OTLP JSON (the sink)",
}


def lint_byte_objects(raw: dict) -> list[str]:
    """The byte_objects section: the rule, the types each SDK treats as one,
    and examples whose output holds a marker and is final (a strip changes
    nothing in it)."""
    where = "media_parts: raw_payloads byte_objects"
    section = raw.get("byte_objects")
    if not isinstance(section, dict):
        return [f"{where} must be a mapping"]
    errors = [
        f"{where} needs {field}"
        for field in ("rule", "size", *sorted(BYTE_OBJECT_LANGUAGES), "examples")
        if not section.get(field)
    ]
    for field in ("rule", "size"):
        if field in section and not isinstance(section[field], str):
            errors.append(f"{where} {field} must be prose")
    if errors:
        return errors
    unknown = re.escape(str(raw["replacement"]["unknown"]))
    marker = re.compile(
        re.escape(str(raw["replacement"]["format"]))
        .replace("<mime>", unknown)
        .replace("<byte_size>", f"([0-9]+|{unknown})")
    )
    names: set[str] = set()
    for example in section["examples"]:
        name = example.get("name")
        if not name or name in names:
            errors.append(f"{where} example needs a unique name, not {name!r}")
        names.add(name)
        if example.get("language") not in BYTE_OBJECT_LANGUAGES:
            errors.append(f"{where} {name} language must be one of {sorted(BYTE_OBJECT_LANGUAGES)}")
        output = example.get("output")
        if not isinstance(example.get("value"), str) or not isinstance(output, str):
            errors.append(f"{where} {name} needs a value and an output string")
            continue
        if not marker.search(output):
            errors.append(f"{where} {name} output holds no marker with the unknown mime")
        if strip(raw, output).text != output:
            errors.append(f"{where} {name} output is not final: a strip changes it")
    attributes = section.get("attribute_values")
    if not isinstance(attributes, dict) or not attributes.get("rule"):
        errors.append(f"{where} needs attribute_values with a rule")
        return errors
    for example in attributes.get("examples") or []:
        name = example.get("name")
        if example.get("language") not in ATTRIBUTE_VALUE_LANGUAGES:
            errors.append(
                f"{where} attribute_values {name} language must be one of "
                f"{sorted(ATTRIBUTE_VALUE_LANGUAGES)}"
            )
        if not _attribute_markers(marker, example.get("output")):
            errors.append(
                f"{where} attribute_values {name} output must be a bare marker,"
                " or an array or mapping holding one, or its JSON holding one"
            )
    if not attributes.get("examples"):
        errors.append(f"{where} attribute_values needs examples")
    return errors


def _attribute_markers(marker: re.Pattern, output: Any) -> bool:
    """Whether an attribute value holds a marker: a string that is one, an
    array or mapping whose values hold one, or an array's or a mapping's JSON
    fallback that does. Anything that is no attribute value holds none."""
    if isinstance(output, dict):
        values = list(output.values())
    elif isinstance(output, list):
        values = output
    elif isinstance(output, str):
        if marker.fullmatch(output):
            return True
        try:
            fallback = json.loads(output)
        except ValueError:
            return False
        return isinstance(fallback, (list, dict)) and _attribute_markers(marker, fallback)
    else:
        return False
    found = False
    for value in values:
        if isinstance(value, (dict, list, str)):
            found = _attribute_markers(marker, value) or found
        elif not isinstance(value, (bool, int, float)) and value is not None:
            return False
    return found


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
        if "second_output" in golden:
            second = strip(raw, golden["output"])
            if second.text != golden["second_output"]:
                errors.append(f"{where} {name}: a second pass gives {second.text!r}")
            second_tokens = [t.as_dict(str(raw["replacement"]["unknown"])) for t in second.tokens]
            if second_tokens != golden.get("second_tokens"):
                errors.append(f"{where} {name}: a second pass finds tokens {second_tokens}")
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


def run_size(run: str) -> int | None:
    """The size of a rule b run: its base64 size with the > of each quoted
    line it goes on over removed too."""
    return base64_size(run.replace(">", ""))


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


def is_mime(raw: dict, value: Any) -> bool:
    """Whether a value can go into a replacement as its mime type: a string the
    whole of which matches replacement.mime_pattern (token/token)."""
    pattern = str(raw["replacement"]["mime_pattern"])
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def _mime_or_unknown(raw: dict, mime: str | None) -> str | None:
    return mime if is_mime(raw, mime) else None


#: data: anywhere in a value, in any ASCII case: where a rule b token can start.
_DATA_ANYWHERE = re.compile("[dD][aA][tT][aA]:")


def data_url_spans(raw: dict, value: str) -> list[Span]:
    """Rule b: every data URL token in a string, wherever it sits. The string
    is cut before each data: (in any ASCII case), and the pattern is tried at
    the start of each piece and never past its end, so a run that continues
    over a line break never takes the start of the next data URL. A media type
    that is not token/token is unknown."""
    pattern = re.compile(_rules(raw)["b"]["pattern"])
    starts = [m.start() for m in _DATA_ANYWHERE.finditer(value)]
    spans = []
    for start, end in zip(starts, [*starts[1:], len(value)], strict=False):
        m = pattern.match(value, start, end)
        if m:
            mime = _mime_or_unknown(raw, m.group(1))
            spans.append(Span(m.start(), m.end(), mime, run_size(m.group(3))))
    return spans


def whole_data_url(raw: dict, value: str) -> re.Match | None:
    """Rule b's match when it is the whole string: the pattern anchored at the
    start, its match ending at the end. The same as fullmatch, since the run's
    greedy match reaches furthest, but fast when a long value fails."""
    m = re.compile(_rules(raw)["b"]["pattern"]).match(value)
    return m if m and m.end() == len(value) else None


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


#: An object's members in document order, duplicates kept: a dict's items,
#: or the (key, value) pairs of a parsed object.
Members = list[tuple[str, Any]]


def _members(obj: dict | Members) -> Members:
    return list(obj.items()) if isinstance(obj, dict) else obj


def _first(members: Members, key: str, ok: Any) -> Any:
    """The value of the first member named `key`, in document order, for which
    ok(value) holds; None when there is none."""
    return next((v for k, v in members if k == key and ok(v)), None)


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _mime_key(raw: dict, rule: dict, obj: dict | Members) -> str | None:
    """The first mime key, in the rule's list order, with a valid mime value."""
    members = _members(obj)
    for key in rule["mime_keys"]:
        mime = _first(members, key, lambda v: _sibling_string(raw, v) and is_mime(raw, v))
        if mime is not None:
            return mime
    return None


def buffer_data(raw: dict, value: dict | Members) -> list | None:
    """Rule d: the byte array of a Buffer object, or None when it is not one."""
    rule = _rules(raw)["d"]
    members = _members(value)
    if _first(members, "type", lambda v: v == rule["type"]) is None:
        return None
    return _first(members, rule["array_key"], lambda v: isinstance(v, list) and bool(v))


def is_buffer(raw: dict, value: dict | Members) -> bool:
    """Rule d."""
    return buffer_data(raw, value) is not None


def is_replacement(raw: dict, value: str) -> bool:
    """Whether a string is already a complete replacement: the format with a
    mime that is unknown or a valid mime (the only mimes a replacement holds)
    and a byte_size of ASCII digits or unknown."""
    form = str(raw["replacement"]["format"])
    head, rest = form.split("<mime>")
    between, tail = rest.split("<byte_size>")
    if len(value) < len(head) + len(between) + len(tail):
        return False
    if not (value.startswith(head) and value.endswith(tail)):
        return False
    mime, sep, size = value[len(head) : len(value) - len(tail)].rpartition(between)
    unknown = str(raw["replacement"]["unknown"])
    digits = bool(size) and all("0" <= ch <= "9" for ch in size)
    return bool(sep) and (mime == unknown or is_mime(raw, mime)) and (digits or size == unknown)


def _sibling_string(raw: dict, value: Any) -> bool:
    """A sibling value rule e reads (a mime key, format, output_format): a
    non-empty string that is not a complete replacement. A replacement is never
    context, so a Buffer rule d replaced in one pass makes no token in the next."""
    return _non_empty_string(value) and not is_replacement(raw, value)


def _keyed_string(raw: dict, value: Any) -> bool:
    """A string rule e replaces: non-empty, and not already a replacement (so
    stripping twice changes nothing)."""
    return _non_empty_string(value) and not is_replacement(raw, value)


def _typed_keys(
    rule: dict, members: Members, parent_key: str | None, holder: Members | None
) -> list[dict]:
    """The typed keys that hold in an object: one of its types is a type
    member's value, the parent key is one of its parent keys, if it names
    any, and the holder (the nearest enclosing object) has one of its holder
    types, if it names any."""
    out = []
    for typed in rule["typed_keys"]:
        if "parent_keys" in typed and parent_key not in typed["parent_keys"]:
            continue
        if "holder_types" in typed:
            holder_types = typed["holder_types"]
            if holder is None or _first(holder, "type", lambda v, h=holder_types: v in h) is None:
                continue
        types = typed["types"]
        if _first(members, "type", lambda v, types=types: v in types) is not None:
            out.append(typed)
    return out


def is_url(raw: dict, value: Any) -> bool:
    """Whether a string starts with a URL scheme (rule e's url_scheme): an ASCII
    letter, then letters, digits, `+`, `-` or `.`, then a colon. Base64 holds no
    colon, so a base64 string never does."""
    pattern = str(_rules(raw)["e"]["url_scheme"])
    return isinstance(value, str) and re.match(pattern, value) is not None


def kept_url(raw: dict, value: Any) -> bool:
    """Whether a typed key that keeps URLs leaves a string alone for rule b: it
    starts with a URL scheme, and either it holds no data: (in any ASCII case)
    or the whole string is one rule b token, so rule b replaces all of it. Any
    other string holding data: (a percent-encoded data URL, a broken run, a
    link with a data URL after it) stays a rule e token and is replaced whole."""
    if not is_url(raw, value):
        return False
    if _DATA_ANYWHERE.search(value) is None:
        return True
    return whole_data_url(raw, value) is not None


def url_keys(
    raw: dict,
    value: dict | Members,
    parent_key: str | None,
    holder: dict | Members | None = None,
) -> set[str]:
    """The keys of an object whose URL strings rule e leaves to rule b: those
    of a typed key that keeps URLs and holds in the object."""
    rule = _rules(raw)["e"]
    typed = _typed_keys(rule, _members(value), parent_key, _holder(holder))
    return {t["key"] for t in typed if t.get("keeps_urls")}


def keyed_token(raw: dict, key: str, value: Any, urls: set[str]) -> bool:
    """A string rule e replaces under `key`: a keyed string, unless the key
    keeps URLs and the string is one it leaves to rule b (kept_url)."""
    return _keyed_string(raw, value) and not (key in urls and kept_url(raw, value))


def _holder(holder: dict | Members | None) -> Members | None:
    return None if holder is None else _members(holder)


def keyed_base64(
    raw: dict,
    value: dict | Members,
    parent_key: str | None,
    holder: dict | Members | None = None,
) -> list[int]:
    """Rule e: the positions of the members of `value` that hold base64 media,
    duplicates included: a keyed string, or an array holding one directly.
    Every member counts for the context: a sibling key with a non-empty string
    value that is not a complete replacement, the parent key, or a base64
    source. A base64 marker is context for its own keys alone. A blob's
    content, a typed key under one of its types (and its holder's, if it
    names any) and a source's bytes need no other context. A typed key that
    keeps URLs leaves a URL to rule b (kept_url). `holder` is the nearest
    enclosing object, as for rule d."""
    rule = _rules(raw)["e"]
    members = _members(value)
    context = (
        any(k in rule["sibling_keys"] and _sibling_string(raw, v) for k, v in members)
        or parent_key in rule["parent_keys"]
        or (
            parent_key == rule["source_key"]
            and _first(members, "type", lambda v: v == rule["source_type"]) is not None
        )
    )
    keys = set(rule["keys"]) if context else set()
    for marker in rule["base64_markers"]:
        if any(k == marker["key"] and v == marker["value"] for k, v in members):
            keys.update(marker["keys"])
    if _first(members, "type", lambda v: v == rule["blob_type"]) is not None:
        keys.add(rule["blob_key"])
    keys.update(t["key"] for t in _typed_keys(rule, members, parent_key, _holder(holder)))
    if parent_key == rule["source_key"]:
        keys.update(rule["source_bytes_keys"])
    urls = url_keys(raw, members, parent_key, holder)
    return [
        i
        for i, (k, v) in enumerate(members)
        if k in keys
        and (
            keyed_token(raw, k, v, urls)
            or (isinstance(v, list) and any(keyed_token(raw, k, item, urls) for item in v))
        )
    ]


def keyed_mime(
    raw: dict,
    value: dict | Members,
    parent_key: str | None,
    holder: dict | Members | None = None,
) -> str | None:
    """Rule e's mime type: the first mime key with a valid mime, else the first
    mime_formats entry whose sibling is a non-empty string and not a complete
    replacement (and whose parent keys, if any, include the parent) and whose
    mime is valid. Else, when a typed key that reads the holder's mime holds in
    the object, the first mime key of `holder` (the nearest enclosing object,
    as for rule d) with a valid mime."""
    rule = _rules(raw)["e"]
    members = _members(value)
    mime = _mime_key(raw, rule, members)
    if mime:
        return mime
    for entry in rule["mime_formats"]:
        if "parent_keys" in entry and parent_key not in entry["parent_keys"]:
            continue
        sibling = _first(members, entry["key"], lambda v: _sibling_string(raw, v))
        if sibling is None:
            continue
        mime = str(entry["mime"]).replace("<value>", sibling)
        if is_mime(raw, mime):
            return mime
    typed = _typed_keys(rule, members, parent_key, _holder(holder))
    if holder is not None and any(t.get("holder_mime") for t in typed):
        return _mime_key(raw, rule, holder)
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


#: How deep a JSON candidate may nest, arrays and objects counted together
#: from the candidate's root, continued through nested documents. Deeper is
#: "does not parse".
MAX_DEPTH = 64


class _Parser:
    """Strict RFC 8259: no NaN, Infinity, comments or trailing commas, and no
    more than MAX_DEPTH arrays and objects deep (`depth` already enclose the
    text). The depth limit also bounds the recursion."""

    def __init__(self, text: str, depth: int = 0):
        self.text = text
        self.i = 0
        self.depth = depth

    def enter(self) -> None:
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise _NotJson(f"deeper than {MAX_DEPTH} at {self.i}")

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
        return _Value(match.start(), match.end(), _number(match.group()))

    def object(self) -> _Value:
        start = self.i
        self.expect("{")
        self.enter()
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
        self.depth -= 1
        # The Python value keeps the last duplicate, as json.loads does; the
        # rules read `members`, every duplicate in document order.
        return _Value(start, self.i, {k: v.value for k, v in members}, members=members)

    def array(self) -> _Value:
        start = self.i
        self.expect("[")
        self.enter()
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
        self.depth -= 1
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


def _number(text: str) -> int | float:
    """A JSON number's value. Python refuses to read an int of more than 4300
    digits; such a number is read as a float, so no number raises."""
    try:
        return json.loads(text)
    except ValueError:
        return float(text)


def _parse(text: str, depth: int = 0) -> _Value | None:
    try:
        return _Parser(text, depth).document()
    except _NotJson:
        return None


def parse_json_candidate(text: str, depth: int = 0) -> Any:
    """A JSON candidate's value when it parses (strict RFC 8259, at most
    MAX_DEPTH deep counting the `depth` arrays and objects around it), else
    None."""
    if not is_json_candidate(text):
        return None
    document = _parse(text, depth)
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


def _strip_text(raw: dict, text: str, tokens: list[Token], depth: int = 0) -> list[_Edit]:
    """The edits on a string's text (a raw attribute, or a JSON string's
    unescaped value inside `depth` arrays and objects): the JSON walk when it is
    a candidate that parses, else rule b alone. A complete replacement is never
    stripped again."""
    if is_replacement(raw, text):
        return []
    if is_json_candidate(text):
        document = _parse(text, depth)
        if document is not None:
            edits: list[_Edit] = []
            _walk(raw, document, None, None, depth, tokens, edits)
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
    holder: Members | None,
    depth: int,
    tokens: list[Token],
    edits: list[_Edit],
) -> None:
    """Rules d, then e, then b, on one value, in document order. `holder` is the
    nearest enclosing object (through arrays), for rule d's mime type; `depth`
    is how many arrays and objects enclose the value. The parser's depth limit
    bounds the recursion."""
    if node.members is not None:
        members = [(key, child.value) for key, child in node.members]
        data = buffer_data(raw, members)
        if data is not None:
            mime = _mime_key(raw, _rules(raw)["d"], holder or [])
            tokens.append(Token("d", mime, len(data)))
            edits.append((node.start, node.end, _literal(raw, mime, len(data))))
            return
        keyed = set(keyed_base64(raw, members, parent_key, holder))
        mime = keyed_mime(raw, members, parent_key, holder) if keyed else None
        urls = url_keys(raw, members, parent_key, holder) if keyed else set()
        for i, (key, child) in enumerate(node.members):
            if i not in keyed:
                _walk(raw, child, key, members, depth + 1, tokens, edits)
            elif child.items is None:
                _keyed_token(raw, child, mime, tokens, edits)
            else:
                # A string array under the key: each string element is a token.
                for item in child.items:
                    if keyed_token(raw, key, item.value, urls):
                        _keyed_token(raw, item, mime, tokens, edits)
                    else:
                        _walk(raw, item, key, members, depth + 2, tokens, edits)
    elif node.items is not None:
        for child in node.items:
            _walk(raw, child, parent_key, holder, depth + 1, tokens, edits)
    elif node.chars is not None:
        # A JSON string: strip its unescaped value, then map each edit back to
        # the raw characters and write it escaped for this level.
        for start, end, text in _strip_text(raw, node.value, tokens, depth):
            raw_start = node.chars[start][0]
            raw_end = node.chars[end - 1][1] if end > start else raw_start
            edits.append((raw_start, raw_end, json_escape(text)))


def _keyed_token(
    raw: dict, node: _Value, mime: str | None, tokens: list[Token], edits: list[_Edit]
) -> None:
    """Rule e on one string literal: replaced whole, quotes included."""
    size = base64_size(node.value)
    tokens.append(Token("e", mime, size))
    edits.append((node.start, node.end, _literal(raw, mime, size)))


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


# --- LangChain v1 blocks -------------------------------------------------------
#
# langchain_v1_part is the reference for the part_shapes rule on a LangChain v1
# standard content block: the part one block makes, by the rule's numbered
# order, with its modality and MIME type. The v1 part examples are its tests.

#: The block types the rule maps, and the modality each names (None: none).
#: A text-plain block is mapped by its base64 alone.
LANGCHAIN_V1_TYPES = {
    "image": "image",
    "audio": "audio",
    "video": "video",
    "file": None,
    "text-plain": None,
}
#: The marker an instrumentor writes in place of a dropped reference.
REDACTED = "__REDACTED__"


def _usable(value: Any) -> bool:
    """A usable reference: a string that is neither empty nor __REDACTED__."""
    return isinstance(value, str) and value not in ("", REDACTED)


def _is_data_scheme(value: str) -> bool:
    """A value that is a data URL: it starts with data:, in any ASCII case."""
    return value[:5].lower() == "data:"


def _mime_modality(mime: str | None) -> str | None:
    """The modality a valid MIME type's prefix names, case-insensitively;
    document for any other valid type, None when there is none."""
    if mime is None:
        return None
    prefix = mime.split("/", 1)[0].lower()
    return prefix if prefix in ("image", "audio", "video") else "document"


def _extension_modality(data: dict, uri: str) -> str:
    """The modality a URI path's extension names (part_shapes extensions):
    query and fragment cut, the file name after the last '/', the extension
    after its last '.', ASCII case folded; document for any other."""
    path = re.split("[?#]", uri, maxsplit=1)[0]
    name = path.rsplit("/", 1)[-1]
    extension = name.rsplit(".", 1)[1] if "." in name else ""
    folded = extension.translate(str.maketrans(string.ascii_uppercase, string.ascii_lowercase))
    for modality, extensions in data["part_shapes"]["extensions"].items():
        if folded in extensions:
            return modality
    return "document"


def _part(kind: str, modality: str, **members: Any) -> dict:
    """A part with its members in the pinned order, unknown ones omitted."""
    part = {"type": kind, "modality": modality, **members}
    return {m: part[m] for m in PART_MEMBERS[kind] if part.get(m) is not None}


def _data_url_part(data: dict, url: str, hint: str | None, kind_modality: str | None) -> dict:
    """A data URL as a blob: rule (b)'s pattern matching the whole URL is
    base64, with its run's size; any other is not base64, with no size, and
    redacted_upstream when its payload is empty or None. The mime type is the
    URL's when valid, else the hint."""
    raw = data["raw_payloads"]
    match = whole_data_url(raw, url)
    if match:
        mime = _mime_or_unknown(raw, match.group(1)) or hint
        size, reason = run_size(match.group(3)), "not_captured"
    else:
        rest = url.split(":", 1)[1]
        mime = _mime_or_unknown(raw, re.split("[;,]", rest, maxsplit=1)[0]) or hint
        payload = rest.split(",", 1)[1] if "," in rest else ""
        size, reason = None, "redacted_upstream" if payload in ("", "None") else "not_captured"
    modality = _mime_modality(mime) or kind_modality or "document"
    return _part("blob", modality, mime_type=mime, byte_size=size, stripped_reason=reason)


def langchain_v1_part(data: dict, block: dict) -> dict | None:
    """The part a LangChain v1 block of type image, audio, video or file, or
    a text-plain block by base64, makes, by the first case that applies; None
    when it makes none and stays as it came. Only type, base64, url, file_id
    and mime_type are read, but for a native file part ((1) and (5)), which
    keeps a valid modality member first. A text-plain block reads its base64
    alone, in (2)."""
    raw = data["raw_payloads"]
    kind = block.get("type")
    if kind not in LANGCHAIN_V1_TYPES:
        return None
    kind_modality = LANGCHAIN_V1_TYPES[kind]
    mime = _mime_or_unknown(raw, block.get("mime_type"))
    modality = _mime_modality(mime) or kind_modality
    base64, url, file_id = block.get("base64"), block.get("url"), block.get("file_id")
    if kind == "text-plain":
        url = file_id = None
    own = block.get("modality")
    native = own if own in data["modalities"] else modality
    # (1) A file block by a usable file_id: a native file part.
    if kind == "file" and _usable(file_id):
        return _part("file", native or "document", mime_type=mime, file_id=file_id)
    # (2) A string base64: a blob, or the data URL rules when it is one. An
    # empty or __REDACTED__ one beside a file block's string file_id is no
    # usable reference, and the block reads on.
    dropped = kind == "file" and isinstance(file_id, str) and base64 in ("", REDACTED)
    if isinstance(base64, str) and not dropped:
        if _is_data_scheme(base64):
            return _data_url_part(data, base64, mime, kind_modality)
        return _part(
            "blob",
            modality or "document",
            mime_type=mime,
            byte_size=base64_size(base64),
            stripped_reason="not_captured",
        )
    # (3) A usable file_id: a file part.
    if _usable(file_id):
        return _part("file", modality or "document", mime_type=mime, file_id=file_id)
    # (4) A usable url: a blob when it is a data URL, or holds data: anywhere
    # else; otherwise a uri, as it came.
    if _usable(url):
        if _is_data_scheme(url):
            return _data_url_part(data, url, mime, kind_modality)
        if _DATA_ANYWHERE.search(url):
            return _part(
                "blob", modality or "document", mime_type=mime, stripped_reason="not_captured"
            )
        modality = modality or _extension_modality(data, url)
        return _part("uri", modality, mime_type=mime, uri=url)
    # (5) A file block whose file_id is a string and has no other usable
    # reference: a native file part, its file_id kept as written.
    if kind == "file" and isinstance(file_id, str):
        return _part("file", native or "document", mime_type=mime, file_id=file_id)
    # (6) A url or file_id that is a string, none usable: dropped upstream.
    if isinstance(url, str) or isinstance(file_id, str):
        return _part(
            "blob", modality or "document", mime_type=mime, stripped_reason="redacted_upstream"
        )
    return None


def _byte_size_kept(value: Any) -> int | None:
    """A native blob's byte_size, kept when it is a whole, non-negative number
    no larger than MAX_BYTE_SIZE (8.0 is 8); None otherwise."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value or value % 1 or not 0 <= value <= MAX_BYTE_SIZE:
        return None
    return int(value)


def native_part(data: dict, part: dict) -> dict | None:
    """The part a native blob, uri or file part in a message key is rebuilt
    into; None when it is left as it came (a uri or file_id that is not a
    string). An object of type file holding a string base64 or url is a
    LangChain v1 file block, read by langchain_v1_part."""
    raw = data["raw_payloads"]
    kind = part.get("type")
    mime = _mime_or_unknown(raw, part.get("mime_type"))
    own = part.get("modality") if part.get("modality") in data["modalities"] else None
    if kind == "file":
        if isinstance(part.get("base64"), str) or isinstance(part.get("url"), str):
            return langchain_v1_part(data, part)
        if not isinstance(part.get("file_id"), str):
            return None
        modality = own or _mime_modality(mime) or "document"
        return _part("file", modality, mime_type=mime, file_id=part["file_id"])
    if kind == "uri":
        uri = part.get("uri")
        if not isinstance(uri, str):
            return None
        blob_modality = _mime_modality(mime) or own
        if _is_data_scheme(uri):
            return _data_url_part(data, uri, mime, own)
        if _DATA_ANYWHERE.search(uri):
            return _part(
                "blob",
                blob_modality or "document",
                mime_type=mime,
                stripped_reason="not_captured",
            )
        modality = own or _mime_modality(mime) or _extension_modality(data, uri)
        return _part("uri", modality, mime_type=mime, uri=uri)
    if kind == "blob":
        content = part.get("content")
        if isinstance(content, str):
            if _is_data_scheme(content):
                return _data_url_part(data, content, mime, own)
            return _part(
                "blob",
                _mime_modality(mime) or own or "document",
                mime_type=mime,
                byte_size=base64_size(content),
                stripped_reason="not_captured",
            )
        reason = part.get("stripped_reason")
        if not isinstance(reason, str) or reason not in data["stripped_reasons"]:
            reason = "redacted_upstream" if content is None else "not_captured"
        return _part(
            "blob",
            own or _mime_modality(mime) or "document",
            mime_type=mime,
            byte_size=_byte_size_kept(part.get("byte_size")),
            stripped_reason=reason,
        )
    return None


# --- Provider URIs ----------------------------------------------------------------
#
# provider_uri_part is the reference for a provider item that points at its
# media by URI: the part its URI makes, with its modality and MIME type. The
# part examples that carry a provider item are its tests.

#: The flattened OpenInference keys of one image content entry, relative to
#: its message_content prefix.
OPENINFERENCE_IMAGE_TYPE = "message_content.type"
OPENINFERENCE_IMAGE_URL = "message_content.image.image.url"
OPENINFERENCE_IMAGE_MEDIA_TYPE = "message_content.image.media_type"


def _filename_modality(data: dict, filename: Any) -> str | None:
    """The modality an OpenAI file item's filename names; None with none."""
    if not isinstance(filename, str) or not filename:
        return None
    return _extension_modality(data, filename)


def _provider_uri(raw: dict, item: dict) -> tuple[Any, Any, str | None, bool] | None:
    """The URI a provider item points at, with the item's MIME type, the
    modality its kind names (for an OpenAI input_file, its filename does) and
    whether a uri reads its path's extension. None for an item that points at
    nothing by URI: a Vercel value with no URL scheme is base64."""
    kind = item.get("type")
    if kind == "image_url" and isinstance(item.get("image_url"), dict):
        return item["image_url"].get("url"), None, "image", False
    if kind == "input_image" and "image_url" in item:
        return item["image_url"], None, "image", False
    source = item.get("source")
    if kind in ("image", "document") and isinstance(source, dict) and source.get("type") == "url":
        return source.get("url"), source.get("media_type"), kind, False
    if kind == "input_file" and "file_url" in item:
        return item["file_url"], None, None, False
    if isinstance(item.get("file_data"), dict):
        file_data = item["file_data"]
        return file_data.get("file_uri"), file_data.get("mime_type"), None, True
    if kind in ("file", "image"):
        value = item.get("data" if kind == "file" else "image")
        if isinstance(value, dict) and value.get("type") == "url":
            value = value.get("url")
        elif not is_url(raw, value):
            return None
        return value, item.get("mediaType"), "image" if kind == "image" else None, kind == "file"
    if item.get(OPENINFERENCE_IMAGE_TYPE) == "image" and OPENINFERENCE_IMAGE_URL in item:
        return (
            item[OPENINFERENCE_IMAGE_URL],
            item.get(OPENINFERENCE_IMAGE_MEDIA_TYPE),
            "image",
            False,
        )
    return None


#: The references beside a provider URI that win over it when usable.
OTHER_REFERENCES = {"input_image": ("file_id",), "input_file": ("file_id", "file_data")}


def _another_reference_wins(item: dict, uri: Any) -> bool:
    """Whether the item's reader takes another reference before its URI. An
    input_file takes a usable file_id or file_data first. An input_image takes
    its image_url first, so its file_id wins only when the image_url is not
    usable."""
    if item.get("type") == "input_image" and _usable(uri):
        return False
    return any(_usable(item.get(key)) for key in OTHER_REFERENCES.get(item.get("type"), ()))


def provider_uri_part(data: dict, item: dict) -> dict | None:
    """The part a provider item that points at its media by URI makes: an
    OpenAI image_url's url, an input_image's image_url, an Anthropic image or
    document by a url source, an OpenAI input_file's file_url, a Gemini
    file_data's file_uri, a Vercel file or image part by URL (a value that
    starts with a URL scheme, or v7's {"type":"url"} data), and OpenInference's
    flattened image url, with its flattened image media_type as the MIME type
    the item gives. None for any other item, for a URI that is not a string,
    and for an item whose reader takes another usable reference first:
    an input_file's file_id or file_data, and an input_image's file_id when its
    image_url is empty or __REDACTED__. A usable image_url beside a file_id
    stays a uri (or a blob, for a data URL), as the readers take it first.

    An empty or __REDACTED__ URI was dropped upstream. A data URL follows the
    data URL rules. A URI that holds data: anywhere else, in any ASCII case, is
    a blob with no byte_size, so no byte of it is kept. Any other URI is a uri,
    as it came. A blob's modality comes from the MIME type, then the item's
    kind (an input_file's filename), then document; a uri's from the same, then
    its path's extension where the item reads one."""
    raw = data["raw_payloads"]
    found = _provider_uri(raw, item)
    if found is None:
        return None
    uri, mime, kind_modality, reads_extension = found
    if item.get("type") == "input_file":
        kind_modality = _filename_modality(data, item.get("filename"))
    if not isinstance(uri, str):
        return None
    if _another_reference_wins(item, uri):
        return None
    mime = _mime_or_unknown(raw, mime)
    blob_modality = _mime_modality(mime) or kind_modality or "document"
    if not _usable(uri):
        return _part("blob", blob_modality, mime_type=mime, stripped_reason="redacted_upstream")
    if _is_data_scheme(uri):
        return _data_url_part(data, uri, mime, kind_modality)
    if _DATA_ANYWHERE.search(uri):
        return _part("blob", blob_modality, mime_type=mime, stripped_reason="not_captured")
    modality = _mime_modality(mime) or kind_modality
    if modality is None:
        modality = _extension_modality(data, uri) if reads_extension else "document"
    return _part("uri", modality, mime_type=mime, uri=uri)


def part_text(part: dict) -> str:
    """A part as a message key holds it: compact JSON, members in order."""
    return json.dumps(part, separators=(",", ":"), ensure_ascii=False)


# --- byte objects ----------------------------------------------------------------
#
# serialize_value is the reference for raw_payloads.byte_objects on the Python
# side: a value written as the SDKs write a non-string attribute value, with
# every byte object written as the replacement, then stripped.


def byte_object_size(value: bytes | bytearray | memoryview) -> int | None:
    """A byte object's length in bytes; None (unknown) for a released
    memoryview."""
    if isinstance(value, memoryview):
        try:
            return value.nbytes
        except ValueError:
            return None
    return len(value)


#: A lone surrogate: a code point a Python string can hold and UTF-8 cannot.
_SURROGATE = re.compile("[\ud800-\udfff]")


def serialize_value(raw: dict, value: Any) -> str:
    """A value as an SDK writes it into an attribute: compact JSON with raw
    UTF-8, every bytes, bytearray or memoryview in it written as the
    replacement with the unknown mime, and the text then stripped. A lone
    surrogate, which raw UTF-8 cannot carry, is written as its \\uXXXX escape
    in lower-case hex, as the Python SDK and JSON.stringify write it. The
    SDKs' size cap and their fallback for a value JSON cannot hold are theirs,
    not this reference's."""

    def default(obj: Any) -> str:
        if isinstance(obj, (bytes, bytearray, memoryview)):
            return replacement(raw, None, byte_object_size(obj))
        raise TypeError(f"{type(obj).__name__} is not serializable")

    text = json.dumps(value, default=default, separators=(",", ":"), ensure_ascii=False)
    text = _SURROGATE.sub(lambda m: f"\\u{ord(m.group()):04x}", text)
    return strip_raw_payload(raw, text)


#: The Python byte objects.
BYTE_OBJECT_TYPES = (bytes, bytearray, memoryview)


class KvList(dict):
    """An OTLP kvlist_value: the mapping a JSON reader sees, where the last of
    a duplicate key wins, that still lists every member in wire order. items()
    gives every member, so json.dumps writes each one, as the sink does."""

    def __init__(self, members: Any = ()) -> None:
        self.members = list(members)
        super().__init__(self.members)

    def items(self) -> list[tuple[str, Any]]:  # type: ignore[override]
        return list(self.members)


def attribute_value(raw: dict, value: Any) -> Any:
    """A value an SDK sets directly as an attribute value: a byte object is
    the bare marker, at any depth of arrays and mappings. An array that holds
    a byte object beside an element that is then no string cannot stay
    homogeneous, so it is the SDK's JSON of the array (serialize_value), one
    string. Anything else is kept. This is the form the Python SDK sets, as
    OpenTelemetry Python holds a mapping and a nested array; the TypeScript
    SDK sets a walked mapping, or an array OpenTelemetry JS cannot hold, as
    the JSON of the value."""
    if isinstance(value, BYTE_OBJECT_TYPES):
        return replacement(raw, None, byte_object_size(value))
    if isinstance(value, KvList):
        return KvList((k, attribute_value(raw, v)) for k, v in value.items())
    if isinstance(value, dict):
        return {k: attribute_value(raw, v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        out = [attribute_value(raw, v) for v in value]
        if any(isinstance(v, BYTE_OBJECT_TYPES) for v in value) and not all(
            isinstance(v, str) for v in out
        ):
            return serialize_value(raw, list(value))
        return out
    return value


def otlp_bytes(text: str) -> bytes:
    """An OTLP JSON bytesValue as a protobuf JSON parser reads it: standard or
    URL-safe base64, padded or not (proto3 JSON emits standard, padded)."""
    if set("+/") & set(text) and set("-_") & set(text):
        raise ValueError(f"{text!r} mixes the base64 alphabets")
    body = text.rstrip("=").replace("-", "+").replace("_", "/")
    if len(body) % 4 == 1:
        raise ValueError(f"{text!r} is not base64")
    return base64.b64decode(body + "=" * (-len(body) % 4), validate=True)


def otlp_value(any_value: dict) -> Any:
    """An OTLP JSON AnyValue as a native value: a bytesValue is bytes, an
    arrayValue a list, a kvlistValue a KvList (every member kept, in wire
    order), an intValue an int (OTLP JSON may write it as a string), and an
    empty AnyValue, which OTLP defines as an empty value, None."""
    if "bytesValue" in any_value:
        return otlp_bytes(any_value["bytesValue"])
    if "arrayValue" in any_value:
        return [otlp_value(v) for v in any_value["arrayValue"].get("values") or []]
    if "kvlistValue" in any_value:
        values = any_value["kvlistValue"].get("values") or []
        return KvList((kv["key"], otlp_value(kv.get("value") or {})) for kv in values)
    if "intValue" in any_value:
        return int(any_value["intValue"])
    for key in ("stringValue", "boolValue", "doubleValue"):
        if key in any_value:
            return any_value[key]
    if not any_value:
        return None
    raise ValueError(f"no reference for {any_value!r}")


def otlp_attribute_value(raw: dict, any_value: dict) -> Any:
    """An OTLP JSON AnyValue as the sink stores it: read as a native value,
    every bytesValue becoming its bytes, then the SDKs' attribute_value
    rule, so a bytesValue at any depth is the bare marker with its decoded
    length."""
    return attribute_value(raw, otlp_value(any_value))


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
        " rule (b) writes the bare text, inside the quotes already there in a JSON string."
        f" A mime type goes in only when the whole of it matches `{replacement_['mime_pattern']}`"
        f" (token/token); anything else is `{replacement_['unknown']}`.",
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
        if "second_output" in golden:
            second = ", ".join(
                f"({t['rule']}) {t['mime']}, {t['byte_size']} bytes"
                for t in golden.get("second_tokens") or []
            )
            lines += ["Output of a second pass over the output:", ""]
            lines += ["```text", golden["second_output"], "```", ""]
            lines += [f"Tokens of the second pass: {second or 'none'}.", ""]
    lines += _render_byte_objects(raw["byte_objects"])
    return lines


def _render_byte_objects(section: dict) -> list[str]:
    lines = ["### Byte objects", "", _prose(section["rule"]), ""]
    lines += [f"**Size.** {_prose(section['size'])}", ""]
    for language in sorted(BYTE_OBJECT_LANGUAGES):
        lines.append(f"- {BYTE_OBJECT_LANGUAGES[language]}: " + _code_list(section[language]))
    lines.append("")
    for example in section["examples"]:
        lines += [f"#### `{example['name']}`", ""]
        if example.get("note"):
            lines += [_prose(example["note"]), ""]
        lines += [f"Value ({example['language']}):", "", "```text", example["value"], "```", ""]
        lines += ["Attribute value:", "", "```text", example["output"], "```", ""]
    attributes = section["attribute_values"]
    lines += ["#### Byte objects as attribute values", "", _prose(attributes["rule"]), ""]
    for example in attributes["examples"]:
        lines += [f"##### `{example['name']}`", ""]
        if example.get("note"):
            lines += [_prose(example["note"]), ""]
        language = ATTRIBUTE_VALUE_LANGUAGES[example["language"]]
        lines += [f"Value ({language}):", "", "```text", example["value"], "```", ""]
        output = example["output"]
        shown = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
        lines += ["Attribute value:", "", "```text", shown, "```", ""]
    return lines


def _param(value: Any) -> str:
    """A detection rule parameter, for the table."""
    if isinstance(value, list) and all(isinstance(v, dict) and "types" in v for v in value):
        return ", ".join(
            f"`{v['key']}` under type "
            + _code_list(v["types"])
            + (" and parent key " + _code_list(v["parent_keys"]) if v.get("parent_keys") else "")
            + (
                " in an object of type " + _code_list(v["holder_types"])
                if v.get("holder_types")
                else ""
            )
            + (" (keeps URLs)" if v.get("keeps_urls") else "")
            + (" (the holder's mime)" if v.get("holder_mime") else "")
            for v in value
        )
    if isinstance(value, list) and all(isinstance(v, dict) and "value" in v for v in value):
        return ", ".join(
            f"`{v['key']}` = `{v['value']}`, for " + _code_list(v.get("keys") or []) for v in value
        )
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


def _render_part_shapes(shapes: dict) -> list[str]:
    lines = ["## Part shapes", ""]
    lines += [
        "A normalized part in a message key is written with exactly these members, in order:",
        "",
    ]
    for kind, members in shapes["members"].items():
        lines.append(f"- `{kind}`: " + ", ".join(f"`{m}`" for m in members))
    lines += [""]
    lines += [f"- {_prose(rule)}" for rule in shapes["rules"]]
    lines += ["", "Filename extensions (lower case) that give a modality:", ""]
    for modality, extensions in shapes["extensions"].items():
        lines.append(f"- `{modality}`: " + ", ".join(f"`{e}`" for e in extensions))
    lines += ["- anything else: `document`", "", "Examples:", ""]
    for example in shapes["examples"]:
        lines += [f"#### `{example['name']}`", "", _prose(example["from"]), ""]
        lines += ["```json", example["part"], "```", ""]
    for example in shapes.get("in_place_examples") or []:
        lines += [f"#### `{example['name']}`", "", _prose(example["from"]), ""]
        lines += ["Input:", "", "```json", example["input"], "```", ""]
        lines += ["Output:", "", "```json", example["output"], "```", ""]
    for example in shapes.get("message_examples") or []:
        lines += [f"#### `{example['name']}`", "", _prose(example["from"]), ""]
        beside = "".join(
            f", with `{key}` = `{value}`"
            for key, value in (example.get("attributes") or {}).items()
        )
        source = f"{example['source']}{beside}"
        lines += [f"Input ({source}):", "", "```json", example["input"], "```", ""]
        lines += ["Output (gen_ai.input.messages):", "", "```json", example["output"], "```", ""]
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
        "item kind, a filename or a URI path's extension (see the part rules).",
        "A `blob` carries a `stripped_reason`:",
        "",
    ]
    for reason, meaning in data["stripped_reasons"].items():
        lines.append(f"- `{reason}`: {_prose(meaning)}")
    lines += [
        "",
        "*Fixtures* lists the recorded scenarios (`<family>/<scenario>`) that prove the",
        "row; a row with none says why in *Notes*.",
        "",
    ]
    lines += _render_part_shapes(data["part_shapes"])
    lines += _render_raw_payloads(data["raw_payloads"])
    for direction in ("input", "output"):
        rows = [r for r in data["rows"] if r["direction"] == direction]
        if not rows:
            continue
        header = ["Source", "Shape", "Becomes", "Modality", "Paths", "Fixtures", "Notes"]
        lines += [f"## {direction.capitalize()}", ""]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + " -- |" * len(header))
        for row in rows:
            notes = _prose(row.get("note"))
            if row.get("fixtures"):
                fixtures = ", ".join(f"`{f}`" for f in row["fixtures"])
            else:
                fixtures = "none"
                notes = _prose(f"{row.get('reason')} {row.get('note') or ''}")
            cells = [
                f"`{row['source']}`",
                f"`{_one_line(row['shape'])}`",
                _becomes(row),
                row.get("modality", "-"),
                ", ".join(row["paths"]),
                fixtures,
                notes,
            ]
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    return "\n".join(lines)
