"""Check that model/manifest.yaml pins what versions.env and version.txt say.

    python tools/check_weaver_pins.py

The upstream registries are pinned twice: in versions.env, where Renovate
bumps them and the README reads them, and in model/manifest.yaml, where Weaver
reads them. The manifest's own schema_url ends in this registry's version,
which release-please writes to version.txt. Fails when any of these disagree.

Exit 0 when they agree, 1 otherwise, with one line per problem.
"""

from __future__ import annotations

import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent

SCHEMA_URL_BASE = "https://docs.glassflow.ai/rius/schemas/"
CORE_REPO = "https://github.com/open-telemetry/semantic-conventions"
GENAI_REPO = "https://github.com/open-telemetry/semantic-conventions-genai"
REGISTRY_PATH = re.compile(r"(https://github\.com/[^@]+)@([^\[]+)\[model\]")


def read_env(path: pathlib.Path) -> dict[str, str]:
    """A versions.env file, parsed by parse_env."""
    return parse_env(path.read_text())


def parse_env(text: str) -> dict[str, str]:
    """KEY=VALUE lines; comments and blank lines skipped."""
    env = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def check(manifest: dict, env: dict[str, str], version: str) -> list[str]:
    errors = []
    want = SCHEMA_URL_BASE + version
    if manifest.get("schema_url") != want:
        errors.append(f"manifest schema_url is {manifest.get('schema_url')!r}, want {want!r}")
    if manifest.get("file_format") != "definition_manifest/2.0":
        errors.append("manifest file_format must be definition_manifest/2.0")

    paths = {}
    for dep in manifest.get("dependencies") or []:
        m = REGISTRY_PATH.fullmatch(dep.get("registry_path", ""))
        if not m:
            errors.append(f"dependency registry_path not in <repo>@<ref>[model] form: {dep}")
            continue
        paths[m.group(1)] = (m.group(2), dep.get("schema_url", ""))

    core = env.get("SEMCONV_VERSION", "")
    if CORE_REPO not in paths:
        errors.append(f"manifest has no dependency on {CORE_REPO}")
    else:
        ref, schema_url = paths[CORE_REPO]
        if ref != core:
            errors.append(f"manifest pins core at {ref}, versions.env SEMCONV_VERSION={core}")
        if schema_url != f"https://opentelemetry.io/schemas/{core.removeprefix('v')}":
            errors.append(f"core schema_url {schema_url!r} does not match {core}")

    genai = env.get("SEMCONV_GENAI_REF", "")
    if not re.fullmatch(r"[0-9a-f]{40}", genai):
        errors.append(f"versions.env SEMCONV_GENAI_REF must be a full commit SHA, got {genai!r}")
    if GENAI_REPO not in paths:
        errors.append(f"manifest has no dependency on {GENAI_REPO}")
    elif paths[GENAI_REPO][0] != genai:
        errors.append(
            f"manifest pins GenAI at {paths[GENAI_REPO][0]}, versions.env SEMCONV_GENAI_REF={genai}"
        )

    if not env.get("WEAVER_VERSION"):
        errors.append("versions.env sets no WEAVER_VERSION")
    return errors


def main() -> int:
    manifest = yaml.safe_load((ROOT / "model/manifest.yaml").read_text())
    env = read_env(ROOT / "versions.env")
    version = (ROOT / "version.txt").read_text().strip()
    errors = check(manifest, env, version)
    for e in errors:
        print(e)
    print("weaver pins: " + ("consistent" if not errors else f"{len(errors)} problem(s)"))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
