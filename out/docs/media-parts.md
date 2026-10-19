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
| `openai.chat` | image_url.url = data:<mime>;base64,... | blob | image | passthrough, openllmetry, laminar | `openinference-openai/image_data_url` | The mime type comes from the data URL. OpenInference flattens it into the message contents, and its input.value keeps the request JSON. |
| `openai.chat` | image_url.url = http(s)://... | uri | image | passthrough, openllmetry, laminar | `openinference-openai/image_https_url`, `openllmetry/image_https_url` | OpenLLMetry before 0.62 writes the content array as a JSON string in gen_ai.prompt.N.content. From 0.62 it writes a native uri part. |
| `openai.chat` | input_audio {data, format} | blob | audio | passthrough, openllmetry, laminar | `openinference-openai/input_audio` | The mime type is audio/<format>. OpenInference leaves the audio out of the flattened message contents and keeps it only in the request JSON of input.value. |
| `openai.chat` | file {file_id} | file | document | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. |
| `openai.chat` | file {file_data, filename} | blob | from_mime | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. The modality comes from the data URL's mime type, or from the filename extension. |
| `openai.responses` | input_image {image_url \| file_id} | blob / uri / file | image | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. A data URL becomes a blob, an http(s) URL a uri, a file id a file. |
| `openai.responses` | input_file {file_id \| file_data \| file_url} | file / blob / uri | from_mime | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. A file id becomes a file, file data a blob, a file URL a uri. |
| `anthropic.messages` | image / document with source.type = base64 | blob | from_mime | passthrough, openllmetry, laminar | `openinference-anthropic/image_base64`, `openinference-anthropic/document_pdf` | The mime type comes from source.media_type. OpenInference flattens an image into a data URL, drops a document from the flattened messages, and keeps both in the request JSON of input.value. |
| `anthropic.messages` | image / document with source.type = url | uri | from_mime | passthrough, openllmetry, laminar | `openinference-anthropic/image_url` | OpenInference flattens a url source into the placeholder data:None;url,None, so the URL survives only in the request JSON of input.value. |
| `anthropic.messages` | image / document with source.type = file | file | from_mime | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. |
| `anthropic.messages` | document with source.type = text \| content | text | - | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. It is text to the model, so it becomes text parts. |
| `gemini.generate_content` | inline_data {mime_type, data} | blob | from_mime | passthrough | none | No recorded family; covered by the SDK pass-through unit tests. |
| `gemini.generate_content` | file_data {mime_type, file_uri} | uri | from_mime | passthrough | none | No recorded family; covered by the SDK pass-through unit tests. |
| `openinference.llm` | message_content.type = image, image.image.url = data URL \| http(s) \| __REDACTED__ | blob / uri | image | openinference | `openinference-openai/image_data_url`, `openinference-openai/image_https_url`, `openinference-openai/image_redacted`, `openinference-anthropic/image_base64` | A data URL becomes a blob, an http(s) URL a uri, and __REDACTED__ a blob with stripped_reason redacted_upstream. Python and JS. |
| `vercel.ai` | image / file parts in ai.prompt.messages | blob / uri | from_mime | vercel | none | Recorded in this change. The existing blob and uri mapping, with the modality rule. A blob is stripped. TypeScript SDK and sink. |
| `semconv.native` | blob part with content | blob | from_mime | native | `pydantic-ai/image_binary` | The same blob, stripped. pydantic-ai writes it in gen_ai.input.messages and pydantic_ai.all_messages. Any OTel GenAI instrumentation. |
| `semconv.native` | uri part | uri | from_mime | native | `openllmetry/image_https_url` | Unchanged, and modality is filled from the mime type when missing. OpenLLMetry 0.62 writes it in gen_ai.input.messages. |
| `semconv.native` | file part | file | from_mime | native | none | No recorded family; covered by the SDK pass-through unit tests. Unchanged, and modality is filled from the mime type when missing. |
| `openinference.llm` | image.image.url = data:None;url,None | blob | image | openinference | `openinference-anthropic/image_url` | What OpenInference's Anthropic instrumentor writes for an image with a url source; the URL itself is lost. The data URL names no mime type and holds no bytes, so the blob has neither mime_type nor byte_size, and its stripped_reason is not_captured. |
| `laminar.openhands` | ImageContent with image_urls in lmnr.span.input | blob / uri | image | laminar | `laminar/image_base64`, `laminar/image_https_url` | A data URL becomes a blob, an http(s) URL a uri. Written on the conversation.send_message span's input; the LLM span drops the image when the model has no vision support. |

## Output

| Source | Shape | Becomes | Modality | Paths | Fixtures | Why |
| -- | -- | -- | -- | -- | -- | -- |
| `openai.chat` | message.audio {data, transcript} | blob | audio | passthrough, openllmetry, laminar | `openinference-openai/audio_output` | A text part with the transcript follows the blob. OpenInference leaves the audio out of the flattened output messages and keeps it only in the response JSON of output.value. |
| `openai.responses` | image_generation_call.result (base64) | blob | image | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. |
