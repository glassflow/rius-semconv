"""tools/follow_pins.py: the edits it makes to versions.env and the manifest.

The regeneration itself is the generators' own, tested elsewhere; these test
that the text edits touch exactly the lines they name and keep the rest.
"""

from __future__ import annotations

import pytest

from conftest import ROOT
from tools import check_weaver_pins, follow_pins

VERSIONS = (ROOT / "versions.env").read_text()
MANIFEST = (ROOT / "model/manifest.yaml").read_text()

PRINTED = "\n".join(
    f"WEAVER_SHA256_{target}={digit * 64}"
    for target, digit in [
        ("X86_64_UNKNOWN_LINUX_GNU", "1"),
        ("AARCH64_UNKNOWN_LINUX_GNU", "2"),
        ("X86_64_APPLE_DARWIN", "3"),
        ("AARCH64_APPLE_DARWIN", "4"),
    ]
)


def test_checksums_replace_only_their_lines():
    updated = follow_pins.set_checksums(VERSIONS, PRINTED + "\n")
    assert all(line in updated.splitlines() for line in PRINTED.splitlines())
    before = [line for line in VERSIONS.splitlines() if not line.startswith("WEAVER_SHA256_")]
    after = [line for line in updated.splitlines() if not line.startswith("WEAVER_SHA256_")]
    assert before == after


@pytest.mark.parametrize(
    "printed",
    [
        "",
        # A target the release does not publish prints an empty checksum.
        "WEAVER_SHA256_X86_64_APPLE_DARWIN=",
        "WEAVER_SHA256_RISCV64_UNKNOWN_LINUX_GNU=" + "0" * 64,
    ],
)
def test_checksums_refuse_what_versions_env_cannot_take(printed):
    with pytest.raises(ValueError):
        follow_pins.set_checksums(VERSIONS, printed)


def test_schema_urls_move_with_the_pins_and_keep_the_comments():
    updated = follow_pins.set_schema_url(
        MANIFEST, check_weaver_pins.CORE_REPO, "https://opentelemetry.io/schemas/9.9.9"
    )
    updated = follow_pins.set_schema_url(
        updated, check_weaver_pins.GENAI_REPO, "https://opentelemetry.io/schemas/gen-ai-dev/9.9.9"
    )
    changed = [
        (a, b) for a, b in zip(MANIFEST.splitlines(), updated.splitlines(), strict=True) if a != b
    ]
    assert [b for _, b in changed] == [
        "  - schema_url: https://opentelemetry.io/schemas/9.9.9",
        "  - schema_url: https://opentelemetry.io/schemas/gen-ai-dev/9.9.9",
    ]
    assert all(a.startswith("  - schema_url: ") for a, _ in changed)


def test_schema_url_needs_exactly_one_dependency():
    with pytest.raises(ValueError):
        follow_pins.set_schema_url(MANIFEST, "https://github.com/example/none", "x")
