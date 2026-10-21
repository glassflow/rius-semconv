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
| `gen_ai.usage.audio.cache_read.input_tokens` | canonical | canonical | canonical | not in any recording |  |
| `gen_ai.usage.audio.input_tokens` | canonical | canonical | canonical | produced in openinference-js-langchain-openai, openinference-js-openai, openinference-langchain, openinference-langchain-openai, openinference-litellm, openinference-litellm-openai, openinference-llama-index, openinference-llama-index-openai, openinference-openai, vercel-ai-otel |  |
| `gen_ai.usage.audio.output_tokens` | canonical | canonical | canonical | produced in openinference-js-langchain-openai, openinference-js-openai, openinference-langchain, openinference-langchain-openai, openinference-litellm, openinference-litellm-openai, openinference-llama-index, openinference-llama-index-openai, openinference-openai |  |
| `gen_ai.usage.cache_read.input_tokens` | canonical | canonical | canonical | openllmetry, pydantic-ai, rius-python, rius-typescript, vercel-ai-otel |  |
| `gen_ai.usage.cache_write.input_tokens` | canonical | canonical | canonical | produced in laminar, openinference-anthropic, openinference-js-anthropic, openinference-litellm, openinference-litellm-openai, openllmetry |  |
| `gen_ai.usage.image.cache_read.input_tokens` | canonical | canonical | canonical | not in any recording |  |
| `gen_ai.usage.image.input_tokens` | canonical | canonical | canonical | not in any recording |  |
| `gen_ai.usage.image.output_tokens` | canonical | canonical | canonical | not in any recording |  |
| `gen_ai.usage.input_tokens` | canonical | canonical | canonical | laminar, openllmetry, pydantic-ai, rius-python, rius-typescript, vercel-ai-otel, vercel-ai-v5, vercel-ai-v6 |  |
| `gen_ai.usage.output_tokens` | canonical | canonical | canonical | laminar, openllmetry, pydantic-ai, rius-python, rius-typescript, vercel-ai-otel, vercel-ai-v5, vercel-ai-v6 |  |
| `gen_ai.usage.reasoning.output_tokens` | canonical | canonical | canonical | rius-python, rius-typescript |  |
| `gen_ai.usage.text.cache_read.input_tokens` | canonical | canonical | canonical | not in any recording |  |
| `gen_ai.usage.text.input_tokens` | canonical | canonical | canonical | not in any recording |  |
| `gen_ai.usage.text.output_tokens` | canonical | canonical | canonical | not in any recording |  |
| `rius.aggregated_usage.*` | canonical | canonical | canonical | produced in openinference-litellm-openai, vercel-ai-otel, vercel-ai-v5, vercel-ai-v6 | A whole agent run's usage, moved off gen_ai.usage.* by the TypeScript SDK on producers known to repeat it on each call's span. Never read as usage, so the run is not counted twice. |

## Mapped

