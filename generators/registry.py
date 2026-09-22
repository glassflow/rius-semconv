"""Loads the YAML registry into plain dicts and answers the questions the
three generators ask of it.

Deliberately dumb: no schema framework, no codegen DSL. If a generator needs
something the registry does not say, the fix is a column in the YAML, not a
special case here.
"""

from __future__ import annotations

import pathlib
from typing import Any

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "registry"

SHIPPED = "shipped"


def _load(name: str) -> Any:
    return yaml.safe_load((REGISTRY / name).read_text())


class Registry:
    def __init__(self, *, include_planned: bool = False) -> None:
        self.include_planned = include_planned
        self.attributes: list[dict] = _load("attributes.yaml")["attributes"]
        self.allowlists: dict = _load("allowlists.yaml")
        self.taxonomy: dict = _load("taxonomy.yaml")
        self.model_parameters: dict = _load("model_parameters.yaml")
        self._by_const = {a["const"]: a for a in self.attributes}

    # --- filtering -----------------------------------------------------

    def wanted(self, entry: dict) -> bool:
        """Is this row emitted into generated code?

        `status: planned` rows are in the RIUS-917 table but in no SDK yet.
        They stay out of generated code by default so the first generated
        semconv.py is a no-op swap for the hand-written one.
        """
        return self.include_planned or entry.get("status", SHIPPED) == SHIPPED

    def symbols(self) -> list[dict]:
        """Emittable symbols, in registry order, minus the ones that belong to
        the allowlist section of the output."""
        return [
            a
            for a in self.attributes
            if self.wanted(a) and a.get("group") != "partial_content"
        ]

    def const(self, name: str) -> dict:
        return self._by_const[name]

    def key_of(self, name: str) -> str:
        return self._by_const[name]["key"]

    # --- allowlists ----------------------------------------------------

    def allowlist(self, which: str) -> dict:
        """`which` is "pending_identity" or "content"."""
        block = self.allowlists[which]
        # The content block's `prefixes` is a {doc, values} pair matched by
        # string prefix, not a list of registry rows; only the pending block
        # names constants there.
        prefixes = block.get("prefixes", [])
        return {
            "doc": block["doc"],
            "attributes": [e for e in block["attributes"] if self.wanted(e)],
            "prefixes": [e for e in prefixes if isinstance(e, dict) and self.wanted(e)],
        }

    def partial_content(self) -> list[dict]:
        out = []
        for spec in self.allowlists["partial_content"]:
            entry = self._by_const[spec["attribute"]]
            if self.wanted(entry):
                out.append({"entry": entry, **spec})
        return out

    # --- taxonomy ------------------------------------------------------

    def span_kinds(self) -> list[dict]:
        return self.taxonomy["span_kind"]["values"]

    def operation_by_kind(self) -> dict[str, str]:
        m = dict(self.taxonomy["operation_by_kind"]["map"])
        if self.include_planned:
            m.update(self.taxonomy["operation_by_kind"].get("planned", {}))
        return m

    def otel_kind_by_kind(self) -> dict[str, str]:
        return self.taxonomy["otel_kind_by_kind"]["map"]


def comment(text: str | None, marker: str, indent: str = "") -> list[str]:
    """Render authored prose as comment lines.

    Line breaks in the registry are authored, not reflowed: that is what lets
    the generated Python keep the hand-written file's wording verbatim.
    """
    if not text:
        return []
    lines = []
    for line in text.rstrip("\n").split("\n"):
        lines.append(f"{indent}{marker} {line}".rstrip())
    return lines
