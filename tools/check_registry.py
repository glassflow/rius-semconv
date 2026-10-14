"""Lint the registry. Exit 0 when clean, 1 with one line per problem.

    python tools/check_registry.py

The rules live in generators/registry.py (`Registry.lint`) and are tested one
by one in tests/test_registry.py. Generation runs the same lint first and
refuses to write output from a registry that fails it.

The ticket-id rule also covers the files around the registry that are read
outside the team: everything under fixtures/ and tools/ (`ticket_ids`).
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from generators.registry import TICKET, Registry  # noqa: E402

#: Directories outside registry/ whose files must not cite ticket ids.
TICKET_FREE_DIRS = ("fixtures", "tools")
#: Installed or generated, never authored here.
SKIPPED_DIRS = {"node_modules", "__pycache__"}


def ticket_ids(root: pathlib.Path, dirs: tuple[str, ...] = TICKET_FREE_DIRS) -> list[str]:
    """One line per ticket id found in a file under `dirs`, with its location."""
    errors = []
    for top in dirs:
        for path in sorted((root / top).rglob("*")):
            parts = path.relative_to(root).parts
            if not path.is_file() or any(p in SKIPPED_DIRS or p.startswith(".") for p in parts):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for lineno, line in enumerate(text.splitlines(), 1):
                for ticket in TICKET.findall(line):
                    errors.append(
                        f"{pathlib.PurePosixPath(*parts)}:{lineno}: ticket id {ticket}; "
                        "write the reason"
                    )
    return errors


def main() -> int:
    errors = Registry.load(include_planned=True).lint() + ticket_ids(ROOT)
    for e in errors:
        print(e)
    print(f"registry: {'clean' if not errors else f'{len(errors)} problem(s)'}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
