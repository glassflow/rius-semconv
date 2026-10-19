<!-- Generated from registry/media_parts.yaml by `python -m generators.generate`.
     Do not edit. -->

# Media parts

After normalization a media part is a `blob` (inline bytes, always stripped of
`content`), a `uri` or a `file`. The modality is one of `image`, `video`, `audio`, `document`,
taken from the MIME type when known (`from_mime`), else from the provider's
part kind. A `blob` carries a `stripped_reason`:

- `not_captured`: Our default policy removed the inline bytes.
- `redacted_upstream`: The instrumentor dropped or replaced the payload before we saw it (OpenInference \_\_REDACTED\_\_, a data URL with no bytes, an image with no url).

*Fixtures* lists the recorded scenarios (`<family>/<scenario>`) that prove the
row; a row with none says why in *Why*.

## Raw payloads

**Source rule.** Normalized message parts come only from message keys: gen_ai.input.messages, gen_ai.output.messages and gen_ai.system_instructions, or the flattened instrumentor message keys each normalizer already maps (OpenInference llm.input_messages.\* and llm.output_messages.\*, OpenLLMetry gen_ai.prompt.\* and gen_ai.completion.\*, Vercel ai.prompt.messages). Raw request and response payloads are never mined to rebuild parts.

Message keys (a key ending in `.` is a prefix): `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`, `llm.input_messages.`, `llm.output_messages.`, `gen_ai.prompt.`, `gen_ai.completion.`, `ai.prompt.messages`.

Raw payloads, never mined for parts: `input.value`, `output.value`, `lmnr.span.input`, `lmnr.span.output`, `ai.prompt`, `pydantic_ai.all_messages`, `InputValue`, `OutputValue`.

**Strip rule.** Each media token (found by the detection rules below) is replaced in place. Every other byte of the string stays identical: normalizers must not parse and re-serialize the JSON. Byte equality across the Python SDK, the TypeScript SDK and the Go sink depends on this. Message parts in gen_ai.\*.messages keep the stripped blob part shape instead; the replacement string is only for raw payloads.

**Scope.** The strip applies to every string value, and to every element of a string-array value, of the span attributes, the span event attributes, the span link attributes, and the resource and scope attributes of the recording. The sink applies the same rules to its stored columns InputValue, OutputValue, InputMessages and OutputMessages and to the values of SpanAttributes. This is what tools/check_fixtures.py scans.

**Order.** A normalizer first builds parts from the message keys (the source rule). Stripping runs last, over every string attribute in scope, including the message-key attributes it keeps and the gen_ai.\*.messages it produced. A stripped blob part carries no content, so nothing in it matches; a text part holding a data URL gets rule (b) in place.

**JSON candidates.** A string value is a JSON candidate when, after trimming leading space, tab, newline and carriage return (ASCII only: U+00A0 and other Unicode spaces are not trimmed), it starts with `{` or `[`. A candidate parses when the whole string is one RFC 8259 JSON value, with only those four whitespace characters around it (no NaN, Infinity, comments or trailing commas; duplicate keys are allowed, and the last one counts). When it parses, rules (d), (e) and (b) apply to the values inside it; a string value inside it that is itself a JSON candidate is processed by the same rules, recursively, at its escaped location, its own document starting with no parent key. When it does not parse (a truncated payload, say), only rule (b) applies, to the string as it is (for a string inside JSON, to its unescaped value). A string that is not a candidate gets rule (b) only. Object keys are never matched.

**Precedence.** Values are visited in document order. At each value rule (d) is tried, then (e), then (b), and the first that matches wins. A value inside a replaced token is never visited: once (e) replaces a string, (b) does not look inside it, and nothing inside a replaced Buffer object is looked at. An array element inherits the parent key of its array, so `{"audio":[{"data":"..."}]}` matches (e) through the parent key audio; in the same way, the enclosing object rule (d) takes its mime type from is the nearest object holding the Buffer, directly or through arrays. A string that is already a replacement (it starts with `[stripped ` and ends with ` bytes]`) is never an (e) token, so stripping a stripped string changes nothing: the sink re-strips what an SDK already stripped and gets the same bytes.

