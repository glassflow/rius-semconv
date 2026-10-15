"""Bring the derived files up to date after a pin in versions.env moves.

    python tools/follow_pins.py [--base REF]

Renovate bumps one pin at a time in versions.env (and in model/manifest.yaml).
Other files derive from the pins, and CI fails until they follow:

- a new WEAVER_VERSION needs the release's WEAVER_SHA256_* checksums, which
  this fills in from the release (tools/install_weaver.sh --print-checksums)
  when WEAVER_VERSION differs from the one at REF (default origin/main);
- a new core version needs its schema_url in model/manifest.yaml, and a new
  GenAI commit the schema_url that commit's own manifest declares;
- model/, out/ and docs/registry/ are regenerated with the pinned Weaver,
  installed to .weaver/bin.

The renovate-followup workflow runs this on Renovate's pull requests and
commits the result. Needs network access (GitHub) and gofmt.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys
import urllib.request

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.check_weaver_pins import CORE_REPO, GENAI_REPO, parse_env  # noqa: E402

VERSIONS = ROOT / "versions.env"
MANIFEST = ROOT / "model" / "manifest.yaml"
CHECKSUM_LINE = re.compile(r"(WEAVER_SHA256_[A-Z0-9_]+)=[0-9a-f]{64}")
SCHEMA_URL = re.compile(r"https://opentelemetry\.io/schemas/[\w.\-/]+")


def env_at(ref: str) -> dict[str, str]:
    """versions.env as it is at a git ref."""
    text = subprocess.run(
        ["git", "show", f"{ref}:versions.env"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return parse_env(text)


def print_checksums() -> str:
    """What tools/install_weaver.sh --print-checksums prints for the pinned release."""
    return subprocess.run(
        [str(ROOT / "tools" / "install_weaver.sh"), "--print-checksums"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def set_checksums(versions: str, printed: str) -> str:
    """versions.env with each WEAVER_SHA256_* line replaced by the printed one.

    The printed lines must name exactly the targets versions.env pins today."""
    lines = printed.split()
    bad = [line for line in lines if not CHECKSUM_LINE.fullmatch(line)]
    if bad:
        raise ValueError(f"unexpected checksum lines: {bad}")
    printed_names = sorted(CHECKSUM_LINE.fullmatch(line).group(1) for line in lines)
    pinned_names = sorted(re.findall(r"(?m)^(WEAVER_SHA256_[A-Z0-9_]+)=", versions))
    if printed_names != pinned_names:
        raise ValueError(f"checksums printed for {printed_names}, versions.env pins {pinned_names}")
    for line in lines:
        name = CHECKSUM_LINE.fullmatch(line).group(1)
        versions = re.sub(rf"(?m)^{name}=.*$", lambda _, line=line: line, versions)
    return versions


def set_schema_url(manifest: str, repo: str, schema_url: str) -> str:
    """manifest.yaml with the schema_url of the dependency on repo replaced.

    Edited as text so the comments survive."""
    if not SCHEMA_URL.fullmatch(schema_url):
        raise ValueError(f"not an OpenTelemetry schema_url: {schema_url!r}")
    pattern = re.compile(rf"(?m)^(\s*- schema_url: )\S+(\n\s*registry_path: {re.escape(repo)}@)")
    manifest, n = pattern.subn(lambda m: m.group(1) + schema_url + m.group(2), manifest)
    if n != 1:
        raise ValueError(f"model/manifest.yaml has {n} dependencies on {repo}, want 1")
    return manifest


def genai_schema_url(ref: str) -> str:
    """The schema_url the GenAI registry's own manifest declares at a commit."""
    url = (
        "https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/"
        f"{ref}/model/manifest.yaml"
    )
    with urllib.request.urlopen(url, timeout=30) as resp:
        schema_url = (yaml.safe_load(resp.read()) or {}).get("schema_url")
    if not isinstance(schema_url, str) or not SCHEMA_URL.fullmatch(schema_url):
        raise ValueError(f"the GenAI manifest at {ref} declares schema_url {schema_url!r}")
    return schema_url


def run(*cmd: str) -> None:
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def update_pins(base: str) -> None:
    """The checksums and schema_urls that follow from versions.env."""
    env = parse_env(VERSIONS.read_text())
    if env["WEAVER_VERSION"] != env_at(base).get("WEAVER_VERSION"):
        print(f"WEAVER_VERSION is {env['WEAVER_VERSION']}: updating its checksums", flush=True)
        VERSIONS.write_text(set_checksums(VERSIONS.read_text(), print_checksums()))

    manifest = MANIFEST.read_text()
    core = env["SEMCONV_VERSION"].removeprefix("v")
    manifest = set_schema_url(manifest, CORE_REPO, f"https://opentelemetry.io/schemas/{core}")
    genai = genai_schema_url(env["SEMCONV_GENAI_REF"])
    manifest = set_schema_url(manifest, GENAI_REPO, genai)
    MANIFEST.write_text(manifest)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base", default="origin/main", help="the ref to compare pins with")
    args = parser.parse_args(argv)

    update_pins(args.base)
    run(str(ROOT / "tools" / "install_weaver.sh"))
    run(sys.executable, "tools/check_weaver_pins.py")
    run(sys.executable, "tools/to_weaver.py")
    run(sys.executable, "-m", "generators.generate")
    run(sys.executable, "-m", "generators.registry_docs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
