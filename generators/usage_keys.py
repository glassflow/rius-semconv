"""Usage keys: the decisions in registry/usage_keys.yaml, checked against the fixtures.

Three questions, three functions:

- `lint`: is the file well formed? Run by the registry linter with every
  other rule, so it needs no fixtures.
- `check`: does every usage key in a recording have a decision, and does each
  normalizer do what its decision says? Run by tools/check_usage_keys.py.
- `render_table`: the generated table, out/docs/usage-keys.md.

What a normalizer did is read off the expected results, never off its code:
the Python SDK's expected spans, the TypeScript SDK's (Vercel families), and
the sink's stored rows (sink-only families). Each normalizer is checked only
on the families whose expected result it produced.
"""

from __future__ import annotations

import json
import pathlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

DECISIONS = {"canonical", "mapped", "ignored", "not_usage", "gap"}
#: Decisions that leave a usage key unread: each must say why.
REASONED = {"ignored", "not_usage", "gap"}

#: manifest expected.source -> the normalizer whose behaviour that result shows.
SOURCES = {"python-sdk": "python", "typescript-sdk": "typescript", "sink": "sink"}

ROWS_SUFFIX = ".expected-row.json"


# --- the file ----------------------------------------------------------------


def entry_name(entry: dict) -> str:
    return entry.get("key") or f"{entry.get('prefix')}*"


def decision_for(data: dict, key: str) -> dict | None:
    """The entry deciding `key`: an exact key first, then the longest prefix."""
    for entry in data["keys"]:
        if entry.get("key") == key:
            return entry
    prefixes = [e for e in data["keys"] if "prefix" in e and key.startswith(e["prefix"])]
    return max(prefixes, key=lambda e: len(e["prefix"]), default=None)


def is_usage_key(data: dict, key: str) -> bool:
    lowered = key.lower()
    return any(word in lowered for word in data["match"])


def lint(data: dict, registry_keys: set[str], registry_prefixes: set[str]) -> list[str]:
    """Every rule the file itself must satisfy. Empty list = clean."""
    errors: list[str] = []
    normalizers = set(data.get("normalizers", []))
    if not data.get("match"):
        errors.append("usage_keys: match must list at least one word")
    seen: set[str] = set()
    for entry in data.get("keys", []):
        name = entry_name(entry)
        label = f"usage_keys: {name}"
        if ("key" in entry) == ("prefix" in entry):
            errors.append(f"{label}: needs exactly one of key or prefix")
            continue
        if name in seen:
            errors.append(f"{label}: listed twice")
        seen.add(name)
        decision = entry.get("decision")
        if decision not in DECISIONS:
            errors.append(f"{label}: decision must be one of {sorted(DECISIONS)}")
            continue
        if decision in REASONED and not str(entry.get("reason", "")).strip():
            errors.append(f"{label}: a {decision} key needs a reason")
        if decision == "canonical":
            # Exact for a key: a registry prefix such as gen_ai.usage. covers
            # any spelling under it, real or not.
            covered = (
                entry["prefix"] in registry_prefixes
                if "prefix" in entry
                else entry["key"] in registry_keys
            )
            if not covered:
                errors.append(f"{label}: canonical, but not a registry attribute or prefix")
        if decision == "mapped":
            target = entry.get("target")
            if target not in registry_keys:
                errors.append(f"{label}: target {target} is not a registry attribute")
            elif (decision_for(data, target) or {}).get("decision") != "canonical":
                errors.append(f"{label}: target {target} is not a canonical usage key")
            mapped_by = entry.get("mapped_by") or []
            if not mapped_by:
                errors.append(f"{label}: mapped, but mapped_by names no normalizer")
            for normalizer in mapped_by:
                if normalizer not in normalizers:
                    errors.append(f"{label}: unknown normalizer {normalizer}")
        else:
            for only in ("target", "mapped_by"):
                if only in entry:
                    errors.append(f"{label}: {only} is only for mapped keys")
    return errors