**Spans.** Every span is on the original text; nothing is re-serialized. (d) The object token, from its `{` to its matching `}`, is replaced by the replacement as a JSON string literal, quotes included. (e) The string literal, quotes included, is replaced by the replacement as a JSON string literal, quotes included. (b) In a JSON string, only the URL's characters are replaced: the replacement goes inside the existing quotes, with no quotes added. (b) In a string that is not JSON (or did not parse), the URL's characters are replaced by the replacement, with no quotes. Rules (b) and (e) read a JSON string's unescaped value, so a span starts at the first raw character of its first character and ends after the last raw character of its last, escapes included (`data:image\/png` is read as `data:image/png`). Text written into a JSON string is escaped for its level with the minimal escapes JSON.stringify writes, and no others: `\"` for a quote, `\\` for a backslash, `\b` `\f` `\n` `\r` `\t`, `\u00xx` (lowercase hex) for any other control character, `\udxxx` for a lone surrogate. In a JSON string nested in a JSON string, the inner replacement is escaped once per level, and every byte outside the replaced tokens is kept as it was, including escapes the re-encoder would not write (`\u0022`, `\/`).

**Byte size.** Rule (e) computes it on the string's unescaped value, and rule (b) on its base64 run, the same way. Remove space, tab, newline and carriage return. When what is left is not valid base64, byte_size is unknown. Valid means: every character before the padding is from one alphabet, `A-Z a-z 0-9 + /` or `A-Z a-z 0-9 - _` (never `+` or `/` together with `-` or `_`); the padding is at most two `=`, only at the end; and the length, padding counted, is a multiple of 4 (so unpadded base64 is not valid). For valid base64, byte_size is length times 3 / 4, minus the number of `=`. Rule (d) takes the length of its data array.

**Regex dialect.** The pattern of rule (b) uses only constructs Python re, JavaScript RegExp and Go RE2 read the same way: literal characters, character classes with explicit ASCII members and ranges, the escapes `\t` `\n` `\f` `\r`, groups, and the quantifiers `*` and `{m,n}`. No `\s`, `\d`, `\w`, `\b`, lookaround, backreference or inline flag.

**Reference.** generators/media_parts.py strip_raw_payload(raw, text) is the reference implementation: the one function a normalizer author reproduces. It returns the stripped string; strip(raw, text) also returns the tokens it replaced (rule, mime, byte_size), in document order. The golden examples below are its tests, and every normalizer's.

**Replacement.** The text `[stripped <mime> <byte_size> bytes]`, with `unknown` for a mime type or size that is not known: `[stripped image/png 67 bytes]`, `[stripped unknown unknown bytes]`. Rules (d) and (e) write it as a JSON string literal, quotes included; rule (b) writes the bare text, inside the quotes already there in a JSON string.

A data URL inside other text: only the token is replaced, so `see data:image/png;base64,iVBORw0KGgo= here` becomes `see [stripped image/png 8 bytes] here`.

| Token | Replaced | Mime | Byte size |
| -- | -- | -- | -- |
| A data URL (rule b), anywhere in a string | The URL characters alone, from data: to the end of the base64 run, with no quotes added. The text around it stays byte-identical; a string that is only the data URL becomes the replacement text. | The URL's media type; unknown when it names none. | The base64 run's size, per byte_size; unknown when the run is not valid base64. |
| A base64 string value (rule e) | The string literal, quotes included, by the replacement as a JSON string literal. | A sibling media_type, mediaType, mime_type or mimeType; else image/&lt;output_format&gt;; else audio/&lt;format&gt; under input_audio or audio; else unknown. | The unescaped value's size, per byte_size; unknown when it is not valid base64. |
| A Buffer object (rule d) | The whole object token, from { to its matching }, by the replacement as a JSON string literal. | The enclosing object's media_type, mediaType, mime_type or mimeType; else unknown. | The length of the data array. |

**Detection rules.** The normalizers strip, and tools/check_fixtures.py refuses
in an expected result, every token these find (in a string holding JSON too):

