# Where the consumers disagree

Checked 2026-09-24 against each consumer's `main`:

| Consumer | Commit | File |
| -- | -- | -- |
| `rius-sdk-python` | `ac1061a` | `src/rius/semconv.py` |
| `rius-sdk-typescript` | `16a3037` | `src/semconv.ts` |
| `argus-core` | `e3b2a3a` | `packages/argus-core/semconv/semconv.go` |

`python tools/check_parity.py --cross` reproduces the value-level findings.
The registry encodes every value-level divergence with `shipped_in` and
`divergence`, so parity passes for all three consumers while the
divergences stay visible.

## Python vs TypeScript

### Values (what a consumer can observe)

1. **`CONTENT_ATTRIBUTES` contains `llm.invocation_parameters` in Python
   only.** Python treats the whole OpenInference request-parameters bag as
   content, reasoning that normalization runs before masking and has already
   promoted every member it recognises. TypeScript keeps the bag and redacts
   only its `tools` / `functions` members in `masking.ts`. The same span
   therefore exports different content from the two SDKs when content
   capture is off. This is the **only** value-level difference: every other
   constant, allowlist, table and the parameter-spelling table are equal.

### Code and prose (outside the registry, listed for the swap)

2. **`kind_attributes` / `kindAttributes` have different signatures.**
   Python's takes `data_source_id`, `top_k`, `agent_name`, `agent_id`,
   `agent_version`, `executing_agent_name`, `tool_call_id` and `tool_type`;
   TypeScript's takes only `toolName`, and `spans.ts` sets the rest from
   the span options. Logic, so not generated, but it is where "both SDKs stamp the
   same identity at creation" is actually decided.
3. **Python has `set_span_kind`; TypeScript has no counterpart.**
4. **The `cache_write` comment.** Python says "SDKs 0.12.x emitted the
   pre-rename name"; TypeScript and argus-core say no released version did.
   Git history settles it for TypeScript and argus-core: the commits adding
   the cache fields and renaming them ship in exactly the same tags. The
   registry carries the corrected wording, so the swap fixes Python's.
5. **TypeScript has a stray doc comment.** The JSDoc for
   `GEN_AI_TOOL_DEFINITIONS` sits above `GEN_AI_AGENT_VERSION`'s, and the
   constant itself has none. The swap fixes it.
6. **Python's sampling-parameter comment is stale.** It says the SDK's own
   API takes no sampling parameters, which stopped being true when
   `GEN_AI_REQUEST_PARAMETERS` landed. The registry uses TypeScript's
   up-to-date framing.
7. **`SERVICE_VERSION` in TypeScript aliases `ATTR_SERVICE_VERSION`** from
   `@opentelemetry/semantic-conventions` instead of restating the literal.
   The registry keeps that choice (`ts_alias`).

## argus-core

8. **27 canonical keys are missing from argus-core**, and arrive when it
   vendors the generated file: `ChainSpanName`, `ErrorTypeToolError`,
   `ExceptionEvent`, `ExceptionType`, `GenAIAgentID`, `GenAIAgentVersion`,
   `GenAIDataSourceID`, `GenAIOutputType`, `GenAIRequestReasoningLevel`,
   `GenAIRequestStopSequences`, `GenAIResponseID`,
   `GenAIResponseTimeToFirstChunk`, `GenAIRetrievalDocuments`,
   `GenAIRetrievalTopK`, `GenAIToolCallID`, `GenAIToolName`, `GenAIToolType`,
   `MCPMethodName`, `MCPMethodToolsCall`, `MCPProtocolVersion`,
   `MCPResultType`, `RiusMainAgentDescription`, `RiusMainAgentID`,
   `RiusMainAgentVersion`, `RiusRequestPrefix`, `ServiceVersion`,
   `WorkspaceRoute`.
9. **The 43 constants argus-core shares with the registry all agree**, in
   name and value. No renames are needed; the registry adopts argus-core's
   two nonderived names (`OpenInferenceSpanKind`, and the singular
   `GenAIResponseFinishReason`) with `go:` overrides.
10. **28 argus-core constants are not canonical** and stay hand-written:
    21 normalizer inputs, 3 legacy spellings, 1 dynamic key, and 3
    OpenTelemetry SDK resource keys (`TelemetrySDK*`) that nothing in
    argus-core references. See `tools/go_reference_only.yaml` and the
    README's "Go" section.
11. **The file's header is out of date.** It names `glassflow-python` as the
    source of truth and says the SDK emits `gen_ai.system`, which it no
    longer does. The swap replaces that header.

## Registry decisions taken while levelling

- **Resource attributes carry no category** (the linter enforces it). The
  four categories describe a span's lifecycle, and at resource scope every
  one of them is trivially true.
- **`mcp.result_type` stays `identity`, with a `not_pending` reason**: it is
  set when an interim round ends, so a snapshot taken at span start never
  has it. It could equally be reclassified as `metadata`; either is
  consistent with the SDKs' behaviour, since neither lists it in the pending
  allowlist.
- **`telemetry.distro.name` / `.version` stay `planned`**: both SDKs set
  them as inline literals, and no semconv file has a constant for them.
