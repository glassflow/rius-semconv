<p align="center">
  <img src="docs/assets/banner.png" alt="Rius by GlassFlow: the attribute contract, defined once" width="100%">
</p>

# rius-semconv

The attribute contract for [Rius](https://docs.glassflow.ai/rius), GlassFlow's
observability product for AI agents: every wire string Rius's SDKs and backend
agree on, defined once as data, with generators for Python, TypeScript and Go,
and recorded instrumentor spans that every Rius normalizer must turn into the
same result.

<p>
  <a href="https://docs.glassflow.ai/rius"><b>Docs</b></a> ·
  <a href="docs/registry/README.md">Attribute registry</a> ·
  <a href="CHANGELOG.md">Changelog</a> ·
  <a href="https://github.com/glassflow/rius-semconv/issues">Issues</a>
</p>

[![CI](https://img.shields.io/github/actions/workflow/status/glassflow/rius-semconv/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/glassflow/rius-semconv/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-6b7280?style=flat-square)](LICENSE)
[![Latest release](https://img.shields.io/github/v/release/glassflow/rius-semconv?style=flat-square&label=release)](https://github.com/glassflow/rius-semconv/releases/latest)
[![OpenTelemetry Weaver](https://img.shields.io/badge/OpenTelemetry-Weaver-425cc7?style=flat-square&logo=opentelemetry&logoColor=white)](https://github.com/open-telemetry/weaver)
[![OTel semconv](https://img.shields.io/badge/OTel_semconv-v1.44.0-425cc7?style=flat-square)](versions.env)
![Generates Python, TypeScript and Go](https://img.shields.io/badge/generates-Python_%C2%B7_TypeScript_%C2%B7_Go-6b7280?style=flat-square)

## Who it is for

- **SDK authors.** The Rius SDKs
  ([`glassflow-rius`](https://github.com/glassflow/rius-sdk-python) for Python,
  [`@glassflow-ai/rius`](https://github.com/glassflow/rius-sdk-typescript) for
  TypeScript) must match this registry's attribute keys, span kinds,
  allowlists and tables. A new SDK, in any language, starts here.
- **People writing other normalizers.** If you turn OpenInference, Vercel AI
  SDK, OpenLLMetry, Laminar or pydantic-ai spans into the OpenTelemetry GenAI
  conventions, the recordings under `fixtures/` and their expected results are
  a ready-made test suite (see
  [Recorded spans](#recorded-spans-a-conformance-suite)).
- **Anyone who wants Rius's attribute contract.** Each attribute row says what
  the key means, where it belongs, whether it is content that capture settings
  mask, and why it is shaped the way it is.

User documentation for Rius itself is at
[docs.glassflow.ai/rius](https://docs.glassflow.ai/rius).

## What it defines

Rius SDKs emit OpenTelemetry traces that follow the
[OpenTelemetry GenAI conventions](https://github.com/open-telemetry/semantic-conventions-genai)
(`gen_ai.*`) and OpenInference's span taxonomy (`openinference.span.kind`).
The registry holds every wire string the SDKs and the Rius backend have to
agree on: attribute keys, event names, the span-kind taxonomy, the allowlists
that decide what may leave a process, and the table that maps provider
parameter spellings to convention keys.

**It owns one namespace, `rius.*`.** It defines no key in `gen_ai.*`,
`otel.*` or any other OpenTelemetry namespace (`error.*`, `service.*`,
`mcp.*`, `session.*`, `user.*`, ...), with two documented exceptions: the
`mcp.result_type` attribute and the `gen_ai.first_token` event name, which
predate the rule, carry a `namespace_exception` saying why, and are defined
as Rius keys. Every other key in those namespaces is *referenced*. Each row records the upstream key, type and requirement level as
published (`origin: otel`, or `upstream:` on a row whose key OpenTelemetry
defines although OpenInference uses it too, such as `session.id`), and in the
Weaver registry the key is a `ref` to the pinned upstream definition, so its
brief, type and stability are upstream's. The generated constants for them
are a convenience, not a fork. A fact no convention names gets a key under
`rius.*` (`origin: rius`). The linter rejects `glassflow.*`, and an
`origin: rius` key outside `rius.*` needs a written `namespace_exception`.

Keys the Rius normalizers only *read* from other producers are not ours
either. OpenInference's keys (which the SDKs also emit, and no upstream
registry defines) and the
usage keys of OpenInference, OpenLLMetry, the Vercel AI SDK and pydantic-ai
are described under `model/inputs/`, each with the decision
`registry/usage_keys.yaml` records for it and, when it is mapped, the
canonical key it becomes. Their spellings under `gen_ai.*` are not defined
there, because only OpenTelemetry may define that namespace; their decisions
stay in `registry/usage_keys.yaml`.

## Attribute reference

Every key is documented on a page generated from the Weaver registry under
[docs/registry/](docs/registry/README.md), with its stability, type,
description and examples:

| Page | What it holds |
| -- | -- |
| [`rius`](docs/registry/rius.md) | The namespace this registry owns. |
| [`gen_ai`](docs/registry/gen_ai.md), [`mcp`](docs/registry/mcp.md) | The two Rius keys outside `rius.*`, each under its namespace exception. |
| [`glassflow`](docs/registry/glassflow.md) | Deprecated keys from before the move to `rius.*`. |
| [Upstream keys](docs/registry/upstream.md) | The OpenTelemetry keys the SDKs emit or read, linked to their definitions in the pinned upstream registries, with the requirement level Rius gives each. |
| [Keys other producers write](docs/registry/normalizer-inputs.md) | The OpenInference, OpenLLMetry, Vercel AI SDK and pydantic-ai keys the SDKs emit or the normalizers read, with each decision. |

`python -m generators.registry_docs` writes the pages; CI fails when they are
out of date.

## Which upstream versions it tracks

`versions.env` pins every upstream registry and is the record of which
version or commit each one is at; `model/manifest.yaml` names the same pins as
Weaver dependencies, and `tools/check_weaver_pins.py` keeps the two equal:

- **OpenTelemetry semantic conventions (core)** (`SEMCONV_VERSION`, a release
  tag): the general attributes (`service.*`, `error.type`, the `exception`
  event, `telemetry.*`, `session.id`, `user.id`).
- **OpenTelemetry GenAI conventions** (`SEMCONV_GENAI_REF`): `gen_ai.*` and
  `mcp.*`. They are in Development status and
  [semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai)
  cuts no releases, so the pin is a commit on `main`. The request-parameter
  table in `registry/model_parameters.yaml` was verified against commit
  `8ffdf56` (2026-09-22).
- **OTel Weaver** (`WEAVER_VERSION`, a release tag), which checks and
  resolves the registry.
- **OTel Weaver policy packs** (`WEAVER_PACKAGES_REF`): the shared `stability`
  and `backwards-compatibility` policies from
  [opentelemetry-weaver-packages](https://github.com/open-telemetry/opentelemetry-weaver-packages),
  which cuts no releases either, so the pin is a commit.
- **OpenInference.** The span kinds and the flattened `llm.*` keys its
  instrumentors emit. It publishes no Weaver registry, so nothing is pinned;
  the recordings pin every instrumentor to an exact version (each family's
  `manifest.json`), and the third-party content allowlists pin the source
  version each group was read from.

Where a row deliberately differs from the upstream definition it references,
it says so in `upstream_divergence`, and CI fails on any difference a row does
not record (`tools/check_weaver_types.py`). No row differs today.

The registry is moving to the [OTel Weaver](https://github.com/open-telemetry/weaver)
format. `tools/to_weaver.py` writes the Weaver registry under `model/` from
`registry/`, which stays the file you edit; CI fails when the two disagree.
Each Rius key there carries a one-line brief, examples and a stability
level (all in development today), and renamed keys stay as deprecated
entries. `model/manifest.yaml` is the Weaver manifest, maintained by hand: it
names the registry's `schema_url`
(`https://docs.glassflow.ai/rius/schemas/<version>`, the last segment being
the version in `version.txt`) and its dependencies. Renovate (`renovate.json`)
opens a pull request when a pin in `versions.env` moves, and a workflow
commits the files that follow from it (CONTRIBUTING.md, "Dependency bumps").
Each release's schema files are served at that URL, from 1.2.0 on.

## How consumers use it

**Vendored generated files.** Each consumer vendors the generated file for
its language at a pinned registry release, and imports its constants from it:

| Consumer | Vendored as | Release pinned in | Re-pin with |
| -- | -- | -- | -- |
| Python SDK | `src/rius/_semconv_generated.py` | the file's header | `TAG=<tag> scripts/sync-semconv.sh` |
| TypeScript SDK | `src/semconv.generated.ts` | the file's header | `TAG=<tag> scripts/sync-semconv.sh` |
| Rius backend | `packages/argus-core/semconv/semconv_generated.go` | `RIUS_SEMCONV_TAG` in its Makefile | `make sync-semconv` |

Each copy is the release's `out/` file byte for byte, under two comment lines
naming the release (`# Vendored from rius-semconv v1.3.0 ...`). The SDKs'
hand-written `semconv.py` and `semconv.ts` re-export it and keep the helper
functions; the backend's `semconv.go` keeps only the keys the registry does
not generate (see [Go](#go)). Each consumer's CI fails when its copy differs
from its pinned release: the Python SDK's `semconv-vendored` workflow, the
TypeScript SDK's `semconv-parity` workflow (its `vendored` job) and the
backend's `make semconv-parity`. While this repository is private, those
checks read it with a token and skip with a warning when they cannot.

A change reaches a consumer through a release: merge it here, release, then
re-pin the consumer, which is a reviewable diff of the vendored file.

**Parity.** `tools/check_parity.py` compares each consumer's vendored copy
with `out/`, byte for byte after the header. A difference means the consumer
pins an older release, which is allowed, so it is a warning unless
`--strict`. Beside a current copy, every constant the backend's hand-written
`semconv.go` still declares must be classified (see [Go](#go)), and none may
repeat a generated one. A consumer with no vendored copy is checked by value
instead: the tool evaluates the generated module and the consumer's
hand-written file (Python by executing it, TypeScript through Node, Go
constants by name) and fails when a value differs or a name is uncovered.
Comments and literal versus constant-reference spellings are invisible to
that check, by design. Order is not: a table whose entries are equal but
listed in another order fails, because in the request-parameter map the first
spelling listed wins.

Publishing the constants as packages is a separate decision. Nothing depends
on this repository at run time.

## Versioning and stability

The **registry** is versioned: it is the wire contract the SDKs and the
backend implement, and traffic depends on it for as long as an SDK runs.
release-please (`.github/workflows/release.yml`) keeps a release pull request
open; merging it tags `vX.Y.Z` and writes `CHANGELOG.md`, which lists contract
changes only. Nothing is published to a package registry.

A version step says what changed on the wire:

- **major**: a wire value changes in place, a stable key changes type or
  meaning, or a deprecated key's constant is dropped after its window.
  Consumers must act.
- **minor**: rows, members or tables are added, `planned` becomes
  `shipped`, or a key is deprecated.
- **patch**: the meaning of an existing row is corrected; generated values
  are unchanged.

The step comes from the commit type, so label changes accordingly:

| Change | Commit type |
| -- | -- |
| A wire value changed in place, a stable key's type or meaning changed, or a deprecated constant dropped after its window | `feat!:` (or a `BREAKING CHANGE:` footer) |
| A key deprecated (with its replacement, if any) | `feat(deprecate):` |
| A row, member or table added, or `planned` becomes `shipped` | `feat:` |
| A row's meaning or disposition corrected, generated values unchanged | `fix:` |
| Recordings, expected results, tests, tooling | `test:` or `chore:` |
| Documentation only | `docs:` |

Commits that touch nothing but `fixtures/`, `tests/`, `tools/` or `.github/`
never cause a release, whatever their type. Each release's notes list
breaking changes first, then deprecations under their own **Deprecations**
heading, then features and fixes.

Shipped keys are deprecated, never removed:

- A key is never deleted from the registry and its string is never reused.
  A deprecated key names the key that replaces it, or says why nothing does.
- A deprecated key keeps its generated constant for at least **two minor
  releases or six months** after the release that deprecates it, whichever
  is longer. Only a major release after that window may drop the constant;
  the registry still records the key.
- A stable key changes type or meaning only in a major release.
- A development key may still change in a minor release, but not its type:
  a new type is a new key, and the old one is deprecated. Only a row that
  never shipped (`status: planned`) changes freely.

Every Rius-owned key is in development until the registry records stability
per key. [CONTRIBUTING.md](CONTRIBUTING.md#deprecation-and-compatibility)
has the full policy and how to mark a deprecation.

`status: planned` marks a decided row that no consumer ships yet, such as
`telemetry.distro.name`; planned rows are left out of generated output unless
you pass `--include-planned`. Keys borrowed from OpenTelemetry are only as
stable as their upstream convention, and the GenAI conventions are still in
Development: if upstream renames a key and the registry adopts the rename,
the old key stays, deprecated, under the rules above.

## Recorded spans: a conformance suite

`fixtures/` holds real spans from the instrumentors Rius normalizes
(OpenInference for Python and JavaScript, the Vercel AI SDK, pydantic-ai,
OpenLLMetry, Laminar), recorded against scripted providers with no network
and no API keys, plus two control families recorded from the Rius SDKs
themselves. Each recording comes with the result a normalizer is expected to
produce from it. The Python SDK, the TypeScript SDK and the Rius backend each
run the recordings through their own normalizer and must produce exactly that
result, so they agree with each other without ever being compared directly.

Recordings are OTLP/JSON, so any language can decode them with its own OTLP
types, and they are byte-identical when re-recorded in the pinned
environment. A normalizer outside Rius can use them the same way. See
[fixtures/README.md](fixtures/README.md) for the format, where each expected
result comes from, and how to record a new family.

CI also checks every expected result against this registry with Weaver's
`registry live-check`: a key the registry does not define, or one with the
wrong type, fails the build, so what the normalizers produce and what the
registry promises cannot drift apart.

Consumers pin the recordings by exact commit, not by registry version: they
change with every normalizer fix, and only exact equality matters to a
conformance test.

## Layout

```
registry/                  the data (this is what you edit)
  attributes.yaml          every named wire string, one row per constant
  allowlists.yaml          pending-snapshot and content allowlists
  taxonomy.yaml            span kinds, and the maps to and from gen_ai.operation.name
  model_parameters.yaml    provider parameter spellings -> gen_ai.request.* keys
  usage_keys.yaml          a decision for every token, usage and cost key instrumentors send
  preamble.yaml            per-language headers and output file names
generators/                the loader and linter, the generate CLI, and the Weaver runner
out/                       generated files, committed so every change is a reviewable diff
docs/registry/             the attribute reference, one page per namespace (generated by Weaver)
  docs/usage-keys.md       the usage-key table: each key, its decision, what each normalizer does
fixtures/                  recorded spans and the result every normalizer must
                           produce from them (see fixtures/README.md)
  passthrough.yaml         third-party keys live-check allows unmodelled, each with its reason
tools/
  check_registry.py        lint the registry
  check_parity.py          compare out/ with what each consumer ships
  check_fixtures.py        every recording has a manifest entry and an expected result
  check_usage_keys.py      every usage key in a recording has a decision, and it holds
  expect_python.py         write a recording's expected result with the Python SDK
  expect_typescript.mts    write one with the TypeScript SDK (Vercel families), under tsx
  review_expected.py       what a normalizer did to each span, for the hand review
  install_weaver.sh        install the Weaver release pinned in versions.env, checksum-verified
  check_weaver_pins.py     model/manifest.yaml pins what versions.env and version.txt say
  follow_pins.py           after a pin moves: Weaver checksums, schema_urls, regenerate
  to_weaver.py             write model/ and templates/params.yaml from registry/
  check_weaver_types.py    every referenced upstream key has the type its row says
  weaver_check.py          weaver registry check with the policies, against the last release
  expected_to_samples.py   the expected results as weaver registry live-check samples
  live_check_findings.py   what a live-check report found, for the CI log
  go_reference_only.yaml   backend constants the registry does not generate, and why
tests/                     pytest suites for the loader, linter, generators and tools
policies/                  Rego policies weaver registry check runs, and their test cases
model/                     the Weaver registry, written from registry/ by tools/to_weaver.py
  manifest.yaml            the Weaver manifest: schema_url and upstream dependencies (by hand)
  rius/registry.yaml       the Rius keys as Weaver definitions
  rius/upstream.yaml       refs to the upstream keys the SDKs emit or read
  inputs/<producer>.yaml   other producers' keys the normalizers read, with each decision
.weaver.toml               live-check matchers and the naming exception for camelCase third-party keys
templates/params.yaml      the Weaver --params sidecar: emission order and the non-attribute data
templates/registry/        the Weaver templates that render out/, one directory per language
versions.env               pinned Weaver and upstream registry versions (bumped by Renovate)
version.txt                the registry's released version (written by release-please)
```

## Quick start

Python 3.11+, the pinned Weaver (`tools/install_weaver.sh`; generating
fetches the pinned upstream registries from GitHub), Go (for `gofmt`) and
Node 22.7+ (to evaluate TypeScript in the tests and the parity check).

```
pip install -r requirements-dev.txt
tools/install_weaver.sh                   # installs .weaver/bin/weaver
python tools/check_registry.py            # lint
python -m generators.generate             # regenerate out/
python -m generators.generate --check     # exit 1 if out/ is stale
python tools/check_fixtures.py            # every recording is complete
python tools/check_usage_keys.py          # every recorded usage key is decided
python -m pytest
```

`.github/workflows/ci.yml` runs these, plus `ruff check .`,
`ruff format --check .` and a determinism check that generates twice and
diffs. Without Weaver, pytest skips the generator tests that render.

Its `weaver` job runs everything that needs Weaver (generating, and the
generator tests). It also checks and resolves the Weaver registry, runs the
policies (see [policies/README.md](policies/README.md)) and compares the
registry with the last release. It fetches the pinned upstream registries and
policy packs from GitHub:

```
python tools/check_weaver_pins.py         # manifest pins match versions.env
python tools/to_weaver.py --check         # model/ matches registry/
python -m generators.registry_docs --check  # docs/registry/ is current
export PATH="$PWD/.weaver/bin:$PATH"
python tools/weaver_check.py              # policies, and the breaking-change gate
python -m pytest tests/test_policies.py   # the policies' own tests
weaver registry resolve -r model --v2 -o /tmp/resolved.yaml
```

## What a row says

Each row of `registry/attributes.yaml` is one constant. The columns that
matter most (the file's header lists them all):

- **`const` / `key`**: the constant's name in Python and TypeScript, and the
  wire string. Go names are derived (`GEN_AI_TOOL_NAME` becomes
  `GenAIToolName`) unless `go:` overrides them.
- **`symbol`**: an `attribute` key, a key `prefix`, an `event` name, an
  enumerated `value` of another attribute, the instrumentation `scope` name,
  a span `name`, or a key `fragment` read relative to a prefix (the fields of
  OpenInference's flattened messages, such as `message.role`).
- **`origin`**: `otel` (an OpenTelemetry convention, including GenAI and MCP),
  `openinference`, or `rius` (ours).
- **`direction`**: `emitted` (the default) or `read`, for keys the SDKs only
  read from other producers' spans, such as the OTel `exception` event.
- **`kinds`**: `resource`, or the span kinds the attribute belongs on.
- **`level`**: the OpenTelemetry requirement level (`required`,
  `conditionally_required`, `recommended`, `opt_in`), or `vendor` for a
  Rius key.
- **`placements`**: for a key that means different things in different
  places. `gen_ai.agent.name` names the agent a process *is* on the resource,
  the agent *being invoked* on an `invoke_agent` span, and the agent
  *executing a tool* on an `execute_tool` span. That is one row with three
  placements, each with its own level and `when` condition.
- **`rationale`**: why the key exists and why it is shaped the way it is.
  It is emitted as a comment above the constant in every language, so the
  reasoning survives generation.

### Attribute classes

Every **span** attribute has exactly one category. The categories are defined
by a span's lifecycle, and they decide how the SDKs treat the attribute:

| Category | Known | Rides a pending snapshot | Survives content capture off | Leaves the process |
| -- | -- | -- | -- | -- |
| `identity` | at span start | yes | yes | yes |
| `content` | during the work | no | no, masked or stripped | only if capture is on |
| `metadata` | after the work | no | yes | yes |
| `process_local` | at span start | yes | yes | **no**, stripped at export |

A *pending snapshot* is the content-free copy of a span an SDK exports when
the span starts, so a live view can show work that has not finished yet.

**Resource** attributes take no category. They are set once per process and
present on every span, so they would satisfy every column above trivially;
the linter rejects a category on them rather than let two readings coexist.

Two **allowlists** in `registry/allowlists.yaml` turn the categories into
behaviour:

- **`PENDING_IDENTITY_ATTRIBUTES`** (plus `PENDING_IDENTITY_PREFIXES`) is
  what may ride a pending snapshot.
- **`CONTENT_ATTRIBUTES`** (plus prefixes and suffixes) is what gets masked
  or stripped at export. It includes third-party keys the registry has no
  constant for, because content exclusion must hold for other
  instrumentations' spans too. The keys of other tracing SDKs a customer
  runs next to Rius (Langfuse, Traceloop, Logfire, MLflow, OpenLIT, Laminar)
  are kept in their own list, `THIRD_PARTY_CONTENT_ATTRIBUTES`, each group
  pinned to the source version it was read from, and folded into
  `CONTENT_ATTRIBUTES` through `includes`. `CONTENT_PREFIX_IDENTITY_ATTRIBUTES`
  names the few keys under a content prefix that are identity and must stay
  in clear, and `CONTENT_ATTRIBUTE_PREFIXED_SUFFIXES` covers leaves that are
  content only under a given prefix.

Both are allowlists on purpose: a blocklist would have to enumerate every
third-party attribute family. Membership is **authored**, never derived from
the category. The linter checks that the two agree: an `identity` attribute
that is not on the pending allowlist and not covered by a pending prefix has
to say why in `not_pending`. `rius.span.pending` is the case that needs it:
it is identity, but the snapshot builder stamps it on the snapshot rather
than copying it from the span.

## How the generators work

`python -m generators.generate` loads the YAML, **lints it** (and refuses to
write anything if the lint fails), and renders one file per language into
`out/` with `weaver registry generate`. It writes what `tools/to_weaver.py`
would write from the registry into a temporary directory and renders the
template under `templates/registry/<lang>/` against it, so the output follows
`registry/` even before `model/` is rewritten. The context the three templates
share (rows in emission order, allowlist members, Go names) is built by the
jq filter in `templates/registry/weaver.yaml`. If a template needs a fact the
registry does not state, the fix is a column in the YAML, not a special case
in the template. `out/docs/usage-keys.md` is rendered in Python.

Output is deterministic: the same registry always renders byte-identical
files, which CI proves by generating twice and diffing. The Go file is
`gofmt`'d, and a test checks the TypeScript file with `biome` when a
TypeScript SDK checkout is available.

### The generation boundary: constants, not whole files

The templates emit a **constants-and-tables module**, not a replacement for
each SDK's hand-written `semconv.py` / `semconv.ts`: the hand-written file
re-exports the vendored module and keeps the helper
functions (`kind_attributes`, `compose_span_name`, `request_attribute_key`
and their TypeScript twins).

Why not generate the whole file? The helpers are logic, and logic is not
registry data: reproducing them from a template would make the template a
second copy of the code. Everything the helpers *read* (the maps, the
allowlists, the parameter table) is generated, so the two SDKs cannot
disagree about data, only about code, and code is covered by each SDK's own
tests.

In Go, the generated file covers the **canonical** keys only; see [Go](#go).

### Divergence between languages

When the SDKs deliberately differ, the registry says so instead of picking a
winner silently. `shipped_in: [python, go]` limits a row, allowlist member or
table to those languages, and `divergence:` (required) says why;
`git grep -n shipped_in registry/` finds every one. Today:

- `TRACER_NAME` is not generated for Go: the backend deliberately names no
  instrumentation scope.
- `SERVICE_NAME` is generated only for Go: the SDKs set `service.name`
  through the OpenTelemetry SDK and name no constant for it.
- `GEN_AI_USAGE_PREFIX` and `RIUS_AGGREGATED_USAGE_PREFIX` are not generated
  for Go: the SDKs move a run's aggregate usage by prefix, and the backend
  names each usage key on its own.
- The flattened-message prefixes (`llm.input_messages.`,
  `llm.output_messages.`) are generated only for TypeScript: the Python SDK
  keeps the same strings private in its normalizer.
- `otel_kind_by_kind` is not generated for Go, which creates no spans.

## Adding an attribute

1. **Check the OpenTelemetry conventions first**: the
   [GenAI registry](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/model/gen-ai/registry.yaml)
   and the general
   [attribute registry](https://opentelemetry.io/docs/specs/semconv/registry/attributes/).
   If a convention defines the fact, use its key, type and requirement level
   exactly (`origin: otel`).
2. **Only a fact no convention names gets a Rius key**, and it goes under
   **`rius.*`** (`origin: rius`). Never put a Rius key inside a convention's
   namespace such as `gen_ai.*`, even when it looks like a natural fit: the
   convention is free to define that exact key later and mean something
   else. Never use `glassflow.*`: GlassFlow is the company, and Rius is the
   product.
3. **Add the row** to `registry/attributes.yaml` with its category (span
   attributes only), level, kinds and a rationale that says *why*. Write the
   reason itself, never an issue-tracker reference: the linter rejects
   ticket ids. A Rius key also needs a one-line `brief`, `examples` and a
   `stability` (`development` for a new key).
4. **Decide allowlist membership explicitly.** An identity key goes on
   `pending_identity` (or states `not_pending`). A content key goes on
   `content`.
5. If no consumer ships it yet, mark it `status: planned`.
6. `python -m generators.generate` and `python tools/to_weaver.py`, then
   commit the registry change, `out/` and `model/` together. CI fails if
   either lags.
7. Until every consumer has the constant, parity reports the gap. That is
   the signal working, not a failure to silence.

## Parity checks

`tools/check_parity.py` compares `out/` with each consumer's `main` branch.
The SDKs are read from sibling checkouts (`../rius-sdk-python`,
`../rius-sdk-typescript`; override with `--python-repo` and
`--typescript-repo`). The Rius backend has no default location: check it with
`python tools/check_parity.py go --go-dir <dir>`, where `<dir>` is its semconv
package directory (the one holding `semconv.go` and `semconv_generated.go`)
inside a git checkout. Pick a ref with
`--ref`, fetch first with `--fetch`, and add `--cross` to also diff the two
SDKs' hand-written files directly, for review.

- **`ci.yml`** (no secrets): lints this repository's code and the registry,
  checks the fixtures and the usage-key decisions, and runs the tests. Its
  `weaver` job installs the pinned Weaver, checksum-verified, generates twice
  and diffs to prove determinism, fails if `out/` is stale, runs the
  generator tests, and runs `weaver registry check` (with the policies and
  the breaking-change gate) and `resolve` against the pinned upstream
  registries. Its `live-check` job checks every fixture's expected result
  against the registry.
- **`parity.yml`** (no secrets): runs `check_parity.py` against each SDK's
  `main` on every pull request, on pushes to `main`, daily, and on demand.
- **`renovate-followup.yml`**: regenerates the files that follow from the
  pins on Renovate's pull requests and pushes the result with an
  installation token of a GitHub App installed on this repository only
  (Contents: Read and write), from the `RENOVATE_FOLLOWUP_APP_CLIENT_ID` and
  `RENOVATE_FOLLOWUP_APP_KEY` secrets (CONTRIBUTING.md, "Dependency bumps").
- **`release.yml`**: keeps the registry's release pull request up to date
  on pushes to `main` (see [Versioning](#versioning-and-stability)).

Both SDK repositories are public, so `parity.yml` reads them without a
token. The Rius backend runs the Go check in its own CI, against a pinned
release of this registry, and fails when its constants drift from it.

Every action is pinned to a full commit SHA, with its version in a trailing
comment.

## Go

The backend's semconv package holds two kinds of constant. The **canonical**
keys are the ones the SDKs emit, and this registry generates them into
`semconv_generated.go`, in the same package (the directory `--go-dir`
names). The rest are the backend normalizer's **input
spellings**, which the SDKs never emit and the backend reads from other
producers. `tools/go_reference_only.yaml` lists every one by class, except
the usage keys, which `registry/usage_keys.yaml` already decides with their
mapping. Before the whole Go file can be generated, the registry needs:

1. **Per-source-family mapping tables**, one per family, each row a
   source key, target key, converter, when it applies (span start or end) and
   whether the source key is deleted after mapping:
   - OpenInference: `llm.model_name`, `llm.provider`, `llm.finish_reason`,
     the request/response model pair, the flattened message prefixes, the
     indexed tool definitions (`llm.tools.<i>.tool.json_schema`), and the
     `First Token Stream Event` event rename.
   - Vercel AI SDK: `ai.prompt.tools`, then the rest of the `ai.*` family.
   - OTel legacy and draft spellings: `enduser.id`, `enduser.pseudo.id` and
     `gen_ai.conversation.id`, as fallbacks for `user.id` and `session.id`.
2. **An alias table for legacy spellings** that released SDKs still send:
   `gen_ai.system`, `glassflow.span.pending`, and `gen_ai.request.tool_choice`,
   each with the condition for retiring it.
3. **A decision on dynamic keys** the backend reads by name inside a
   namespace the registry owns only as a prefix, such as
   `rius.request.tool_choice`.

Those tables are decisions about normalization that are still being made in
the consumers, so encoding a guess here would create a second source of
truth. The inventory is kept exact instead: parity fails on any backend
constant that is neither generated nor classified.

## Usage keys

A token count present on a span under a name nothing reads is priced as zero,
or not at all, and nobody notices. `registry/usage_keys.yaml` gives every
token, usage and cost key an instrumentor sends a decision: **canonical**,
**mapped** (to which canonical key, and by which normalizers), **ignored**
(and why nothing should read it), **not_usage**, or **gap** (a count that
reaches no canonical key yet, and what that loses).

`tools/check_usage_keys.py` scans every recording under `fixtures/` (span and
event attributes) and fails on a key matching the file's `match` words that no
entry decides, so a new instrumentor version that adds one fails CI. It also
checks each decision against the expected results: a normalizer listed in
`mapped_by` must drop the key and leave its target, and one not listed must
leave it alone.

The generated table, [`out/docs/usage-keys.md`](out/docs/usage-keys.md),
lists each key with its decision, what each normalizer does with it, and the
families it was recorded in.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). In short: edit `registry/`,
regenerate `out/`, run the checks in [Quick start](#quick-start), and title
the pull request with the commit type from
[Versioning and stability](#versioning-and-stability).

## License

[Apache License 2.0](LICENSE).

OpenTelemetry, OpenInference, Vercel, OpenLLMetry, Laminar, pydantic-ai and
other product names are trademarks of their respective owners.
