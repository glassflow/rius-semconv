"""The semconv.ts counterpart of check_parity.py.

Weaker than the Python check on purpose: it compares exported string
constants by regex rather than parsing TypeScript, because pulling a TS
parser into this repo to check one file is not worth it. The set literals,
the enum and the two functions are checked only for presence. The Python
check is the load-bearing one; this is the sanity net.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONST = re.compile(r'export const ([A-Z][A-Z0-9_]*)\s*(?::[^=]*)?=\s*"([^"]*)"')
REQUIRED = (
    "PENDING_IDENTITY_ATTRIBUTES",
    "PENDING_IDENTITY_PREFIXES",
    "CONTENT_ATTRIBUTES",
    "CONTENT_ATTRIBUTE_PREFIXES",
    "CONTENT_ATTRIBUTE_SUFFIXES",
    "INVOCATION_PARAMETERS_CONTENT_MEMBERS",
    "export enum SpanKind",
    "export function otelSpanKind",
    "export function kindAttributes",
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", default=str(ROOT.parent / "rius-sdk-typescript"))
    p.add_argument("--reference", default="origin/main:src/semconv.ts")
    p.add_argument("--generated", default=str(ROOT / "out" / "semconv.ts"))
    args = p.parse_args(argv)

    reference = subprocess.run(
        ["git", "-C", args.repo, "show", args.reference],
        check=True, capture_output=True, text=True,
    ).stdout
    generated = pathlib.Path(args.generated).read_text()

    ref = dict(CONST.findall(reference))
    gen = dict(CONST.findall(generated))
    missing = sorted(set(ref) - set(gen))
    added = sorted(set(gen) - set(ref))
    changed = sorted(n for n in set(ref) & set(gen) if ref[n] != gen[n])
    absent = [r for r in REQUIRED if r not in generated]

    print(f"reference: {args.reference} ({len(ref)} exported string constants)")
    print(f"generated: {args.generated} ({len(gen)})")
    print(f"MISSING: {missing}\nADDED: {added}\nCHANGED: {changed}")
    print(f"ABSENT NON-STRING SYMBOLS: {absent}")
    ok = not (missing or added or changed or absent)
    print("\nPARITY: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
