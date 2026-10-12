"""CLI: lint the registry, then regenerate one or all languages into out/.

    python -m generators.generate                  # all languages and docs -> out/
    python -m generators.generate python go        # a subset
    python -m generators.generate --check          # exit 1 if out/ is stale
    python -m generators.generate --include-planned --out /tmp/preview

Exit codes: 0 ok, 1 stale output (--check), 2 the registry fails lint.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from collections.abc import Callable
from typing import NamedTuple

from . import go, python, typescript, usage_keys
from .registry import ROOT, Registry, load_data


class Target(NamedTuple):
    render: Callable[[Registry], str]
    directory: str
    #: The output file's name, when the preamble does not give one.
    filename: str | None = None


def render_usage_keys(reg: Registry) -> str:
    """The usage-key table, with where each key was recorded."""
    result = usage_keys.scan(reg.usage_keys, ROOT / "fixtures")
    return usage_keys.render_table(reg.usage_keys, result)


TARGETS = {
    "python": Target(python.render, "python"),
    "typescript": Target(typescript.render, "typescript"),
    "go": Target(go.render, "go"),
    "docs": Target(render_usage_keys, "docs", "usage-keys.md"),
}


def output_path(out_dir: pathlib.Path, reg: Registry, lang: str) -> pathlib.Path:
    target = TARGETS[lang]
    return out_dir / target.directory / (target.filename or reg.preamble[lang]["filename"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m generators.generate")
    parser.add_argument(
        "targets", nargs="*", metavar="LANG", help=f"any of {', '.join(TARGETS)}, or all (default)"
    )
    parser.add_argument("--out", default=str(ROOT / "out"))
    parser.add_argument(
        "--include-planned",
        action="store_true",
        help="also emit rows with status: planned (decided, but in no SDK yet)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing; exit 1 if any output file differs from what would be generated",
    )
    parser.add_argument("--stdout", action="store_true", help="print instead of writing")
    args = parser.parse_args(argv)

    unknown = [t for t in args.targets if t not in TARGETS and t != "all"]
    if unknown:
        parser.error(f"unknown target(s): {', '.join(unknown)}")
    langs = list(TARGETS) if not args.targets or "all" in args.targets else args.targets
    reg = Registry(load_data(), include_planned=args.include_planned)

    errors = reg.lint()
    if errors:
        print("registry fails lint:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 2

    out_dir = pathlib.Path(args.out)
    stale = []
    for lang in langs:
        text = TARGETS[lang].render(reg)
        path = output_path(out_dir, reg, lang)
        if args.stdout:
            sys.stdout.write(text)
        elif args.check:
            current = path.read_text() if path.exists() else None
            if current != text:
                stale.append(path)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            print(f"wrote {path}")
    if stale:
        for path in stale:
            print(f"stale: {path}", file=sys.stderr)
        print("regenerate with: python -m generators.generate", file=sys.stderr)
        return 1
    if args.check:
        print(f"up to date: {', '.join(langs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
