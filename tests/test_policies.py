"""The Weaver policies under policies/check, and tools/weaver_check.py.

Each directory under policies/tests is a case: a `current` registry, an
optional `base` (the baseline), and expected.yaml listing every finding the
case must produce. The gate test runs the real model/ against itself as the
baseline, with breaking changes applied, and the shared OTel packs loaded.

The policy tests need `weaver` on PATH and network access (Weaver clones the
pinned upstream registries and policy packs). Without weaver they skip, unless
RIUS_REQUIRE_WEAVER is set, as in CI's weaver job, where a missing weaver fails.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess

import pytest
import yaml

from conftest import ROOT
from tools import weaver_check
from tools.check_weaver_pins import read_env

CASES = sorted(p for p in (ROOT / "policies/tests").iterdir() if p.is_dir())


@pytest.fixture(scope="module")
def weaver():
    if shutil.which("weaver") is None:
        if os.environ.get("RIUS_REQUIRE_WEAVER"):
            pytest.fail("RIUS_REQUIRE_WEAVER is set but weaver is not on PATH")
        pytest.skip("weaver is not on PATH (tools/install_weaver.sh)")


def keyed(found: list[dict]) -> set[tuple[str, str]]:
    """(id, the attribute key or location the finding names)."""
    return {
        (
            f["id"],
            (f.get("context") or {}).get("attribute_key")
            or (f.get("context") or {}).get("location"),
        )
        for f in found
    }


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_policy_case(weaver, case):
    baseline = pathlib.Path("base") if (case / "base").is_dir() else None
    _, found = weaver_check.findings(
        pathlib.Path("current"), baseline, [str(ROOT / "policies/check")], cwd=case
    )
    expected = {
        (e["id"], e.get("attribute_key") or e.get("location"))
        for e in yaml.safe_load((case / "expected.yaml").read_text())
    }
    assert keyed(found) == expected


def _load(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text())


def _dump(path: pathlib.Path, doc: dict) -> None:
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))


def _attribute(doc: dict, key: str) -> dict:
    return next(a for a in doc["attributes"] if a.get("key") == key)


def test_gate_fails_breaking_changes_against_a_release(weaver, tmp_path):
    """The gate as CI runs it once a release has model/: the real registry is
    the baseline, and a copy with one change of each kind is checked
    against it. Exactly the breaking changes fail; the deprecation into a
    dependency's key with reason uncategorized passes."""
    base = tmp_path / "base"
    current = tmp_path / "current"
    shutil.copytree(ROOT / "model", base)
    shutil.copytree(ROOT / "model", current)

    own = _load(current / "rius/registry.yaml")
    # Removed: a shipped key, gone without deprecation.
    own["attributes"] = [a for a in own["attributes"] if a.get("key") != "rius.context.sizes"]
    for group in own["attribute_groups"]:
        group["attributes"] = [
            r for r in group["attributes"] if r.get("ref") != "rius.context.sizes"
        ]
    # Retyped: a development key changes type.
    _attribute(own, "rius.workspace")["type"] = "int"
    # Renamed into a dependency's key: Weaver rejects renamed_to there.
    _attribute(own, "rius.main_agent.name")["deprecated"] = {
        "reason": "renamed",
        "renamed_to": "gen_ai.main_agent.name",
    }
    # Moved into a dependency's key the documented way: passes.
    _attribute(own, "rius.main_agent.id")["deprecated"] = {
        "reason": "uncategorized",
        "note": "Use gen_ai.main_agent.id.",
    }
    _dump(current / "rius/registry.yaml", own)

    upstream = _load(current / "rius/upstream.yaml")
    # A referenced upstream key we shipped a constant for, no longer referenced.
    for group in upstream["attribute_groups"]:
        group["attributes"] = [r for r in group["attributes"] if r.get("ref") != "service.name"]
    _dump(current / "rius/upstream.yaml", upstream)

    status, found = weaver_check.findings(
        current, base, weaver_check.policies(read_env(ROOT / "versions.env"))
    )
    assert status != 0
    assert keyed(found) == {
        ("compatibility_removed_attribute", "rius.context.sizes"),
        ("rius_development_attribute_retyped", "rius.workspace"),
        ("deprecation_attribute_renamed_to_invalid", "rius.main_agent.name"),
        ("rius_referenced_attribute_removed", "service.name"),
    }


# Choosing the baseline.


def _git(repo: pathlib.Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "test")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    _git(tmp_path, "config", "tag.gpgsign", "false")
    return tmp_path


def _release(repo: pathlib.Path, tag: str, *, model: bool) -> None:
    if model:
        (repo / "model").mkdir(exist_ok=True)
        (repo / "model/manifest.yaml").write_text(f"name: rius\n# {tag}\n")
    (repo / "version.txt").write_text(tag)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", tag)
    _git(repo, "tag", tag)


def test_no_baseline_before_a_release_has_model(repo):
    _release(repo, "v1.0.0", model=False)
    _release(repo, "v1.1.0", model=False)
    assert weaver_check.baseline_tag(repo) is None


def test_baseline_is_the_newest_release_with_model(repo):
    _release(repo, "v1.1.0", model=False)
    _release(repo, "v1.2.0", model=True)
    _release(repo, "v1.10.0", model=True)
    _git(repo, "tag", "v2.0.0-rc.1")
    assert weaver_check.baseline_tag(repo) == "v1.10.0"


def test_baseline_is_extracted_from_the_tag(repo, tmp_path_factory):
    _release(repo, "v1.2.0", model=True)
    (repo / "model/manifest.yaml").write_text("changed after the release\n")
    out = weaver_check.extract("v1.2.0", tmp_path_factory.mktemp("baseline"), cwd=repo)
    assert (out / "manifest.yaml").read_text() == "name: rius\n# v1.2.0\n"


def test_shared_packs_are_pinned_to_a_commit():
    env = read_env(ROOT / "versions.env")
    paths = weaver_check.policies(env)
    assert paths[0] == str(ROOT / "policies/check")
    assert all(f"@{env['WEAVER_PACKAGES_REF']}[" in p for p in paths[1:])
    with pytest.raises(SystemExit):
        weaver_check.policies({**env, "WEAVER_PACKAGES_REF": "main"})
