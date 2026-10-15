"""Loads the YAML registry and answers the questions the generators ask of it.

Deliberately dumb: no schema framework and no codegen DSL. If a generator
needs something the registry does not say, the fix is a column in the YAML,
not a special case here.

`Registry` takes the loaded data as an argument rather than reading files
itself, so tests can hand it a mutated copy (see tests/test_registry.py).
"""

from __future__ import annotations

import pathlib
import re
from typing import Any

import yaml

from . import usage_keys

ROOT = pathlib.Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "registry"

LANGS = ("python", "typescript", "go")
FILES = {
    "attributes": "attributes.yaml",
    "allowlists": "allowlists.yaml",
    "taxonomy": "taxonomy.yaml",
    "model_parameters": "model_parameters.yaml",
    "preamble": "preamble.yaml",
    "usage_keys": "usage_keys.yaml",
}

SYMBOLS = {"attribute", "prefix", "event", "value", "scope", "name", "fragment"}
ORIGINS = {"otel", "openinference", "rius"}
DIRECTIONS = {"emitted", "read"}
CATEGORIES = {"identity", "content", "metadata", "process_local"}
LEVELS = {"required", "conditionally_required", "recommended", "opt_in", "vendor"}
TYPES = {"string", "boolean", "int", "double", "string[]", "json"}
FILLS = {"native", "openinference", "vercel"}
STATUSES = {"shipped", "planned"}
PLACEMENT_SCOPES = {"resource", "span"}
STABILITIES = {"development", "stable"}
DEPRECATION_REASONS = {"renamed", "obsoleted", "uncategorized"}
UPSTREAMS = {"core", "genai"}


def defined_here(row: dict) -> bool:
    """Whether the Weaver registry defines this row's key (and so the row
    needs a brief, examples and a stability), rather than referencing an
    upstream definition or keeping the row in the params sidecar."""
    symbol, origin = row.get("symbol"), row.get("origin")
    if symbol == "attribute":
        return origin == "rius" or (origin == "openinference" and "upstream" not in row)
    if symbol == "prefix":
        return origin == "rius" and str(row.get("key", "")).startswith("rius.")
    return symbol == "event" and origin == "rius"


def referenced(row: dict) -> bool:
    """Whether the Weaver registry references this row's key upstream."""
    return row.get("symbol") == "attribute" and (row.get("origin") == "otel" or "upstream" in row)


# Internal ticket references. The registry is written for readers outside the
# team: a decision is recorded as its reason, never as a ticket number.
TICKET = re.compile(r"\b(?:RIUS|GLA2?)-\d+\b")


def load_data(root: pathlib.Path = REGISTRY) -> dict[str, Any]:
    return {name: yaml.safe_load((root / file).read_text()) for name, file in FILES.items()}


