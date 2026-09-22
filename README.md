# rius-semconv

One registry for the Rius semantic conventions, and the generators that turn it
into `semconv.py`, `semconv.ts` and `semconv.go`.

Today the same set of keys is hand-maintained in three places and kept honest by
a fixture generator that scrapes constants out of `semconv.py` with a regex.
That works while the content is a flat list of constants. It stops working as
soon as the content becomes tables — categories, requirement levels, allowlists,
per-family mapping rules — which is what RIUS-917 makes it.

This repo is the single source. Consumers **vendor** the generated file and fail
CI when it drifts. Nobody depends on this at runtime.

Status: **proposal**. Not published, no remote, no release. See
[DISCREPANCIES.md](DISCREPANCIES.md) for everything the registry and the live
code disagree about.

## Layout

```
registry/                 the data
  attributes.yaml         every canonical key, in emission order
  allowlists.yaml         pending-identity and content allowlists
  taxonomy.yaml           span kinds, operation maps both ways, OTel kind map
  model_parameters.yaml   spec params, provider aliases, the fallback namespace
  preamble.yaml           per-language file headers and imports
generators/               one small module per language
  registry.py             loads the YAML, answers the generators' questions
  python.py  typescript.py  go.py
  generate.py             the CLI
tools/
  check_parity.py         generated semconv.py vs. the hand-written one
  check_parity_ts.py      the same, weaker, for semconv.ts
out/                      generated files (committed, so diffs are reviewable)
```

## Regenerate

```
python -m generators.generate all          # -> out/
python -m generators.generate python       # one language
python -m generators.generate --include-planned all
```

`--include-planned` also emits the rows marked `status: planned` — keys RIUS-917
decided but no SDK has yet (`rius.request.`, `gen_ai.agent.name`,
`gen_ai.data_source.id`, the distro resource attributes). **Default output is
shipped-only**, which is what makes the first generated `semconv.py` a no-op
swap for the hand-written one.

Generating Go runs `gofmt` when it is on PATH. Alignment is Go's formatter's job,
not a second formatter's worth of template code.

## Parity with today

```
python tools/check_parity.py --show-diff
python tools/check_parity_ts.py
```

Both read the reference from `origin/main` of the sibling checkout
(`../rius-sdk-python`, `../rius-sdk-typescript`), so a stale local branch cannot
make the check pass by accident. Point them elsewhere with `--repo` /
`--reference`.

The Python check parses both files and compares the public surface: every
module-level name that does not start with `_`, the `SpanKind` members, and the
module-level function names. Set members are compared order-insensitively, so
reordering a frozenset is not a failure but losing a member is. The textual diff
is printed but never fails the check — RIUS-937 excuses a generated-file header.

## How a consumer pins, regenerates, and fails on drift

1. **Pin a tag.** The consumer stores the `rius-semconv` tag it was generated
   from, in the same file as the generated code (the header carries it) or in
   the CI workflow. Not a floating `main`: a registry edit must not silently
   change an SDK's behaviour on its next unrelated CI run.
2. **Vendor the output.** `out/semconv.py` is copied to `src/rius/semconv.py`
   and committed. The SDK builds and tests against the committed file with no
   dependency on this repo at build or run time.
3. **CI regenerates and diffs.** A job checks out the pinned tag, runs the
   generator, and `diff`s against the committed file. Non-empty diff = red.
   This replaces `rius-sdk-typescript`'s `scripts/gen-semconv-fixture.mjs` and
   its `semconv-parity.yml` workflow, which scrape the Python file directly.
4. **Bumping is a deliberate PR.** Move the pinned tag, regenerate, commit the
   new file. The diff in that PR is the review surface for a convention change —
   which is the point: today the same change is three PRs that nobody diffs
   against each other.
5. **A consumer may lag.** Different consumers can sit on different tags during
   a migration. CI says which, loudly, instead of the drift being invisible.

## What belongs in the registry

- A **canonical attribute key** the platform reads, with its category, level,
  applicable span kinds and fill source.
- The **rationale** for it. Prose lives in the YAML and is emitted into every
  generated file, so the reasoning survives generation. Line breaks in
  `rationale` are authored, not reflowed — that is what lets the generated
  Python keep the hand-written file's wording verbatim.
- **Allowlists** that decide what leaves the process (content) and what rides a
  pending snapshot (identity).
- **Maps between two vocabularies** we own the translation for: span kind ↔
  operation name, span kind → OTel `SpanKind`, provider parameter → spec
  parameter.
- **Decisions with no code yet**, as `status: planned` plus the ticket. A
  decision with nowhere to live gets re-litigated.

## What does not

- **Anything a consumer decides for itself.** How the Python SDK serializes
  messages, how the sink batches, what the TS exporter retries on.
- **Third-party keys we only read.** `llm.*`, `ai.*`, `enduser.*`,
  `gen_ai.conversation.id` are normalizer *input*, not canonical output. They
  belong in the per-family mapping tables (not yet built — see below), not in
  `attributes.yaml`.
- **Formatting.** One exception exists and it is marked as such:
  `blank_before` on a single row, to keep the generated Python byte-identical.
  If a second one appears, the answer is to stop chasing byte-identity, not to
  add more.
- **Anything that would make a generator need a special case.** If a generator
  needs something the registry does not say, add a column.

## Deliberately left out of this proposal

Not oversights. Both are later parts of RIUS-937 and depend on work that has not
happened:

- **Golden span fixtures** (RIUS-927/929/931). They are per-instrumentor raw and
  canonical span pairs; the instrumentor mappings they would encode do not exist
  yet.
- **The docs-generation hook** (RIUS-935).

Also not built, and needed before `semconv.go` can replace argus-core's file:

- **The per-source-family mapping tables** (OpenInference, OpenLLMetry, Vercel
  `ai.*`, legacy `gen_ai.system`) — source key, target key, converter,
  start-time or end-time, deletion rule. RIUS-937 calls for them; RIUS-920 is
  their first consumer. `semconv.go` as generated today covers the canonical
  half only. See DISCREPANCIES.md §8.

## Requirements

Python 3.11+ and PyYAML. `gofmt` optional.