| Rule | Name | Matches | Parameters |
| -- | -- | -- | -- |
| (b) | data URL | A data:&lt;mime&gt;;base64,&lt;base64&gt; token anywhere in a string: the pattern finds each one, group 1 the mime type (empty when none), group 2 the base64 run (standard or URL-safe). A whole-string data URL is the special case. | pattern: `data:([^;,\t\n\f\r "]*);base64,([A-Za-z0-9+/_-]*={0,2})` |
| (d) | Buffer object | An object {"type": "Buffer", "data": [...]} whose data is a non-empty array. | type: `Buffer`; array_key: `data`; mime_keys: `media_type`, `mediaType`, `mime_type`, `mimeType` |
| (e) | keyed base64 string | A non-empty string under one of the keys, when its object has one of the sibling keys, or its object's parent key is one of the parent keys, or its object is a source with type base64. | keys: `data`, `b64_json`, `result`; sibling_keys: `media_type`, `mediaType`, `mime_type`, `mimeType`, `format`, `output_format`; parent_keys: `input_audio`, `audio`, `inline_data`, `inlineData`; source_key: `source`; source_type: `base64`; mime_keys: `media_type`, `mediaType`, `mime_type`, `mimeType`; mime_formats: `output_format` gives `image/<value>`, `format` gives `audio/<value>` under `input_audio`, `audio` |

### Golden examples

Each normalizer must turn each input into exactly its output (`strip_raw_payload`
in generators/media_parts.py does). Tokens are listed in document order.

#### `anthropic_base64_image_pretty_printed`

Rule (e) through a base64 source. The pretty-printed spacing survives, so nothing was re-serialized.

Input:

```text
{
  "model": "claude-sonnet-4-5",
  "messages": [
    {
      "role": "user",
      "content": [
        { "type": "image",  "source": { "type": "base64", "media_type": "image/png", "data": "iVBORw0KGgo=" } },
        { "type": "text", "text": "What is in this image?" }
      ]
    }
  ]
}
```

Output:

```text
{
  "model": "claude-sonnet-4-5",
  "messages": [
    {
      "role": "user",
      "content": [
        { "type": "image",  "source": { "type": "base64", "media_type": "image/png", "data": "[stripped image/png 8 bytes]" } },
        { "type": "text", "text": "What is in this image?" }
      ]
    }
  ]
}
```

Tokens: (e) image/png, 8 bytes.

#### `openai_input_audio_wav`

Rule (e) through the parent key input_audio; the mime type is audio/&lt;format&gt;.

Input:

```text
{"messages":[{"role":"user","content":[{"type":"input_audio","input_audio":{"data":"UklGRiQAAABXQVZF","format":"wav"}}]}]}
```

Output:

```text
{"messages":[{"role":"user","content":[{"type":"input_audio","input_audio":{"data":"[stripped audio/wav 12 bytes]","format":"wav"}}]}]}
```

Tokens: (e) audio/wav, 12 bytes.

#### `vercel_buffer_in_ai_prompt`

Rule (d). The whole Buffer object becomes a string literal; the mime type is the enclosing object's mediaType, byte_size the array length.

Input:

```text
{"messages":[{"role":"user","content":[{"type":"text","text":"What is in this image?"},{"type":"file","data":{"type":"Buffer","data":[137,80,78,71]},"mediaType":"image/png"}]}]}
```

Output:

```text
{"messages":[{"role":"user","content":[{"type":"text","text":"What is in this image?"},{"type":"file","data":"[stripped image/png 4 bytes]","mediaType":"image/png"}]}]}
```

Tokens: (d) image/png, 4 bytes.

#### `data_url_in_prose`

Rule (b) in a string that is not JSON. No quotes are added.

Input:

```text
Describe data:image/png;base64,iVBORw0KGgo= in one line.
```

Output:

```text
Describe [stripped image/png 8 bytes] in one line.
```

Tokens: (b) image/png, 8 bytes.

#### `data_url_in_json_string`

Rule (b) inside JSON string values. The replacement goes inside the quotes already there, and the text around the URL stays.

Input:

```text
{"messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,/9j/4AAQSkZJRg=="}},{"type":"text","text":"compare with data:image/png;base64,iVBORw0KGgo= please"}]}]}
```

Output:

