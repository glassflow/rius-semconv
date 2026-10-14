<!--
The title is the squash commit on main, and release-please reads its type:
feat: adds to the registry, fix: corrects a row's meaning, feat!: changes or
removes a wire value, test:/chore:/docs: for everything else. See
CONTRIBUTING.md.
-->

## Why

<!-- The problem this solves. Link the issue or proposal if there is one. -->

## What

<!-- What changes. For a registry change: the rows, their category and allowlist membership, and what consumers have to do. -->

## Testing

<!-- What you ran and what you checked by hand (for expected results, anything surprising in review_expected.py's output). -->

- [ ] `ruff check .` and `ruff format --check .`
- [ ] `python tools/check_registry.py`
- [ ] `python -m generators.generate --check` (`out/` is committed with the registry change)
- [ ] `python tools/check_fixtures.py` and `python tools/check_usage_keys.py`
- [ ] `python -m pytest`
- [ ] Every commit is signed off (`git commit -s`)