class Registry:
    def __init__(self, data: dict[str, Any], *, include_planned: bool = False) -> None:
        self.data = data
        self.include_planned = include_planned
        self.attributes: list[dict] = data["attributes"]["attributes"]
        # Deprecated keys with no generated constant. Never generated.
        self.retired: list[dict] = data["attributes"].get("retired") or []
        # Upstream keys other producers write that no SDK emits. Never generated.
        self.passthrough: list[dict] = data["attributes"].get("passthrough") or []
        self.allowlists: dict = data["allowlists"]
        self.taxonomy: dict = data["taxonomy"]
        self.model_parameters: dict = data["model_parameters"]
        self.preamble: dict = data["preamble"]
        self.usage_keys: dict = data["usage_keys"]
        self._by_const = {a["const"]: a for a in self.attributes if "const" in a}

    @classmethod
    def load(cls, *, include_planned: bool = False) -> Registry:
        return cls(load_data(), include_planned=include_planned)

    # --- filtering -----------------------------------------------------

    @staticmethod
    def languages(entry: dict) -> tuple[str, ...]:
        return tuple(entry.get("shipped_in", LANGS))

    def wanted(self, entry: dict, lang: str) -> bool:
        """Is this entry generated for `lang`?

        `status: planned` rows are decisions no SDK ships yet; they stay out
        of generated code unless asked for, so generated output describes
        what the SDKs actually do.
        """
        if not self.include_planned and entry.get("status", "shipped") != "shipped":
            return False
        return lang in self.languages(entry)

    def rows(self, lang: str) -> list[dict]:
        """Rows generated for `lang`, in order. A skipped row's `section`
        heading moves to the next emitted row, so a heading survives in a
        language that lacks the row it was written on."""
        out: list[dict] = []
        carried = None
        for a in self.attributes:
            if not self.wanted(a, lang):
                carried = a.get("section", carried)
                continue
            if carried is not None and "section" not in a:
                a = {**a, "section": carried}
            carried = None
            out.append(a)
        return out

    def row(self, const: str) -> dict:
        return self._by_const[const]

    def const_for_key(self, key: str, lang: str) -> str | None:
        """The constant a wire key is emitted as in `lang`, if it has one."""
        for a in self.rows(lang):
            if a["key"] == key and a["symbol"] in {"attribute", "prefix", "event"}:
                return a["const"]
        return None

    def members(self, section: str, lang: str) -> list[dict]:
        return [m for m in self.allowlists[section]["attributes"] if self.wanted(m, lang)]

    def included(self, section: str) -> list[str]:
        """The member allowlists folded into `section`, in order. A name that
        is not a member allowlist is skipped here and reported by the linter."""
        al = self.allowlists
        return [
            name
            for name in al[section].get("includes", [])
            if name in al and "attributes" in al[name]
        ]

    def table(self, name: str, lang: str) -> dict | None:
        """A taxonomy table, or None when it is not generated for `lang`."""
        table = self.taxonomy[name]
        return table if self.wanted(table, lang) else None

    def kind_names(self) -> list[str]:
        return [k["name"] for k in self.taxonomy["span_kind"]["values"]]

    def model_parameter_items(self) -> list[tuple[str, str, str | None]]:
        """(spelling, target key, note) in emission order; a group's note rides
        on its first spelling only."""
        out = []
        for group in self.model_parameters["groups"]:
            for i, spelling in enumerate(group["spellings"]):
                out.append((spelling, group["target"], group.get("note") if i == 0 else None))
        return out

    # --- lint ----------------------------------------------------------

    def lint(self) -> list[str]:
        """Every rule the registry must satisfy. Empty list = clean.

        Runs over ALL rows, planned included, and never raises on malformed
        input: a missing field is itself an error to report.
        """
        return (
            self._lint_prose()
            + self._lint_rows()
            + self._lint_weaver_fields()
            + self._lint_allowlists()
            + self._lint_taxonomy()
            + self._lint_model_parameters()
            + self._lint_usage_keys()
        )

    def _lint_prose(self) -> list[str]:
        errors: list[str] = []

        def walk(node: Any, path: str) -> None:
            if isinstance(node, dict):
                for k, v in node.items():
                    walk(v, f"{path}.{k}")
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, f"{path}[{i}]")
            elif isinstance(node, str):
                for ticket in TICKET.findall(node):
                    errors.append(f"{path}: ticket id {ticket} in the registry; write the reason")

        walk(self.data, "registry")
        return errors

    def _lint_languages(self, entry: dict, label: str) -> list[str]:
        errors = []
        if "shipped_in" in entry:
            for lang in entry["shipped_in"]:
                if lang not in LANGS:
                    errors.append(f"{label}: unknown language {lang}")
            if not str(entry.get("divergence", "")).strip():
                errors.append(f"{label}: shipped_in needs a divergence saying why")
        return errors

    def _lint_rows(self) -> list[str]:
        errors: list[str] = []
        seen_const: set[str] = set()
        seen_key: dict[tuple[str, str], str] = {}
        for i, r in enumerate(self.attributes):
            label = r.get("const", f"attributes[{i}]")
            for field in ("const", "key", "symbol"):
                if field not in r:
                    errors.append(f"{label}: missing {field}")
            if "const" not in r or "key" not in r:
                continue
            const, key, symbol = r["const"], r["key"], r.get("symbol")
            if const in seen_const:
                errors.append(f"duplicate const {const}")
            seen_const.add(const)
            if symbol in {"attribute", "prefix", "event"}:
                if (symbol, key) in seen_key:
                    errors.append(f"duplicate key {key} ({seen_key[(symbol, key)]}, {const})")
                seen_key[(symbol, key)] = const
            errors += self._lint_languages(r, const)
            errors += _enum(r, "symbol", SYMBOLS, const)
            errors += _enum(r, "status", STATUSES, const)
            errors += _enum(r, "direction", DIRECTIONS, const)
            if key.startswith("glassflow."):
                errors.append(f"{const}: key {key} is under glassflow.; Rius keys use rius.*")
            if symbol == "value" and r.get("of") not in self._by_const:
                errors.append(f"{const}: value of unknown const {r.get('of')}")
            if symbol in {"attribute", "prefix", "event", "scope", "fragment"}:
                errors += _enum(r, "origin", ORIGINS, const, required=True)
                if (
                    r.get("origin") == "rius"
                    and not key.startswith("rius.")
                    and not str(r.get("namespace_exception", "")).strip()
                ):
                    errors.append(
                        f"{const}: origin rius outside rius.* needs a namespace_exception"
                    )
            if symbol == "attribute":
                errors += self._lint_attribute(r)
        return errors

    def _lint_weaver_fields(self) -> list[str]:
        """The columns only the Weaver registry reads: brief, examples,
        stability, deprecated, upstream_equivalent, and the retired rows."""
        errors: list[str] = []
        keys = {r.get("key") for r in self.attributes if r.get("symbol") == "attribute"}
        upstream = {r.get("key") for r in self.attributes if referenced(r)}
        for i, r in enumerate(self.attributes):
            errors += _lint_weaver_row(r, r.get("const", f"attributes[{i}]"), keys, upstream)
        for i, r in enumerate(self.retired):
            label = r.get("key", f"retired[{i}]")
            for field in ("key", "type", "origin", "deprecated"):
                if field not in r:
                    errors.append(f"retired {label}: missing {field}")
            if r.get("symbol") != "attribute":
                errors.append(f"retired {label}: only attributes can be retired")
            if r.get("key") in keys:
                errors.append(f"retired {label}: still a row in attributes; keep it in one place")
            errors += _enum(r, "origin", ORIGINS, f"retired {label}")
            errors += _lint_weaver_row(r, f"retired {label}", keys, upstream)
        for i, r in enumerate(self.passthrough):
            label = f"passthrough {r.get('key', i)}"
            if r.get("key") in keys:
                errors.append(f"{label}: has a row in attributes; keep it in one place")
            if r.get("origin") != "otel":
                errors.append(f"{label}: only upstream (origin: otel) keys pass through")
            if not str(r.get("rationale", "")).strip():
                errors.append(f"{label}: needs a rationale saying who writes and reads it")
            errors += _enum(r, "upstream", UPSTREAMS, label, required=True)
        return errors

    def _lint_attribute(self, r: dict) -> list[str]:
        const = r["const"]
        errors = []
        kinds = r.get("kinds")
        if kinds is None:
            errors.append(f"{const}: attribute needs kinds")
        elif kinds == "resource":
            if "category" in r:
                errors.append(
                    f"{const}: resource attributes take no category; the four categories "
                    "describe a span's lifecycle"
                )
        else:
            if "category" not in r:
                errors.append(f"{const}: span attribute needs a category")
            errors += _enum(r, "category", CATEGORIES, const)
            errors += self._lint_kinds(kinds, const)
        if r.get("direction", "emitted") == "emitted" and "level" not in r:
            errors.append(f"{const}: emitted attribute needs a level")
        errors += _enum(r, "level", LEVELS, const)
        errors += _enum(r, "type", TYPES, const)
        for fill in r.get("fill", []):
            if fill not in FILLS:
                errors.append(f"{const}: fill {fill} is not one of {sorted(FILLS)}")
        errors += self._lint_placements(r)
        return errors

    def _lint_kinds(self, kinds: Any, label: str) -> list[str]:
        if kinds == "all":
            return []
        listed = kinds.get("all_but", []) if isinstance(kinds, dict) else kinds
        if not isinstance(listed, list):
            return [f"{label}: kinds must be resource, all, all_but or a list"]
        known = set(self.kind_names())
        return [f"{label}: unknown kind {k}" for k in listed if k not in known]

    def _lint_placements(self, r: dict) -> list[str]:
        const = r["const"]
        placements = r.get("placements", [])
        spans = [p for p in placements if p.get("scope") == "span"]
        errors = []
        for p in placements:
            if p.get("scope") not in PLACEMENT_SCOPES:
                errors.append(f"{const}: placement scope {p.get('scope')} unknown")
            errors += _enum(p, "level", LEVELS, const)
            if not p.get("brief"):
                errors.append(f"{const}: every placement needs a brief")
            if p.get("scope") == "span" and len(spans) > 1 and "when" not in p:
                errors.append(f"{const}: span placement needs `when` when a key has several")
            if p.get("scope") == "span":
                errors += self._lint_kinds(p.get("kinds", "all"), const)
        return errors

    def _lint_member(self, member: dict, label: str) -> list[str]:
        errors = self._lint_languages(member, label)
        ref = member.get("ref")
        if ref is None:
            if "key" not in member:
                errors.append(f"{label}: member needs ref or key")
            return errors
        if ref not in self._by_const:
            return errors + [f"{label}: unknown const {ref}"]
        row_langs = self.languages(self._by_const[ref])
        for lang in self.languages(member):
            if lang not in row_langs:
                errors.append(f"{label}: {ref} is not generated for {lang}")
        return errors

    def _lint_allowlists(self) -> list[str]:
        errors: list[str] = []
        al = self.allowlists
        for section in ("pending_identity", "content", *self.included("content")):
            for m in al[section]["attributes"]:
                errors += self._lint_member(m, section)
        for m in al["content_prefix_identity"]["attributes"]:
            errors += self._lint_member(m, "content_prefix_identity")
        for section in al["content"].get("includes", []):
            if section not in al or "attributes" not in al[section]:
                errors.append(f"content.includes: {section} is not a member allowlist")
        for ref in al["pending_identity_prefixes"]["refs"]:
            if ref not in self._by_const:
                errors.append(f"pending_identity_prefixes: unknown const {ref}")
        for ref in al["content"].get("derived", {}).get("prefixes", []):
            if ref not in self._by_const:
                errors.append(f"content.derived: unknown const {ref}")

        pending_refs = {m["ref"] for m in al["pending_identity"]["attributes"] if "ref" in m}
        content_refs = {m["ref"] for m in al["content"]["attributes"] if "ref" in m}
        content_keys = {m["key"] for m in al["content"]["attributes"] if "key" in m}
        for section in self.included("content"):
            # A key in both would be a duplicate entry in Go's map literal,
            # which does not compile, and a second place to forget to edit.
            keys = {m["key"] for m in al[section]["attributes"] if "key" in m}
            for key in sorted(keys & content_keys):
                errors.append(f"{key}: in both content and {section}; list it once")
            content_keys |= keys
        pending_prefixes = [
            self._by_const[r]["key"]
            for r in al["pending_identity_prefixes"]["refs"]
            if r in self._by_const
        ]
        content_prefixes = al["content_prefixes"]["values"]
        for m in al["content_prefix_identity"]["attributes"]:
            key = m.get("key", "")
            if not any(key.startswith(p) for p in content_prefixes):
                errors.append(
                    f"content_prefix_identity: {key} is under no content prefix, "
                    "so it needs no exception"
                )

        for ref in sorted(pending_refs & set(self._by_const)):
            category = self._by_const[ref].get("category")
            if category not in {"identity", "process_local"}:
                errors.append(f"{ref}: pending member is {category}, not identity")
        for ref in sorted(content_refs & set(self._by_const)):
            category = self._by_const[ref].get("category")
            if category != "content":
                errors.append(f"{ref}: content allowlist member is {category}, not content")

        for r in self.attributes:
            if r.get("symbol") != "attribute" or r.get("kinds") == "resource":
                continue
            if "const" not in r or "key" not in r:
                continue
            const, key = r["const"], r["key"]
            if r.get("category") == "identity" and r.get("direction", "emitted") == "emitted":
                covered = const in pending_refs or any(key.startswith(p) for p in pending_prefixes)
                if not covered and not str(r.get("not_pending", "")).strip():
                    errors.append(
                        f"{const}: identity but not pending (add it to pending_identity, "
                        "or say why in not_pending)"
                    )
            if r.get("category") == "content":
                covered = (
                    const in content_refs
                    or key in content_keys
                    or any(key.startswith(p) for p in content_prefixes)
                )
                if not covered:
                    errors.append(f"{const}: content but not on the content allowlist")
        return errors

    def _lint_taxonomy(self) -> list[str]:
        errors: list[str] = []
        kinds = self.kind_names()
        for name, table in self.taxonomy.items():
            errors += self._lint_languages(table, name)
            for lang in self.languages(table):
                if lang not in table.get("names", {}):
                    errors.append(f"{name}: no emitted name for {lang}")
            if name == "span_kind":
                continue
            mapping = table.get("map", {})
            if name == "kind_by_operation":
                errors += [f"{name}: unknown kind {k}" for k in mapping.values() if k not in kinds]
                continue
            errors += [f"{name}: unknown kind {k}" for k in mapping if k not in kinds]
            if name == "name_target_by_kind":
                unknown = [c for c in mapping.values() if c not in self._by_const]
                errors += [f"{name}: unknown const {c}" for c in unknown]
            if name in {"operation_by_kind", "name_target_by_kind"}:
                unmapped = table.get("unmapped", {})
                for kind in kinds:
                    if kind not in mapping and kind not in unmapped:
                        errors.append(f"{name}: {kind} is neither mapped nor unmapped")
            if name == "otel_kind_by_kind":
                errors += [f"{name}: {k} has no OTel kind" for k in kinds if k not in mapping]
        return errors

    def _lint_model_parameters(self) -> list[str]:
        errors: list[str] = []
        seen: set[str] = set()
        for group in self.model_parameters["groups"]:
            target = group.get("target", "")
            if not target.startswith("gen_ai.request."):
                errors.append(f"model_parameters: target {target} is not under gen_ai.request.")
            for spelling in group.get("spellings", []):
                if spelling in seen:
                    errors.append(f"model_parameters: duplicate spelling {spelling}")
                seen.add(spelling)
        fallback = self.model_parameters.get("fallback_prefix")
        if fallback not in self._by_const:
            errors.append(f"model_parameters: unknown fallback_prefix {fallback}")
        return errors

    def _lint_usage_keys(self) -> list[str]:
        # .get: a row missing its key is reported by _lint_rows, not raised here.
        keys = {a.get("key") for a in self.attributes if a.get("symbol") == "attribute"}
        prefixes = {a.get("key") for a in self.attributes if a.get("symbol") == "prefix"}
        return usage_keys.lint(self.usage_keys, keys, prefixes)