```text
{"messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"[stripped image/jpeg 10 bytes]"}},{"type":"text","text":"compare with [stripped image/png 8 bytes] please"}]}]}
```

Tokens: (b) image/jpeg, 10 bytes, (b) image/png, 8 bytes.

#### `keyed_data_url_rule_e_wins`

The string under data is also a data URL. Rule (e) is tried first and wins, so the whole literal is replaced; the data URL is not valid base64, so byte_size is unknown.

Input:

```text
{"data":"data:image/png;base64,iVBORw0KGgo=","mediaType":"image/png"}
```

Output:

```text
{"data":"[stripped image/png unknown bytes]","mediaType":"image/png"}
```

Tokens: (e) image/png, unknown bytes.

#### `truncated_json_rule_b_only`

The payload was cut off, so it does not parse. Only rule (b) applies, to the raw text; the base64 source is left alone.

Input:

```text
{"messages":[{"role":"user","content":[{"type":"image","source":{"type":"base64","media_type":"image/png","data":"iVBORw0KGgo="}},{"type":"image_url","image_url":{"url":"data:image/png;base64,iVBORw0KGgo="}}
```

Output:

```text
{"messages":[{"role":"user","content":[{"type":"image","source":{"type":"base64","media_type":"image/png","data":"iVBORw0KGgo="}},{"type":"image_url","image_url":{"url":"[stripped image/png 8 bytes]"}}
```

Tokens: (b) image/png, 8 bytes.

#### `json_nested_in_a_json_string`

A tool result holds JSON as a string. It is a JSON candidate, so rule (e) applies inside it, and the replacement literal is written escaped for that level.

Input:

```text
{"messages":[{"role":"tool","content":"{\"source\":{\"type\":\"base64\",\"media_type\":\"image/png\",\"data\":\"iVBORw0KGgo=\"}}"}]}
```

Output:

```text
{"messages":[{"role":"tool","content":"{\"source\":{\"type\":\"base64\",\"media_type\":\"image/png\",\"data\":\"[stripped image/png 8 bytes]\"}}"}]}
```

Tokens: (e) image/png, 8 bytes.

#### `nested_json_with_escapes_a_reencoder_would_not_write`

The outer string escapes its quotes as \u0022 and its slashes as \/. Only the tokens change; the replacement is written with the minimal escapes, and every other byte, \u0022 and \/ included, is kept.

Input:

```text
{"content":"{\u0022image\u0022:{\u0022url\u0022:\u0022data:image\/png;base64,iVBORw0KGgo=\u0022},\u0022source\u0022:{\u0022type\u0022:\u0022base64\u0022,\u0022data\u0022:\u0022iVBORw0KGgo=\u0022}}"}
```

Output:

```text
{"content":"{\u0022image\u0022:{\u0022url\u0022:\u0022[stripped image/png 8 bytes]\u0022},\u0022source\u0022:{\u0022type\u0022:\u0022base64\u0022,\u0022data\u0022:\"[stripped unknown 8 bytes]\"}}"}
```

Tokens: (b) image/png, 8 bytes, (e) unknown, 8 bytes.

#### `invalid_base64_under_keyed_data`

Rule (e) still replaces the string; it is not valid base64, so byte_size is unknown.

Input:

```text
{"input_audio":{"data":"not base64!","format":"wav"}}
```

Output:

```text
{"input_audio":{"data":"[stripped audio/wav unknown bytes]","format":"wav"}}
```

Tokens: (e) audio/wav, unknown bytes.

#### `unicode_space_before_brace_is_not_json`

U+00A0 is not trimmed, so the string is not a JSON candidate. Only rule (b) applies; the base64 source stays.

Input:

```text
 {"source":{"type":"base64","media_type":"image/png","data":"iVBORw0KGgo="},"url":"data:image/png;base64,iVBORw0KGgo="}
```

Output:

```text
 {"source":{"type":"base64","media_type":"image/png","data":"iVBORw0KGgo="},"url":"[stripped image/png 8 bytes]"}
```

Tokens: (b) image/png, 8 bytes.

#### `gemini_inline_data_camel_case`

