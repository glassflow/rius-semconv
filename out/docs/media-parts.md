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

**Strip rule.** In every string attribute value on every span and span event, and in the sink's stored columns, each media token (found by the detection rules below) is replaced in place. Every other byte of the string stays identical: normalizers must not parse and re-serialize the JSON. Byte equality across the Python SDK, the TypeScript SDK and the Go sink depends on this. Message parts in gen_ai.\*.messages keep the stripped blob part shape instead; the replacement string is only for raw payloads.

**Replacement.** The JSON string `"[stripped <mime> <byte_size> bytes]"`, with `unknown` for a mime type or size that is not known: `"[stripped image/png 67 bytes]"`, `"[stripped unknown unknown bytes]"`.

A data URL inside other text: only the token is replaced, so `see data:image/png;base64,iVBORw0KGgo= here` becomes `see [stripped image/png 8 bytes] here`.

| Token | Replaced | Mime | Byte size |
| -- | -- | -- | -- |
| A data URL (rule b), anywhere in a string | The data URL token alone: from data: to the end of the base64 run, in place, inside the string. The text around it stays byte-identical; a string that is only the data URL becomes the replacement string. | The URL's media type; unknown when it names none. | The decoded length of the base64 run, floor(3 \* characters without padding / 4). |
| A base64 string value (rule e) | The string token. | The sibling media_type, mediaType or mime_type; else audio/&lt;format&gt; from a format sibling; else unknown. | The decoded length of the base64 data. |
| A Buffer object (rule d) | The whole object token, by the string. | The enclosing object's media_type, mediaType or mime_type; else unknown. | The length of the data array. |

**Detection rules.** The normalizers strip, and tools/check_fixtures.py refuses
in an expected result, every token these find (in a string holding JSON too):

| Rule | Name | Matches | Parameters |
| -- | -- | -- | -- |
| (b) | data URL | A data:&lt;mime&gt;;base64,&lt;base64&gt; token anywhere in a string: the pattern finds each one, group 1 the mime type (empty when none), group 2 the base64 run. A whole-string data URL is the special case. | pattern: `data:([^;,\s"]*);base64,([A-Za-z0-9+/]*={0,2})` |
| (d) | Buffer object | An object {"type": "Buffer", "data": [...]} whose data is a non-empty array. | type: `Buffer`; array_key: `data` |
| (e) | keyed base64 string | A non-empty string under one of the keys, when its object has one of the sibling keys, or its object's parent key is one of the parent keys, or its object is a source with type base64. | keys: `data`, `b64_json`, `result`; sibling_keys: `media_type`, `mediaType`, `mime_type`, `format`; parent_keys: `input_audio`, `audio`, `inline_data`; source_key: `source`; source_type: `base64` |

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
