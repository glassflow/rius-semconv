<!-- Generated from registry/usage_keys.yaml and the recordings under
     fixtures/ by `python -m generators.generate`. Do not edit. -->

# Usage keys

Every token, usage and cost key an instrumentor sends, the decision recorded
for it, and what each normalizer does with it: maps it (→ the canonical
key), keeps it on the span, or treats it as canonical. *Recorded in* lists
the families whose raw spans carry the key; a key that only appears after
normalization lists the families whose expected result carries it
(*produced in*).

`tools/check_usage_keys.py` fails CI on a recorded usage key with no
decision, and checks each normalizer against the expected results of the
families it produced them for.

## Canonical

| Key | python | typescript | sink | Recorded in | Why |
| -- | -- | -- | -- | -- | -- |
| `gen_ai.usage.cache_read.input_tokens` | canonical | canonical | canonical | openllmetry, pydantic-ai, rius-python, rius-typescript, vercel-ai-otel |  |
| `gen_ai.usage.cache_write.input_tokens` | canonical | canonical | canonical | produced in laminar, openinference-anthropic, openinference-js-anthropic, openinference-litellm, openinference-litellm-openai, openllmetry |  |
| `gen_ai.usage.input_tokens` | canonical | canonical | canonical | laminar, openllmetry, pydantic-ai, rius-python, rius-typescript, vercel-ai-otel, vercel-ai-v5 |  |
| `gen_ai.usage.output_tokens` | canonical | canonical | canonical | laminar, openllmetry, pydantic-ai, rius-python, rius-typescript, vercel-ai-otel, vercel-ai-v5 |  |
| `gen_ai.usage.reasoning.output_tokens` | canonical | canonical | canonical | rius-python, rius-typescript |  |
| `rius.aggregated_usage.*` | canonical | canonical | canonical | produced in openinference-litellm-openai, vercel-ai-otel | A whole agent run's usage, moved off gen_ai.usage.* by the TypeScript SDK on producers known to repeat it on each call's span. Never read as usage, so the run is not counted twice. |

## Mapped