Rule (e) through the parent key inlineData; the mime type from mimeType.

Input:

```text
{"contents":[{"role":"user","parts":[{"inlineData":{"mimeType":"image/png","data":"iVBORw0KGgo="}}]}]}
```

Output:

```text
{"contents":[{"role":"user","parts":[{"inlineData":{"mimeType":"image/png","data":"[stripped image/png 8 bytes]"}}]}]}
```

Tokens: (e) image/png, 8 bytes.

#### `openai_responses_image_generation_result`

Rule (e) through the sibling output_format; the mime type is image/&lt;output_format&gt;.

Input:

```text
{"output":[{"type":"image_generation_call","status":"completed","output_format":"png","result":"iVBORw0KGgo="}]}
```

Output:

```text
{"output":[{"type":"image_generation_call","status":"completed","output_format":"png","result":"[stripped image/png 8 bytes]"}]}
```

Tokens: (e) image/png, 8 bytes.

#### `format_names_audio_only_under_an_audio_parent`

A format sibling makes the string a token, but audio/&lt;format&gt; applies only under input_audio or audio, so the mime type is unknown.

Input:

```text
{"b64_json":"iVBORw0KGgo=","format":"png"}
```

Output:

```text
{"b64_json":"[stripped unknown 8 bytes]","format":"png"}
```

Tokens: (e) unknown, 8 bytes.

#### `parent_key_through_an_array`

An array element inherits its array's parent key, so audio reaches the object inside the list.

Input:

```text
{"audio":[{"data":"UklGRiQAAABXQVZF"}]}
```

Output:

```text
{"audio":[{"data":"[stripped unknown 12 bytes]"}]}
```

Tokens: (e) unknown, 12 bytes.

#### `size_on_the_unescaped_value`

The size is computed on the unescaped value with its whitespace removed; unpadded base64 is not valid, so its size is unknown.

Input:

```text
[{"source":{"type":"base64","media_type":"image/png","data":"iVBO\nRw0K\r\nGgo="}},{"source":{"type":"base64","media_type":"image/png","data":"iVBORw0KGgo"}}]
```

Output:

```text
[{"source":{"type":"base64","media_type":"image/png","data":"[stripped image/png 8 bytes]"}},{"source":{"type":"base64","media_type":"image/png","data":"[stripped image/png unknown bytes]"}}]
```

Tokens: (e) image/png, 8 bytes, (e) image/png, unknown bytes.

#### `stripping_twice_changes_nothing`

A string that is already a replacement is not a token, so the sink re-stripping an SDK's output gets the same bytes.

Input:

```text
{"source":{"type":"base64","media_type":"image/png","data":"[stripped image/png 8 bytes]"},"inline_data":{"data":"[stripped unknown unknown bytes]"}}
```

Output:

```text
{"source":{"type":"base64","media_type":"image/png","data":"[stripped image/png 8 bytes]"},"inline_data":{"data":"[stripped unknown unknown bytes]"}}
```

Tokens: none.

#### `url_safe_data_url`

The base64 run may be URL-safe; mixing the two alphabets is not valid base64.

Input:

```text
a data:image/png;base64,-_-_ and data:image/png;base64,+_+_ b
```

Output:

```text
a [stripped image/png 3 bytes] and [stripped image/png unknown bytes] b
```

Tokens: (b) image/png, 3 bytes, (b) image/png, unknown bytes.

## Input