def _lint_weaver_row(r: dict, label: str, keys: set, upstream: set) -> list[str]:
    errors: list[str] = []
    symbol = r.get("symbol")
    own = defined_here(r)
    if referenced(r):
        for field in ("brief", "examples", "stability"):
            if field in r:
                errors.append(f"{label}: {field} on a referenced upstream key; upstream defines it")
    errors += _enum(r, "upstream", UPSTREAMS, label)
    if "upstream_divergence" in r:
        d = r["upstream_divergence"]
        if not referenced(r):
            errors.append(f"{label}: upstream_divergence only goes on a referenced upstream key")
        elif not isinstance(d, dict) or not str(d.get("note", "")).strip():
            errors.append(f"{label}: upstream_divergence needs a note")
        elif d.get("type") not in TYPES or d.get("type") == r.get("type"):
            errors.append(f"{label}: upstream_divergence type must be a type other than the row's")
    if own:
        for field in ("brief", "stability"):
            if field not in r:
                errors.append(f"{label}: missing {field}")
        if symbol != "event" and "examples" not in r:
            errors.append(f"{label}: missing examples")
    if "brief" in r:
        brief = r["brief"]
        if not isinstance(brief, str) or not brief.strip() or "\n" in brief.strip():
            errors.append(f"{label}: brief must be one line of text")
        elif not brief.strip().endswith("."):
            errors.append(f"{label}: brief must end with a full stop")
    errors += _enum(r, "stability", STABILITIES, label)
    if symbol == "prefix":
        errors += _enum(r, "type", TYPES, label)
    if "examples" in r:
        examples = r["examples"]
        if not isinstance(examples, list) or not examples:
            errors.append(f"{label}: examples must be a non-empty list")
        elif symbol == "event":
            errors.append(f"{label}: an event takes no examples")
        else:
            for example in examples:
                if not _example_fits(example, r.get("type")):
                    errors.append(f"{label}: example {example!r} is not a {r.get('type')}")
    if "deprecated" in r:
        d = r["deprecated"]
        if not isinstance(d, dict):
            errors.append(f"{label}: deprecated must be a mapping")
        else:
            errors += _enum(d, "reason", DEPRECATION_REASONS, label, required=True)
            if not str(d.get("note", "")).strip():
                errors.append(f"{label}: deprecated needs a note saying why")
            if d.get("reason") == "renamed":
                if d.get("renamed_to") not in keys:
                    errors.append(
                        f"{label}: renamed_to {d.get('renamed_to')} is not an attribute row"
                    )
            elif "renamed_to" in d:
                errors.append(f"{label}: renamed_to only goes with reason renamed")
            if "replaced_by" in d:
                if d.get("reason") != "uncategorized":
                    errors.append(f"{label}: replaced_by only goes with reason uncategorized")
                elif d["replaced_by"] not in upstream:
                    errors.append(
                        f"{label}: replaced_by {d['replaced_by']} is not an upstream attribute row"
                    )
    if "upstream_equivalent" in r:
        upstream = r["upstream_equivalent"]
        if not isinstance(upstream, str) or upstream.startswith("rius."):
            errors.append(f"{label}: upstream_equivalent must name an upstream key")
        if "deprecated" in r:
            errors.append(
                f"{label}: a deprecated row takes no upstream_equivalent; "
                "its deprecation note names the upstream key"
            )
    return errors


