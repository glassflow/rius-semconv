"""tools/check_weaver_pins.py: the manifest, versions.env and version.txt agree.

The baseline test reads the committed files; each other test breaks one pin
and asserts the break is named.
"""

from __future__ import annotations

import copy

import pytest
import yaml

from conftest import ROOT
from tools import check_weaver_pins


@pytest.fixture(scope="module")
def committed():
    manifest = yaml.safe_load((ROOT / "model/manifest.yaml").read_text())
    env = check_weaver_pins.read_env(ROOT / "versions.env")
    version = (ROOT / "version.txt").read_text().strip()
    return manifest, env, version


def test_committed_pins_agree(committed):
    assert check_weaver_pins.check(*committed) == []


def test_schema_url_must_end_in_the_released_version(committed):
    manifest, env, _ = committed
    errors = check_weaver_pins.check(manifest, env, "9.9.9")
    assert any("schema_url" in e for e in errors), errors


def test_core_pin_must_match_versions_env(committed):
    manifest, env, version = committed
    env = {**env, "SEMCONV_VERSION": "v1.0.0"}
    errors = check_weaver_pins.check(manifest, env, version)
    assert any("pins core" in e for e in errors), errors


def test_genai_pin_must_match_versions_env(committed):
    manifest, env, version = committed
    env = {**env, "SEMCONV_GENAI_REF": "0" * 40}
    errors = check_weaver_pins.check(manifest, env, version)
    assert any("pins GenAI" in e for e in errors), errors


def test_genai_pin_must_be_a_full_sha(committed):
    manifest, env, version = committed
    manifest = copy.deepcopy(manifest)
    for dep in manifest["dependencies"]:
        dep["registry_path"] = dep["registry_path"].replace(env["SEMCONV_GENAI_REF"], "main")
    env = {**env, "SEMCONV_GENAI_REF": "main"}
    errors = check_weaver_pins.check(manifest, env, version)
    assert any("full commit SHA" in e for e in errors), errors
