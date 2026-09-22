# RIUS-917 table vs. the live code

Cross-check performed 2026-09-23 against:

- `rius-sdk-python` `origin/main` @ `c9344c6`, `src/rius/semconv.py` and
  `src/rius/generation.py`
- `rius-sdk-typescript` `origin/main`, `src/semconv.ts`
- `argus-core` `origin/main`, `packages/argus-core/semconv/semconv.go`

**Where the ticket and the code disagree, the registry follows the code.** Every
row the ticket has and the code does not carries `status: planned`, so it is in
the registry as data but not in generated output. That is what lets the first
generated `semconv.py` be a no-op swap.

These are findings for review, not resolved questions.

---

## 1. The model-parameter alias table does not exist in code

RIUS-917: "Keys the spec defines, including recognised provider spellings,
normalise to `gen_ai.request.*`. Everything else goes to `rius.request.<key>`."

`generation.py::_configure` writes **every** `model_parameters` key verbatim as
`gen_ai.request.<key>`. There is no alias table, no spec-key list, and no
`rius.request.` constant anywhere in either SDK. A caller passing
`max_tokens_to_sample` today gets `gen_ai.request.max_tokens_to_sample`, not
`gen_ai.request.max_tokens`.

`registry/model_parameters.yaml` is therefore **entirely `status: planned`**, and
its contents are the largest piece of invention in this proposal:

- The **spec list** is my reading of the GenAI conventions, not something I
  found written down in the repos. Needs review against the pinned semconv
  version.
- The **alias table** is likewise proposed, not derived. I listed the provider
  spellings I am confident about (`max_tokens_to_sample`,
  `max_completion_tokens`, the Vercel camelCase family, `stop`, `n`,
  `candidate_count`). It is certainly incomplete and possibly wrong in places.
- Direction of `n` → `choice_count` and `stop` → `stop_sequences` are the two I
  am least sure of.

**This table should not be treated as decided.** It is a placeholder shaped
correctly.

## 2. `rius.request.` prefix does not exist

Follows from (1). RIUS-917 says it joins `PENDING_IDENTITY_PREFIXES`. Neither
SDK has the constant. Registry: `RIUS_REQUEST_PREFIX`, `status: planned`, and a
`status: planned` entry in `allowlists.yaml` under `pending_identity.prefixes`.

## 3. Resource attributes have no semconv constants

RIUS-917 lists `service.name`, `telemetry.distro.name` and
`telemetry.distro.version` as Required identity rows. `semconv.py` defines only
`SERVICE_INSTANCE_ID`. The other three keys are set through the OTel SDK's own
resource constants, so they are real on the wire but absent from the parity
source. Registry: `status: planned` for all three.

`argus-core` does have `ServiceName`, plus `TelemetrySDKName/Ver/Lang` — which
are the OTel SDK attributes, **not** the distro attributes RIUS-917 asks for.
Two different things with similar names.

## 4. `gen_ai.agent.name` appears twice in the ticket with different levels

RIUS-917 lists it under **Resource** (Recommended, RIUS-953) and again under
**Tools, agent, retrieval** (Conditionally Required on AGENT spans, RIUS-954).
One key, two placements, two levels. The registry has one row
(`GEN_AI_AGENT_NAME`, CR, kinds `[AGENT]`) with the resource placement recorded
in its rationale, because the row schema has a single `level`.

**If a key can legitimately carry different levels at different placements, the
registry needs a `placements:` list instead of flat columns.** I did not build
that; flagging it.

Neither SDK emits it. `argus-core` has the constant and the sink already reads
it in both positions.

## 5. `gen_ai.data_source.id` does not exist anywhere

RIUS-917, RETRIEVER, CR. Not in any of the three repos. `status: planned`.
Related: `RETRIEVER` has no `gen_ai.operation.name` today; the ticket's
"all but CHAIN" requirement implies `retrieval`. Recorded as
`operation_by_kind.planned`.

## 6. "MCP" is used as a span kind in the ticket, and is not one

RIUS-917's Kinds column says `MCP` for `mcp.method.name`,
`mcp.protocol.version` and `mcp.result_type`. There is no MCP member of
`SpanKind` in any SDK; an MCP call is a `TOOL` span that carries
`mcp.method.name`. The registry keeps the ticket's spelling in the `kinds:`
column (so the table round-trips) and `registry/taxonomy.yaml` carries the
reconciliation note. Nothing generates an MCP enum member.

**Either the ticket's column should say `TOOL (MCP)` or the registry needs a
separate "span profile" concept.** Unresolved.

## 7. `rius.span.pending` category

RIUS-917 files it as **I** (identity). It does ride pending snapshots by
definition, but it is not in `PENDING_IDENTITY_ATTRIBUTES` — `pending.py` sets
it directly rather than allowlisting it. The registry keeps category `identity`
per the ticket, which means **a structural test generated from the category
column would wrongly expect it in the pending allowlist.** Worth a column
(`allowlisted: false`) before RIUS-933 generates tests from this.

## 8. `argus-core`'s Go semconv is a full release behind

Not a ticket/code disagreement, but it will bite the migration:

| argus-core has | the SDKs emit |
| -- | -- |
| `TracerName = "glassflow"` | `"rius"` |
| `GlassflowSpanPending = "glassflow.span.pending"` | `rius.span.pending` |
| `GenAISystem = "gen_ai.system"` | not emitted; `gen_ai.provider.name` |

It also carries keys the SDKs deliberately never emit but the **sink reads as
fallbacks**: `enduser.id`, `enduser.pseudo.id`, `gen_ai.conversation.id`,
`llm.*`, `OpenInferenceFirstTokenEvent`, `ai.prompt.tools`. Those are
**normalizer input**, a different concept from the canonical table, and the
generated `semconv.go` does **not** contain them.

**So `semconv.go` as generated today cannot replace argus-core's file.** It
replaces the canonical half. The source-family mapping tables RIUS-937 calls
for (OpenInference, OpenLLMetry, Vercel, legacy `gen_ai.system`) are the other
half and are **not** in this proposal — see "Deliberately left out" in the
README.

## 9. Small wording drift between the two SDKs

`semconv.py` on `GEN_AI_USAGE_CACHE_WRITE_INPUT_TOKENS` says "SDKs 0.12.x
emitted the pre-rename name"; `semconv.ts` says "no released version carries
the old name"; `argus-core` says "No released SDK emitted the old spelling".
The Python comment contradicts the other two.

The registry carries the **Python** wording, per the "follow the code, and
Python is the parity source" rule. **One of these is wrong and it changes
whether a ClickHouse coalesce can ever be dropped.** Someone who knows should
settle it.