| Key | python | typescript | sink | Recorded in | Why |
| -- | -- | -- | -- | -- | -- |
| `gen_ai.usage.cache_creation.input_tokens` | → `gen_ai.usage.cache_write.input_tokens` | → `gen_ai.usage.cache_write.input_tokens` | → `gen_ai.usage.cache_write.input_tokens` | openllmetry | The cache-write count's name before the conventions renamed it. Current releases still send it (pydantic-ai, @ai-sdk/otel), and the backend prices cache writes from the canonical key alone. |
| `gen_ai.usage.cache_creation_input_tokens` | keeps | keeps | → `gen_ai.usage.cache_write.input_tokens` | laminar, openllmetry | OpenLLMetry's and Laminar's cache-write count (Anthropic's field name). |
| `gen_ai.usage.cache_read_input_tokens` | keeps | keeps | → `gen_ai.usage.cache_read.input_tokens` | laminar, openllmetry | OpenLLMetry's and Laminar's cache-read count (Anthropic's field name). |
| `gen_ai.usage.completion_tokens` | keeps | keeps | → `gen_ai.usage.output_tokens` | openllmetry | OpenLLMetry's output count before the GenAI rename (0.47 and earlier). |
| `gen_ai.usage.details.cache_read_tokens` | keeps | keeps | → `gen_ai.usage.cache_read.input_tokens` | pydantic-ai | pydantic-ai's backwards-compatible copy of the cache-read count, which it also writes under the canonical key. The sink maps it only as a fallback; the SDKs leave it, since the canonical key is always there. |
| `gen_ai.usage.details.cache_write_tokens` | keeps | keeps | → `gen_ai.usage.cache_write.input_tokens` | not in any recording | As cache_read_tokens, for cache writes. |
| `gen_ai.usage.details.reasoning_tokens` | → `gen_ai.usage.reasoning.output_tokens` | → `gen_ai.usage.reasoning.output_tokens` | → `gen_ai.usage.reasoning.output_tokens` | pydantic-ai | pydantic-ai's OpenAI reasoning split. |
| `gen_ai.usage.details.thinking_tokens` | → `gen_ai.usage.reasoning.output_tokens` | → `gen_ai.usage.reasoning.output_tokens` | → `gen_ai.usage.reasoning.output_tokens` | not in any recording | pydantic-ai's Anthropic reasoning split. |
| `gen_ai.usage.details.thoughts_tokens` | → `gen_ai.usage.reasoning.output_tokens` | → `gen_ai.usage.reasoning.output_tokens` | → `gen_ai.usage.reasoning.output_tokens` | not in any recording | pydantic-ai's Google reasoning split. |
| `gen_ai.usage.prompt_tokens` | keeps | keeps | → `gen_ai.usage.input_tokens` | openllmetry | OpenLLMetry's input count before the GenAI rename (0.47 and earlier). |
| `gen_ai.usage.reasoning_tokens` | keeps | keeps | → `gen_ai.usage.reasoning.output_tokens` | openllmetry | OpenLLMetry's reasoning count. |
| `llm.token_count.completion` | → `gen_ai.usage.output_tokens` | → `gen_ai.usage.output_tokens` | → `gen_ai.usage.output_tokens` | openinference-anthropic, openinference-js-anthropic, openinference-js-langchain, openinference-js-langchain-openai, openinference-js-openai, openinference-langchain, openinference-langchain-openai, openinference-litellm, openinference-litellm-openai, openinference-llama-index, openinference-openai |  |
| `llm.token_count.completion_details.reasoning` | → `gen_ai.usage.reasoning.output_tokens` | → `gen_ai.usage.reasoning.output_tokens` | → `gen_ai.usage.reasoning.output_tokens` | openinference-js-langchain, openinference-js-langchain-openai, openinference-js-openai, openinference-langchain, openinference-langchain-openai, openinference-litellm, openinference-litellm-openai, openinference-llama-index, openinference-openai |  |
| `llm.token_count.prompt` | → `gen_ai.usage.input_tokens` | → `gen_ai.usage.input_tokens` | → `gen_ai.usage.input_tokens` | openinference-anthropic, openinference-js-anthropic, openinference-js-langchain, openinference-js-langchain-openai, openinference-js-openai, openinference-langchain, openinference-langchain-openai, openinference-litellm, openinference-litellm-openai, openinference-llama-index, openinference-openai | Copied, never summed with the cache counts: every bundled instrumentor already reports it inclusive of them. |
| `llm.token_count.prompt_details.cache_read` | → `gen_ai.usage.cache_read.input_tokens` | → `gen_ai.usage.cache_read.input_tokens` | → `gen_ai.usage.cache_read.input_tokens` | openinference-anthropic, openinference-js-anthropic, openinference-js-langchain, openinference-js-langchain-openai, openinference-js-openai, openinference-langchain, openinference-langchain-openai, openinference-litellm, openinference-litellm-openai, openinference-llama-index, openinference-openai |  |
| `llm.token_count.prompt_details.cache_write` | → `gen_ai.usage.cache_write.input_tokens` | → `gen_ai.usage.cache_write.input_tokens` | → `gen_ai.usage.cache_write.input_tokens` | openinference-anthropic, openinference-js-anthropic, openinference-litellm, openinference-litellm-openai |  |
| `llm.usage.reasoning_tokens` | keeps | keeps | → `gen_ai.usage.reasoning.output_tokens` | openllmetry | OpenLLMetry's reasoning count in older releases. |

## Gap

| Key | python | typescript | sink | Recorded in | Why |
| -- | -- | -- | -- | -- | -- |
| `ai.usage.cachedInputTokens` | keeps | keeps | keeps | vercel-ai-v5 | The cache-read count of a v5 stream. The AI SDK writes no gen_ai.usage.* counterpart and no normalizer maps it, so cached input is priced as uncached input. |
| `ai.usage.reasoningTokens` | keeps | keeps | keeps | vercel-ai-v5 | The reasoning count of a v5 stream. No gen_ai.usage.* counterpart and no normalizer maps it, so it reaches no canonical key. |
| `ai.usage.tokens` | keeps | keeps | keeps | vercel-ai-v5 | An embedding call's token count (ai.embed, ai.embed.doEmbed). No gen_ai.usage.* counterpart and no normalizer maps it, so embedding calls carry no usage at all. |

## Ignored

| Key | python | typescript | sink | Recorded in | Why |
| -- | -- | -- | -- | -- | -- |
| `ai.usage.completionTokens` | keeps | keeps | keeps | vercel-ai-v5 | v5's output count; as ai.usage.promptTokens. |
| `ai.usage.inputTokens` | keeps | keeps | keeps | vercel-ai-v5 | The v5 streaming spelling of ai.usage.promptTokens; as that key. |
| `ai.usage.outputTokens` | keeps | keeps | keeps | vercel-ai-v5 | The v5 streaming spelling of ai.usage.completionTokens; as that key. |
| `ai.usage.promptTokens` | keeps | keeps | keeps | vercel-ai-v5 | v5's input count. On a doGenerate/doStream span the AI SDK writes the same value to gen_ai.usage.input_tokens; on the outer generateText / streamText span it is the call's total again, which must not be counted a second time. |
| `ai.usage.totalTokens` | keeps | keeps | keeps | vercel-ai-v5 | A total; the conventions define none. |
| `gen_ai.aggregated_usage.*` | keeps | keeps | keeps | pydantic-ai | pydantic-ai's whole-run total on its agent span, next to each call's usage on the call's own span. Reading it as usage would count the run twice; it stays under its own name, which nothing reads. |
| `gen_ai.usage.details.audio_tokens` | keeps | keeps | keeps | pydantic-ai | No canonical key; modality splits are not priced separately. |
| `gen_ai.usage.total_tokens` | keeps | keeps | keeps | openllmetry | Not a convention key: OpenLLMetry's total. No canonical key holds a total, so it stays on the span as an extra. |
| `llm.cost.total` | keeps | keeps | keeps | openinference-litellm, openinference-litellm-openai | Cost stays off the wire on purpose: the backend prices from the token counts with its own table, so a producer's figure is never trusted. |
| `llm.token_count.completion_details.audio` | keeps | keeps | keeps | openinference-js-langchain-openai, openinference-js-openai, openinference-langchain, openinference-langchain-openai, openinference-litellm, openinference-litellm-openai, openinference-llama-index, openinference-openai | No canonical key; modality splits are not priced separately. |
| `llm.token_count.prompt_details.audio` | keeps | keeps | keeps | openinference-js-langchain-openai, openinference-js-openai, openinference-langchain, openinference-langchain-openai, openinference-litellm, openinference-litellm-openai, openinference-llama-index, openinference-openai | No canonical key; modality splits are not priced separately. |
| `llm.token_count.total` | keeps | keeps | keeps | openinference-anthropic, openinference-js-anthropic, openinference-js-langchain, openinference-js-langchain-openai, openinference-js-openai, openinference-langchain, openinference-langchain-openai, openinference-litellm, openinference-litellm-openai, openinference-llama-index, openinference-openai | The conventions define no total: they record input and output and leave the sum to the reader. The sink reads it for validation only. |
| `llm.usage.total_tokens` | keeps | keeps | keeps | laminar, openllmetry | OpenLLMetry's and Laminar's total, as gen_ai.usage.total_tokens. |
| `operation.cost` | keeps | keeps | keeps | pydantic-ai | pydantic-ai's own price for the call. Cost stays off the wire on purpose, as with llm.cost.total. |

## Not usage

| Key | python | typescript | sink | Recorded in | Why |
| -- | -- | -- | -- | -- | -- |
| `ai.response.avgOutputTokensPerSecond` | keeps | keeps | keeps | vercel-ai-v5 | A throughput figure, not a count. |
| `ai.settings.maxOutputTokens` | keeps | keeps | keeps | vercel-ai-v5 | A request parameter. The AI SDK also writes it as gen_ai.request.max_tokens. |
| `gen_ai.request.max_tokens` | keeps | keeps | keeps | openllmetry, pydantic-ai, rius-python, rius-typescript, vercel-ai-otel, vercel-ai-v5 | A request parameter (registry/model_parameters.yaml), not usage. |
| `metadata.ai.response.avgOutputTokensPerSecond` | keeps | keeps | keeps | produced in vercel-ai-v5 | @arizeai/openinference-vercel's metadata.* mirror of ai.response.avgOutputTokensPerSecond. |
| `pydantic_ai.cache.*` | keeps | keeps | keeps | pydantic-ai | pydantic-ai's prompt-cache health diagnostics (the cached prefix a conversation established, hit ratio, misses), not provider usage. |
