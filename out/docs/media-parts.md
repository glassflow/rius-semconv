<!-- Generated from registry/media_parts.yaml by `python -m generators.generate`.
     Do not edit. -->

# Media parts

After normalization a media part is a `blob` (inline bytes, always stripped of
`content`), a `uri` or a `file`. The modality is one of `image`, `video`, `audio`, `document`,
taken from the MIME type when known (`from_mime`), else from the provider's
part kind. A `blob` carries a `stripped_reason`:

- `not_captured`: Our default policy removed the inline bytes.
- `redacted_upstream`: The instrumentor had already replaced the payload (OpenInference __REDACTED__).

*Fixtures* lists the recorded scenarios (`<family>/<scenario>`) that prove the
row; a row with none says why in *Why*.

## Input

| Source | Shape | Becomes | Modality | Paths | Fixtures | Why |
| -- | -- | -- | -- | -- | -- | -- |
| `openai.chat` | image_url.url = data:<mime>;base64,... | blob | image | passthrough, openllmetry, laminar | none | Recorded in this change. The mime type comes from the data URL. |
| `openai.chat` | image_url.url = http(s)://... | uri | image | passthrough, openllmetry, laminar | none | Recorded in this change. |
| `openai.chat` | input_audio {data, format} | blob | audio | passthrough, openllmetry, laminar | none | Recorded in this change. The mime type is audio/<format>. |
| `openai.chat` | file {file_id} | file | document | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. |
| `openai.chat` | file {file_data, filename} | blob | from_mime | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. The modality comes from the data URL's mime type, or from the filename extension. |
| `openai.responses` | input_image {image_url \| file_id} | blob / uri / file | image | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. A data URL becomes a blob, an http(s) URL a uri, a file id a file. |
| `openai.responses` | input_file {file_id \| file_data \| file_url} | file / blob / uri | from_mime | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. A file id becomes a file, file data a blob, a file URL a uri. |
| `anthropic.messages` | image / document with source.type = base64 | blob | from_mime | passthrough, openllmetry, laminar | none | Recorded in this change. The mime type comes from source.media_type. |
| `anthropic.messages` | image / document with source.type = url | uri | from_mime | passthrough, openllmetry, laminar | none | Recorded in this change. |
| `anthropic.messages` | image / document with source.type = file | file | from_mime | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. |
| `anthropic.messages` | document with source.type = text \| content | text | - | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. It is text to the model, so it becomes text parts. |
| `gemini.generate_content` | inline_data {mime_type, data} | blob | from_mime | passthrough | none | No recorded family; covered by the SDK pass-through unit tests. |
| `gemini.generate_content` | file_data {mime_type, file_uri} | uri | from_mime | passthrough | none | No recorded family; covered by the SDK pass-through unit tests. |
| `openinference.llm` | message_content.type = image, image.image.url = data URL \| http(s) \| __REDACTED__ | blob / uri | image | openinference | none | Recorded in this change. A data URL becomes a blob, an http(s) URL a uri, and __REDACTED__ a blob with stripped_reason redacted_upstream. Python and JS. |
| `openinference.llm` | audio.url / audio.mime_type | blob / uri | audio | openinference | none | Recorded in this change when the instrumentor writes audio.url; otherwise covered by the sink normalizer unit tests. Only when an instrumentor records them. |
| `vercel.ai` | image / file parts in ai.prompt.messages | blob / uri | from_mime | vercel | none | Recorded in this change. The existing blob and uri mapping, with the modality rule. A blob is stripped. TypeScript SDK and sink. |
| `semconv.native` | blob part with content | blob | from_mime | native | none | Recorded in this change. The same blob, stripped. Any OTel GenAI instrumentation. |
| `semconv.native` | uri / file part | uri / file | from_mime | native | none | No recorded family; covered by the SDK pass-through unit tests. Unchanged, and modality is filled from the mime type when missing. |

## Output

| Source | Shape | Becomes | Modality | Paths | Fixtures | Why |
| -- | -- | -- | -- | -- | -- | -- |
| `openai.chat` | message.audio {data, transcript} | blob | audio | passthrough, openllmetry, laminar | none | Recorded in this change. A text part with the transcript follows the blob. |
| `openai.responses` | image_generation_call.result (base64) | blob | image | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. |
