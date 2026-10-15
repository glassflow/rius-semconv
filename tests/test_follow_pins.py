"""tools/follow_pins.py: the edits it makes to versions.env and the manifest.

The regeneration itself is the generators' own, tested elsewhere; these test
that the text edits touch exactly the lines they name and keep the rest, and
that update_pins derives each one from the right pin. Git, the network and
the Weaver release are mocked.
"""

from __future__ import annotations

import io
import re

import pytest

from conftest import ROOT
from tools import check_weaver_pins, follow_pins

VERSIONS = (ROOT / "versions.env").read_text()
MANIFEST = (ROOT / "model/manifest.yaml").read_text()
TARGETS = re.findall(r"(?m)^WEAVER_SHA256_([A-Z0-9_]+)=", VERSIONS)
GENAI_URL = "https://opentelemetry.io/schemas/gen-ai-dev/9.9.9-dev"


def printed(targets=TARGETS, digit="1"):
    return "\n".join(f"WEAVER_SHA256_{t}={digit * 64}" for t in targets) + "\n"


def test_checksums_replace_only_their_lines():
    updated = follow_pins.set_checksums(VERSIONS, printed())
    assert all(line in updated.splitlines() for line in printed().splitlines())
    before = [line for line in VERSIONS.splitlines() if not line.startswith("WEAVER_SHA256_")]
    after = [line for line in updated.splitlines() if not line.startswith("WEAVER_SHA256_")]
    assert before == after


@pytest.mark.parametrize(
    "out",
    [
        "",
        # A target the release does not publish prints an empty checksum.
        printed(TARGETS[:-1]) + f"WEAVER_SHA256_{TARGETS[-1]}=\n",
        # A partial set would leave a stale checksum behind.
        printed(TARGETS[:-1]),
        printed(TARGETS + ["RISCV64_UNKNOWN_LINUX_GNU"]),
    ],
    ids=["empty", "empty-checksum", "partial", "extra-target"],
)
def test_checksums_refuse_what_versions_env_cannot_take(out):
    with pytest.raises(ValueError):
        follow_pins.set_checksums(VERSIONS, out)


def test_checksums_refuse_a_versions_env_without_checksums():
    # Nothing pinned and nothing printed would otherwise match and pass.
    versions = "".join(
        line for line in VERSIONS.splitlines(keepends=True) if not line.startswith("WEAVER_SHA256_")
    )
    with pytest.raises(ValueError, match="pins no WEAVER_SHA256_"):
        follow_pins.set_checksums(versions, "")


def test_schema_urls_move_with_the_pins_and_keep_the_comments():
    updated = follow_pins.set_schema_url(
        MANIFEST, check_weaver_pins.CORE_REPO, "https://opentelemetry.io/schemas/9.9.9"
    )
    updated = follow_pins.set_schema_url(updated, check_weaver_pins.GENAI_REPO, GENAI_URL)
    changed = [
        (a, b) for a, b in zip(MANIFEST.splitlines(), updated.splitlines(), strict=True) if a != b
    ]
    assert [b for _, b in changed] == [
        "  - schema_url: https://opentelemetry.io/schemas/9.9.9",
        f"  - schema_url: {GENAI_URL}",
    ]
    assert all(a.startswith("  - schema_url: ") for a, _ in changed)


@pytest.mark.parametrize(
    "repo, url",
    [
        ("https://github.com/example/none", "https://opentelemetry.io/schemas/1.0.0"),
        (check_weaver_pins.CORE_REPO, "https://example.com/schemas/1.0.0"),
        (check_weaver_pins.CORE_REPO, r"https://opentelemetry.io/schemas/\g<0>"),
    ],
    ids=["no-dependency", "other-host", "replacement-escape"],
)
def test_schema_url_refuses(repo, url):
    with pytest.raises(ValueError):
        follow_pins.set_schema_url(MANIFEST, repo, url)


@pytest.mark.parametrize(
    "body, want",
    [
        (f"name: x\nschema_url: {GENAI_URL}\n", GENAI_URL),
        ("name: x\n", None),
        ("schema_url: https://example.com/evil\n", None),
        ("", None),
    ],
)
def test_genai_schema_url_is_read_and_validated(monkeypatch, body, want):
    seen = []

    def urlopen(url, timeout):
        seen.append(url)
        return io.BytesIO(body.encode())

    monkeypatch.setattr(follow_pins.urllib.request, "urlopen", urlopen)
    if want is None:
        with pytest.raises(ValueError):
            follow_pins.genai_schema_url("abc123")
    else:
        assert follow_pins.genai_schema_url("abc123") == want
    assert seen == [
        "https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/"
        "abc123/model/manifest.yaml"
    ]


@pytest.fixture
def pins(monkeypatch, tmp_path):
    """update_pins against copies of the committed files, with git and the network mocked."""
    versions, manifest = tmp_path / "versions.env", tmp_path / "manifest.yaml"
    versions.write_text(VERSIONS)
    manifest.write_text(MANIFEST)
    monkeypatch.setattr(follow_pins, "VERSIONS", versions)
    monkeypatch.setattr(follow_pins, "MANIFEST", manifest)
    calls = {"checksums": 0, "genai": []}

    def print_checksums():
        calls["checksums"] += 1
        return printed(digit="2")

    def genai_schema_url(ref):
        calls["genai"].append(ref)
        return GENAI_URL

    monkeypatch.setattr(follow_pins, "print_checksums", print_checksums)
    monkeypatch.setattr(follow_pins, "genai_schema_url", genai_schema_url)
    monkeypatch.setattr(follow_pins, "env_at", lambda ref: check_weaver_pins.parse_env(VERSIONS))
    return versions, manifest, calls


def test_update_pins_leaves_checksums_when_weaver_did_not_move(pins):
    versions, manifest, calls = pins
    follow_pins.update_pins("origin/main")
    assert calls["checksums"] == 0
    assert versions.read_text() == VERSIONS
    env = check_weaver_pins.parse_env(VERSIONS)
    assert calls["genai"] == [env["SEMCONV_GENAI_REF"]]
    assert f"  - schema_url: {GENAI_URL}\n" in manifest.read_text()


def test_update_pins_fetches_checksums_when_weaver_moved(pins):
    versions, _, calls = pins
    versions.write_text(re.sub(r"(?m)^WEAVER_VERSION=.*$", "WEAVER_VERSION=v99.0.0", VERSIONS))
    follow_pins.update_pins("origin/main")
    assert calls["checksums"] == 1
    env = check_weaver_pins.parse_env(versions.read_text())
    assert env["WEAVER_VERSION"] == "v99.0.0"
    assert {env[f"WEAVER_SHA256_{t}"] for t in TARGETS} == {"2" * 64}


def test_update_pins_takes_the_core_schema_url_from_semconv_version(pins):
    versions, manifest, _ = pins
    versions.write_text(re.sub(r"(?m)^SEMCONV_VERSION=.*$", "SEMCONV_VERSION=v9.8.7", VERSIONS))
    follow_pins.update_pins("origin/main")
    assert "  - schema_url: https://opentelemetry.io/schemas/9.8.7\n" in manifest.read_text()
