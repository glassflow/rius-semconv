# rius-semconv

The semantic-convention registry for **Rius**, GlassFlow's observability
product for AI agents, and the generators that turn it into Python,
TypeScript and Go.

Rius SDKs emit OpenTelemetry traces that follow the
[OpenTelemetry GenAI conventions](https://github.com/open-telemetry/semantic-conventions-genai)
(`gen_ai.*`) and OpenInference's span taxonomy (`openinference.span.kind`).
Every wire string those SDKs and the Rius backend have to agree on (attribute
keys, event names, the span-kind taxonomy, the allowlists that decide what
may leave a process, the table that maps provider parameter spellings to
convention keys) is defined **once**, here, as data. Each consumer vendors
the generated file for its language; nothing depends on this repository at
run time.

Consumers today:

| Consumer | Language | Generated file, vendored as |
| -- | -- | -- |
| `rius-sdk-python` | Python | `src/rius/_semconv_generated.py` |
| `rius-sdk-typescript` | TypeScript | `src/semconv.generated.ts` |
| `argus-core` (the Rius backend) | Go | `packages/argus-core/semconv/semconv_generated.go` |

## Layout

```
registry/                  the data (this is what you edit)
  attributes.yaml          every named wire string, one row per constant
  allowlists.yaml          pending-snapshot and content allowlists
  taxonomy.yaml            span kinds, and the maps to and from gen_ai.operation.name
  model_parameters.yaml    provider parameter spellings -> gen_ai.request.* keys
  usage_keys.yaml          a decision for every token, usage and cost key instrumentors send
  preamble.yaml            per-language headers and output file names
generators/                one small module per language, plus the loader and linter
out/                       generated files, committed so every change is a reviewable diff
  docs/usage-keys.md       the usage-key table: each key, its decision, what each normalizer does
fixtures/                  real instrumentor spans and the result every normalizer must
                           produce from them (see fixtures/README.md)
tools/
  check_registry.py        lint the registry
  check_parity.py          compare out/ with what each consumer ships
  check_fixtures.py        every recording has a manifest entry and an expected result
  check_usage_keys.py      every usage key in a recording has a decision, and it holds
  expect_python.py         write a recording's expected result with the Python SDK
  expect_typescript.mts    write one with the TypeScript SDK (Vercel families), under tsx
  review_expected.py       what a normalizer did to each span, for the hand review
  go_reference_only.yaml   argus-core constants the registry does not generate, and why
tests/                     pytest suites for the loader, linter, generators and parity tools
```

## Quick start

Python 3.11+, plus Go (for `gofmt`) and Node 22.7+ (to evaluate TypeScript in
tests and parity checks).

```
pip install -r requirements-dev.txt
python tools/check_registry.py            # lint
python -m generators.generate             # regenerate out/
python -m generators.generate --check     # exit 1 if out/ is stale
python tools/check_fixtures.py            # every recording is complete
python tools/check_usage_keys.py          # every recorded usage key is decided
python -m pytest
python tools/check_parity.py --fetch      # compare with the consumers' main branches
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
  runs next to rius (Langfuse, Traceloop, Logfire, MLflow, OpenLIT, Laminar)
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
`out/`. Each generator is a short, readable template: no templating engine,
no code-generation DSL. If a generator needs a fact the registry does not
state, the fix is a column in the YAML, not a special case in the generator.

Output is deterministic. The same registry always renders byte-identical
files, which CI proves by generating twice and diffing. The Python file
passes `ruff`, the TypeScript file passes `biome`, and the Go file is
`gofmt`'d, under the consumers' own settings, so vendoring needs no lint
exemptions.

### The generation boundary: constants, not whole files

The generators emit a **constants-and-tables module**, not a replacement for
each SDK's hand-written `semconv.py` / `semconv.ts`. The hand-written file
re-exports the generated module and keeps the helper functions
(`kind_attributes`, `compose_span_name`, `request_attribute_key` and their
TypeScript twins).

Why not generate the whole file? The helpers are logic, and logic is not
registry data: reproducing them from a template would make the template a
second copy of the code. The SDKs' comments also differ in wording and
order, so a byte-identical copy of both files from one source is not
possible without keeping per-language prose, which is the drift this
repository exists to remove. Everything the helpers *read* (the maps, the
allowlists, the parameter table) is generated, so the two SDKs cannot
disagree about data, only about code, and code is covered by each SDK's own
tests.

In Go, the generated file covers the **canonical** keys only; see "Go" below.

### Divergence between languages

When the SDKs deliberately differ, the registry says so instead of picking a
winner silently. `shipped_in: [python, go]` limits a row, allowlist member or
table to those languages, and `divergence:` (required) says why. Today:

- `TRACER_NAME` is not generated for Go: argus-core deliberately names no
  instrumentation scope.
- `SERVICE_NAME` is generated only for Go: the SDKs set `service.name`
  through the OpenTelemetry SDK and name no constant for it.
- `llm.invocation_parameters` is content in Python and Go, but not in
  TypeScript, which redacts only the bag's `tools` / `functions` members.
- `otel_kind_by_kind` is not generated for Go, which creates no spans.

`status: planned` marks a decided row that no consumer ships yet, such as
`telemetry.distro.name`. Planned rows are left out of generated output unless
you pass `--include-planned`.

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
   product. The linter rejects `glassflow.*`, and an `origin: rius` key
   outside `rius.*` needs a written `namespace_exception`. Two keys predate
   the rule and carry one: `gen_ai.first_token` and `mcp.result_type`.
3. **Add the row** to `registry/attributes.yaml` with its category (span
   attributes only), level, kinds and a rationale that says *why*. Write the
   reason itself, never a ticket number: this registry is read outside the
   team, and the linter rejects internal ticket IDs.
4. **Decide allowlist membership explicitly.** An identity key goes on
   `pending_identity` (or states `not_pending`). A content key goes on
   `content`.
5. If no consumer ships it yet, mark it `status: planned`.
6. `python -m generators.generate`, then commit the registry change and
   `out/` together. CI fails if `out/` lags.
7. Land the constant in each consumer by bumping its pinned version (below).
   Until every consumer has it, parity reports the gap. That is the signal
   working, not a failure to silence.

## Consumers: pinning, vendoring, drift

1. **Pin a version.** A consumer records which `rius-semconv` tag it vendors,
   in its CI workflow. Never a floating `main`: a registry edit must not
   change an SDK's behaviour on its next unrelated CI run.
2. **Vendor the output.** Copy the file from `out/<language>/` to the path in
   the table at the top, and commit it. The consumer builds and tests
   against the committed file with no dependency on this repository.
3. **CI regenerates and diffs.** A job in the consumer checks out the pinned
   tag, runs `python -m generators.generate <language> --out <tmp>`, and
   fails if the result differs from the committed file.
4. **Bumping is a deliberate PR.** Move the pin, regenerate, commit. The
   diff in that PR is the review surface for a convention change.
5. **A consumer may lag.** Consumers can sit on different versions during a
   migration. This repository's parity job reports a vendored file that
   differs from `out/` as *lagging*, a warning rather than a failure.

## Parity checks

`tools/check_parity.py` compares `out/` with each consumer's `main` branch
(from sibling checkouts: `../rius-sdk-python`, `../rius-sdk-typescript`,
`../argus-core`; override with `--python-repo` and friends, pick a ref with
`--ref`).

- **Before a consumer vendors the generated file**, parity is checked by
  *value*: both files are evaluated (Python by executing it, TypeScript
  through Node) and every name the generated module defines must exist in
  the consumer with an equal value, while every data name the consumer
  defines must be covered by the registry. Comments, ordering, and literal
  versus constant-reference spellings are invisible, by design.
- **Go** compares constants. A constant argus-core has and the registry does
  not generate must be explained in `tools/go_reference_only.yaml`, or be a
  usage key `registry/usage_keys.yaml` decides (its `go` field).
- **After a consumer vendors the file**, the check compares it byte for
  byte, and a difference means that consumer pins an older version.
- `--cross` also diffs the two SDKs' hand-written files directly, for
  review.

## CI

- **`ci.yml`** (no secrets): lints this repository's code and the registry,
  generates twice and diffs to prove determinism, fails if `out/` is stale,
  checks the fixtures and the usage-key decisions, and runs the tests.
- **`parity.yml`**: runs `check_parity.py` against each consumer's `main`
  on every pull request, on pushes to `main`, daily, and on demand.

The consumer repositories are private, so `parity.yml` needs a secret named
**`SDK_READ_TOKEN`**: a fine-grained personal access token or GitHub App
token with **read-only Contents** permission on `glassflow/rius-sdk-python`,
`glassflow/rius-sdk-typescript` and `glassflow/argus-core`, and nothing else.
When the secret is absent (a fork's pull request, or before it is created),
the job skips the comparison, raises a **"Parity NOT checked"** warning and
writes the same message to the run summary. A green run without that warning
is the only proof of parity.

## Go

argus-core's `semconv.go` holds two kinds of constant. The **canonical** keys
are the ones the SDKs emit, and this registry generates them into
`semconv_generated.go`, in the same package. The rest are the backend
normalizer's **input spellings**, which the SDKs never emit and the sink
reads from other producers. `tools/go_reference_only.yaml` lists every one
by class, except the usage keys, which `registry/usage_keys.yaml` already
decides with their mapping. Before the whole Go file can be generated, the
registry needs:

1. **Per-source-family mapping tables**, one per family, each row a
   source key, target key, converter, when it applies (span start or end) and
   whether the source key is deleted after mapping:
   - OpenInference: `llm.model_name`, `llm.provider`, `llm.finish_reason`, the request/response model pair, the
     flattened message prefixes, the indexed tool definitions
     (`llm.tools.<i>.tool.json_schema`), and the `First Token Stream Event`
     event rename.
   - Vercel AI SDK: `ai.prompt.tools`, then the rest of the `ai.*` family.
   - OTel legacy and draft spellings: `enduser.id`, `enduser.pseudo.id` and
     `gen_ai.conversation.id`, as fallbacks for `user.id` and `session.id`.
2. **An alias table for legacy spellings** that released SDKs still send:
   `gen_ai.system`, `glassflow.span.pending`, and `gen_ai.request.tool_choice`,
   each with the condition for retiring it.
3. **A decision on dynamic keys** the sink reads by name inside a namespace
   the registry owns only as a prefix, such as `rius.request.tool_choice`.

Those tables are decisions about normalization that are still being made in
the consumers, so encoding a guess here would create the second source of
truth this repository exists to prevent. The inventory is kept exact instead:
parity fails on any argus-core constant that is neither generated nor
classified.

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
leave it alone. Python is checked on the families it produced the expected
result for, TypeScript on the Vercel families, the sink on its stored rows.

The generated table, [`out/docs/usage-keys.md`](out/docs/usage-keys.md),
lists each key with its decision, what each normalizer does with it, and the
families it was recorded in.

## Versioning (proposed)

Nothing is tagged yet. The proposal: semantic-version tags on this
repository, where

- **major**: a wire value changes or a row is removed. Consumers must act.
- **minor**: rows, members or tables are added, or `planned` becomes
  `shipped`.
- **patch**: prose only; generated values are unchanged.

Consumers pin a tag, as described above. Choosing and publishing the first
tag is an open decision.

## Status

The repository is private while the contract is reviewed. Licensing, and
whether and when to make it public, are open decisions; there is deliberately
no LICENSE file yet. See [DISCREPANCIES.md](DISCREPANCIES.md) for where the
consumers currently disagree with each other.