| Source | Shape | Becomes | Modality | Paths | Fixtures | Why |
| -- | -- | -- | -- | -- | -- | -- |
| `openai.chat` | `image_url.url = data:<mime>;base64,...` | blob | image | passthrough, openinference, laminar | `openinference-openai/image_data_url`, `openinference-js-openai/image_data_url` | The mime type comes from the data URL. OpenInference (Python and JS) flattens it into the message contents, and its input.value keeps the request JSON. |
| `openai.chat` | `image_url.url = http(s)://...` | uri | image | passthrough, openinference, openllmetry, laminar | `openinference-openai/image_https_url`, `openinference-js-openai/image_https_url`, `openllmetry/image_https_url` | OpenLLMetry before 0.62 writes the content array as a JSON string in gen_ai.prompt.N.content. From 0.62 it writes a native uri part. |
| `openai.chat` | `input_audio {data, format}` | blob | audio | passthrough, openllmetry, laminar | none | No recorded family writes it in a message key (OpenInference keeps it only in input.value; see the OpenInference raw-payload row); covered by the SDK pass-through unit tests. The mime type is audio/&lt;format&gt;. |
| `openai.chat` | `file {file_id}` | file | document | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. |
| `openai.chat` | `file {file_data, filename}` | blob | from_mime | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. The modality comes from the data URL's mime type, or from the filename extension. |
| `openai.responses` | `input_image {image_url \| file_id}` | blob / uri / file | image | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. A data URL becomes a blob, an http(s) URL a uri, a file id a file. |
| `openai.responses` | `input_file {file_id \| file_data \| file_url}` | file / blob / uri | from_mime | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. A file id becomes a file, file data a blob, a file URL a uri. |
| `anthropic.messages` | `image / document with source.type = base64` | blob | from_mime | passthrough, openinference, openllmetry, laminar | `openinference-anthropic/image_base64`, `openinference-js-anthropic/image_base64` | The mime type comes from source.media_type. OpenInference Python flattens an image into a data URL in the message contents; OpenInference JS flattens it to image.media_type and image.type with no data at all (a blob with stripped_reason redacted_upstream). A document is dropped from the flattened messages, so it makes no part (see the OpenInference raw-payload row). |
| `anthropic.messages` | `image / document with source.type = url` | uri | from_mime | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. |
| `anthropic.messages` | `image / document with source.type = file` | file | from_mime | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. |
| `anthropic.messages` | `document with source.type = text \| content` | text | - | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. It is text to the model, so it becomes text parts. |
| `gemini.generate_content` | `inline_data {mime_type, data}` | blob | from_mime | passthrough | none | No recorded family; covered by the SDK pass-through unit tests. |
| `gemini.generate_content` | `file_data {mime_type, file_uri}` | uri | from_mime | passthrough | none | No recorded family; covered by the SDK pass-through unit tests. |
| `openinference.llm` | `message_content.type = image, image.image.url = data URL \| http(s) \| __REDACTED__` | blob / uri | image | openinference | `openinference-openai/image_data_url`, `openinference-openai/image_https_url`, `openinference-openai/image_redacted`, `openinference-anthropic/image_base64`, `openinference-js-openai/image_data_url`, `openinference-js-openai/image_https_url`, `openinference-js-openai/image_redacted` | A data URL becomes a blob, an http(s) URL a uri, and \_\_REDACTED\_\_ a blob with stripped_reason redacted_upstream. Python and JS; the JS instrumentor redacts above the same 32,000 characters. |
| `vercel.ai` | `image / file parts in ai.prompt.messages` | blob / uri | from_mime | vercel | `vercel-ai-v5/image_file`, `vercel-ai-v5/pdf_file`, `vercel-ai-v5/text_plain_file`, `vercel-ai-v5/audio_file`, `vercel-ai-v6/image_file`, `vercel-ai-v6/pdf_file`, `vercel-ai-v6/text_plain_file`, `vercel-ai-v6/audio_file` | The existing blob and uri mapping, with the modality rule. A blob is stripped. TypeScript SDK and sink. The AI SDK writes a file part as a part of type file with mediaType and base64 data in ai.prompt.messages (the model call), whatever the media type. A PDF and a text/plain file are not images. |
| `semconv.native` | `blob part with content` | blob | from_mime | native | `pydantic-ai/image_binary` | The same blob, stripped. pydantic-ai writes it in gen_ai.input.messages and pydantic_ai.all_messages. Any OTel GenAI instrumentation. |
| `semconv.native` | `uri part` | uri | from_mime | native | `openllmetry/image_https_url` | Unchanged, and modality is filled from the mime type when missing. OpenLLMetry 0.62 writes it in gen_ai.input.messages. |
| `semconv.native` | `file part` | file | from_mime | native | none | No recorded family; covered by the SDK pass-through unit tests. Unchanged, and modality is filled from the mime type when missing. |
| `openinference.llm` | `image.image.url = data:None;url,None` | blob | image | openinference | `openinference-anthropic/image_url` | What OpenInference's Anthropic instrumentor writes for an image with a url source; the URL itself is lost. The data URL names no mime type and holds no bytes, so the blob has neither mime_type nor byte_size, and its stripped_reason is redacted_upstream. |
| `laminar.openhands` | `ImageContent with image_urls in lmnr.span.input` | no part (raw payload stripped: `lmnr.span.input`) | - | laminar | `laminar/image_base64`, `laminar/image_https_url` | lmnr.span.input is a raw payload, not a message key, so it makes no part. A data URL in it is stripped per raw_payloads; an http(s) URL stays. Written on the conversation.send_message span's input, and the sink keeps it in InputValue. The LLM span drops the image when the model has no vision support. |
| `vercel.ai` | `file part with Buffer data in ai.prompt` | no part (raw payload stripped: `ai.prompt`) | - | vercel | `vercel-ai-v5/image_file`, `vercel-ai-v5/pdf_file`, `vercel-ai-v5/text_plain_file`, `vercel-ai-v5/audio_file`, `vercel-ai-v6/image_file`, `vercel-ai-v6/pdf_file`, `vercel-ai-v6/text_plain_file`, `vercel-ai-v6/audio_file` | On the operation span (ai.generateText) the prompt is JSON, and a file given as a Buffer is written as an object of type Buffer whose data is a JSON array of byte values, not base64. ai.prompt is a raw payload, so it makes no part; the Buffer object is replaced per raw_payloads, with byte_size the array length. The part comes from ai.prompt.messages on the model-call span (the image / file parts row). |
| `vercel.ai_otel` | `blob part with modality image for a non-image file, in gen_ai.input.messages` | blob | from_mime | native | `vercel-ai-otel/image_file`, `vercel-ai-otel/pdf_file`, `vercel-ai-otel/text_plain_file`, `vercel-ai-otel/audio_file` | @ai-sdk/otel writes every file part as a blob with base64 content and labels application/pdf and text/plain as modality image (audio/wav is labelled audio). The modality is recomputed from the mime type, so these become document blobs. |
| `openinference.llm` | `message_content.type = image with no image.url (image.media_type and image.type only, or nothing)` | blob | image | openinference | `openinference-js-anthropic/image_base64`, `openinference-js-anthropic/image_url` | What OpenInference's JS Anthropic instrumentor writes for an image. A base64 source leaves image.media_type (the mime type) and image.type = base64 but no data; a url source leaves only message_content.type = image. The blob carries the mime type when given, no byte_size, and stripped_reason redacted_upstream. |
| `openinference.llm` | `media present only in input.value / output.value (audio input, audio output, PDF document)` | no part (raw payload stripped: `input.value`, `output.value`) | - | openinference | `openinference-openai/input_audio`, `openinference-openai/audio_output`, `openinference-js-openai/input_audio`, `openinference-js-openai/audio_output`, `openinference-anthropic/document_pdf`, `openinference-js-anthropic/document_pdf` | OpenInference (Python and JS) leaves OpenAI input_audio, an OpenAI message.audio response and an Anthropic base64 document out of the flattened messages, and keeps them only in the request or response JSON of input.value / output.value. No part is made; the raw payload is stripped per raw_payloads. |
| `openllmetry.openai` | `image as a data URL: the instrumentor drops the prompt content; nothing to normalize` | no part | - | openllmetry | `openllmetry/image_base64` | Before 0.62 the span keeps only gen_ai.prompt.0.role, with no content; 0.62 writes no gen_ai.input.messages at all. Every recorded version. |

## Output

| Source | Shape | Becomes | Modality | Paths | Fixtures | Why |
| -- | -- | -- | -- | -- | -- | -- |
| `openai.chat` | `message.audio {data, transcript}` | blob | audio | passthrough, openllmetry, laminar | none | No recorded family writes it in a message key (OpenInference keeps it only in output.value; see the OpenInference raw-payload row); covered by the SDK pass-through unit tests. A text part with the transcript follows the blob. |
| `openai.responses` | `image_generation_call.result (base64)` | blob | image | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. |
