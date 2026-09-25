"""Lint the registry. Exit 0 when clean, 1 with one line per problem.

    python tools/check_registry.py

The rules live in generators/registry.py (`Registry.lint`) and are tested one
by one in tests/test_registry.py. Generation runs the same lint first and
refuses to write output from a registry that fails it.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from generators.registry import Registry  # noqa: E402


def main() -> int:
    errors = Registry.load(include_planned=True).lint()
    for e in errors:
        print(e)
    print(f"registry: {'clean' if not errors else f'{len(errors)} problem(s)'}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
