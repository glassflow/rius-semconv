"""Writes the attribute reference with OTel Weaver, for this repository and
for the docs site.

    python -m generators.registry_docs            write docs/registry/ and out/docs-site/
    python -m generators.registry_docs --check    exit 1 if either is stale

`weaver registry generate` runs the templates under templates/registry/markdown/
against the Weaver registry in model/ (written from registry/ by
tools/to_weaver.py, so run that first): one page per namespace Rius defines
keys in, a page of the upstream keys it references, linked to the upstream
registries at the versions versions.env pins, and a page of the other
producers' keys. Each run fetches the pinned upstream registries.

Every page renders twice. docs/registry/<page>.md is the Markdown read in this
repository. out/docs-site/ holds the same pages as Nextra pages
(<slug>/page.mdx, the index as page.mdx, and _meta.tsx for the navigation),
which glassflow-docs copies from each release tag to SITE_BASE. Those pages
name the release they come from (version.txt); release-please moves that
version in the release PR, which is why each page.mdx is one of its
extra-files.
"""

from __future__ import annotations

import argparse
import difflib
import pathlib
import shutil
import subprocess
import sys
import tempfile

from tools.check_weaver_pins import read_env

from .registry import ROOT
from .weaver import MODEL, TEMPLATES, weaver_binary

DOCS = ROOT / "docs" / "registry"
SITE = ROOT / "out" / "docs-site"
# Where glassflow-docs serves out/docs-site/; the site pages link each other
# under it.
SITE_BASE = "/rius/interoperability/registry"
# Weaver writes the site pages under this directory of its output.
SITE_PREFIX = "site/"


def render() -> dict[str, str]:
    """Every page Weaver generates, by path relative to its output: the
    Markdown pages at the top, the site's under SITE_PREFIX."""
    env = read_env(ROOT / "versions.env")
    version = (ROOT / "version.txt").read_text().strip()
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
            "--param",
            f"version={version}",
            "--param",
            f"docs_base={SITE_BASE}",
            "markdown",
            tmp,
        ]
        done = subprocess.run(cmd, capture_output=True, text=True)
        if done.returncode != 0:
            raise RuntimeError(f"weaver registry generate markdown failed:\n{done.stderr}")
        root = pathlib.Path(tmp)
        return {
            p.relative_to(root).as_posix(): p.read_text()
            for p in sorted(root.rglob("*"))
            if p.is_file()
        }


def split(pages: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """(docs/registry/ pages, out/docs-site/ pages), each by path relative
    to its directory."""
    docs = {n: t for n, t in pages.items() if not n.startswith(SITE_PREFIX)}
    site = {n.removeprefix(SITE_PREFIX): t for n, t in pages.items() if n.startswith(SITE_PREFIX)}
    return docs, site


def committed(directory: pathlib.Path) -> dict[str, str]:
    if not directory.is_dir():
        return {}
    return {
        p.relative_to(directory).as_posix(): p.read_text()
        for p in sorted(directory.rglob("*"))
        if p.is_file()
    }


def stale(pages: dict[str, str], docs: pathlib.Path = DOCS) -> list[str]:
    """One unified diff per page that differs from `docs`: changed, missing or left over."""
    have = committed(docs)
    diffs = []
    for name in sorted(pages.keys() | have.keys()):
        want, got = have.get(name, ""), pages.get(name, "")
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
    """Replaces everything under `docs` with `pages`."""
    if docs.is_dir():
        shutil.rmtree(docs)
    for name, text in pages.items():
        path = docs / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m generators.registry_docs")
    parser.add_argument(
        "--check", action="store_true", help="compare with docs/registry/ and out/docs-site/"
    )
    args = parser.parse_args(argv)

    outputs = list(zip((DOCS, SITE), split(render()), strict=True))
    if not args.check:
        for directory, pages in outputs:
            write(pages, directory)
            print(f"wrote {len(pages)} file(s) to {directory.relative_to(ROOT)}")
        return 0
    status = 0
    for directory, pages in outputs:
        diffs = stale(pages, directory)
        rel = directory.relative_to(ROOT)
        if diffs:
            sys.stdout.writelines(diffs)
            print(f"{rel} is stale: run 'python -m generators.registry_docs'")
            status = 1
        else:
            print(f"{rel}: up to date ({len(pages)} files)")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
