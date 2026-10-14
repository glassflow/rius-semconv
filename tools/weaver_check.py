"""Check the Weaver registry against its policies and the last release.

    python tools/weaver_check.py [--registry DIR] [--baseline DIR]

Runs `weaver registry check --v2` on model/ with three sets of policies:
ours under policies/check, and the shared `stability` and
`backwards-compatibility` packs of opentelemetry-weaver-packages at the commit
versions.env pins.

The baseline is the last release: the newest v* tag whose tree has
model/manifest.yaml, extracted with `git archive`. Against it the
backwards-compatibility pack and policies/check/rius_compat.rego fail a
removed or retyped key (CONTRIBUTING.md, "Deprecation and compatibility").
When no release has model/ yet, it says so and checks without one. --baseline
names a directory to compare with instead.

Needs `weaver` on PATH (tools/install_weaver.sh) and the release tags
(a full clone, or `git fetch --tags`). Exits with weaver's status.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import tarfile
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.check_weaver_pins import read_env  # noqa: E402

PACKAGES_REPO = "https://github.com/open-telemetry/opentelemetry-weaver-packages.git"
SHARED_PACKS = ("stability", "backwards-compatibility")
RELEASE_TAG = re.compile(r"v\d+\.\d+\.\d+")


def policies(env: dict[str, str]) -> list[str]:
    """Our policy directory, then the shared packs at the pinned commit."""
    ref = env.get("WEAVER_PACKAGES_REF", "")
    if not re.fullmatch(r"[0-9a-f]{40}", ref):
        raise SystemExit(
            f"versions.env: WEAVER_PACKAGES_REF must be a full commit sha, got {ref!r}"
        )
    return [str(ROOT / "policies/check")] + [
        f"{PACKAGES_REPO}@{ref}[policies/check/{pack}]" for pack in SHARED_PACKS
    ]


def git(*args: str, cwd: pathlib.Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def baseline_tag(cwd: pathlib.Path = ROOT) -> str | None:
    """The newest release tag whose tree has a Weaver registry."""
    tags = git("tag", "--list", "v*", "--sort=-v:refname", cwd=cwd).stdout.split()
    for tag in tags:
        if (
            RELEASE_TAG.fullmatch(tag)
            and git("cat-file", "-e", f"{tag}:model/manifest.yaml", cwd=cwd).returncode == 0
        ):
            return tag
    return None


def extract(tag: str, dest: pathlib.Path, cwd: pathlib.Path = ROOT) -> pathlib.Path:
    """Write the tag's model/ under dest and return its path."""
    archive = dest / "baseline.tar"
    out = git("archive", "--format=tar", f"--output={archive}", tag, "model", cwd=cwd)
    if out.returncode != 0:
        raise SystemExit(f"git archive {tag} model failed: {out.stderr.strip()}")
    with tarfile.open(archive) as tar:
        tar.extractall(dest, filter="data")
    return dest / "model"


def command(
    registry: pathlib.Path, baseline: pathlib.Path | None, policy_paths: list[str]
) -> list[str]:
    cmd = ["weaver", "registry", "check", "-r", str(registry), "--v2"]
    if baseline is not None:
        cmd += ["--baseline-registry", str(baseline)]
    for p in policy_paths:
        cmd += ["-p", p]
    return cmd


def findings(
    registry: pathlib.Path,
    baseline: pathlib.Path | None,
    policy_paths: list[str],
    cwd: pathlib.Path | None = None,
) -> tuple[int, list[dict]]:
    """Run the check and return its exit status and the policy findings, each
    {"id", "context", "level", "message"}. Raises when the registry itself
    fails to load or resolve, so a broken test registry cannot pass as one
    with no findings."""
    out = subprocess.run(
        [
            *command(registry, baseline, policy_paths),
            "--quiet",
            "--diagnostic-format",
            "json",
            "--diagnostic-stdout",
        ],
        capture_output=True,
        text=True,
        cwd=cwd,
        env={**os.environ, "NO_COLOR": "1"},
    )
    start = out.stdout.find("[")
    if start < 0:
        raise RuntimeError(
            f"weaver printed no diagnostics (exit {out.returncode}):\n{out.stdout}\n{out.stderr}"
        )
    report = json.loads(out.stdout[start:])
    found = [
        d["error"]["violation"]
        for d in report
        if (d.get("error") or {}).get("type") == "policy_violation"
    ]
    broken = [
        d["diagnostic"]["message"]
        for d in report
        if (d.get("error") or {}).get("type") != "policy_violation"
        # An invalid policy file is reported with no severity at all.
        and d["diagnostic"].get("severity") in (None, "Error")
    ]
    if broken:
        raise RuntimeError("weaver could not check the registry:\n" + "\n".join(broken))
    return out.returncode, found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--registry", type=pathlib.Path, default=ROOT / "model")
    parser.add_argument(
        "--baseline", type=pathlib.Path, help="compare with this registry, not the last release"
    )
    args = parser.parse_args(argv)

    policy_paths = policies(read_env(ROOT / "versions.env"))
    with tempfile.TemporaryDirectory() as tmp:
        baseline = args.baseline
        if baseline is None:
            tag = baseline_tag()
            if tag is None:
                print(
                    "::notice::No release has a Weaver registry (model/manifest.yaml) yet, so "
                    "there is no baseline: the breaking-change gate is skipped and the other "
                    "policies still run."
                )
            else:
                print(f"Baseline: {tag}")
                baseline = extract(tag, pathlib.Path(tmp))
        cmd = command(args.registry, baseline, policy_paths)
        print("+", " ".join(cmd), flush=True)
        return subprocess.run(cmd).returncode


if __name__ == "__main__":
    sys.exit(main())