# --- the fixtures ------------------------------------------------------------


@dataclass
class Observation:
    """One usage key on one span, before and after one normalizer."""

    key: str
    family: str
    scenario: str
    span: str
    normalizer: str
    kept: bool
    after: set[str]


@dataclass
class Scan:
    #: usage key -> families it was recorded in (raw spans only)
    recorded: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    #: usage key -> families whose expected result has it (output only)
    produced: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    observations: list[Observation] = field(default_factory=list)


def _keys(attributes: list[dict]) -> set[str]:
    return {a["key"] for a in attributes}


def _span_keys(span: dict) -> set[str]:
    keys = _keys(span.get("attributes", []))
    for event in span.get("events", []):
        keys |= _keys(event.get("attributes", []))
    return keys


def scan(data: dict, fixtures: pathlib.Path) -> Scan:
    """Every usage key in every recording, and what became of it."""
    result = Scan()
    for manifest_path in sorted(fixtures.glob("*/manifest.json")):
        family_dir = manifest_path.parent
        manifest = json.loads(manifest_path.read_text())
        family = manifest["family"]
        for recording_name, entry in manifest["recordings"].items():
            raw = json.loads((family_dir / recording_name).read_text())["recordings"]
            expected_entry = entry["expected"]
            normalizer = SOURCES.get(expected_entry["source"])
            expected = json.loads((family_dir / expected_entry["file"]).read_text())
            after_by_span = _after(expected, expected_entry["file"].endswith(ROWS_SUFFIX))
            for scenario in raw:
                for key in _keys(scenario.get("resource", {}).get("attributes", [])):
                    if is_usage_key(data, key):
                        result.recorded[key].add(family)
                for wrapped in scenario["spans"]:
                    span = wrapped["span"]
                    before = _span_keys(span)
                    after = after_by_span.get((scenario["scenario"], span["spanId"]))
                    for key in before:
                        if not is_usage_key(data, key):
                            continue
                        result.recorded[key].add(family)
                        if normalizer is not None and after is not None:
                            result.observations.append(
                                Observation(
                                    key,
                                    family,
                                    scenario["scenario"],
                                    span["name"],
                                    normalizer,
                                    key in after,
                                    after,
                                )
                            )
            for keys in after_by_span.values():
                for key in keys:
                    if is_usage_key(data, key):
                        result.produced[key].add(family)
    return result


def _after(expected: dict, rows: bool) -> dict[tuple[str, str], set[str]]:
    """(scenario, span id) -> the keys a normalizer left on that span."""
    out: dict[tuple[str, str], set[str]] = {}
    for scenario in expected["recordings"]:
        name = scenario["scenario"]
        if rows:
            for row in scenario["rows"]:
                out[(name, row["SpanID"])] = set(row.get("SpanAttributes") or {})
        else:
            for wrapped in scenario["spans"]:
                out[(name, wrapped["span"]["spanId"])] = _span_keys(wrapped["span"])
    return out


_USAGE = "gen_ai.usage."
_AGGREGATED = "rius.aggregated_usage."


def _target_set(target: str, after: Any) -> bool:
    """The target is on the span, or moved aside with the rest of its usage.

    A wrapper span that repeats a call's usage keeps it as
    rius.aggregated_usage.<suffix> (see RIUS_AGGREGATED_USAGE_PREFIX): the
    mapping happened, then the whole family moved.
    """
    if target in after:
        return True
    return target.startswith(_USAGE) and _AGGREGATED + target[len(_USAGE) :] in after


