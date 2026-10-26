"""Check that every usage key in the recordings has a decision, and that it holds.

    python tools/check_usage_keys.py [fixtures-dir]

Reads registry/usage_keys.yaml and every recording under fixtures/. Fails when:

- a recording (or an expected result) carries a key matching the file's
  `match` words that no entry decides;
- a normalizer's expected output contradicts an entry: a normalizer listed in
  `mapped_by` kept the key or left no target, or one not listed removed it. A
  mapped source recorded at 0 may leave no target when the target is an
  `omit_zero` key;
- an expected result holds an `omit_zero` key (or its rius.aggregated_usage.*
  twin) at 0;
- a normalizer dropped an `omit_zero` key the recording carried with a count:
  it must be kept, or moved to its rius.aggregated_usage.* twin.

A span's event attributes count with its own, for every rule.

Exit 0 when clean, 1 otherwise, with one line per problem. The rules live in
generators/usage_keys.py and are tested in tests/test_usage_keys.py.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from generators import usage_keys  # noqa: E402
from generators.registry import Registry  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    fixtures = pathlib.Path(argv[0]) if argv else ROOT / "fixtures"
    data = Registry.load().usage_keys
    result = usage_keys.scan(data, fixtures)
    errors = usage_keys.check(data, result)
    for e in errors:
        print(e)
    keys = len(set(result.recorded) | set(result.produced))
    verdict = "all decided" if not errors else f"{len(errors)} problem(s)"
    print(f"usage keys: {keys} in the recordings, {verdict}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
