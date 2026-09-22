"""CLI: regenerate one or all language outputs into out/."""

from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys

import yaml

from . import go, python, typescript
from .registry import REGISTRY, ROOT, Registry

TARGETS = {
    "python": (python.render, "semconv.py"),
    "typescript": (typescript.render, "semconv.ts"),
    "go": (go.render, "semconv.go"),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="generate")
    parser.add_argument("targets", nargs="*", choices=[*TARGETS, "all"], default=["all"])
    parser.add_argument("--out", default=str(ROOT / "out"))
    parser.add_argument(
        "--include-planned",
        action="store_true",
        help="also emit rows with status: planned (RIUS-917 rows no SDK has yet)",
    )
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args(argv)

    names = list(TARGETS) if "all" in args.targets or not args.targets else args.targets
    reg = Registry(include_planned=args.include_planned)
    preamble = yaml.safe_load((REGISTRY / "preamble.yaml").read_text())

    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        render, filename = TARGETS[name]
        text = render(reg, preamble)
        if args.stdout:
            sys.stdout.write(text)
        else:
            path = out_dir / filename
            path.write_text(text)
            if name == "go" and shutil.which("gofmt"):
                # Go's own formatter owns alignment; generating aligned
                # columns by hand would be a second formatter to maintain.
                subprocess.run(["gofmt", "-w", str(path)], check=True)
            print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
