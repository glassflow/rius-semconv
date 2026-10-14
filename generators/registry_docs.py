"""Writes the attribute reference under docs/registry/ with OTel Weaver.

    python -m generators.registry_docs            write docs/registry/
    python -m generators.registry_docs --check    exit 1 if docs/registry/ is stale

`weaver registry generate` runs the templates under templates/registry/markdown/
against the Weaver registry in model/ (written from registry/ by
tools/to_weaver.py, so run that first): one page per namespace Rius defines
keys in, a page of the upstream keys it references, linked to the upstream
registries at the versions versions.env pins, and a page of the other
producers' keys. Each run fetches the pinned upstream registries.
"""

from __future__ import annotations

import argparse
import difflib
import pathlib
import subprocess
import sys
import tempfile

from tools.check_weaver_pins import read_env

from .registry import ROOT
from .weaver import MODEL, TEMPLATES, weaver_binary

DOCS = ROOT / "docs" / "registry"


def render() -> dict[str, str]:
    """Every page Weaver generates, by file name."""
    env = read_env(ROOT / "versions.env")
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [
            weaver_binary(),
            "registry",
            "generate",
            "--registry",
            str(MODEL),
            "--v2",
            "--templates",
            str(TEMPLATES),
            "--param",
            f"semconv_version={env['SEMCONV_VERSION']}",
            "--param",
            f"genai_ref={env['SEMCONV_GENAI_REF']}",
            "markdown",
            tmp,
        ]
        done = subprocess.run(cmd, capture_output=True, text=True)
        if done.returncode != 0:
            raise RuntimeError(f"weaver registry generate markdown failed:\n{done.stderr}")
        return {p.name: p.read_text() for p in sorted(pathlib.Path(tmp).iterdir())}


def stale(pages: dict[str, str], docs: pathlib.Path = DOCS) -> list[str]:
    """One unified diff per page that differs from docs/: changed, missing or left over."""
    committed = {p.name: p.read_text() for p in docs.glob("*.md")} if docs.is_dir() else {}
    diffs = []
    for name in sorted(pages.keys() | committed.keys()):
        want, got = committed.get(name, ""), pages.get(name, "")
        if want != got:
            rel = (docs / name).relative_to(ROOT)
            diffs.append(
                "".join(
                    difflib.unified_diff(
                        want.splitlines(keepends=True),
                        got.splitlines(keepends=True),
                        fromfile=str(rel),
                        tofile=f"weaver markdown {name}",
                    )
                )
            )
    return diffs


def write(pages: dict[str, str], docs: pathlib.Path = DOCS) -> None:
    docs.mkdir(parents=True, exist_ok=True)
    for old in docs.glob("*.md"):
        if old.name not in pages:
            old.unlink()
    for name, text in pages.items():
        (docs / name).write_text(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m generators.registry_docs")
    parser.add_argument("--check", action="store_true", help="compare with docs/registry/")
    args = parser.parse_args(argv)

    pages = render()
    if not args.check:
        write(pages)
        print(f"wrote {len(pages)} page(s) to {DOCS.relative_to(ROOT)}")
        return 0
    diffs = stale(pages)
    if diffs:
        sys.stdout.writelines(diffs)
        print(f"{DOCS.relative_to(ROOT)} is stale: run 'python -m generators.registry_docs'")
        return 1
    print(f"{DOCS.relative_to(ROOT)}: up to date ({len(pages)} pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