def check(data: dict, result: Scan) -> list[str]:
    """Undecided keys, and decisions a normalizer's output contradicts."""
    errors: list[str] = []
    for key in sorted(set(result.recorded) | set(result.produced)):
        if decision_for(data, key) is None:
            families = sorted(result.recorded.get(key) or result.produced.get(key, ()))
            errors.append(
                f"{key}: usage key with no decision in registry/usage_keys.yaml "
                f"(in {', '.join(families)})"
            )
    reported: set[tuple[str, str, str]] = set()
    for obs in result.observations:
        entry = decision_for(data, obs.key)
        if entry is None or entry["decision"] in ("canonical", "not_usage"):
            # A canonical key may legitimately move (a run total to
            # rius.aggregated_usage.*); what happens to it is not a mapping.
            # A key that is not usage (a request parameter such as
            # ai.settings.maxOutputTokens, mapped to gen_ai.request.max_tokens)
            # is no usage key's business either.
            continue
        maps = entry["decision"] == "mapped" and obs.normalizer in entry.get("mapped_by", [])
        problem = None
        if maps and obs.kept:
            problem = f"{obs.normalizer} should map it to {entry['target']}, but kept it"
        elif maps and not _target_set(entry["target"], obs.after):
            problem = f"{obs.normalizer} removed it without setting {entry['target']}"
        elif not maps and not obs.kept:
            problem = f"{obs.normalizer} removed it, but mapped_by does not list {obs.normalizer}"
        if problem and (obs.key, obs.normalizer, obs.family) not in reported:
            reported.add((obs.key, obs.normalizer, obs.family))
            errors.append(f"{obs.key}: {problem} ({obs.family}/{obs.scenario} {obs.span!r})")
    return errors


# --- the table ---------------------------------------------------------------

DECISION_ORDER = ["canonical", "mapped", "gap", "ignored", "not_usage"]


def _cell(entry: dict, normalizer: str) -> str:
    decision = entry["decision"]
    if decision == "canonical":
        return "canonical"
    if decision == "mapped":
        return f"→ `{entry['target']}`" if normalizer in entry["mapped_by"] else "keeps"
    return "keeps"


def _one_line(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip().replace("|", "\\|")


def render_table(data: dict, result: Scan) -> str:
    """out/docs/usage-keys.md: every decision, what each normalizer does, where it was seen."""
    normalizers = data["normalizers"]
    lines = [
        "<!-- Generated from registry/usage_keys.yaml and the recordings under",
        "     fixtures/ by `python -m generators.generate`. Do not edit. -->",
        "",
        "# Usage keys",
        "",
        "Every token, usage and cost key an instrumentor sends, the decision recorded",
        "for it, and what each normalizer does with it: maps it (→ the canonical",
        "key), keeps it on the span, or treats it as canonical. *Recorded in* lists",
        "the families whose raw spans carry the key; a key that only appears after",
        "normalization lists the families whose expected result carries it",
        "(*produced in*).",
        "",
        "`tools/check_usage_keys.py` fails CI on a recorded usage key with no",
        "decision, and checks each normalizer against the expected results of the",
        "families it produced them for.",
        "",
    ]
    order = {d: i for i, d in enumerate(DECISION_ORDER)}
    entries = sorted(data["keys"], key=lambda e: (order[e["decision"]], entry_name(e)))
    for decision in DECISION_ORDER:
        group = [e for e in entries if e["decision"] == decision]
        if not group:
            continue
        lines += [f"## {decision.replace('_', ' ').capitalize()}", ""]
        header = ["Key", *normalizers, "Recorded in", "Why"]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + " -- |" * len(header))
        for entry in group:
            recorded = _families(data, entry, result.recorded)
            produced = _families(data, entry, result.produced)
            seen = ", ".join(recorded) or (
                f"produced in {', '.join(produced)}" if produced else "not in any recording"
            )
            cells = [
                f"`{entry_name(entry)}`",
                *(_cell(entry, n) for n in normalizers),
                seen,
                _one_line(entry.get("reason")),
            ]
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    return "\n".join(lines)


def _families(data: dict, entry: dict, seen: dict[str, set[str]]) -> list[str]:
    """The families a key the entry decides was seen in (a prefix entry
    covers only the keys no more specific entry decides)."""
    families: set[str] = set()
    for key, where in seen.items():
        if decision_for(data, key) is entry:
            families |= where
    return sorted(families)