def _example_fits(example: Any, type_: str | None) -> bool:
    """Whether an example value has the row's type. A prefix with no type
    takes any value; json is carried on the wire as a string."""
    if type_ is None:
        return isinstance(example, (str, int, float, bool))
    if type_ in {"string", "json"}:
        return isinstance(example, str)
    if type_ == "boolean":
        return isinstance(example, bool)
    if type_ == "int":
        return isinstance(example, int) and not isinstance(example, bool)
    if type_ == "double":
        return isinstance(example, (int, float)) and not isinstance(example, bool)
    if type_ == "string[]":
        return isinstance(example, list) and all(isinstance(x, str) for x in example)
    return False


def _enum(entry: dict, field: str, allowed: set[str], label: str, *, required=False) -> list[str]:
    if field not in entry:
        return [f"{label}: missing {field}"] if required else []
    value = entry[field]
    if value not in allowed:
        return [f"{label}: {field} {value} is not one of {sorted(allowed)}"]
    return []


def comment(text: str | None, marker: str, indent: str = "") -> list[str]:
    """Render authored prose as comment lines.

    Line breaks in the registry are authored, not reflowed; a blank line in
    the prose becomes a bare comment marker, so a paragraph break survives.
    """
    if not text:
        return []
    return [f"{indent}{marker} {line}".rstrip() for line in text.rstrip("\n").split("\n")]
