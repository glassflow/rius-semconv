"""Renders a language's constants module with OTel Weaver.

    python -m generators.weaver --check [LANG ...]   exit 1 if Weaver's output differs from out/

`weaver registry generate` runs the template under templates/registry/<lang>/
against the Weaver registry in model/ and the params file templates/params.yaml,
both written from registry/ by tools/to_weaver.py, so run that first. Each run
fetches the pinned upstream registries.

The Weaver binary is $WEAVER, else .weaver/bin/weaver (tools/install_weaver.sh
puts it there), else `weaver` on PATH.
"""

from __future__ import annotations

import argparse
import difflib
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

from .registry import ROOT, load_data

LANGS = ("python", "typescript", "go")
MODEL = ROOT / "model"
TEMPLATES = ROOT / "templates"
PARAMS = TEMPLATES / "params.yaml"


class WeaverMissing(RuntimeError):
    pass


def weaver_binary() -> str:
    for candidate in (os.environ.get("WEAVER"), str(ROOT / ".weaver" / "bin" / "weaver")):
        if candidate and pathlib.Path(candidate).is_file():
            return candidate
    found = shutil.which("weaver")
    if found is None:
        raise WeaverMissing("Weaver is required; run tools/install_weaver.sh or set WEAVER")
    return found


def render(lang: str, *, include_planned: bool = False) -> str:
    """The module Weaver generates for `lang`, as text."""
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
            "--params",
            str(PARAMS),
            "--param",
            f"include_planned={'true' if include_planned else 'false'}",
            lang,
            tmp,
        ]
        done = subprocess.run(cmd, capture_output=True, text=True)
        if done.returncode != 0:
            raise RuntimeError(f"weaver registry generate {lang} failed:\n{done.stderr}")
        (path,) = pathlib.Path(tmp).iterdir()
        text = path.read_text()
    if lang == "go":
        from .go import gofmt

        text = gofmt(text)
    return text


def output_path(lang: str) -> pathlib.Path:
    preamble = load_data()["preamble"]
    return ROOT / "out" / lang / preamble[lang]["filename"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m generators.weaver")
    parser.add_argument("langs", nargs="*", metavar="LANG", help=f"any of {', '.join(LANGS)}")
    parser.add_argument(
        "--check", action="store_true", required=True, help="compare with the committed out/"
    )
    args = parser.parse_args(argv)
    langs = args.langs or list(LANGS)
    unknown = [lang for lang in langs if lang not in LANGS]
    if unknown:
        parser.error(f"unknown language(s): {', '.join(unknown)}")

    differs = []
    for lang in langs:
        path = output_path(lang)
        want = path.read_text()
        got = render(lang)
        if got != want:
            differs.append(path)
            sys.stdout.writelines(
                difflib.unified_diff(
                    want.splitlines(keepends=True),
                    got.splitlines(keepends=True),
                    fromfile=str(path.relative_to(ROOT)),
                    tofile=f"weaver {lang}",
                )
            )
    if differs:
        print(f"Weaver output differs from: {', '.join(str(p.relative_to(ROOT)) for p in differs)}")
        return 1
    print(f"Weaver output matches out/: {', '.join(langs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