| Key | python | typescript | sink | Recorded in | Why |
| -- | -- | -- | -- | -- | -- |
| `ai.usage.cachedInputTokens` | keeps | → `gen_ai.usage.cache_read.input_tokens` | → `gen_ai.usage.cache_read.input_tokens` | vercel-ai-v5, vercel-ai-v6 | v5's cache-read count, still written beside the detailed spelling by v6. Without it cached input was priced as uncached. |
| `ai.usage.inputTokenDetails.cacheReadTokens` | keeps | → `gen_ai.usage.cache_read.input_tokens` | → `gen_ai.usage.cache_read.input_tokens` | vercel-ai-v6 |  |
| `ai.usage.inputTokenDetails.cacheWriteTokens` | keeps | → `gen_ai.usage.cache_write.input_tokens` | → `gen_ai.usage.cache_write.input_tokens` | not in any recording |  |
| `ai.usage.inputTokens` | keeps | → `gen_ai.usage.input_tokens` | → `gen_ai.usage.input_tokens` | vercel-ai-v5, vercel-ai-v6 | Inclusive of the cached tokens, as the canonical key is. |
| `ai.usage.outputTokenDetails.reasoningTokens` | keeps | → `gen_ai.usage.reasoning.output_tokens` | → `gen_ai.usage.reasoning.output_tokens` | vercel-ai-otel, vercel-ai-v6 |  |
| `ai.usage.outputTokens` | keeps | → `gen_ai.usage.output_tokens` | → `gen_ai.usage.output_tokens` | vercel-ai-v5, vercel-ai-v6 |  |
| `ai.usage.reasoningTokens` | keeps | → `gen_ai.usage.reasoning.output_tokens` | → `gen_ai.usage.reasoning.output_tokens` | vercel-ai-v5, vercel-ai-v6 | v5's reasoning count, still written beside the detailed spelling by v6. |
| `ai.usage.tokens` | keeps | → `gen_ai.usage.input_tokens` | → `gen_ai.usage.input_tokens` | vercel-ai-v5, vercel-ai-v6 | An embedding call's input count (ai.embed, ai.embedMany and their doEmbed). |
| `gen_ai.usage.cache_creation.input_tokens` | → `gen_ai.usage.cache_write.input_tokens` | → `gen_ai.usage.cache_write.input_tokens` | → `gen_ai.usage.cache_write.input_tokens` | openllmetry | The cache-write count's name before the conventions renamed it. Current releases still send it (pydantic-ai, @ai-sdk/otel), and the backend prices cache writes from the canonical key alone. |
| `gen_ai.usage.cache_creation_input_tokens` | keeps | keeps | → `gen_ai.usage.cache_write.input_tokens` | laminar, openllmetry | OpenLLMetry's and Laminar's cache-write count (Anthropic's field name). |
| `gen_ai.usage.cache_read_input_tokens` | keeps | keeps | → `gen_ai.usage.cache_read.input_tokens` | laminar, openllmetry | OpenLLMetry's and Laminar's cache-read count (Anthropic's field name). |
| `gen_ai.usage.completion_tokens` | keeps | keeps | → `gen_ai.usage.output_tokens` | openllmetry | OpenLLMetry's output count before the GenAI rename (0.47 and earlier). |
| `gen_ai.usage.details.audio_cache_tokens` | → `gen_ai.usage.audio.cache_read.input_tokens` | → `gen_ai.usage.audio.cache_read.input_tokens` | → `gen_ai.usage.audio.cache_read.input_tokens` | not in any recording | pydantic-ai's Google cached audio split (cacheTokensDetails, modality AUDIO). A subset of the cache-read count, never added to it. A fallback for details.cache_audio_read_tokens, which wins. |
| `gen_ai.usage.details.audio_candidates_tokens` | → `gen_ai.usage.audio.output_tokens` | → `gen_ai.usage.audio.output_tokens` | → `gen_ai.usage.audio.output_tokens` | not in any recording | pydantic-ai's Google audio output split (candidatesTokensDetails, modality AUDIO). A subset of the output count, never added to it. A fallback for details.output_audio_tokens, which wins. |
| `gen_ai.usage.details.audio_prompt_tokens` | → `gen_ai.usage.audio.input_tokens` | → `gen_ai.usage.audio.input_tokens` | → `gen_ai.usage.audio.input_tokens` | not in any recording | pydantic-ai's Google audio input split (promptTokensDetails, modality AUDIO). A subset of the input count, never added to it. A fallback for details.input_audio_tokens, which wins. |
| `gen_ai.usage.details.audio_response_tokens` | → `gen_ai.usage.audio.output_tokens` | → `gen_ai.usage.audio.output_tokens` | → `gen_ai.usage.audio.output_tokens` | not in any recording | pydantic-ai's Google audio output split on its realtime path (the Gemini Live API's responseTokensDetails, modality AUDIO). A subset of the output count, never added to it. A fallback for details.output_audio_tokens, which wins. |
| `gen_ai.usage.details.cache_audio_read_tokens` | → `gen_ai.usage.audio.cache_read.input_tokens` | → `gen_ai.usage.audio.cache_read.input_tokens` | → `gen_ai.usage.audio.cache_read.input_tokens` | not in any recording | pydantic-ai's cached audio input count. A subset of the cache-read count, never added to it. Wins over details.audio_cache_tokens, which carries the same count on Gemini. |
| `gen_ai.usage.details.cache_read_tokens` | keeps | keeps | → `gen_ai.usage.cache_read.input_tokens` | pydantic-ai | pydantic-ai's backwards-compatible copy of the cache-read count, which it also writes under the canonical key. The sink maps it only as a fallback; the SDKs leave it, since the canonical key is always there. |
| `gen_ai.usage.details.cache_write_tokens` | keeps | keeps | → `gen_ai.usage.cache_write.input_tokens` | not in any recording | As cache_read_tokens, for cache writes. |
| `gen_ai.usage.details.image_cache_tokens` | → `gen_ai.usage.image.cache_read.input_tokens` | → `gen_ai.usage.image.cache_read.input_tokens` | → `gen_ai.usage.image.cache_read.input_tokens` | not in any recording | pydantic-ai's Google cached image split (cacheTokensDetails, modality IMAGE). A subset of the cache-read count, never added to it. |
| `gen_ai.usage.details.image_candidates_tokens` | → `gen_ai.usage.image.output_tokens` | → `gen_ai.usage.image.output_tokens` | → `gen_ai.usage.image.output_tokens` | not in any recording | pydantic-ai's Google image output split (candidatesTokensDetails, modality IMAGE). A subset of the output count, never added to it. |
| `gen_ai.usage.details.image_prompt_tokens` | → `gen_ai.usage.image.input_tokens` | → `gen_ai.usage.image.input_tokens` | → `gen_ai.usage.image.input_tokens` | not in any recording | pydantic-ai's Google image input split (promptTokensDetails, modality IMAGE). A subset of the input count, never added to it. |
| `gen_ai.usage.details.input_audio_tokens` | → `gen_ai.usage.audio.input_tokens` | → `gen_ai.usage.audio.input_tokens` | → `gen_ai.usage.audio.input_tokens` | not in any recording | pydantic-ai's audio input count. A subset of the input count, never added to it. On Gemini it is the audio prompt split plus the audio tool-use prompt split, so it wins over details.audio_prompt_tokens. OpenInference's and @ai-sdk/otel's audio input keys win over it. |
| `gen_ai.usage.details.output_audio_tokens` | → `gen_ai.usage.audio.output_tokens` | → `gen_ai.usage.audio.output_tokens` | → `gen_ai.usage.audio.output_tokens` | not in any recording | pydantic-ai's audio output count. A subset of the output count, never added to it. Wins over details.audio_candidates_tokens and details.audio_response_tokens, which carry the same count on Gemini. OpenInference's audio output key wins over it. |
| `gen_ai.usage.details.reasoning_tokens` | → `gen_ai.usage.reasoning.output_tokens` | → `gen_ai.usage.reasoning.output_tokens` | → `gen_ai.usage.reasoning.output_tokens` | pydantic-ai | pydantic-ai's OpenAI reasoning split. |
| `gen_ai.usage.details.thinking_tokens` | → `gen_ai.usage.reasoning.output_tokens` | → `gen_ai.usage.reasoning.output_tokens` | → `gen_ai.usage.reasoning.output_tokens` | not in any recording | pydantic-ai's Anthropic reasoning split. |
| `gen_ai.usage.details.thoughts_tokens` | → `gen_ai.usage.reasoning.output_tokens` | → `gen_ai.usage.reasoning.output_tokens` | → `gen_ai.usage.reasoning.output_tokens` | not in any recording | pydantic-ai's Google reasoning split. |
| `gen_ai.usage.input_token_details.audio_tokens` | → `gen_ai.usage.audio.input_tokens` | → `gen_ai.usage.audio.input_tokens` | → `gen_ai.usage.audio.input_tokens` | vercel-ai-otel | @ai-sdk/otel's flattening of a provider's input_token_details on a transcription span (OpenAI's gpt-4o-transcribe). A subset of the input count, never added to it. |
| `gen_ai.usage.prompt_tokens` | keeps | keeps | → `gen_ai.usage.input_tokens` | openllmetry | OpenLLMetry's input count before the GenAI rename (0.47 and earlier). |
| `gen_ai.usage.reasoning_tokens` | keeps | keeps | → `gen_ai.usage.reasoning.output_tokens` | openllmetry | OpenLLMetry's reasoning count. |
| `llm.token_count.completion` | → `gen_ai.usage.output_tokens` | → `gen_ai.usage.output_tokens` | → `gen_ai.usage.output_tokens` | openinference-anthropic, openinference-js-anthropic, openinference-js-langchain, openinference-js-langchain-openai, openinference-js-openai, openinference-langchain, openinference-langchain-openai, openinference-litellm, openinference-litellm-openai, openinference-llama-index, openinference-llama-index-openai, openinference-openai |  |
| `llm.token_count.completion_details.audio` | → `gen_ai.usage.audio.output_tokens` | → `gen_ai.usage.audio.output_tokens` | → `gen_ai.usage.audio.output_tokens` | openinference-js-langchain-openai, openinference-js-openai, openinference-langchain, openinference-langchain-openai, openinference-litellm, openinference-litellm-openai, openinference-llama-index, openinference-llama-index-openai, openinference-openai | A subset of the output count, never added to it. |
| `llm.token_count.completion_details.reasoning` | → `gen_ai.usage.reasoning.output_tokens` | → `gen_ai.usage.reasoning.output_tokens` | → `gen_ai.usage.reasoning.output_tokens` | openinference-js-langchain, openinference-js-langchain-openai, openinference-js-openai, openinference-langchain, openinference-langchain-openai, openinference-litellm, openinference-litellm-openai, openinference-llama-index, openinference-llama-index-openai, openinference-openai |  |
| `llm.token_count.prompt` | → `gen_ai.usage.input_tokens` | → `gen_ai.usage.input_tokens` | → `gen_ai.usage.input_tokens` | openinference-anthropic, openinference-js-anthropic, openinference-js-langchain, openinference-js-langchain-openai, openinference-js-openai, openinference-langchain, openinference-langchain-openai, openinference-litellm, openinference-litellm-openai, openinference-llama-index, openinference-llama-index-openai, openinference-openai | Copied, never summed with the cache counts: every bundled instrumentor already reports it inclusive of them. |
| `llm.token_count.prompt_details.audio` | → `gen_ai.usage.audio.input_tokens` | → `gen_ai.usage.audio.input_tokens` | → `gen_ai.usage.audio.input_tokens` | openinference-js-langchain-openai, openinference-js-openai, openinference-langchain, openinference-langchain-openai, openinference-litellm, openinference-litellm-openai, openinference-llama-index, openinference-llama-index-openai, openinference-openai | A subset of the input count, never added to it. |
| `llm.token_count.prompt_details.cache_read` | → `gen_ai.usage.cache_read.input_tokens` | → `gen_ai.usage.cache_read.input_tokens` | → `gen_ai.usage.cache_read.input_tokens` | openinference-anthropic, openinference-js-anthropic, openinference-js-langchain, openinference-js-langchain-openai, openinference-js-openai, openinference-langchain, openinference-langchain-openai, openinference-litellm, openinference-litellm-openai, openinference-llama-index, openinference-llama-index-openai, openinference-openai |  |
| `llm.token_count.prompt_details.cache_write` | → `gen_ai.usage.cache_write.input_tokens` | → `gen_ai.usage.cache_write.input_tokens` | → `gen_ai.usage.cache_write.input_tokens` | openinference-anthropic, openinference-js-anthropic, openinference-litellm, openinference-litellm-openai |  |
| `llm.usage.reasoning_tokens` | keeps | keeps | → `gen_ai.usage.reasoning.output_tokens` | openllmetry | OpenLLMetry's reasoning count in older releases. |

## Gap

| Key | python | typescript | sink | Recorded in | Why |
| -- | -- | -- | -- | -- | -- |
| `gen_ai.usage.input_token_details.text_tokens` | keeps | keeps | keeps | vercel-ai-otel | The text subset of a transcription span's input, beside input_token_details.audio_tokens. It belongs in gen_ai.usage.text.input_tokens, but no normalizer maps it yet, so the text split of the input is not attributed. |

## Ignored

| Key | python | typescript | sink | Recorded in | Why |
| -- | -- | -- | -- | -- | -- |
| `ai.response.usage` | keeps | keeps | keeps | vercel-ai-otel | @ai-sdk/otel's speech and transcription spans, with its usage option: the provider's usage object whole, as a JSON string, in whatever units the provider bills (tokens, seconds, characters). The integration also writes its numeric leaves on the same span as gen_ai.usage.<key>, which is what is read (input_tokens, output_tokens) or decided above, so parsing this would count the same usage twice. |
| `ai.usage.completionTokens` | keeps | keeps | keeps | vercel-ai-v5 | v5's output count on generateText and generateObject; as ai.usage.promptTokens. |
| `ai.usage.inputTokenDetails.noCacheTokens` | keeps | keeps | keeps | vercel-ai-otel, vercel-ai-v6 | The uncached remainder of ai.usage.inputTokens. The conventions record the inclusive input count and the cached part; this is their difference. |
| `ai.usage.outputTokenDetails.textTokens` | keeps | keeps | keeps | vercel-ai-otel, vercel-ai-v6 | The non-reasoning remainder of ai.usage.outputTokens; the conventions record the inclusive output count and the reasoning part. |
| `ai.usage.promptTokens` | keeps | keeps | keeps | vercel-ai-v5 | v5's input count on generateText and generateObject, left unread on purpose. On a model call the AI SDK writes the same value to gen_ai.usage.input_tokens itself. On the generateText wrapper v5 takes it from the LAST step's response, not the run's total (v5's streams and v6 report the total under ai.usage.inputTokens), so mapping it to rius.aggregated_usage.* would put a short total under a key that promises the whole run. |
| `ai.usage.totalTokens` | keeps | keeps | keeps | vercel-ai-v5, vercel-ai-v6 | A total; the conventions define none. |
| `gen_ai.aggregated_usage.*` | keeps | keeps | keeps | pydantic-ai | pydantic-ai's whole-run total on its agent span, next to each call's usage on the call's own span. Reading it as usage would count the run twice; it stays under its own name, which nothing reads. |
| `gen_ai.usage.details.audio_tokens` | keeps | keeps | keeps | pydantic-ai | pydantic-ai's OpenAI output audio count: its chat adapter copies completion_tokens_details whole, and its realtime adapter writes the output audio under this name. The name carries no direction, and pydantic-ai writes the same count as details.output_audio_tokens, which is mapped, so this copy stays. |
| `gen_ai.usage.details.audio_tool_use_prompt_tokens` | keeps | keeps | keeps | not in any recording | The audio part of Google's tool-use prompt, a second audio input split beside audio_prompt_tokens. pydantic-ai already adds it into details.input_audio_tokens, which is mapped, and a normalizer renames a count, never adds two, so it stays. |
| `gen_ai.usage.details.image_response_tokens` | keeps | keeps | keeps | not in any recording | The image output split on pydantic-ai's realtime path (the Gemini Live API's responseTokensDetails). Live output is text or audio, so no image count is expected there, and nothing reads one. |
| `gen_ai.usage.details.image_tool_use_prompt_tokens` | keeps | keeps | keeps | not in any recording | The image part of Google's tool-use prompt, a second image input split beside image_prompt_tokens. The image input key would be their sum, and a normalizer renames a count, never adds two, so it stays. |
| `gen_ai.usage.total_tokens` | keeps | keeps | keeps | openllmetry, vercel-ai-otel | Not a convention key: OpenLLMetry's total. No canonical key holds a total, so it stays on the span as an extra. |
| `llm.cost.total` | keeps | keeps | keeps | openinference-litellm, openinference-litellm-openai | Cost stays off the wire on purpose: the backend prices from the token counts with its own table, so a producer's figure is never trusted. |
| `llm.token_count.total` | keeps | keeps | keeps | openinference-anthropic, openinference-js-anthropic, openinference-js-langchain, openinference-js-langchain-openai, openinference-js-openai, openinference-langchain, openinference-langchain-openai, openinference-litellm, openinference-litellm-openai, openinference-llama-index, openinference-llama-index-openai, openinference-openai | The conventions define no total: they record input and output and leave the sum to the reader. The sink reads it for validation only. |
| `llm.usage.total_tokens` | keeps | keeps | keeps | laminar, openllmetry | OpenLLMetry's and Laminar's total, as gen_ai.usage.total_tokens. |
| `operation.cost` | keeps | keeps | keeps | pydantic-ai | pydantic-ai's own price for the call. Cost stays off the wire on purpose, as with llm.cost.total. |

