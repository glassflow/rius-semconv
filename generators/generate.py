"""CLI: lint the registry, then regenerate one or all languages into out/.

    python -m generators.generate                  # all languages and docs -> out/
    python -m generators.generate python go        # a subset
    python -m generators.generate --check          # exit 1 if out/ is stale
    python -m generators.generate --include-planned --out /tmp/preview

The language modules are rendered by OTel Weaver (generators/weaver.py) from
the templates under templates/registry/, against the Weaver registry and
params file that tools/to_weaver.py writes from registry/. Those are written
into a temporary directory first, so the output follows registry/ even before
model/ is rewritten. The usage-key table is rendered here.

Exit codes: 0 ok, 1 stale output (--check), 2 the registry fails lint.
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

from tools import to_weaver

from . import media_parts, usage_keys, weaver
from .registry import ROOT, Registry, load_data

TARGETS = (*weaver.LANGS, "docs", "media")


def render_usage_keys(reg: Registry) -> str:
    """The usage-key table, with where each key was recorded."""
    result = usage_keys.scan(reg.usage_keys, ROOT / "fixtures")
    return usage_keys.render_table(reg.usage_keys, result)


def stage_weaver_inputs(data: dict, tmp: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    """Writes what tools/to_weaver.py would write from `data` under `tmp`,
    with the hand-maintained manifest and the templates. Returns the model
    and templates directories."""
    model, templates = tmp / "model", tmp / "templates"
    model.mkdir()
    shutil.copy(weaver.MODEL / "manifest.yaml", model / "manifest.yaml")
    shutil.copytree(weaver.TEMPLATES / "registry", templates / "registry")
    for path, text in to_weaver.render(data).items():
        dest = tmp / path.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
    return model, templates


def render(reg: Registry, targets: list[str]) -> dict[str, str]:
    """target -> generated text. The languages render in parallel, since each
    Weaver run spends most of its time fetching the upstream registries."""
    out = {}
    langs = [t for t in targets if t in weaver.LANGS]
    if langs:
        with tempfile.TemporaryDirectory() as tmp:
            model, templates = stage_weaver_inputs(reg.data, pathlib.Path(tmp))
            with ThreadPoolExecutor(len(langs)) as pool:
                texts = pool.map(
                    lambda lang: weaver.render(
                        lang, include_planned=reg.include_planned, model=model, templates=templates
                    ),
                    langs,
                )
                out.update(zip(langs, texts, strict=True))
    if "docs" in targets:
        out["docs"] = render_usage_keys(reg)
    if "media" in targets:
        out["media"] = media_parts.render_table(reg.media_parts)
    return {t: out[t] for t in targets}


def output_path(out_dir: pathlib.Path, reg: Registry, target: str) -> pathlib.Path:
    if target == "docs":
        return out_dir / "docs" / "usage-keys.md"
    if target == "media":
        return out_dir / "docs" / "media-parts.md"
    return out_dir / target / reg.preamble[target]["filename"]


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
    targets = list(TARGETS) if not args.targets or "all" in args.targets else args.targets
    reg = Registry(load_data(), include_planned=args.include_planned)

    errors = reg.lint()
    if errors:
        print("registry fails lint:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 2

    out_dir = pathlib.Path(args.out)
    stale = []
    for target, text in render(reg, targets).items():
        path = output_path(out_dir, reg, target)
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
        print(f"up to date: {', '.join(targets)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
