"""fixtures/_media.mjs must produce the same bytes as fixtures/_media.py, so a
Node recording and a Python one send identical media."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
sys.path.insert(0, str(FIXTURES))

import _media  # noqa: E402

NODE = shutil.which("node")

SCRIPT = """
import { PNG_1X1, WAV_SILENT, PDF_ONE_PAGE, bigPng, b64, dataUrl } from "./_media.mjs";
console.log(JSON.stringify({
  png: b64(PNG_1X1), wav: b64(WAV_SILENT), pdf: b64(PDF_ONE_PAGE),
  big: b64(bigPng(32000)), url: dataUrl("image/png", PNG_1X1),
}));
"""


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_node_and_python_payloads_are_byte_identical():
    out = subprocess.run(
        [NODE, "--input-type=module", "-e", SCRIPT],
        cwd=FIXTURES,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    node = json.loads(out)
    assert node == {
        "png": _media.b64(_media.PNG_1X1),
        "wav": _media.b64(_media.WAV_SILENT),
        "pdf": _media.b64(_media.PDF_ONE_PAGE),
        "big": _media.b64(_media.big_png(32000)),
        "url": _media.data_url("image/png", _media.PNG_1X1),
    }