## Not usage

| Key | python | typescript | sink | Recorded in | Why |
| -- | -- | -- | -- | -- | -- |
| `ai.response.avgOutputTokensPerSecond` | keeps | keeps | keeps | vercel-ai-v5, vercel-ai-v6 | A throughput figure, not a count. |
| `ai.settings.maxOutputTokens` | keeps | keeps | keeps | vercel-ai-v5, vercel-ai-v6 | A request parameter, mapped to gen_ai.request.max_tokens (which the AI SDK also writes itself on a model call). |
| `gen_ai.request.max_tokens` | keeps | keeps | keeps | openllmetry, pydantic-ai, rius-python, rius-typescript, vercel-ai-otel, vercel-ai-v5, vercel-ai-v6 | A request parameter (registry/model_parameters.yaml), not usage. |
| `metadata.ai.response.avgOutputTokensPerSecond` | keeps | keeps | keeps | not in any recording | @arizeai/openinference-vercel's metadata.* mirror of ai.response.avgOutputTokensPerSecond. No recording carries it: the TypeScript SDK no longer runs that transform. An app can still run the package's span processor itself on a provider the SDK bridges onto, and its spans then carry the mirror, so the entry stays. |
| `pydantic_ai.cache.*` | keeps | keeps | keeps | pydantic-ai | pydantic-ai's prompt-cache health diagnostics (the cached prefix a conversation established, hit ratio, misses), not provider usage. |
