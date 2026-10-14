"""Check that each upstream key we reference has the type our row says.

    python tools/check_weaver_types.py <resolved.yaml>

<resolved.yaml> is `weaver registry resolve -r model --v2` output. A ref takes
its type from the pinned upstream registry, so when upstream retypes a key (or
a pin moves) our row and the wire stop matching it silently. This fails when a
row's `type` differs from the resolved upstream type and the row records no
`upstream_divergence` naming that type, and when a recorded divergence no
longer exists.

Exit 0 when every ref agrees, 1 otherwise, with one line per problem.
"""

from __future__ import annotations

import pathlib
import sys

import yaml

GROUPS = {"rius.upstream", "rius.passthrough"}


def upstream_type(attribute: dict) -> str:
    """The resolved type, with an enum reduced to its value type."""
    t = attribute["type"]
    if isinstance(t, dict):
        value = t["members"][0]["value"]
        return {bool: "boolean", int: "int", str: "string"}.get(type(value), "string")
    return t


def agrees(ours: str | None, theirs: str) -> bool:
    if ours is None or theirs == "any":
        return True
    return ours == theirs or (ours == "json" and theirs == "string")


def check(resolved: dict) -> list[str]:
    errors = []
    for group in resolved["registry"]["attribute_groups"]:
        if group["id"] not in GROUPS:
            continue
        for a in group["attributes"]:
            rius = (a.get("annotations") or {}).get("rius") or {}
            ours, theirs = rius.get("type"), upstream_type(a)
            divergence = rius.get("upstream_divergence")
            if agrees(ours, theirs):
                if divergence:
                    errors.append(
                        f"{a['key']}: upstream_divergence recorded, but upstream is {theirs} "
                        f"and the row is {ours}; drop it"
                    )
            elif not divergence or divergence.get("type") != theirs:
                errors.append(
                    f"{a['key']}: the row says {ours}, upstream says {theirs}; fix the row "
                    "or record an upstream_divergence"
                )
    return errors


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    resolved = yaml.safe_load(pathlib.Path(argv[0]).read_text())
    errors = check(resolved)
    for e in errors:
        print(e)
    print("upstream types: " + ("agree" if not errors else f"{len(errors)} problem(s)"))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
