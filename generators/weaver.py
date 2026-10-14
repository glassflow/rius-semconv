"""Renders a language's constants module with OTel Weaver.

`weaver registry generate` runs the template under templates/registry/<lang>/
against a Weaver registry and its params file, the ones tools/to_weaver.py
writes from registry/ (model/ and templates/params.yaml). Each run fetches the
pinned upstream registries. Go output is piped through gofmt, which owns
alignment.

The Weaver binary is $WEAVER, else .weaver/bin/weaver (tools/install_weaver.sh
puts it there), else `weaver` on PATH.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import tempfile

from .registry import ROOT

LANGS = ("python", "typescript", "go")
MODEL = ROOT / "model"
TEMPLATES = ROOT / "templates"


class WeaverMissing(RuntimeError):
    pass


class GofmtMissing(RuntimeError):
    pass


def weaver_binary() -> str:
    for candidate in (os.environ.get("WEAVER"), str(ROOT / ".weaver" / "bin" / "weaver")):
        if candidate and pathlib.Path(candidate).is_file():
            return candidate
    found = shutil.which("weaver")
    if found is None:
        raise WeaverMissing("Weaver is required; run tools/install_weaver.sh or set WEAVER")
    return found


def gofmt(source: str) -> str:
    binary = shutil.which("gofmt")
    if binary is None:
        raise GofmtMissing("gofmt is required to generate Go; install Go or put gofmt on PATH")
    return subprocess.run([binary], input=source, capture_output=True, text=True, check=True).stdout


def render(
    lang: str,
    *,
    include_planned: bool = False,
    model: pathlib.Path = MODEL,
    templates: pathlib.Path = TEMPLATES,
) -> str:
    """The module Weaver generates for `lang` from `model` and
    `templates`/params.yaml, as text."""
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [
            weaver_binary(),
            "registry",
            "generate",
            "--registry",
            str(model),
            "--v2",
            "--templates",
            str(templates),
            "--params",
            str(templates / "params.yaml"),
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
    return gofmt(text) if lang == "go" else text
