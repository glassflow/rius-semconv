"""Media parts: the mapping in registry/media_parts.yaml, checked and rendered.

Three questions, three functions:

- `lint`: is the file well formed? Run by the registry linter with every
  other rule, so it needs no fixtures.
- `check_fixture_refs`: does every scenario a row names exist? A fixtures id
  is `<family>/<scenario>`: `<family>` is a directory under fixtures/ and
  `<scenario>` is a key of `recordings.<file>.scenarios` in that family's
  manifest.json. Run by tools/check_fixtures.py.
- `render_table`: the generated table, out/docs/media-parts.md.
"""

from __future__ import annotations

import json
import pathlib
import re

NORMALIZED = {"blob", "uri", "file", "text", "generic"}
DIRECTIONS = {"input", "output"}
PATHS = {"passthrough", "openinference", "openllmetry", "laminar", "vercel", "native"}
#: The modality column's extra value: the modality rule (MIME type first).
FROM_MIME = "from_mime"


def row_name(row: dict) -> str:
    return f"media_parts: {row.get('source')} {row.get('shape')}:"


def normalized_of(row: dict) -> list[str]:
    value = row.get("normalized")
    return list(value) if isinstance(value, list) else [value]


# --- the file ----------------------------------------------------------------


def lint(data: dict) -> list[str]:
    """Every rule the file itself must satisfy. Empty list = clean."""
    errors: list[str] = []
    modalities = set(data.get("modalities") or [])
    if not modalities:
        errors.append("media_parts: modalities must list at least one modality")
    for reason, meaning in (data.get("stripped_reasons") or {}).items():
        if not str(meaning).strip():
            errors.append(f"media_parts: stripped_reasons {reason} needs a description")
    if not data.get("stripped_reasons"):
        errors.append("media_parts: stripped_reasons must list at least one reason")
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
        modality = row.get("modality")
        if modality is None:
            if normalized != ["text"]:
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
    return re.sub(r"\s+", " ", str(text or "")).strip().replace("|", "\\|")


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
        lines.append(f"- `{reason}`: {_one_line(meaning)}")
    lines += [
        "",
        "*Fixtures* lists the recorded scenarios (`<family>/<scenario>`) that prove the",
        "row; a row with none says why in *Why*.",
        "",
    ]
    for direction in ("input", "output"):
        rows = [r for r in data["rows"] if r["direction"] == direction]
        if not rows:
            continue
        header = ["Source", "Shape", "Becomes", "Modality", "Paths", "Fixtures", "Why"]
        lines += [f"## {direction.capitalize()}", ""]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + " -- |" * len(header))
        for row in rows:
            why = _one_line(row.get("note"))
            if row.get("fixtures"):
                fixtures = ", ".join(f"`{f}`" for f in row["fixtures"])
            else:
                fixtures = "none"
                why = _one_line(f"{row.get('reason')} {row.get('note') or ''}")
            cells = [
                f"`{row['source']}`",
                _one_line(row["shape"]),
                " / ".join(normalized_of(row)),
                row.get("modality", "-"),
                ", ".join(row["paths"]),
                fixtures,
                why,
            ]
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    return "\n".join(lines)
