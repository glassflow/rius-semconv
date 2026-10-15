# Contributing to rius-semconv

Thanks for helping. This repository is the attribute registry for Rius: the
wire strings the Rius SDKs and the Rius backend agree on, the generators that
turn them into Python, TypeScript and Go, and recorded instrumentor spans with
the result every normalizer must produce from them. A change here is a change
to a contract, so the workflow below is mostly about making that change
reviewable.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
To report a vulnerability, follow [SECURITY.md](SECURITY.md) instead of
opening an issue.

## Before you start

- **Proposing an attribute?** Open a
  [new attribute proposal](https://github.com/glassflow/rius-semconv/issues/new?template=attribute-proposal.yml)
  first. Most of the review is about whether the key should exist and what it
  is called, and that is cheaper to settle before you write the row.
- **Found a wrong value, a bad mapping or a broken tool?** Open a
  [bug report](https://github.com/glassflow/rius-semconv/issues/new?template=bug.yml).
- Small fixes (typos, a rationale that reads wrong, a tool bug with an
  obvious fix) can go straight to a pull request.

## Setting up

You need Python 3.11 or later, the pinned Weaver (it renders `out/`), Go
(for `gofmt`, and the tests compile the generated Go) and Node 22.7 or later
(the tests and the parity check evaluate the generated TypeScript). CI uses
Python 3.12, Go 1.25 and Node 24. Generating fetches the pinned upstream
registries from GitHub.

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
tools/install_weaver.sh
```

## Changing the registry

The registry is the YAML under `registry/`. Everything in `out/` is generated
from it: never edit `out/` by hand.

1. **Check the OpenTelemetry conventions first**: the
   [GenAI registry](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/model/gen-ai/registry.yaml)
   and the general
   [attribute registry](https://opentelemetry.io/docs/specs/semconv/registry/attributes/).
   If a convention defines the fact, use its key, type and requirement level
   exactly, with `origin: otel`.
2. **Only a fact no convention names gets a Rius key**, under `rius.*`
   (`origin: rius`). Never put a Rius key inside a convention's namespace
   such as `gen_ai.*`: the convention is free to define that key later and
   mean something else. Never use `glassflow.*`. The linter rejects
   `glassflow.*` keys, and an `origin: rius` key outside `rius.*` needs a
   written `namespace_exception`. Only two keys have one, and they are the
   only keys this registry defines in a convention's namespace: the
   `mcp.result_type` attribute and the `gen_ai.first_token` event name. Every
   other key in those namespaces is referenced from the upstream registry,
   never defined here.
3. **Add or change the row** in `registry/attributes.yaml`. The file's header
   lists every column; the README's "What a row says" explains the ones that
   matter most. Give a span attribute its category, level and kinds, and write
   a `rationale` that says *why* the key exists. Write the reason itself, not
   a link to an issue tracker: the rationale is emitted as a comment in every
   generated file, and the linter rejects internal ticket IDs.
4. **Decide allowlist membership explicitly** in `registry/allowlists.yaml`.
   An `identity` key goes on the pending allowlist or states `not_pending`; a
   `content` key goes on the content allowlist.
5. If no consumer ships the key yet, mark it `status: planned`.
6. If the languages deliberately differ, say so with `shipped_in:` and a
   `divergence:` that explains why.
7. A Rius key (`origin: rius`), or an OpenInference key no upstream registry
   defines, also needs a one-line `brief`, realistic `examples` and a
   `stability` (`development` for a new key). A key a convention defines
   takes none of them: `model/` references the upstream definition. If its
   row's `type` must differ from upstream's, say why in
   `upstream_divergence`; CI fails on a difference no row records. These are
   for the Weaver registry under `model/`; the file's header lists the
   columns.
8. Lint, regenerate, and commit the registry change, `out/` and `model/`
   together:

   ```
   python tools/check_registry.py
   python -m generators.generate
   python tools/to_weaver.py
   ```

   CI fails if `out/` or `model/` does not match the registry.

The other registry files follow the same rules: `taxonomy.yaml` (span kinds),
`model_parameters.yaml` (provider parameter spellings) and `usage_keys.yaml`
(a decision for every token, usage and cost key an instrumentor sends).

Do not edit `CHANGELOG.md` or `version.txt`: release-please writes them (see
[Releases](#releases)).

### Templates

Each language's module is rendered by a Weaver template under
`templates/registry/<lang>/`, from a context the jq filter in
`templates/registry/weaver.yaml` builds. If a template needs a fact the
registry does not state, add a column to the YAML rather than a special case
in the template. Output must stay deterministic and must pass each consumer's
own formatter (`ruff`, `biome`, `gofmt`); `tests/test_generators.py` checks
both (the `biome` check runs only when a rius-sdk-typescript checkout sits
next to this one).

## Deprecation and compatibility

Spans written by an SDK released today are read for as long as that SDK runs,
so a key, once shipped, keeps its meaning. These rules apply to every key a
consumer can have shipped, that is every row not marked `status: planned`.

### The rules

1. **Deprecate, never remove.** A shipped key is never deleted from the
   registry and its string is never reused for something else. To retire a
   key, mark it deprecated and say either which key replaces it or why it has
   no replacement.
2. **A rename is a deprecation.** The key is the identity, so a new spelling
   is a new row. The old row stays, deprecated, pointing at the new one.
3. **Deprecation window.** A deprecated key keeps its generated constant for
   at least two minor releases or six months after the release that first
   marks it deprecated, whichever is longer. During the window, readers (the
   backend and the normalizers) accept both keys; producers move to the new
   one. After the window, a major release may stop generating the constant.
   The row itself stays, so readers, documentation and the checks still
   recognise the key.
4. **Stable keys.** A stable key's type or meaning changes only in a major
   release.
5. **Development keys.** A key in development may still change its
   description, requirement level, category or kinds in a minor release. Its
   type may not: a new type is a new key, and the old one is deprecated under
   rule 3. The only exception is a row that never shipped (`status: planned`),
   which can change freely.

Every Rius-owned key states its stability in the `stability` column, and
every one is in development today. A key borrowed from OpenTelemetry has the stability of its
upstream convention, and the GenAI conventions are still in development.
Adopting an upstream rename follows rules 2 and 3: the old key stays,
deprecated.

### Marking a deprecation

A deprecation is written in the rows of `registry/attributes.yaml`:

1. **Keep the old row** with its `const`, `key` and `type` unchanged, and
   give it a `deprecated` column (below).
2. **Start its `rationale`** with one line that says what replaces it, or why
   nothing does:

   ```yaml
   rationale: |
     Deprecated: renamed to rius.new.key.
     ...
   ```

   The generated Go keeps that line as its `// Deprecated:` paragraph, and the
   generated TypeScript turns it into a JSDoc `@deprecated` tag, so both
   languages' editors mark the constant.

3. **Add the replacement row**, if there is one, and say in its `rationale`
   which key it replaces, so a reader of either row finds the other.
4. **Title the pull request `feat(deprecate): ...`** (see
   [Commits and pull requests](#commits-and-pull-requests)).

The `deprecated` column is spelled as Weaver's `deprecated` field, and
`tools/to_weaver.py` carries it into `model/` unchanged:

```yaml
- const: RIUS_OLD_KEY
  key: rius.old.key
  deprecated:
    reason: renamed
    renamed_to: rius.new.key
    note: Renamed so the key says what it measures.
```

with `reason: obsoleted` and a `note` when nothing replaces the key. Once a
deprecated key's constant is dropped (after its window, or because it never
had one), its row moves to the `retired:` list at the end of the file: it is
never generated again, but readers, the docs and Weaver still recognise it.
`glassflow.span.pending` is the first. A key
that moves into a convention we depend on (for example a `rius.*` key that
OpenTelemetry later defines under `gen_ai.*`) uses `reason: uncategorized`
with a `note` naming the new key, not `renamed`: Weaver's compatibility
check rejects a `renamed_to` that points into a dependency's registry.

### How it is enforced

CI's `weaver` job runs `python tools/weaver_check.py`, which compares every
pull request with the last release that has a Weaver registry
(`weaver registry check --baseline-registry`). The shared OpenTelemetry
`backwards-compatibility` pack rejects a removed attribute and a retyped
stable one; `policies/check/rius_compat.rego` rejects a retyped development
attribute (rule 5) and an upstream key that is no longer referenced (rule 1).
Rows marked `status: planned` are exempt. No release has a Weaver registry
yet, so until one does the job prints a notice and skips that comparison;
`tests/test_policies.py` exercises it against a synthetic baseline in the
meantime. A rename into a dependency's key with `reason: renamed` fails
the shared `stability` pack, as described above.

## Recordings and expected results

`fixtures/` holds real spans from the instrumentors Rius normalizes, and the
result each normalizer must produce from them.
[`fixtures/README.md`](fixtures/README.md) is the full reference; in short:

1. **Record.** Each family has a recorder (`record.py`, or `record.mjs` for
   JavaScript) that drives the real instrumentor against a scripted provider,
   with no network and no API keys. Its `manifest.json` pins the exact
   packages (and Python or Node version). In an environment holding exactly
   those pins:

   ```
   cd fixtures/<family>
   python record.py <family>-<version>.json <environment.json>
   ```

   For a Node family, run `npm ci` in the family directory first, then
   `node record.mjs <family>-<version>.json <environment.json>`.
   Record twice and compare: the two outputs must be byte-identical. A new
   instrumentor version is a new recording beside the old one, not a
   replacement.
2. **Produce the expected result** with the normalizer named in the
   manifest's `expected.source`:
   - `python-sdk`: in an environment with the Python SDK installed from the
     commit you name,

     ```
     pip install "glassflow-rius @ git+https://github.com/glassflow/rius-sdk-python@<sha>"
     python tools/expect_python.py --sdk-commit <sha> fixtures/<family>/<recording>.json
     ```

   - `typescript-sdk` (the Vercel AI SDK families): from a checkout of
     [rius-sdk-typescript](https://github.com/glassflow/rius-sdk-typescript)
     with its `node_modules` installed,

     ```
     npx tsx tools/expect_typescript.mts --sdk <checkout> --sdk-commit <sha> fixtures/<family>/<recording>.json
     ```

   - `sink` (families only the Rius backend normalizes): the expected result
     is the rows the backend stores, `<recording>.expected-row.json`. Only
     maintainers can regenerate these. If your change needs new ones, say so
     in the pull request and a maintainer will produce them.
3. **Review the expected result by hand.** The tools record what a
   normalizer does, not what it should do:

   ```
   python tools/review_expected.py --unchanged fixtures/<family>/<recording>.json
   ```

   lists what the normalizer removed, added, changed and left alone. Put
   anything surprising in the pull request description.
4. **Check the fixtures and the usage keys:**

   ```
   python tools/check_fixtures.py
   python tools/check_usage_keys.py
   ```

   A usage key that appears in a recording and has no decision in
   `registry/usage_keys.yaml` fails the second check. Add the decision.

## Checks

These are what CI (`.github/workflows/ci.yml`) runs. Run them before you push:

```
ruff check .
ruff format --check .
python tools/check_registry.py
python -m generators.generate --check
python tools/check_fixtures.py
python tools/check_usage_keys.py
python -m pytest
python tools/check_weaver_pins.py
python tools/to_weaver.py --check
PATH="$PWD/.weaver/bin:$PATH" python tools/weaver_check.py
```

A separate workflow compares `out/` with what each consumer ships. It needs
a secret that pull requests from forks do not get, so on a fork it skips the
comparison and reports "Parity NOT checked". That is expected; a maintainer
checks parity before merging. A consumer that has not yet picked up a new
constant is reported as a gap, which is the signal working, not a failure.

## Dependency bumps

[Renovate](renovate.json) opens a pull request when a pin moves: the Weaver
release, the core semantic conventions tag, the GenAI conventions commit or
the Weaver policy packs commit, in `versions.env` and `model/manifest.yaml`.
Other files derive from those pins, so the `renovate-followup` workflow
(`.github/workflows/renovate-followup.yml`) runs `python tools/follow_pins.py`
on each of Renovate's branches. It fills in the new Weaver release's
`WEAVER_SHA256_*` checksums, moves the dependencies' `schema_url`s in the
manifest, regenerates `model/`, `out/` and `docs/registry/` with the pinned
Weaver, and commits anything that changed as `chore(deps): regenerate for the
new pins`. CI then runs on that commit. Review the regenerated diff with the
bump: a new upstream commit can change the keys we reference, not only the
links.

The workflow runs the branch's code in one job with no secrets, and commits
the result in a second job that runs none of it: that job applies the change
only if it touches `versions.env`, `model/`, `out/` and `docs/registry/`, as
plain files. It pushes with the `RENOVATE_FOLLOWUP_TOKEN` repository secret: a
fine-grained personal access token, or a GitHub App token, with **Contents:
read and write** on this repository only. A push made with the workflow's own
`GITHUB_TOKEN` would not run CI on the new commit. Without the secret the
workflow regenerates, and fails if anything changed.

If it fails, prefer rerunning it (the workflow's **Run workflow** button, with
the branch name) once the secret is set, or let Renovate recreate the pull
request. Renovate keeps updating a branch only while every commit on it is its
own or the workflow's (`gitIgnoredAuthors` in `renovate.json`): after a commit
of yours it stops rebasing the branch and leaves it to you. If you do commit
the result by hand:

```
git fetch origin
git switch renovate/<branch>
python tools/follow_pins.py --base origin/main
git add -A && git commit -s -m "chore(deps): regenerate for the new pins"
git push
```

## Commits and pull requests

- **Sign off every commit** (see [Developer Certificate of Origin](#developer-certificate-of-origin)).
- **Use [Conventional Commits](https://www.conventionalcommits.org/)** for the
  pull request title. Pull requests are squash-merged, so the title becomes
  the commit on `main`, and release-please reads its type.
- **Pick the type by what changes on the wire:**

  | Change | Type |
  | -- | -- |
  | A wire value changed in place, a stable key's type or meaning changed, or a deprecated constant dropped after its window | `feat!:` (or a `BREAKING CHANGE:` footer) |
  | A key deprecated (with its replacement, if any) | `feat(deprecate):` |
  | A row, member or table added, or `planned` becomes `shipped` | `feat:` |
  | A row's meaning or disposition corrected, generated values unchanged | `fix:` |
  | Recordings, expected results, tests, tooling | `test:` or `chore:` |
  | Documentation only | `docs:` |

- Keep one change per pull request, and commit `out/` with the registry
  change that produced it.
- Fill in the pull request template: why the change is needed, what it
  changes, and how you tested it.

### Releases

The registry is versioned, because it is the wire contract. release-please
keeps a release pull request open on `main`; merging it tags `vX.Y.Z` and
writes `CHANGELOG.md`. A `feat:` or `fix:` commit that touches the registry,
the generators or `out/` cuts a release: a minor or patch step, or a breaking
step for `feat!:`. The changelog lists breaking changes first, then
deprecations (`feat(deprecate):`) under their own heading, then features and
fixes. A deprecation is a `feat` with the `deprecate` scope, not a type of
its own, because release-please picks the version step from the type: a
custom type would never cut more than a patch release. Commits that touch only `fixtures/`, `tests/`, `tools/` or
`.github/` never cut a release, whatever their type: consumers pin the
recordings by commit, not by version. Maintainers merge the release pull
request.

## Developer Certificate of Origin

Contributions are accepted under the
[Developer Certificate of Origin](https://developercertificate.org/) (DCO).
It is a statement that you wrote the change, or otherwise have the right to
submit it under the project's license. There is no contributor license
agreement to sign.

Certify it by adding a `Signed-off-by` line to every commit:

```
git commit -s -m "feat: add rius.example.key"
```

which appends

```
Signed-off-by: Your Name <you@example.com>
```

using your `user.name` and `user.email`. To sign off commits you already
made on your branch, run `git rebase --signoff main` and force-push.
