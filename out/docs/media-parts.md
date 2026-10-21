<!-- Generated from registry/media_parts.yaml by `python -m generators.generate`.
     Do not edit. -->

# Media parts

After normalization a media part is a `blob` (inline bytes, always stripped of
`content`), a `uri` or a `file`. The modality is one of `image`, `video`, `audio`, `document`,
taken from the MIME type when known (`from_mime`), else from the provider's
item kind, a filename or a URI path's extension (see the part rules).
A `blob` carries a `stripped_reason`:

- `not_captured`: Our default policy removed the inline bytes.
- `redacted_upstream`: The instrumentor dropped or replaced the payload before we saw it (OpenInference \_\_REDACTED\_\_, a data URL with no bytes, an image with no url).

*Fixtures* lists the recorded scenarios (`<family>/<scenario>`) that prove the
row; a row with none says why in *Notes*.

## Part shapes

A normalized part in a message key is written with exactly these members, in order:

- `blob`: `type`, `modality`, `mime_type`, `byte_size`, `stripped_reason`
- `uri`: `type`, `modality`, `mime_type`, `uri`
- `file`: `type`, `modality`, `mime_type`, `file_id`

- Members appear in exactly the order of members, and no member appears twice.
- A member whose value is unknown is omitted, never written as null. This applies to mime_type and byte_size.
- mime_type is written only when it is a valid token/token MIME type, matching the replacement's mime_pattern in full. Anything else is omitted.
- The modality is taken from the prefix of the MIME type, matched case-insensitively. image/\* is image, audio/\* audio, video/\* video, anything else document.
- Every native media part in a message key (blob, uri or file) is always rebuilt into its canonical shape: members in the pinned order, extra members dropped, and every member that is unknown omitted. The only exception is a uri part whose uri is not a string, or a file part whose file_id is not a string: it is left as it came. Any string is a usable uri or file_id, the empty string included. An object of type file that holds a base64 or a url that is a string is no native file part but a LangChain v1 file block, read by the v1 rule below: so {"type":"file","file_id":5,"url":"https://example.com/a.wav"} is a uri, while {"type":"file","file_id":5} is a native file part left as it came. Every other normalized media part carries a modality. generators/media_parts.py native_part(data, part) is the reference: each example's native part, and the part in each in_place example, is its test.
- Parts are rebuilt only in a message-key value that parses as JSON and nests at most 1000 levels deep. Arrays and objects count together from the value's root, which is level 1: the message array, a message, its parts array and a tool call part are 4 levels. A value nested deeper (a tool call whose arguments add 997 more arrays makes 1001 levels) is left as it came, every part in it included; at 1000 levels its parts are rebuilt. The implementation counts the depth itself and never relies on its parser's or its language's recursion limit. The strip still runs on a value left this way.
- The modality that the part already has is kept, when it is one of modalities (any other value is ignored), except for a blob whose content is a string and a uri holding a data URL (below). Otherwise it is taken from the MIME type. Failing that, a provider item whose kind names a modality takes it from the kind: an image, image_url, input_image or image_generation_call item is image, an input_audio item audio, a document item document. A LangChain v1 block of type image, audio or video is that modality; a block of type file names none, so by a url that is not a data URL it takes the modality from the extension of the URL's path (see extensions), and otherwise it is document. A text-plain block by base64 names none either and is document (one by url or file_id makes no part). A Bedrock Converse image, video, audio or document block is that modality. An OpenAI file or input_file item names none; its modality comes from the extension of its filename member alone (never from a file_url), and with no filename, or an empty one, it is document. A Gemini file_data, a native uri and a Vercel file part by URL take it from the extension of their URI's path (see extensions), the Vercel part whether its URL is a plain string or v7's {"type":"url"} data; a Vercel image part is an image. Otherwise it is document. So an Anthropic document by URL ending in .png is a document, an OpenAI input_file named a.png is an image, and an input_file by a file_url ending in .png with no filename is a document; a LangChain v1 image block by a URL ending in .bin is an image, and a v1 file block by a URL ending in .wav is audio. A native file part with no valid modality and no MIME type gets document; no member of it is read for an extension. Any other part with no MIME type and no other hint also gets document.
- A blob whose `content` is a string is rebuilt with stripped_reason not_captured and a byte_size taken from the content under the size rule of the strip (omitted when the size is unknown). Its modality comes from its MIME type first, then from the modality it has, then document: a PDF blob labelled image is a document. A content string that is itself a data URL follows the data URL rules below, with the part's mime_type as the hint and the same modality order. A blob in a message key never carries content.
- A blob with no string `content` keeps a stripped_reason that is one of stripped_reasons. Otherwise its stripped_reason is redacted_upstream when it has no content member or a null one, and not_captured when its content is any other value. It keeps a byte_size that is a whole, non-negative number no larger than 2^53 - 1 (8, 8.0 and 8e0 alike, written 8); any other byte_size is omitted.
- A uri part, or a provider URI, whose URI is a data URL is never a uri: it becomes a blob under the data URL rules below. A data URL is a value that starts with data:, or with data%3A (rule (b)'s percent_scheme: a data URL percent-encoded whole, as encodeURIComponent writes it), in any ASCII case. Nor is a native uri part or a provider URI whose value holds data: anywhere else, in any ASCII case (a value led by whitespace, or a link with a data URL after it, wrapped, percent-encoded or not): it becomes a blob with the stripped_reason not_captured and no byte_size, its MIME type kept when valid, so no byte of the data URL survives. The provider URIs are an OpenAI image_url's url and input_image's image_url, an Anthropic image or document by a url source, an OpenAI input_file's file_url, a Gemini file_data's file_uri, a Vercel file or image part by URL (a plain string that starts with a URL scheme, or v7's {"type":"url"} data), and the image url OpenInference flattens; a LangChain v1 url is read the same way (below). Any other value stays a uri as it came, a link that holds data%3A and no data: included (a proxy link with an encoded data URL in its query): the strip then replaces the encoded data URL inside it where it sits, as rule (b) does under any key that keeps URLs. A native uri part takes that blob's modality as a blob whose content is a string does: from the MIME type first, then the modality it has, then document. A provider URI takes it from the MIME type the item gives (an Anthropic source's media_type, a Gemini file_data's mime_type, a Vercel part's mediaType, the image media_type OpenInference flattens beside its url), then from the item's kind (an image_url, an input_image and a Vercel image part are image, an Anthropic image or document that kind, an input_file the modality its filename names), then document: such a value has no path to read an extension from. The test is one search for [dD][aA][tT][aA]: with no trimming and no word boundary, so a link with data: in its path (https://e/metadata:x.png) becomes this blob too: a lost link, never a leak. generators/media_parts.py provider_uri_part(data, item) is the reference for a provider URI, and each example's provider item is its test.
- A URL of any scheme other than data: is a uri, its link kept as written: http, https, gs, s3, file and any other scheme alike. Only a data: URL, or inline data, becomes a blob, and a native uri, a provider URI or a LangChain v1 url that holds data: anywhere else (above and below). Where one value may hold either a URL or bare base64 (a Vercel file part's data or image part's image, as a plain string or as v7's {"type":"data"} data), it is a URL when it starts with a scheme: an ASCII letter, then any ASCII letters, digits, `+`, `-` or `.`, then a colon. Base64 holds no colon, so the two never meet; anything else is base64, but a value that starts with data%3A, which is a data URL (above). A value v7 tags {"type":"url"} is a URL whatever it holds. The strip reads these values the same way: rule (e) leaves a value that starts with a scheme to rule (b) (raw_payloads, rule (e)'s url_scheme and keeps_urls), except a value holding data: that rule (b)'s pattern does not match in full (a percent-encoded data URL, a link with a data URL after it), which rule (e) replaces whole, as the part rules make it a blob.
- In a provider media item, a URL or a file id that is empty, or that is the \_\_REDACTED\_\_ marker an instrumentor writes in its place, was dropped upstream. When the item has no other usable reference (one that is neither empty nor \_\_REDACTED\_\_), it becomes a blob with the stripped_reason redacted_upstream and no byte_size. It keeps the MIME type the item gives (an Anthropic source's media_type, a Gemini file_data's mime_type, a Vercel part's mediaType, OpenInference's flattened image media_type) and takes its modality by the rule above, so an image_url or input_image is image. This covers an image_url's url, an input_image's image_url and file_id, an Anthropic url or file source, a Gemini file_data's file_uri, a Vercel part's v7 {"type":"url"} data, an OpenAI file or input_file's file_id, file_data and file_url (an empty file_data counts as dropped too, since its item has nothing else to point to), and a LangChain v1 image, audio, video or file block's url and an image, audio or video block's file_id. An OpenAI file or input_file with no usable reference becomes this blob too when it has no reference member at all, or only ones that are not strings (a file_id of 5 or null): its type file would otherwise collide with a native file part. A usable reference wins: an input_image whose image_url is \_\_REDACTED\_\_ and whose file_id is usable is a file, and an OpenAI file with an empty file_id and non-empty file_data is a blob of that data. It matches OpenInference's \_\_REDACTED\_\_ on the flattened path. So no provider item this rule covers is left as a part of type file without a file_id. A native uri or file part is no provider item: its empty uri or file_id is kept, and so is that of a LangChain v1 file block with no other usable reference (no base64 but an empty or \_\_REDACTED\_\_ one, and no usable url), since such a block has a native file part's shape and is read as one (below); a v1 file block that has one is read by it, as the usable reference wins. Nor is a reference not yet mapped to a part (a Bedrock Converse source by s3Location): it stays as it came, empty or not.
- A Vercel file part whose data, or image part whose image, is neither a string nor v7 tagged data holding one makes no part: it is dropped from its message's parts, never written as a bare {"type":"file"} or {"type":"image"}, and any raw payload holding its bytes is stripped per raw_payloads. So is a v7 {"type":"text"} whose text is not a string. A v7 tag no rule here names becomes a blob with the stripped_reason not_captured and no byte_size, keeping the part's mediaType: its size was never measured.
- A LangChain v1 standard content block of type image, audio, video or file, or of type text-plain, makes one part, by the first of these that applies. A usable url or file_id is a string that is neither empty nor \_\_REDACTED\_\_. (1) A block of type file whose file_id is usable, a string that is neither empty nor \_\_REDACTED\_\_, is a native file part, whatever else it holds (a url, a base64, even an OpenAI-style file member): it is rebuilt as one (above), its mime_type kept when valid, and its modality by the native order: its own modality member when that is one of modalities, else from the MIME type, else document. (2) A base64 that is a string is a blob (the bare base64 rule below): an empty one is 0 bytes, and \_\_REDACTED\_\_, which is valid base64, is 9, as for any bare base64 payload. The one exception is a block of type file whose file_id is a string: there an empty or \_\_REDACTED\_\_ base64 is no usable reference, and the block reads on, so it never beats an empty file_id. (3) A usable file_id is a file part. (4) A usable url that is a data URL is a blob under the data URL rules, the block's mime_type the hint: a data URL that rule (b)'s pattern does not match in full (a trailing space, a percent-encoded payload) is a blob with no byte_size, while a base64 run wrapped at a line break is a full match, sized. A usable url that holds data: anywhere else, in any ASCII case (one led by whitespace, or a link with a data URL after it), is a blob with the stripped_reason not_captured and no byte_size, so no byte of it is kept. Any other usable url is a uri, its value kept as it came, whatever its scheme and relative or not: {"type":"image","url":"/img/a.png"} is a uri. (5) A block of type file whose file_id is a string, and that reached here with no other usable reference, has a native file part's shape and is one, rebuilt as in (1): its file_id is kept as written, empty or \_\_REDACTED\_\_ included. (6) When url or file_id is a string but none is usable, the block becomes a blob with the stripped_reason redacted_upstream and no byte_size (above). So a usable reference wins over an empty or \_\_REDACTED\_\_ file_id for every block type: {"type":"file","file_id":"","url":"https://example.com/a.pdf"} is a uri, and {"type":"file","file_id":""} alone is a file part. Nor does an empty or \_\_REDACTED\_\_ base64 beside one: {"type":"file","file_id":"","base64":""} is a file part by (5), while {"type":"image","base64":""} is a 0-byte blob by (2). A text-plain block is read by its base64 alone, in (2), and is document unless its mime_type names another modality; by url or file_id it makes no part and stays as it came. Every one keeps the block's mime_type when it is valid and takes its modality by the rule above. A block with no base64, url or file_id that is a string makes no part this way and stays as it came. In every case but a native file part ((1) and (5)), only type, base64, url, file_id and mime_type are read, a modality member included in none; a native file part is read as one, so its valid modality member comes first. So a LangChain v0 block by url ({"type":"image","source_type":"url","url":...}) is read the same way, and a v0 block by base64 or by id holds none of them and stays as it came, its data stripped per raw_payloads. generators/media_parts.py langchain_v1_part(data, block) is the reference, and each v1 example's block is its test. A block is read the same way on every path that delivers it: passthrough, and the provider blocks OpenLLMetry and Laminar write as gen_ai.prompt.N.content.
- When a part has duplicate `type` members, the last one wins, as in a standard JSON decoder. The strip is different: there, a condition on `type` holds when any member qualifies.
- A base64 data URL (rule (b)'s pattern matching the whole string, or all of it but one final line break, a newline or a carriage return and newline, as base64.encodebytes ends its output and as a key that keeps URLs reads it in the strip; percent_pattern for a data URL percent-encoded whole, whose one final line break may also be %0A or %0D%0A) becomes a blob with the stripped_reason not_captured. Its mime type is the URL's when that is a valid token/token MIME type, else the hint (a native part's mime_type). Its byte_size is that of the base64 run under the size rule of the strip: an empty run is 0 bytes, and an invalid run has no byte_size. A percent-encoded one's mime type and run are percent-decoded first, as rule (b) reads them.
- A provider item's bare base64 payload (an input_audio data, a Mistral input_audio or inputAudio string, an Anthropic base64 source's data, a LangChain v1 block's base64 (but an empty or \_\_REDACTED\_\_ one beside a file block's string file_id, below), a Bedrock Converse source's bytes, an image_generation_call result, a Gemini inline_data data, a Vercel file part's data or image part's image, a non-empty OpenAI file_data) becomes a blob with the stripped_reason not_captured, its byte_size under the size rule of the strip: an empty string is 0 bytes, never redacted_upstream. A payload that is itself a data URL follows the data URL rules. An OpenAI file or input_file with no usable file_id, file_data or file_url was dropped upstream (above).
- A data URL that is not base64 (`data:<mime>,<payload>`) becomes a blob with the stripped_reason not_captured and no byte_size. Its mime type is the text after `data:` up to the first `;` or `,`, when that is a valid token/token MIME type, else the hint; its payload is everything after the first comma. This rule also covers a URL that names base64 but whose run does not match rule (b), such as `data:image/png;base64,@@`. When its payload is empty or `None`, it becomes a blob with the stripped_reason redacted_upstream. A data URL percent-encoded whole that percent_pattern does not match (`data%3Aimage%2Fpng;base64,...`, its `;` and comma kept) is read by this rule once each `%XX` is decoded.
- When a normalizer rebuilds a native part inside an existing message-key value, it edits in place: only that part object token is replaced by its canonical compact serialization (no spaces, the minimal escaping of the strip), and every other byte of the value stays as it came. A value with nothing to rebuild stays byte for byte. Messages a normalizer builds itself are serialized compactly.

Filename extensions (lower case) that give a modality:

- `image`: `png`, `jpg`, `jpeg`, `gif`, `webp`
- `audio`: `wav`, `mp3`, `m4a`, `ogg`, `flac`
- `video`: `mp4`, `mov`, `webm`
- anything else: `document`

Examples:

#### `blob_with_a_known_size`

A base64 data URL of image/png, 8 bytes decoded.

```json
{"type":"blob","modality":"image","mime_type":"image/png","byte_size":8,"stripped_reason":"not_captured"}
```

#### `blob_whose_bytes_never_arrived`

An image item whose content is the placeholder the instrumentor wrote, with no MIME type: the part kind the provider gives it is the modality hint.

```json
{"type":"blob","modality":"image","stripped_reason":"redacted_upstream"}
```

#### `data_url_that_is_not_base64`

The data URL data:text/plain,hello.

```json
{"type":"blob","modality":"document","mime_type":"text/plain","stripped_reason":"not_captured"}
```

#### `data_url_that_is_not_base64_and_empty`

The data URL data:image/png, with no payload.

```json
{"type":"blob","modality":"image","mime_type":"image/png","stripped_reason":"redacted_upstream"}
```

#### `blob_with_content_and_no_hint`

A native blob part with a content member holding the base64 iVBORw0KGgo= and neither a MIME type nor a modality.

```json
{"type":"blob","modality":"document","byte_size":8,"stripped_reason":"not_captured"}
```

#### `blob_with_content_labelled_image_for_a_pdf`

A native blob part with a content member holding the base64 JVBERi0=, the mime_type application/pdf and the modality image, as @ai-sdk/otel writes a PDF: the MIME type wins over the modality it has.

```json
{"type":"blob","modality":"document","mime_type":"application/pdf","byte_size":5,"stripped_reason":"not_captured"}
```

#### `blob_with_content_that_is_an_empty_base64_data_url`

A native blob part with the mime_type image/png and a content member holding data:;base64, which names no mime type and has an empty run: the part's mime_type is the hint.

```json
{"type":"blob","modality":"image","mime_type":"image/png","byte_size":0,"stripped_reason":"not_captured"}
```

#### `blob_with_no_content_and_no_stripped_reason`

A native blob part with the modality audio and neither content nor stripped_reason.

```json
{"type":"blob","modality":"audio","stripped_reason":"redacted_upstream"}
```

#### `blob_with_content_that_is_not_a_string`

A native blob part whose content is the number 5 and whose byte_size is 8.0, with no stripped_reason.

```json
{"type":"blob","modality":"document","byte_size":8,"stripped_reason":"not_captured"}
```

#### `uri_with_no_mime_type_and_no_modality`

A uri part for https://example.com/download with neither a MIME type nor a modality.

```json
{"type":"uri","modality":"document","uri":"https://example.com/download"}
```

#### `uri_with_members_out_of_order_keeps_its_modality`

A uri part written as uri, modality image, type uri and an extra member, in that order.

```json
{"type":"uri","modality":"image","uri":"https://example.com/talk"}
```

#### `uri_with_an_invalid_mime_type`

A uri part with the mime_type text/plain;charset=x, which is not token/token.

```json
{"type":"uri","modality":"document","uri":"https://example.com/notes"}
```

#### `uri_that_is_a_data_url`

A uri part, or a Gemini file_data, whose URI is data:image/png;base64,iVBORw0KGgo=.

```json
{"type":"blob","modality":"image","mime_type":"image/png","byte_size":8,"stripped_reason":"not_captured"}
```

#### `uri_with_a_mime_type`

An audio part by URL, with the MIME type audio/mpeg.

```json
{"type":"uri","modality":"audio","mime_type":"audio/mpeg","uri":"https://example.com/a.mp3"}
```

#### `uri_with_only_an_extension`

A part by URL, with no MIME type, ending in .mov.

```json
{"type":"uri","modality":"video","uri":"https://example.com/clip.mov"}
```

#### `file_with_no_hint`

A provider file id and nothing else.

```json
{"type":"file","modality":"document","file_id":"file-abc123"}
```

#### `uri_with_a_cloud_storage_scheme`

A part by the URL gs://bucket/a.png with the MIME type image/png: a Vercel file part with that mediaType, a native uri or a Gemini file_data. The link is kept; it is no blob.

```json
{"type":"uri","modality":"image","mime_type":"image/png","uri":"gs://bucket/a.png"}
```

#### `uri_tagged_url_with_an_s3_scheme`

A Vercel file part whose data is v7's {"type":"url","url":"s3://bucket/report.pdf"}, with no mediaType, or a native uri for that URL: pdf names no modality, so it is a document.

```json
{"type":"uri","modality":"document","uri":"s3://bucket/report.pdf"}
```

#### `uri_with_the_file_scheme_and_only_an_extension`

A Vercel file part, plain or v7 {"type":"url"}, or a native uri, by file:///tmp/clip.mov with no MIME type.

```json
{"type":"uri","modality":"video","uri":"file:///tmp/clip.mov"}
```

#### `vercel_file_by_url_with_no_media_type`

A Vercel file part whose data is https://example.com/a.png, with no mediaType: the URL path's extension names the modality, as for a native uri.

```json
{"type":"uri","modality":"image","uri":"https://example.com/a.png"}
```

#### `blob_from_an_unknown_v7_data_tag`

A Vercel file part with the mediaType image/png whose data is v7 tagged data of a type no rule names: its size was never measured, so it has no byte_size.

```json
{"type":"blob","modality":"image","mime_type":"image/png","stripped_reason":"not_captured"}
```

#### `image_url_that_is_empty`

An OpenAI image_url item whose url is the empty string.

```json
{"type":"blob","modality":"image","stripped_reason":"redacted_upstream"}
```

#### `image_url_that_is_redacted`

An OpenAI image_url item whose url is \_\_REDACTED\_\_, the marker an instrumentor writes in place of the image.

```json
{"type":"blob","modality":"image","stripped_reason":"redacted_upstream"}
```

#### `anthropic_url_source_that_is_empty`

An Anthropic document whose url source has an empty url.

```json
{"type":"blob","modality":"document","stripped_reason":"redacted_upstream"}
```

#### `anthropic_file_source_that_is_empty`

An Anthropic image whose file source has an empty file_id and the media_type image/png: the MIME type the item gives is kept.

```json
{"type":"blob","modality":"image","mime_type":"image/png","stripped_reason":"redacted_upstream"}
```

#### `input_image_with_an_empty_file_id`

An OpenAI input_image whose file_id is empty, with no image_url.

```json
{"type":"blob","modality":"image","stripped_reason":"redacted_upstream"}
```

#### `openai_file_with_an_empty_file_id`

An OpenAI chat file item whose file is {"file_id":"","filename":"a.png"}: it is no file part without a file_id, but a blob whose modality the filename names.

```json
{"type":"blob","modality":"image","stripped_reason":"redacted_upstream"}
```

#### `input_image_with_a_usable_url_and_a_file_id`

An OpenAI input_image whose image_url is https://x/a.png and whose file_id is file-abc123: the image_url is read first, so the item is a uri.

```json
{"type":"uri","modality":"image","uri":"https://x/a.png"}
```

#### `input_image_with_a_redacted_url_and_a_file_id`

An OpenAI input_image whose image_url is \_\_REDACTED\_\_ and whose file_id is file-abc123: the usable reference wins.

```json
{"type":"file","modality":"image","file_id":"file-abc123"}
```

#### `openai_file_with_no_reference`

An OpenAI chat file item whose file is {"filename":"a.png"}, with no file_id, file_data or file_url: it is no file part without a file_id, but a blob whose modality the filename names.

```json
{"type":"blob","modality":"image","stripped_reason":"redacted_upstream"}
```

#### `openai_file_with_a_file_id_that_is_not_a_string`

An OpenAI chat file item whose file is {"file_id":5,"filename":"a.wav"}, or an input_file whose file_id is null and whose filename is a.wav: a file_id that is not a string is no reference.

```json
{"type":"blob","modality":"audio","stripped_reason":"redacted_upstream"}
```

#### `input_file_with_no_reference_and_no_filename`

An OpenAI input_file item with no member but its type.

```json
{"type":"blob","modality":"document","stripped_reason":"redacted_upstream"}
```

#### `langchain_v1_image_by_url`

A LangChain v1 block {"type":"image","url":"https://example.com/a.png","mime_type":"image/png"}.

```json
{"type":"uri","modality":"image","mime_type":"image/png","uri":"https://example.com/a.png"}
```

#### `langchain_v1_image_by_url_kind_before_extension`

A LangChain v1 block {"type":"image","url":"https://example.com/download.bin"}, with no mime_type: the block type names the modality before the URL's extension is read.

```json
{"type":"uri","modality":"image","uri":"https://example.com/download.bin"}
```

#### `langchain_v1_file_by_url_with_only_an_extension`

A LangChain v1 block {"type":"file","url":"https://example.com/a.wav"}, with no mime_type: the type file names no modality, so the URL path's extension does.

```json
{"type":"uri","modality":"audio","uri":"https://example.com/a.wav"}
```

#### `langchain_v1_file_by_url_with_no_extension`

A LangChain v1 block {"type":"file","url":"s3://bucket/report"}, with no mime_type.

```json
{"type":"uri","modality":"document","uri":"s3://bucket/report"}
```

#### `langchain_v1_audio_by_data_url`

A LangChain v1 block {"type":"audio","url":"data:;base64,UklGRg==","mime_type":"audio/wav"}: the data URL names no mime type, so the block's mime_type is the hint.

```json
{"type":"blob","modality":"audio","mime_type":"audio/wav","byte_size":4,"stripped_reason":"not_captured"}
```

#### `langchain_v1_image_by_redacted_url`

A LangChain v1 block {"type":"image","url":"\_\_REDACTED\_\_","mime_type":"image/png"}.

```json
{"type":"blob","modality":"image","mime_type":"image/png","stripped_reason":"redacted_upstream"}
```

#### `langchain_v1_file_by_empty_url`

A LangChain v1 block {"type":"file","url":""}: no URL is left to give an extension, so it is a document.

```json
{"type":"blob","modality":"document","stripped_reason":"redacted_upstream"}
```

#### `langchain_v1_image_by_file_id`

A LangChain v1 block {"type":"image","file_id":"file-abc123"}.

```json
{"type":"file","modality":"image","file_id":"file-abc123"}
```

#### `langchain_v1_video_by_empty_file_id`

A LangChain v1 block {"type":"video","file_id":"","mime_type":"video/mp4"}.

```json
{"type":"blob","modality":"video","mime_type":"video/mp4","stripped_reason":"redacted_upstream"}
```

#### `langchain_v1_image_by_redacted_url_and_a_file_id`

A LangChain v1 block {"type":"image","url":"\_\_REDACTED\_\_","file_id":"file-abc123"}: the usable reference wins.

```json
{"type":"file","modality":"image","file_id":"file-abc123"}
```

#### `langchain_v1_file_by_file_id`

A LangChain v1 block {"type":"file","file_id":"file-abc123","mime_type":"application/pdf"}, read as the native file part it has the shape of.

```json
{"type":"file","modality":"document","mime_type":"application/pdf","file_id":"file-abc123"}
```

#### `langchain_v1_file_by_empty_file_id_is_a_native_file_part`

A LangChain v1 block {"type":"file","file_id":""}: it has a native file part's shape, and a native file part keeps its empty file_id.

```json
{"type":"file","modality":"document","file_id":""}
```

#### `langchain_v1_file_by_file_id_keeps_its_modality`

A LangChain v1 block {"type":"file","file_id":"x","modality":"image"}: read as a native file part, so its valid modality member is kept before anything else is tried.

```json
{"type":"file","modality":"image","file_id":"x"}
```

#### `langchain_v1_file_by_empty_file_id_and_a_url`

A LangChain v1 block {"type":"file","file_id":"","url":"https://example.com/a.pdf"}: the usable url wins over the empty file_id, as a usable reference does everywhere.

```json
{"type":"uri","modality":"document","uri":"https://example.com/a.pdf"}
```

#### `langchain_v1_file_by_redacted_file_id_and_base64`

A LangChain v1 block {"type":"file","file_id":"\_\_REDACTED\_\_","base64":"JVBERi0=","mime_type":"application/pdf"}: the base64 wins over the redacted file_id.

```json
{"type":"blob","modality":"document","mime_type":"application/pdf","byte_size":5,"stripped_reason":"not_captured"}
```

#### `langchain_v1_file_by_redacted_file_id_and_an_empty_url`

A LangChain v1 block {"type":"file","file_id":"\_\_REDACTED\_\_","url":""}: no reference in it is usable, so its file_id makes it the native file part it has the shape of, the file_id kept as written.

```json
{"type":"file","modality":"document","file_id":"__REDACTED__"}
```

#### `langchain_v1_file_with_a_file_id_that_is_not_a_string_and_a_url`

A LangChain v1 block {"type":"file","file_id":5,"url":"https://example.com/a.wav"}: it holds a string url, so it is a v1 block, not a native file part left as it came, and its url makes a uri.

```json
{"type":"uri","modality":"audio","uri":"https://example.com/a.wav"}
```

#### `langchain_v1_text_plain_by_base64`

A LangChain v1 block {"type":"text-plain","base64":"aGk=","mime_type":"text/plain"}: a text-plain block by base64 is a document blob.

```json
{"type":"blob","modality":"document","mime_type":"text/plain","byte_size":2,"stripped_reason":"not_captured"}
```

#### `langchain_v1_image_by_a_url_led_by_whitespace`

A LangChain v1 block {"type":"image","url":" data:image/png;base64,iVBO\nRw0KGgo="}: the url holds data: but is no data URL, so it is a blob with no byte_size, and no byte of the data URL is kept.

```json
{"type":"blob","modality":"image","stripped_reason":"not_captured"}
```

#### `langchain_v1_image_by_a_url_led_by_a_tab`

A LangChain v1 block {"type":"image","url":"\tdata:image/png,%89PNG"}: led by a tab, the percent-encoded data URL is a blob too.

```json
{"type":"blob","modality":"image","stripped_reason":"not_captured"}
```

#### `langchain_v1_file_by_an_https_url_led_by_a_space`

A LangChain v1 block {"type":"file","url":" https://example.com/a.pdf"}: a url that holds no data: is a uri, its value kept as it came, the space included.

```json
{"type":"uri","modality":"document","uri":" https://example.com/a.pdf"}
```

#### `langchain_v1_image_by_a_data_url_with_a_trailing_space`

A LangChain v1 block {"type":"image","url":"data:image/png;base64,iVBORw0KGgo= "}: it starts with the data scheme, but rule (b)'s pattern does not match all of it, so it is a data URL that is not base64: a blob with no byte_size.

```json
{"type":"blob","modality":"image","mime_type":"image/png","stripped_reason":"not_captured"}
```

#### `langchain_v1_image_by_a_wrapped_data_url`

A LangChain v1 block {"type":"image","url":"data:image/png;base64,iVBO\nRw0KGgo="}: a base64 run wrapped at a newline goes on over the next line, so rule (b)'s pattern matches the whole url and it is a blob with its size.

```json
{"type":"blob","modality":"image","mime_type":"image/png","byte_size":8,"stripped_reason":"not_captured"}
```

#### `langchain_v1_file_by_a_url_led_by_whitespace_and_an_empty_file_id`

A LangChain v1 block {"type":"file","file_id":"","url":" data:image/png;base64,iVBORw0KGgo="}: the url is usable and wins over the empty file_id, and since it holds data: it is a blob.

```json
{"type":"blob","modality":"document","stripped_reason":"not_captured"}
```

#### `langchain_v1_file_by_empty_file_id_and_empty_base64`

A LangChain v1 block {"type":"file","file_id":"","base64":""}: an empty base64 is no usable reference, so it does not beat the empty file_id, and the block is a native file part.

```json
{"type":"file","modality":"document","file_id":""}
```

#### `langchain_v1_file_by_empty_file_id_and_redacted_base64`

A LangChain v1 block {"type":"file","file_id":"","base64":"\_\_REDACTED\_\_"}: a \_\_REDACTED\_\_ base64 is no usable reference either.

```json
{"type":"file","modality":"document","file_id":""}
```

#### `langchain_v1_image_by_redacted_base64`

A LangChain v1 block {"type":"image","base64":"\_\_REDACTED\_\_"}: \_\_REDACTED\_\_ is valid base64, and with no file block's file_id beside it, it is a 9-byte blob as any bare base64 payload is.

```json
{"type":"blob","modality":"image","byte_size":9,"stripped_reason":"not_captured"}
```

#### `langchain_v1_audio_by_empty_base64`

A LangChain v1 block {"type":"audio","base64":""}: an empty bare base64 payload is 0 bytes, never redacted_upstream.

```json
{"type":"blob","modality":"audio","byte_size":0,"stripped_reason":"not_captured"}
```

#### `langchain_v1_file_by_a_relative_url`

A LangChain v1 block {"type":"file","url":"a.png"}: a url with no scheme is a uri as it came, its modality from the extension.

```json
{"type":"uri","modality":"image","uri":"a.png"}
```

#### `langchain_v1_image_by_a_rooted_relative_url`

A LangChain v1 block {"type":"image","url":"/img/a.png"}: a relative url is a uri as it came.

```json
{"type":"uri","modality":"image","uri":"/img/a.png"}
```

#### `langchain_v1_image_by_a_link_followed_by_a_data_url`

A LangChain v1 block {"type":"image","url":"https://example.com/a.png\ndata:image/png;base64,iVBO\nRw0KGgo="}: an https url that holds data: is a blob, so the run past the newline is not kept.

```json
{"type":"blob","modality":"image","stripped_reason":"not_captured"}
```

#### `uri_led_by_whitespace_holding_a_data_url`

A native uri part {"type":"uri","modality":"image","uri":" data:image/png;base64,iVBO\nRw0KGgo="}: its uri holds data: but is no data URL, so it is a blob with no byte_size, its modality kept.

```json
{"type":"blob","modality":"image","stripped_reason":"not_captured"}
```

#### `uri_that_is_a_percent_encoded_data_url`

A native uri part whose uri is a data URL percent-encoded whole, its scheme in upper case: a sized blob under the data URL rules, its media type percent-decoded.

```json
{"type":"blob","modality":"audio","mime_type":"audio/wav","byte_size":4,"stripped_reason":"not_captured"}
```

#### `uri_that_is_a_data_url_and_one_final_line_break`

A native uri part whose uri is a base64 data URL and one final newline: a sized blob under the data URL rules.

```json
{"type":"blob","modality":"audio","mime_type":"audio/wav","byte_size":4,"stripped_reason":"not_captured"}
```

#### `image_url_by_a_link_followed_by_a_data_url`

An OpenAI image_url item whose url is an https link with a wrapped data URL on the next line: it holds data: but is no data URL, so it is a blob with no byte_size, image by the item's kind, and no byte of the link or the data URL is kept.

```json
{"type":"blob","modality":"image","stripped_reason":"not_captured"}
```

#### `image_url_by_a_url_led_by_whitespace`

An OpenAI image_url item whose url is a data URL led by a space: no data URL, so a blob with no byte_size.

```json
{"type":"blob","modality":"image","stripped_reason":"not_captured"}
```

#### `image_url_by_a_wrapped_uppercase_data_url`

An OpenAI image_url item whose url is a base64 data URL, its scheme in upper case and its run wrapped at a newline: rule (b)'s pattern matches all of it, so it is a blob with its own mime type and size.

```json
{"type":"blob","modality":"image","mime_type":"image/png","byte_size":8,"stripped_reason":"not_captured"}
```

#### `image_url_by_a_plain_link`

An OpenAI image_url item whose url is an https link that holds no data: is a uri, its link kept.

```json
{"type":"uri","modality":"image","uri":"https://example.com/a.png"}
```

#### `image_url_by_a_link_with_data_colon_in_its_path`

An OpenAI image_url item whose url is https://e/metadata:x.png: the search for data: has no word boundary, so it is a blob, the link lost (the false positive ruled acceptable, as for a LangChain v1 url).

```json
{"type":"blob","modality":"image","stripped_reason":"not_captured"}
```

#### `image_url_by_a_whole_data_url`

An OpenAI image_url item whose url is a base64 data URL rule (b) matches whole: a sized blob, as before.

```json
{"type":"blob","modality":"image","mime_type":"image/jpeg","byte_size":10,"stripped_reason":"not_captured"}
```

#### `image_url_by_a_data_url_that_ends_in_one_line_break`

An OpenAI image_url item whose url is a base64 data URL and one final newline, as base64.encodebytes writes it: rule (b)'s pattern matches all of it but that line break, so it is a sized blob, as the strip sizes it.

```json
{"type":"blob","modality":"image","mime_type":"image/png","byte_size":8,"stripped_reason":"not_captured"}
```

#### `vercel_image_by_a_wrapped_data_url_that_ends_in_one_line_break`

A Vercel image part whose image is a base64 data URL wrapped at a carriage return and newline, with one final carriage return and newline: a sized blob.

```json
{"type":"blob","modality":"image","mime_type":"image/png","byte_size":8,"stripped_reason":"not_captured"}
```

#### `image_url_by_a_data_url_that_ends_in_two_line_breaks`

An OpenAI image_url item whose url is a base64 data URL and two final newlines: no whole match, so it is a blob with no byte_size, its mime type read up to the first ; as for a data URL that is not base64.

```json
{"type":"blob","modality":"image","mime_type":"image/png","stripped_reason":"not_captured"}
```

#### `image_url_by_a_whole_percent_encoded_data_url`

An OpenAI image_url item whose url is a data URL percent-encoded whole, as encodeURIComponent writes it: a data URL, so a blob with its media type and run percent-decoded, as rule (b) sizes it, never a uri.

```json
{"type":"blob","modality":"image","mime_type":"image/png","byte_size":8,"stripped_reason":"not_captured"}
```

#### `vercel_image_by_a_percent_encoded_data_url_that_ends_in_one_line_break`

A Vercel image part whose image is a data URL percent-encoded whole in lower-case hex, and one final newline: it has no URL scheme but is a data URL, so it is a sized blob, not base64.

```json
{"type":"blob","modality":"image","mime_type":"image/png","byte_size":8,"stripped_reason":"not_captured"}
```

#### `image_url_by_a_partly_percent_encoded_data_url`

An OpenAI image_url item whose url is data%3Aimage%2Fpng;base64,..., its colon and slash encoded and its ; and comma kept: percent_pattern does not match it, so once each %XX is decoded it is read as a data URL that rule (b) does not match, a blob with its media type and no byte_size.

```json
{"type":"blob","modality":"image","mime_type":"image/png","stripped_reason":"not_captured"}
```

#### `image_url_by_a_link_holding_a_percent_encoded_data_url`

An OpenAI image_url item whose url is a proxy link holding a percent-encoded data URL in its query, and no data:: a uri, its link kept as it came. The strip then replaces the encoded data URL inside it, where it sits.

```json
{"type":"uri","modality":"image","uri":"https://proxy.example/fetch?u=data%3Aimage%2Fpng%3Bbase64%2CiVBORw0KGgo%3D&w=1"}
```

#### `input_image_by_a_link_followed_by_a_percent_encoded_data_url`

An OpenAI input_image whose image_url is a link followed by a percent-encoded data URL: a blob with no byte_size.

```json
{"type":"blob","modality":"image","stripped_reason":"not_captured"}
```

#### `anthropic_url_source_by_a_link_followed_by_a_data_url`

An Anthropic image by a url source with the media_type image/png, whose url is a link followed by an upper-case data URL: a blob keeping the item's MIME type.

```json
{"type":"blob","modality":"image","mime_type":"image/png","stripped_reason":"not_captured"}
```

#### `anthropic_document_url_source_by_a_link_followed_by_a_data_url`

An Anthropic document by a url source, with no media_type, whose url holds a data URL after a link: a document blob, by the item's kind.

```json
{"type":"blob","modality":"document","stripped_reason":"not_captured"}
```

#### `input_file_by_a_link_followed_by_a_data_url`

An OpenAI input_file whose file_url is a link followed by a wrapped data URL, with the filename scan.png: a blob whose modality the filename names.

```json
{"type":"blob","modality":"image","stripped_reason":"not_captured"}
```

#### `input_file_by_a_file_url_led_by_whitespace`

An OpenAI input_file whose file_url is a data URL led by a tab, with no filename: a document blob.

```json
{"type":"blob","modality":"document","stripped_reason":"not_captured"}
```

#### `gemini_file_data_by_a_link_followed_by_a_data_url`

A Gemini file_data whose file_uri is a gs link followed by a wrapped data URL, with the mime_type image/png: a blob keeping it.

```json
{"type":"blob","modality":"image","mime_type":"image/png","stripped_reason":"not_captured"}
```

#### `gemini_file_data_by_a_plain_link`

A Gemini file_data whose file_uri is gs://bucket/a.wav, with no mime_type: a uri, its modality from the extension.

```json
{"type":"uri","modality":"audio","uri":"gs://bucket/a.wav"}
```

#### `vercel_file_by_a_link_followed_by_a_data_url`

A Vercel file part with the mediaType application/pdf whose data is a link followed by a wrapped data URL: a blob keeping the mediaType.

```json
{"type":"blob","modality":"document","mime_type":"application/pdf","stripped_reason":"not_captured"}
```

#### `vercel_file_by_a_url_tag_holding_a_data_url_after_a_link`

A Vercel file part whose data is v7's {"type":"url"} data holding a link followed by an upper-case percent-encoded data URL, with no mediaType: a document blob, since its URL has no path to read an extension from.

```json
{"type":"blob","modality":"document","stripped_reason":"not_captured"}
```

#### `vercel_image_by_a_link_followed_by_a_data_url`

A Vercel image part whose image is a link followed by a wrapped data URL: an image blob.

```json
{"type":"blob","modality":"image","stripped_reason":"not_captured"}
```

#### `openinference_image_url_by_a_link_followed_by_a_data_url`

The image url OpenInference flattens (message_content.image.image.url beside message_content.type image), holding a link followed by a wrapped data URL: an image blob.

```json
{"type":"blob","modality":"image","stripped_reason":"not_captured"}
```

#### `openinference_image_url_by_a_data_url_with_a_media_type`

The image url OpenInference flattens, a base64 data URL that names no media type, beside the flattened image media_type image/jpeg: the media_type is the MIME hint, so the blob is image/jpeg with its size. A data URL that names a valid media type keeps its own.

```json
{"type":"blob","modality":"image","mime_type":"image/jpeg","byte_size":10,"stripped_reason":"not_captured"}
```

#### `openinference_image_url_by_a_link_holding_a_data_url_with_a_media_type`

The image url OpenInference flattens, a link followed by a data URL, beside the flattened image media_type image/png: a blob with no byte_size that keeps the media_type as its MIME type.

```json
{"type":"blob","modality":"image","mime_type":"image/png","stripped_reason":"not_captured"}
```

#### `openinference_image_url_by_a_link_with_a_media_type`

The image url OpenInference flattens, an https link that holds no data:, beside the flattened image media_type image/webp: a uri with that MIME type.

```json
{"type":"uri","modality":"image","mime_type":"image/webp","uri":"https://example.com/a"}
```

#### `only_the_part_is_replaced`

A spaced message value holding a native blob with content and a MIME type, and no modality.

Input:

```json
[ {"role": "user", "parts": [ {"type": "blob", "content": "QUJD", "mime_type": "image/png"} ] } ]
```

Output:

```json
[ {"role": "user", "parts": [ {"type":"blob","modality":"image","mime_type":"image/png","byte_size":3,"stripped_reason":"not_captured"} ] } ]
```

#### `file_part_by_a_url_led_by_whitespace_holding_a_data_url`

An object of type file with a string url is a LangChain v1 file block, not a native file part, on this path too. Its url holds data: but is no data URL, so it is a blob with no byte_size.

Input:

```json
[ {"role": "user", "parts": [ {"type": "file", "url": " data:image/png;base64,iVBO\nRw0KGgo="} ] } ]
```

Output:

```json
[ {"role": "user", "parts": [ {"type":"blob","modality":"document","stripped_reason":"not_captured"} ] } ]
```

#### `file_part_with_an_empty_file_id_and_a_url`

The usable url wins over the empty file_id, so the object is a uri, not a native file part with an empty file_id.

Input:

```json
[ {"role": "user", "parts": [ {"type": "file", "file_id": "", "url": "https://example.com/a.pdf"} ] } ]
```

Output:

```json
[ {"role": "user", "parts": [ {"type":"uri","modality":"document","uri":"https://example.com/a.pdf"} ] } ]
```

#### `file_part_with_a_file_id_that_is_not_a_string_and_a_url`

A file_id that is not a string would leave a native file part as it came, but the string url makes the object a v1 file block, so it is a uri, its modality from the extension.

Input:

```json
[ {"role": "user", "parts": [ {"type": "file", "file_id": 5, "url": "https://example.com/a.wav"} ] } ]
```

Output:

```json
[ {"role": "user", "parts": [ {"type":"uri","modality":"audio","uri":"https://example.com/a.wav"} ] } ]
```

#### `file_part_with_a_redacted_file_id_and_base64`

The string base64 makes the object a v1 file block, and as a usable reference it wins over the \_\_REDACTED\_\_ file_id, so it is a blob of 3 bytes.

Input:

```json
[ {"role": "user", "parts": [ {"type": "file", "file_id": "__REDACTED__", "base64": "QUJD"} ] } ]
```

Output:

```json
[ {"role": "user", "parts": [ {"type":"blob","modality":"document","byte_size":3,"stripped_reason":"not_captured"} ] } ]
```

#### `vercel_file_part_with_unreadable_data_makes_no_part`

Vercel file and image parts whose data is no string (an object with no tag, a number, a v7 text tag whose text is a number) make no part: the message keeps its other parts.

Input (ai.prompt.messages):

```json
[{"role":"user","content":[{"type":"text","text":"Look:"},{"type":"file","mediaType":"image/png","data":{"0":1}},{"type":"image","image":7},{"type":"file","mediaType":"text/plain","data":{"type":"text","text":7}}]}]
```

Output (gen_ai.input.messages):

```json
[{"role":"user","parts":[{"type":"text","content":"Look:"}]}]
```

#### `openllmetry_langchain_v1_reference_blocks`

OpenLLMetry writes a message's content blocks as JSON in gen_ai.prompt.N.content. LangChain v1 blocks by file_id and by url there are file and uri parts, never text parts.

Input (gen_ai.prompt.0.content, with `gen_ai.prompt.0.role` = `user`):

```json
[{"type":"text","text":"Compare these."},{"type":"file","file_id":"file-abc123"},{"type":"image","url":"https://example.com/a.png"},{"type":"audio","file_id":"__REDACTED__"}]
```

Output (gen_ai.input.messages):

```json
[{"role":"user","parts":[{"type":"text","content":"Compare these."},{"type":"file","modality":"document","file_id":"file-abc123"},{"type":"uri","modality":"image","uri":"https://example.com/a.png"},{"type":"blob","modality":"audio","stripped_reason":"redacted_upstream"}]}]
```

#### `laminar_langchain_v1_reference_blocks`

Laminar writes the same keys on an LLM span (lmnr.span.type LLM), and its blocks are read the same way.

Input (gen_ai.prompt.0.content, with `gen_ai.prompt.0.role` = `user`, with `lmnr.span.type` = `LLM`):

```json
[{"type":"text","text":"Read this."},{"type":"file","file_id":"file-abc123","mime_type":"application/pdf"},{"type":"file","url":"https://example.com/a.wav"}]
```

Output (gen_ai.input.messages):

```json
[{"role":"user","parts":[{"type":"text","content":"Read this."},{"type":"file","modality":"document","mime_type":"application/pdf","file_id":"file-abc123"},{"type":"uri","modality":"audio","uri":"https://example.com/a.wav"}]}]
```

## Raw payloads

**Source rule.** Normalized message parts come only from message keys: gen_ai.input.messages, gen_ai.output.messages and gen_ai.system_instructions, or the flattened instrumentor message keys each normalizer already maps (OpenInference llm.input_messages.\* and llm.output_messages.\*, OpenLLMetry gen_ai.prompt.\* and gen_ai.completion.\*, Vercel ai.prompt.messages). Raw request and response payloads are never mined to rebuild parts.

Message keys (a key ending in `.` is a prefix): `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`, `llm.input_messages.`, `llm.output_messages.`, `gen_ai.prompt.`, `gen_ai.completion.`, `ai.prompt.messages`.

Raw payloads, never mined for parts: `input.value`, `output.value`, `lmnr.span.input`, `lmnr.span.output`, `ai.prompt`, `pydantic_ai.all_messages`, `InputValue`, `OutputValue`.

**Strip rule.** Each media token (found by the detection rules below) is replaced in place. Every other byte of the string stays identical: normalizers must not parse and re-serialize the JSON. Byte equality across the Python SDK, the TypeScript SDK and the Go sink depends on this. Message parts in gen_ai.\*.messages keep the stripped blob part shape instead; the replacement string is only for raw payloads.

**Scope.** The SDKs strip every string value, and every element of a string-array value, of the span attributes, the span event attributes and the span link attributes. They do not strip resource or scope attributes: a span processor cannot rewrite them. The sink applies the same rules to its stored columns InputValue, OutputValue, InputMessages and OutputMessages and to the values of SpanAttributes. tools/check_fixtures.py scans more than the strip covers: it also scans the resource and scope attributes of a recording. That scan is a check, not a strip rule, and media in those attributes would still be a bug. An SDK may bound the work it spends on one very large value. Past that bound no media survives, but byte identity with the other implementations is not promised.

**Order.** A normalizer first builds parts from the message keys (the source rule). Stripping runs last, over every string attribute in scope, including the message-key attributes it keeps and the gen_ai.\*.messages it produced. A stripped blob part carries no content, so nothing in it matches; a text part holding a data URL gets rule (b) in place. So in a message key (and in the sink's InputMessages and OutputMessages columns) a blob part never has a content member, while in any other attribute or column a blob part's content may be a complete replacement, the one rule (e) writes there. The fixture check holds expected results to exactly this: a normalized blob part carries no content. Within one pass, every rule reads the text as it was before the pass: rule (e) takes its context and its mime type from each object's member values as they were, never from a sibling the same pass has already rewritten (see members). A walker that rewrites the document in place must keep reading the original values.

**JSON candidates.** A string value is a JSON candidate when, after trimming leading space, tab, newline and carriage return (ASCII only: U+00A0 and other Unicode spaces are not trimmed), it starts with `{` or `[`. A candidate parses when the whole string is one RFC 8259 JSON value, with only those four whitespace characters around it (no NaN, Infinity, comments or trailing commas; duplicate keys are allowed, and every one is read, see members), nested at most 64 levels deep. Arrays and objects count together, from the candidate's root: the root array or object is level 1, and a candidate nested deeper than 64 levels does not parse. A JSON document in a string inside JSON continues the same count: its root is one level below the deepest array or object holding that string, so a nested document that goes past 64 does not parse (rule (b) only, for it), while the document around it still does. The limit is explicit: an implementation counts the depth itself and never relies on its parser's or its language's recursion limit, so no input makes the strip fail. When it parses, rules (d), (e) and (b) apply to the values inside it; a string value inside it that is itself a JSON candidate is processed by the same rules, recursively, at its escaped location, its own document starting with no parent key and no enclosing object: nothing outside it is context for rule (e), and rule (d) inside it takes no mime type from outside. When it does not parse (a truncated payload, say), only rule (b) applies, to the string as it is (for a string inside JSON, to its unescaped value), with escaped_pattern in place of pattern: the text still holds the JSON escapes of the strings in it, so a run there also goes on over a line break written as an escape (`\n`, or `\r\n`), and a wrapped payload in a truncated JSON string is replaced whole. A string that is not a candidate gets rule (b) only, with pattern. Object keys are never matched.

**Precedence.** Values are visited in document order. At each value rule (d) is tried, then (e), then (b), and the first that matches wins. A value inside a replaced token is never visited: once (e) replaces a string, (b) does not look inside it, and nothing inside a replaced Buffer object is looked at. An array element inherits the parent key of its array, so `{"audio":[{"data":"..."}]}` matches (e) through the parent key audio; in the same way, the enclosing object rule (d) takes its mime type from is the nearest object holding the Buffer, directly or through arrays, and so is the holder whose mime type a typed key with holder_mime reads. A typed key with keeps_urls leaves a string that starts with a URL scheme to (b) only when it holds no data: (in any ASCII case), or when (b)'s pattern matches the whole unescaped string, or all of it but one final line break (a newline, or a carriage return and newline, as base64.encodebytes ends its output): such a string is no (e) token, so (b) is tried on it, and a base64 data URL that is the whole value is replaced with its own mime type and size, its final line break included (see spans), while any other URL stays. A string that starts with data%3A has no URL scheme, but that key leaves it to (b) too when percent_pattern matches all of it, or all of it but one final line break, raw or percent-encoded (%0A, or %0D%0A). Any other string under such a key that holds data%3A, and no data:, is left to (b) like any URL: (b) replaces a percent-encoded data URL in a link where it sits. Any other string under that key that holds data: (a data URL whose payload is percent-encoded, data:image/png,%89PNG, a run (b) stops short in, a link with a data URL after it) is an (e) token, replaced whole with the key's usual mime type (see rule (e)), as the part rules make such a value a blob.

**Idempotence.** Every implementation follows this rule: a string that is already a complete replacement, `[stripped <mime> <byte_size> bytes]` whose mime is unknown or matches mime_pattern in full (exactly the mimes a replacement can hold) and whose byte_size is ASCII digits or unknown, is never stripped again, by rule (e) or rule (b). Nor is a complete replacement ever context for rule (e): as the value of a sibling (a mime key, format or output_format) it counts neither for whether rule (e) fires nor for the mime type it chooses. So a Buffer that rule (d) turned into a replacement in one pass (`{"mediaType": {"type":"Buffer","data":[1]},"data":"QUFB"}`) makes no token of its siblings in the next. With both, strip(strip(x)) is strip(x) for every x except one class: a JSON candidate that does not parse before pass 1 and does parse after it. Elsewhere the sink re-strips what an SDK already stripped and gets the same bytes. In that class a second pass may strip more. It needs malformed JSON whose only defect sits inside a rule (b) data URL (an invalid escape such as `\d` in a mime type): pass 1 can only apply rule (b), which removes the defect, and pass 2 then parses the candidate and rules (d) and (e) fire on what pass 1 left, a partial replacement for instance. No media survives in either pass, and only the replacement text differs. See `a_second_pass_after_the_candidate_starts_to_parse`. A string that only looks like one is still a token: `[stripped image/png lots bytes]`, or `[stripped a b 3 bytes]` (rule e), or `[stripped data:image/png;base64,... 1 bytes]`, whose data URL rule (b) replaces.

**Spans.** Every span is on the original text; nothing is re-serialized. (d) The object token, from its `{` to its matching `}`, is replaced by the replacement as a JSON string literal, quotes included. (e) The string literal, quotes included, is replaced by the replacement as a JSON string literal, quotes included. (b) In a JSON string, only the URL's characters are replaced: the replacement goes inside the existing quotes, with no quotes added. Under a key that keeps URLs, a value that is one data URL and one final line break is replaced whole, line break included, inside its quotes, so it becomes a complete replacement. (b) In a string that is not JSON (or did not parse), the URL's characters are replaced by the replacement, with no quotes. Rules (b) and (e) read a JSON string's unescaped value, so a span starts at the first raw character of its first character and ends after the last raw character of its last, escapes included (`data:image\/png` is read as `data:image/png`). Text written into a JSON string is escaped for its level with the minimal escapes JSON.stringify writes, and no others: `\"` for a quote, `\\` for a backslash, `\b` `\f` `\n` `\r` `\t`, `\u00xx` (lowercase hex) for any other control character, `\udxxx` for a lone surrogate. In a JSON string nested in a JSON string, the inner replacement is escaped once per level, and every byte outside the replaced tokens is kept as it was, including escapes the re-encoder would not write (`\u0022`, `\/`).

**Byte size.** Rule (e) computes it on the string's unescaped value, and rule (b) on its base64 run, the same way. Remove space, tab, newline and carriage return, and for rule (b) also each `>` (the quote marker its run goes on over) and each escaped line break escaped_pattern's run goes on over (a backslash, an optional `r`, an optional backslash, then `n`). A percent-encoded data URL's run is percent-decoded first, its hex digits in either case: `%2B`, `%2F` and `%3D` are `+`, `/` and `=`, and the encoded line breaks `%0A` and `%0D` are a newline and a carriage return, removed with the rest. `%0B`, `%0F` and `%2A` decode to characters no base64 holds, so a run with one is unknown, and `%2D` is `-`. When what is left is not valid base64, byte_size is unknown. Valid means: every character before the padding is from one alphabet, `A-Z a-z 0-9 + /` or `A-Z a-z 0-9 - _` (never `+` or `/` together with `-` or `_`); the padding is at most two `=`, only at the end; and the length, padding counted, is a multiple of 4 (so unpadded base64 is not valid). For valid base64, byte_size is length times 3 / 4, minus the number of `=`. Rule (d) takes the length of its data array.

**Members.** Every member of an object is visited, in document order, duplicate keys included. A condition on a key holds when any member with that key meets it (a type equal to Buffer, blob or base64 or to one of a typed key's types, a non-empty data array, a sibling), and a value read from a key (a mime type, a format, a Buffer's data array) is that of the first member with that key, in document order, that qualifies. Rule (e) applies to each member under one of its keys that qualifies, duplicates included, all with the context and mime type computed from all the siblings: `{"mediaType":"image/png","data":"QUFB","data":"QkJC"}` strips both data values. A sibling counts as context only when its value is a non-empty string that is not a complete replacement (see idempotence), the same rule as mime selection. Context and mime type are read from the member values as they were before the pass, so document order does not matter: in `{"mediaType":"data:image/png;base64,QUFB","data":"QkJC"}` mediaType is context, though rule (b) rewrites it in the same pass, and data is a token whichever comes first; its mime type is unknown, since the original mediaType is not a valid mime. `format` is not a sibling key: it counts only under the parent key input_audio or audio (which is context already), where it names audio/&lt;format&gt;, and elsewhere a format sibling is ignored; output_format counts anywhere. The mime type is chosen by the order of the mime key list, not by document order: the first mime key in list order whose value is a non-empty valid mime (see replacement) wins; else the first mime format, in order, whose sibling is a non-empty string, not a complete replacement, and whose mime is valid; else unknown. When a rule (e) key holds an array directly, each string element is its own token (when it is non-empty and not already a complete replacement), with the same context and mime type; any other element is visited as usual, with that key as its parent key.

**Regex dialect.** The pattern of rule (b), rule (e)'s url_scheme and the replacement's mime_pattern use only constructs Python re, JavaScript RegExp and Go RE2 read the same way: literal characters, character classes with explicit ASCII members and ranges, the escapes `\t` `\n` `\f` `\r`, capturing groups, and the quantifiers `*`, `+` and `{m,n}`. No `\s`, `\d`, `\w`, `\b`, `?`, lookaround, backreference, non-capturing group, alternation or inline flag: the case-insensitive scheme is written `[dD][aA][tT][aA]:`, an optional carriage return `\r{0,1}`, and the repeated RFC 2397 parameter and the repeated continuation line are capturing groups. Neither the mime class nor the parameter class holds `;` or `:`. RFC 2045 lists `:` as a tspecial, so it cannot appear in an unquoted mime type or parameter token. Rule (b) finds its tokens this way: cut the string before each `data:` and each `data%3A` (in any ASCII case, `[dD][aA][tT][aA]:` and percent_scheme searched left to right; no two overlap), and try the pattern once at the start of each piece that starts with `data:`, and percent_pattern at the start of each that starts with `data%3A`, never past its end (Python `pattern.match(text, start, end)`, or `^` before it on the piece in JavaScript and Go). A decoded header holds no colon but may hold %, so a data URL whose header holds data%3A is cut there and is no token: a header no encoder writes. Each piece that matches gives one token, so tokens never overlap and a run that continues over a line break never takes the start of the next data URL (`...;base64,QUFB\ndata:...` is two tokens). The search is linear: each character is in one piece and read by one attempt, the mime type and parameters split in exactly one way, and once `;base64,` is read the rest of the pattern cannot fail, so the run is taken greedily with no backtracking into it. The run's first line is capped by `{0,76}`, so line breaks are crossed only after a first line of at most 76; a longer first line goes on in the last `[A-Za-z0-9+/_-]*` and ends the run at its line break. Continuation lines are not capped: a capped quantifier inside the repeated group makes V8 keep backtracking state for each character, and its regex stack then overflows on a few megabytes of wrapped input. `[ \t>]*` after a line break takes the indent of a block and the `>` of a quoted reply. escaped_pattern, for a JSON candidate that does not parse, is pattern with a second repeated group after the first: a line break written as a JSON escape, `\\r{0,1}\\{0,1}n` (a backslash, an optional `r`, an optional backslash, then `n`), then the same indent and more base64. It is found the same way, cut at each data:. The two groups start with different characters, so the run still splits in one way. Raw line breaks come first and escaped ones after them, never the other way. The escaped break holds no group: written exactly, as `\\(r\\){0,1}n`, a group inside the repeated group lowers V8's regex stack limit for `\r\n` to about 0.93M wrapped lines, from about 1.66M. The loose form also takes `\rn` and `\\n`, which no encoder writes after a base64 line. percent_pattern is linear too: a header escape is never one whose second digit is C, so the header stops at the %2C of %3Bbase64%2C, and backtracking to find %3Bbase64 reads only the header. Each % starts one repetition of a group, so the header and the run each split in exactly one way, and once %2C is read nothing after it can fail. The run's escape class `%[02][ABDFabdf]` (the line breaks %0A and %0D, `+` %2B and `/` %2F, and the harmless %0B, %0F, %2A and %2D) never starts with %3, so it never meets the padding %3D. mime_pattern must match the whole value: Python re.fullmatch, or `^` and `$` around it in JavaScript and Go (where, without the m flag, `$` is the end of the text; in Python `$` also matches before a final newline, so use fullmatch). url_scheme must match at the start of the unescaped value and need not reach its end: Python re.match, or `^` before it in JavaScript and Go. A keeps_urls key searches its value for `[dD][aA][tT][aA]:` anywhere, with no trimming. For that key, and wherever a part rule asks for rule (b)'s pattern to match a whole value, the pattern matches the whole value when its match anchored at the start (Python re.match, or `^` before it in JavaScript and Go) ends at the end of the value. A keeps_urls key also takes a match that ends one line break before the end, where what is left is exactly a newline, or a carriage return and newline, and so does a part rule; for percent_pattern, what is left may also be exactly `%0A` or `%0D%0A`, its hex digits in either case. Do not use re.fullmatch or `$` for rule (b): the greedy match reaches furthest, so they agree, but when a long value fails they try each way to share a line between `{0,76}` and the last `*`, many times slower in Python. A whole value that holds a second `data:` never matches, since the pattern holds no colon after the scheme.

**Implementers.** Do not write the replacement, or any escape, with a standard library JSON encoder: Go's json.Marshal, for example, writes `<`, `>`, `&` and U+2028 as `\u003c`, `\u003e`, `\u0026` and `\u2028`, which no other implementation writes. Do not compute byte_size with a strict standard library base64 decoder either: decoders differ on whitespace, URL-safe input and padding. The escaping rules (spans), the size rules (byte_size) and the mime rule (replacement) here are exhaustive: write exactly what they say, and keep every other byte as it was. Read JSON with a parser that keeps the span of every value on the text and every duplicate member (members), and that counts the depth itself (json_candidate).

**Reference.** generators/media_parts.py strip_raw_payload(raw, text) is the reference implementation: the one function a normalizer author reproduces. It returns the stripped string; strip(raw, text) also returns the tokens it replaced (rule, mime, byte_size), in document order. The golden examples below are its tests, and every normalizer's.

**Replacement.** The text `[stripped <mime> <byte_size> bytes]`, with `unknown` for a mime type or size that is not known: `[stripped image/png 67 bytes]`, `[stripped unknown unknown bytes]`. Rules (d) and (e) write it as a JSON string literal, quotes included; rule (b) writes the bare text, inside the quotes already there in a JSON string. A mime type goes in only when the whole of it matches `[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+` (token/token); anything else is `unknown`.

A data URL inside other text: only the token is replaced, so `see data:image/png;base64,iVBORw0KGgo= here` becomes `see [stripped image/png 8 bytes] here`.

| Token | Replaced | Mime | Byte size |
| -- | -- | -- | -- |
| A data URL (rule b), anywhere in a string, as it is or percent-encoded whole | The URL characters alone, from data: or data%3A (in any case) to the end of the base64 run, parameters included, with no quotes added. A run wrapped at a line break goes on over each next line that starts with base64, after any spaces, tabs or &gt;, when its first line holds at most 76 base64 characters, so nothing of a payload an encoder wrapped is left; a run percent-encoded whole goes on over each encoded line break (%0A, or %0D%0A) the same way. The text around it stays byte-identical; a string that is only the data URL becomes the replacement text. Under a key that keeps URLs, so does a string that is the data URL and one final line break (for one percent-encoded whole, also %0A or %0D%0A). In JSON that does not parse, the run also goes on over a line break written as an escape. | The URL's media type when it is token/token (percent-decoded first, for a data URL percent-encoded whole); unknown when it names none, or anything else. | The base64 run's size, per byte_size (percent-decoded first, for a data URL percent-encoded whole); unknown when the run is not valid base64. |
| A base64 string value (rule e) | The string literal, quotes included, by the replacement as a JSON string literal; for an array under the key, each string element the same way. | The first of media_type, mediaType, mime_type, mimeType, in that order, that holds a token/token mime; else image/&lt;output_format&gt;; else audio/&lt;format&gt; under input_audio or audio; else, under a typed key with holder_mime (a Vercel v7 tagged data), the enclosing object's first such mime key; else unknown. | The unescaped value's size, per byte_size; unknown when it is not valid base64. |
| A Buffer object (rule d) | The whole object token, from { to its matching }, by the replacement as a JSON string literal. | The first of the enclosing object's media_type, mediaType, mime_type, mimeType, in that order, that holds a token/token mime; else unknown. | The length of the data array. |

**Detection rules.** The normalizers strip, and tools/check_fixtures.py refuses
in an expected result, every token these find (in a string holding JSON too):

| Rule | Name | Matches | Parameters |
| -- | -- | -- | -- |
| (b) | data URL | A data:&lt;mime&gt;[;&lt;parameter&gt;]\*;base64,&lt;base64&gt; token anywhere in a string, the scheme in any case (DATA:, Data:) and RFC 2397 parameters allowed before ;base64, (data:image/png;name=a.png;base64,...). The base64 run may be wrapped: at a line break (a newline, or a carriage return and a newline) followed by any spaces, tabs or &gt; (an indented block or a quoted reply) and more base64, the run goes on, line after line, as base64.encodebytes, MIME and PEM encoders write it, and ends at the padding or at the first character that is no base64. It goes on over line breaks only when its first line, counted from ;base64,, holds at most 76 base64 characters, the most RFC 2045 lets a MIME line hold and what every wrapping encoder writes or less. A real image as a single-line data URL is far longer, so the prose after it stays whole. The cost: a tiny unpadded data URL (a run of 76 characters or fewer, about 57 bytes or less) at the end of a line takes each next line that starts with base64 with it, whatever that line's length, up to its first character that is no base64; and a payload wrapped wider than 76 keeps everything after its first line. A padded run ends at its padding. The pattern finds each one, tried at each data: and never past the next (see regex_dialect): group 1 the mime type (empty when none), group 2 the last parameter (unused), group 3 the base64 run (standard or URL-safe), its line breaks included, group 4 its last continuation line (unused). A whole-string data URL is the special case. In the text of a JSON candidate that does not parse, escaped_pattern is tried instead: the same, but after its raw line breaks the run also goes on over line breaks written as JSON escapes (\n, or \r\n, as a backslash and a letter), with the same first-line guard; its group 5 is its last escaped continuation line (unused). A data URL percent-encoded whole, as a link carries one in its query (data%3Aimage%2Fpng%3Bbase64%2CiVBOR...%3D), is a token too, anywhere and under any key, by percent_pattern: its scheme data%3A in any ASCII case, a header of any characters but %, ;, comma, colon, ASCII whitespace and the quote, or percent escapes but those whose second digit is C (so %2C ends it), then %3Bbase64%2C, then a run of base64 characters and the escapes %2B and %2F and the line breaks %0A and %0D (the class %[02][ABDFabdf], so also the harmless %0B, %0F, %2A and %2D), ended by at most two %3D. The hex digits are in either case, and a / may be written as it is, as Python's quote leaves it. Group 1 is the header: its media type is the header up to its first %3B, percent-decoded. Group 3 is the run, sized once its escapes are decoded and its line breaks removed. Groups 2, 4 and 5 are unused. So a payload wrapped before it was percent-encoded (quote of base64.encodebytes output) is one token, as a wrapped data URL is; with no first-line guard, a tiny unpadded run followed by %0A and more encoded base64 takes it too, only inside an encoded string. The run takes no other escape, and a twice-encoded data URL (data%253A) is no token. Every match holds base64%2, a literal a pre-check can look for. | pattern: `[dD][aA][tT][aA]:([^;,:\t\n\f\r "]*)(;[^;,:\t\n\f\r "]*)*;base64,([A-Za-z0-9+/_-]{0,76}(\r{0,1}\n[ \t>]*[A-Za-z0-9+/_-]+)*[A-Za-z0-9+/_-]*={0,2})`; percent_scheme: `[dD][aA][tT][aA]%3[aA]`; percent_pattern: `[dD][aA][tT][aA]%3[aA]([^%;,:\t\n\f\r "]*(%[0-9A-Fa-f][0-9ABD-Fabd-f][^%;,:\t\n\f\r "]*)*)%3[bB]base64%2[cC]([A-Za-z0-9+/_-]*(%[02][ABDFabdf][A-Za-z0-9+/_-]*)*(%3[dD]){0,2})`; escaped_pattern: `[dD][aA][tT][aA]:([^;,:\t\n\f\r "]*)(;[^;,:\t\n\f\r "]*)*;base64,([A-Za-z0-9+/_-]{0,76}(\r{0,1}\n[ \t>]*[A-Za-z0-9+/_-]+)*(\\r{0,1}\\{0,1}n[ \t>]*[A-Za-z0-9+/_-]+)*[A-Za-z0-9+/_-]*={0,2})` |
| (d) | Buffer object | An object {"type": "Buffer", "data": [...]} whose data is a non-empty array. | type: `Buffer`; array_key: `data`; mime_keys: `media_type`, `mediaType`, `mime_type`, `mimeType` |
| (e) | keyed base64 string | A non-empty string (or each string of an array) under one of the keys, when its object has one of the sibling keys with a non-empty string value that is not a complete replacement, or its object's parent key is one of the parent keys, or its object is the value of a source key and has type base64 (the Anthropic {"source":{"type":"base64","media_type":...,"data":...}}: the object holding data is the source itself, not the content block around it); a non-empty string under content when its object has type blob (the semconv blob part, as in a raw payload like pydantic_ai.all_messages: the raw-payload twin of the fixture check's rule that a normalized blob part carries no content); a non-empty string under a typed key when its object has one of that key's types and, for a typed key that names parent keys, its object's parent key is one of them (a LangChain v1 standard content block {"type":"image","base64":...,"mime_type":...}, Mistral's audio chunk {"type":"input_audio","input_audio":...}, which its TypeScript SDK spells inputAudio, a Vercel image part {"type":"image","image":...}, or the v7 tagged data {"type":"data","data":...} a Vercel file part's data or image part's image holds); a non-empty string under one of the source bytes keys when its object is the value of a source key, whatever its type (the Bedrock Converse {"image":{"format":"png","source":{"bytes":...}}}: as for Anthropic, the object holding bytes is the source); and a non-empty string under one of a base64 marker's own keys when its object has the marker (a member with exactly the marker's key and string value, as in the LangChain v0 block {"type":"image","source_type":"base64","data":...}, whose marker reaches data and no other key). A typed key with holder_types counts only when the nearest object holding its object, through arrays, has one of those types: the v7 tagged data counts in a Vercel file or image part, never in a {"data":{"type":"data",...}} envelope of some other API. A typed key with keeps_urls leaves a string that starts with a URL scheme (url_scheme) to rule (b), whatever other way its key qualifies, when it holds no data: (searched anywhere, in any ASCII case) or rule (b)'s pattern matches the whole string, or all of it but one final line break (a newline, or a carriage return and newline): an http URL under a Vercel image stays, and a base64 data URL that is the whole value, wrapped or not, is replaced by rule (b) with its own mime type and size, a final line break with it, so the base64.encodebytes output of an image gets its size. A string that starts with data%3A, a data URL percent-encoded whole, is left to rule (b) the same way when rule (b)'s percent_pattern matches all of it, or all of it but one final line break, raw or percent-encoded (%0A, or %0D%0A). Any other string that holds data: (a data URL whose payload is percent-encoded, a run rule (b) stops short in, a link with a data URL after it) is a rule (e) token like any other, replaced whole with the key's usual mime type, so no byte of its payload survives. The search has no word boundary, so a link with data: in its path (https://e/metadata:x.png) is replaced too. A typed key with holder_mime takes its mime type, when its own object names none, from the mime keys of the nearest object holding it, as rule (d) does, so a tagged data reads its Vercel part's mediaType. Never a string that is already a complete replacement (see idempotence). See members for duplicate keys, siblings and arrays. | keys: `data`, `b64_json`, `result`, `base64`; sibling_keys: `media_type`, `mediaType`, `mime_type`, `mimeType`, `output_format`; parent_keys: `input_audio`, `audio`, `inline_data`, `inlineData`; source_key: `source`; source_type: `base64`; blob_type: `blob`; blob_key: `content`; base64_markers: `source_type` = `base64`, for `data`; typed_keys: `base64` under type `image`, `audio`, `video`, `file`, `text-plain`, `input_audio` under type `input_audio`, `inputAudio` under type `input_audio`, `image` under type `image` (keeps URLs), `data` under type `data` and parent key `data`, `image` in an object of type `file`, `image` (keeps URLs) (the holder's mime); url_scheme: `[A-Za-z][A-Za-z0-9+.-]*:`; source_bytes_keys: `bytes`; mime_keys: `media_type`, `mediaType`, `mime_type`, `mimeType`; mime_formats: `output_format` gives `image/<value>`, `format` gives `audio/<value>` under `input_audio`, `audio` |

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

#### `a_wrapped_data_url_in_json_that_does_not_parse`

The payload was cut off, so it does not parse, and rule (b) runs on the raw text, where a wrapped run's line breaks are the JSON escapes \n and \r\n. escaped_pattern takes them as line breaks, so each wrapped payload is replaced whole and gets its size: base64.encodebytes output with LF or CRLF (its final escaped line break stays, as rule (b) replaces the URL alone), and a quoted reply. The first-line guard holds as for a raw line break: a data URL longer than 76 characters on one line keeps the line after it.

Input:

```text
{"messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"data:image/png;base64,AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8gISIjJCUmJygpKissLS4vMDEyMzQ1Njc4\nOTo7\n"}},{"type":"image_url","image_url":{"url":"data:image/png;base64,AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8gISIjJCUmJygpKissLS4vMDEyMzQ1Njc4\r\nOTo7\r\n"}},{"type":"text","text":"> see data:image/png;base64,AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8gISIjJCUmJygpKissLS4vMDEyMzQ1Njc4\n> OTo7PD0=\n> Thanks"},{"type":"text","text":"data:image/png;base64,AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8gISIjJCUmJygpKissLS4vMDEyMzQ1Njc4OTo7\nThanks"},{"type":"text","text":"cut off
```

Output:

```text
{"messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"[stripped image/png 60 bytes]\n"}},{"type":"image_url","image_url":{"url":"[stripped image/png 60 bytes]\r\n"}},{"type":"text","text":"> see [stripped image/png 62 bytes]\n> Thanks"},{"type":"text","text":"[stripped image/png 60 bytes]\nThanks"},{"type":"text","text":"cut off
```

Tokens: (b) image/png, 60 bytes, (b) image/png, 60 bytes, (b) image/png, 62 bytes, (b) image/png, 60 bytes.

#### `an_escaped_line_break_outside_json_ends_the_run`

A string that is not a JSON candidate gets rule (b) by its pattern, which takes only a raw line break: a backslash and an n in prose end the run there, and what follows stays. escaped_pattern applies only to JSON that does not parse.

Input:

```text
see data:image/png;base64,AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8gISIjJCUmJygpKissLS4vMDEyMzQ1Njc4\nOTo7 here
```

Output:

```text
see [stripped image/png 57 bytes]\nOTo7 here
```

Tokens: (b) image/png, 57 bytes.

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

#### `a_null_sibling_is_not_context`

A sibling counts as context only when its value is a non-empty string (and format is not a sibling key at all), so data is left alone.

Input:

```text
{"data":"hello","format":null}
```

Output:

```text
{"data":"hello","format":null}
```

Tokens: none.

#### `format_is_ignored_outside_an_audio_parent`

A format sibling counts only under input_audio or audio; here it is ignored, so result is left alone.

Input:

```text
{"result":"hello","format":"text"}
```

Output:

```text
{"result":"hello","format":"text"}
```

Tokens: none.

#### `format_under_input_audio`

Under input_audio the parent key is the context, and format names audio/&lt;format&gt;.

Input:

```text
{"input_audio":{"data":"UklGRg==","format":"wav"}}
```

Output:

```text
{"input_audio":{"data":"[stripped audio/wav 4 bytes]","format":"wav"}}
```

Tokens: (e) audio/wav, 4 bytes.

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

Already-stripped text, stripped again: complete replacements are not tokens, so strip(strip(x)) is strip(x) (test_stripping_is_idempotent checks it for every golden output). [stripped image/png lots bytes] is not a complete replacement, so it is a token.

Input:

```text
{"source":{"type":"base64","media_type":"image/png","data":"[stripped image/png 8 bytes]"},"inline_data":{"data":"[stripped unknown unknown bytes]"},"text":"see [stripped image/png 8 bytes]","audio":{"data":"[stripped image/png lots bytes]"}}
```

Output:

```text
{"source":{"type":"base64","media_type":"image/png","data":"[stripped image/png 8 bytes]"},"inline_data":{"data":"[stripped unknown unknown bytes]"},"text":"see [stripped image/png 8 bytes]","audio":{"data":"[stripped unknown unknown bytes]"}}
```

Tokens: (e) unknown, unknown bytes.

#### `pydantic_ai_blob_part_in_all_messages`

A semconv blob part in a raw payload (pydantic_ai.all_messages): rule (e) replaces its content string in place, mime from mime_type. A text part's content is left alone.

Input:

```text
[{"role":"user","parts":[{"type":"text","content":"What is in this image?"},{"type":"blob","mime_type":"image/png","modality":"image","content":"iVBORw0KGgo="}]}]
```

Output:

```text
[{"role":"user","parts":[{"type":"text","content":"What is in this image?"},{"type":"blob","mime_type":"image/png","modality":"image","content":"[stripped image/png 8 bytes]"}]}]
```

Tokens: (e) image/png, 8 bytes.

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

#### `depth_64_parses`

62 arrays, the object and its source object are 64 levels, the limit. It parses, so rule (e) strips data and rule (b) the url inside its JSON string.

Input:

```text
[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[{"source":{"type":"base64","data":"iVBORw0KGgo=","url":"data:image/png;base64,iVBORw0KGgo="}}]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]
```

Output:

```text
[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[{"source":{"type":"base64","data":"[stripped unknown 8 bytes]","url":"[stripped image/png 8 bytes]"}}]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]
```

Tokens: (e) unknown, 8 bytes, (b) image/png, 8 bytes.

#### `depth_65_is_rule_b_only`

One array more is 65 levels, so the candidate does not parse. Only rule (b) applies, to the raw text; data stays.

Input:

```text
[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[{"source":{"type":"base64","data":"iVBORw0KGgo=","url":"data:image/png;base64,iVBORw0KGgo="}}]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]
```

Output:

```text
[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[{"source":{"type":"base64","data":"iVBORw0KGgo=","url":"[stripped image/png 8 bytes]"}}]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]
```

Tokens: (b) image/png, 8 bytes.

#### `duplicate_keys_strip_every_member`

Every member is visited in document order; both data members qualify, with the context and mime type of all the siblings.

Input:

```text
{"mediaType":"image/png","data":"QUFB","data":"QkJC"}
```

Output:

```text
{"mediaType":"image/png","data":"[stripped image/png 3 bytes]","data":"[stripped image/png 3 bytes]"}
```

Tokens: (e) image/png, 3 bytes, (e) image/png, 3 bytes.

#### `mime_key_list_order_wins`

mime_type comes first in the document, but media_type comes first in the mime key list, so its value is the mime type.

Input:

```text
{"mime_type":"image/jpeg","media_type":"image/png","data":"QUFB"}
```

Output:

```text
{"mime_type":"image/jpeg","media_type":"image/png","data":"[stripped image/png 3 bytes]"}
```

Tokens: (e) image/png, 3 bytes.

#### `string_array_under_a_keyed_key`

An array held directly under data; each string element is its own token, with the same context.

Input:

```text
{"mediaType":"image/png","data":["QUFB"]}
```

Output:

```text
{"mediaType":"image/png","data":["[stripped image/png 3 bytes]"]}
```

Tokens: (e) image/png, 3 bytes.

#### `uppercase_data_url_scheme`

The data scheme is case-insensitive.

Input:

```text
see DATA:image/png;base64,iVBORw0KGgo= here
```

Output:

```text
see [stripped image/png 8 bytes] here
```

Tokens: (b) image/png, 8 bytes.

#### `data_url_with_parameters`

RFC 2397 parameters may sit between the mime type and ;base64, and are replaced with the URL.

Input:

```text
{"url":"data:image/png;name=a.png;base64,iVBORw0KGgo="}
```

Output:

```text
{"url":"[stripped image/png 8 bytes]"}
```

Tokens: (b) image/png, 8 bytes.

#### `a_replacement_holding_a_data_url_is_not_complete`

Its mime is not unknown and not token/token, so the string is not a complete replacement and rule (b) replaces the data URL inside it. A second pass finds nothing (test_stripping_is_idempotent).

Input:

```text
[stripped data:image/png;base64,iVBORw0KGgo= 1 bytes]
```

Output:

```text
[stripped [stripped image/png 8 bytes] 1 bytes]
```

Tokens: (b) image/png, 8 bytes.

#### `a_replacement_with_a_mime_that_is_not_a_token_is_a_token`

[stripped a b 3 bytes] only looks like a replacement (its mime a b is not token/token), so rule (e) replaces it; it is not valid base64, so byte_size is unknown.

Input:

```text
{"mediaType":"image/png","data":"[stripped a b 3 bytes]"}
```

Output:

```text
{"mediaType":"image/png","data":"[stripped image/png unknown bytes]"}
```

Tokens: (e) image/png, unknown bytes.

#### `a_nested_document_has_no_enclosing_object`

The Buffer is the root of the document nested in x, so it has no enclosing object and the outer mediaType is not its mime type. The replacement literal is written escaped for the string it sits in.

Input:

```text
{"mediaType":"image/png","x":"{\"type\":\"Buffer\",\"data\":[1,2]}"}
```

Output:

```text
{"mediaType":"image/png","x":"\"[stripped unknown 2 bytes]\""}
```

Tokens: (d) unknown, 2 bytes.

#### `a_replaced_buffer_is_not_context`

Rule (d) replaces the Buffer under mediaType, and a complete replacement is never context, so data is no token: this output is final, and a second pass changes nothing. (tools/check_fixtures.py still flags {"mediaType":{"type":"Buffer",...}} before the strip.)

Input:

```text
{"mediaType":{"type":"Buffer","data":[1]},"data":"QUFB"}
```

Output:

```text
{"mediaType":"[stripped unknown 1 bytes]","data":"QUFB"}
```

Tokens: (d) unknown, 1 bytes.

#### `a_replaced_buffer_next_to_a_replacement_lookalike`

The Buffer gives no context, so data is no rule (e) token; it is not a complete replacement either (its mime is a data URL), so rule (b) replaces the data URL inside it. The output is stable on a second pass.

Input:

```text
{"mediaType":{"type":"Buffer","data":[1]},"data":"[stripped data:image/png;base64,QUFB 1 bytes]"}
```

Output:

```text
{"mediaType":"[stripped unknown 1 bytes]","data":"[stripped [stripped image/png 3 bytes] 1 bytes]"}
```

Tokens: (d) unknown, 1 bytes, (b) image/png, 3 bytes.

#### `context_is_read_before_the_pass`

mediaType is a non-empty string before the pass, so it is context for data, though rule (b) rewrites it in the same pass; the mime type is unknown, since the original value is not a valid mime. Stable on a second pass.

Input:

```text
{"mediaType":"data:image/png;base64,QUFB","data":"QkJC"}
```

Output:

```text
{"mediaType":"[stripped image/png 3 bytes]","data":"[stripped unknown 3 bytes]"}
```

Tokens: (b) image/png, 3 bytes, (e) unknown, 3 bytes.

#### `context_is_read_before_the_pass_in_any_order`

The same members the other way round give the same bytes for each; only the token order follows the document.

Input:

```text
{"data":"QkJC","mediaType":"data:image/png;base64,QUFB"}
```

Output:

```text
{"data":"[stripped unknown 3 bytes]","mediaType":"[stripped image/png 3 bytes]"}
```

Tokens: (e) unknown, 3 bytes, (b) image/png, 3 bytes.

#### `output_format_is_read_before_the_pass`

output_format is context before rule (b) rewrites it; image/&lt;value&gt; is not a valid mime for a data URL value, so the mime type is unknown.

Input:

```text
{"output_format":"data:image/png;base64,QUFB","b64_json":"QkJC"}
```

Output:

```text
{"output_format":"[stripped image/png 3 bytes]","b64_json":"[stripped unknown 3 bytes]"}
```

Tokens: (b) image/png, 3 bytes, (e) unknown, 3 bytes.

#### `a_second_pass_after_the_candidate_starts_to_parse`

The candidate does not parse because of the invalid escape \d inside the data URL, so pass 1 applies rule (b) alone, and the replacement removes the escape. The result parses, and its b64_json string is not a complete replacement, so a second pass applies rule (e) to it. This is the one input class where strip(strip(x)) differs from strip(x); no media survives in either pass.

Input:

```text
{"output_format":"stripped image/png 3 bytes]","b64_json":"[stDATA:au\dio/wav;x=1;base64,UklGRg==ripped unknown 3 bytes]"}
```

Output:

```text
{"output_format":"stripped image/png 3 bytes]","b64_json":"[st[stripped unknown 4 bytes]ripped unknown 3 bytes]"}
```

Tokens: (b) unknown, 4 bytes.

Output of a second pass over the output:

```text
{"output_format":"stripped image/png 3 bytes]","b64_json":"[stripped unknown unknown bytes]"}
```

Tokens of the second pass: (e) unknown, unknown bytes.

#### `a_sibling_mime_that_is_not_a_token_is_unknown`

The mime_type sibling is a non-empty string, so it is context, but it is not a token/token mime, so the mime type is unknown and none of it reaches the replacement. The sibling itself is a data URL, stripped by rule (b).

Input:

```text
{"data":"QUFB","mime_type":"data:image/png;base64,QUFB"}
```

Output:

```text
{"data":"[stripped unknown 3 bytes]","mime_type":"[stripped image/png 3 bytes]"}
```

Tokens: (e) unknown, 3 bytes, (b) image/png, 3 bytes.

#### `a_mime_with_a_colon_is_no_data_url`

The mime type of rule (b) cannot hold a colon, so the first data: is no token start: the match begins at the second data: and the first stays as text.

Input:

```text
data:data:image/png;base64,QUFB
```

Output:

```text
data:[stripped image/png 3 bytes]
```

Tokens: (b) image/png, 3 bytes.

#### `a_colon_inside_the_mime_leaves_the_data_url`

Because the mime type cannot hold a colon, a data URL whose mime type or parameter has one (text/x:y) is not matched and stays as it came. This is the cost of keeping rule (b) linear.

Input:

```text
data:text/x:y;base64,QUFB
```

Output:

```text
data:text/x:y;base64,QUFB
```

Tokens: none.

#### `duplicate_mime_keys_take_the_first_that_qualifies`

Both members are mediaType. The first is not a valid mime, so the second, the first that qualifies, gives the mime type.

Input:

```text
{"mediaType":"a b","mediaType":"image/png","data":"QUFB"}
```

Output:

```text
{"mediaType":"a b","mediaType":"image/png","data":"[stripped image/png 3 bytes]"}
```

Tokens: (e) image/png, 3 bytes.

#### `duplicate_type_any_member_makes_a_buffer`

In the strip a condition on type holds when any member meets it, so one type member equal to Buffer makes this a Buffer object whatever the others say. Part building reads only the last type member instead (see part_shapes).

Input:

```text
{"file":{"type":"text","type":"Buffer","data":[1]}}
```

Output:

```text
{"file":"[stripped unknown 1 bytes]"}
```

Tokens: (d) unknown, 1 bytes.

#### `langchain_v1_base64_image`

Rule (e) through a typed key. A LangChain v1 standard content block holds its bytes under base64, and its type image is the context; the mime type comes from mime_type.

Input:

```text
{"messages":[{"role":"user","content":[{"type":"text","text":"Describe this."},{"type":"image","base64":"iVBORw0KGgo=","mime_type":"image/png"}]}]}
```

Output:

```text
{"messages":[{"role":"user","content":[{"type":"text","text":"Describe this."},{"type":"image","base64":"[stripped image/png 8 bytes]","mime_type":"image/png"}]}]}
```

Tokens: (e) image/png, 8 bytes.

#### `langchain_v1_blocks_of_every_media_type`

The type alone is the context, with or without a mime_type, for each of the block types that carry base64.

Input:

```text
[{"type":"audio","base64":"UklGRg=="},{"type":"video","base64":"AAAA","mime_type":"video/mp4"},{"type":"file","base64":"JVBERi0=","mime_type":"application/pdf"},{"type":"text-plain","base64":"aGVsbG8=","mime_type":"text/plain"}]
```

Output:

```text
[{"type":"audio","base64":"[stripped unknown 4 bytes]"},{"type":"video","base64":"[stripped video/mp4 3 bytes]","mime_type":"video/mp4"},{"type":"file","base64":"[stripped application/pdf 5 bytes]","mime_type":"application/pdf"},{"type":"text-plain","base64":"[stripped text/plain 5 bytes]","mime_type":"text/plain"}]
```

Tokens: (e) unknown, 4 bytes, (e) video/mp4, 3 bytes, (e) application/pdf, 5 bytes, (e) text/plain, 5 bytes.

#### `a_base64_key_beside_a_mime_type`

base64 is one of the keys, so a sibling mime key is context for it as for data, whatever the type.

Input:

```text
{"base64":"QUFB","mime_type":"image/png"}
```

Output:

```text
{"base64":"[stripped image/png 3 bytes]","mime_type":"image/png"}
```

Tokens: (e) image/png, 3 bytes.

#### `a_base64_key_with_no_media_context`

With no sibling mime key, no parent key and no media type, base64 is left alone: on its own, beside a type that names no media (text, image_url), and beside a format, which is not a sibling key.

Input:

```text
[{"base64":"QUFB"},{"type":"text","base64":"QUFB"},{"type":"image_url","base64":"QUFB"},{"base64":"QUFB","format":"png"}]
```

Output:

```text
[{"base64":"QUFB"},{"type":"text","base64":"QUFB"},{"type":"image_url","base64":"QUFB"},{"base64":"QUFB","format":"png"}]
```

Tokens: none.

#### `a_typed_key_counts_when_any_type_member_qualifies`

As with Buffer and blob, a condition on type holds when any member meets it, so the second type member makes base64 a token.

Input:

```text
{"type":"text","type":"image","base64":"QUFB"}
```

Output:

```text
{"type":"text","type":"image","base64":"[stripped unknown 3 bytes]"}
```

Tokens: (e) unknown, 3 bytes.

#### `bedrock_converse_image_bytes`

Rule (e) through a source key. Bedrock Converse holds the bytes in {"image":{"format":"png","source":{"bytes":...}}}; the object holding bytes is the source, whatever its type. format sits on the image object, not beside bytes, so the mime type is unknown.

Input:

```text
{"messages":[{"role":"user","content":[{"image":{"format":"png","source":{"bytes":"iVBORw0KGgo="}}},{"text":"Describe this."}]}]}
```

Output:

```text
{"messages":[{"role":"user","content":[{"image":{"format":"png","source":{"bytes":"[stripped unknown 8 bytes]"}}},{"text":"Describe this."}]}]}
```

Tokens: (e) unknown, 8 bytes.

#### `bedrock_converse_document_and_video_bytes`

A document and a video hold their bytes the same way.

Input:

```text
[{"document":{"format":"pdf","name":"report","source":{"bytes":"JVBERi0="}}},{"video":{"format":"mp4","source":{"bytes":"AAAA"}}}]
```

Output:

```text
[{"document":{"format":"pdf","name":"report","source":{"bytes":"[stripped unknown 5 bytes]"}}},{"video":{"format":"mp4","source":{"bytes":"[stripped unknown 3 bytes]"}}}]
```

Tokens: (e) unknown, 5 bytes, (e) unknown, 3 bytes.

#### `bedrock_converse_audio_bytes`

An audio block holds its bytes the same way. Its format names no mime type here either.

Input:

```text
{"messages":[{"role":"user","content":[{"audio":{"format":"mp3","source":{"bytes":"SUQzBA=="}}},{"text":"Transcribe this."}]}]}
```

Output:

```text
{"messages":[{"role":"user","content":[{"audio":{"format":"mp3","source":{"bytes":"[stripped unknown 4 bytes]"}}},{"text":"Transcribe this."}]}]}
```

Tokens: (e) unknown, 4 bytes.

#### `bytes_outside_a_source_is_left_alone`

bytes counts only in an object under source. Here it is at the top, directly in an image object, a number, and an empty string; an S3 location is a reference, not bytes.

Input:

```text
{"bytes":"QUFB","image":{"format":"png","bytes":"QUFB"},"video":{"source":{"bytes":12,"s3Location":{"uri":"s3://bucket/clip.mp4"}}},"document":{"source":{"bytes":""}}}
```

Output:

```text
{"bytes":"QUFB","image":{"format":"png","bytes":"QUFB"},"video":{"source":{"bytes":12,"s3Location":{"uri":"s3://bucket/clip.mp4"}}},"document":{"source":{"bytes":""}}}
```

Tokens: none.

#### `mistral_input_audio_string`

Rule (e) through a typed key. Mistral's audio chunk holds the bare base64 as the string value of input_audio, beside the type input_audio. It names no format, so the mime type is unknown. OpenAI's input_audio object (openai_input_audio_wav) is visited as before.

Input:

```text
{"messages":[{"role":"user","content":[{"type":"input_audio","input_audio":"UklGRiQAAABXQVZF"},{"type":"text","text":"Transcribe this."}]}]}
```

Output:

```text
{"messages":[{"role":"user","content":[{"type":"input_audio","input_audio":"[stripped unknown 12 bytes]"},{"type":"text","text":"Transcribe this."}]}]}
```

Tokens: (e) unknown, 12 bytes.

#### `mistral_typescript_input_audio_string`

Mistral's TypeScript SDK spells the member inputAudio in the request object an app records, and only the wire form input_audio. It is a typed key too, beside the same type; with no type it is left alone.

Input:

```text
[{"type":"input_audio","inputAudio":"UklGRiQAAABXQVZF"},{"inputAudio":"UklGRg=="}]
```

Output:

```text
[{"type":"input_audio","inputAudio":"[stripped unknown 12 bytes]"},{"inputAudio":"UklGRg=="}]
```

Tokens: (e) unknown, 12 bytes.

#### `input_audio_string_with_no_type_is_left_alone`

The input_audio string counts only beside the type input_audio.

Input:

```text
{"input_audio":"UklGRg=="}
```

Output:

```text
{"input_audio":"UklGRg=="}
```

Tokens: none.

#### `the_new_shapes_stripped_twice_change_nothing`

Complete replacements under base64, bytes and input_audio are not tokens, so a second pass over these shapes changes nothing.

Input:

```text
[{"type":"image","base64":"[stripped image/png 8 bytes]","mime_type":"image/png"},{"image":{"format":"png","source":{"bytes":"[stripped unknown 8 bytes]"}}},{"type":"input_audio","input_audio":"[stripped unknown 12 bytes]"}]
```

Output:

```text
[{"type":"image","base64":"[stripped image/png 8 bytes]","mime_type":"image/png"},{"image":{"format":"png","source":{"bytes":"[stripped unknown 8 bytes]"}}},{"type":"input_audio","input_audio":"[stripped unknown 12 bytes]"}]
```

Tokens: none.

#### `vercel_image_part_base64_in_ai_prompt`

Rule (e) through a typed key. A Vercel image part holds bare base64 under image, beside the type image; the mime type comes from mediaType.

Input:

```text
{"messages":[{"role":"user","content":[{"type":"text","text":"Describe this."},{"type":"image","image":"iVBORw0KGgo=","mediaType":"image/png"}]}]}
```

Output:

```text
{"messages":[{"role":"user","content":[{"type":"text","text":"Describe this."},{"type":"image","image":"[stripped image/png 8 bytes]","mediaType":"image/png"}]}]}
```

Tokens: (e) image/png, 8 bytes.

#### `vercel_image_part_base64_without_a_media_type`

The type image is the context on its own; with no mediaType the mime type is unknown.

Input:

```text
[{"type":"image","image":"iVBORw0KGgo="}]
```

Output:

```text
[{"type":"image","image":"[stripped unknown 8 bytes]"}]
```

Tokens: (e) unknown, 8 bytes.

#### `vercel_image_string_that_is_not_base64`

An image string with no URL scheme is base64 to the part rules, so it is a token here too, whatever it holds; it is not valid base64, so byte_size is unknown.

Input:

```text
[{"type":"image","image":"a cat on a mat"}]
```

Output:

```text
[{"type":"image","image":"[stripped unknown unknown bytes]"}]
```

Tokens: (e) unknown, unknown bytes.

#### `vercel_image_url_is_left_alone`

image keeps URLs: a string that starts with a URL scheme is no rule (e) token, and rule (b) finds no data URL in it, so http, https and gs links stay as they came.

Input:

```text
[{"type":"image","image":"https://example.com/a.png","mediaType":"image/png"},{"type":"image","image":"gs://bucket/a.png"}]
```

Output:

```text
[{"type":"image","image":"https://example.com/a.png","mediaType":"image/png"},{"type":"image","image":"gs://bucket/a.png"}]
```

Tokens: none.

#### `vercel_image_data_url_keeps_its_own_mime`

A base64 data URL that is the whole value under image is left to rule (b), so it is replaced with the URL's own mime type, not the part's mediaType, and with its size.

Input:

```text
[{"type":"image","image":"data:image/jpeg;base64,/9j/4AAQSkZJRg==","mediaType":"image/png"}]
```

Output:

```text
[{"type":"image","image":"[stripped image/jpeg 10 bytes]","mediaType":"image/png"}]
```

Tokens: (b) image/jpeg, 10 bytes.

#### `vercel_tagged_file_data_in_ai_prompt`

Rule (e) through the typed key data under the type data and the parent key data. The tag object names no mime type, so it reads the file part's mediaType, as rule (d) does.

Input:

```text
{"messages":[{"role":"user","content":[{"type":"file","data":{"type":"data","data":"JVBERi0="},"mediaType":"application/pdf"}]}]}
```

Output:

```text
{"messages":[{"role":"user","content":[{"type":"file","data":{"type":"data","data":"[stripped application/pdf 5 bytes]"},"mediaType":"application/pdf"}]}]}
```

Tokens: (e) application/pdf, 5 bytes.

#### `vercel_tagged_image_data`

An image part's image holds tagged data the same way, under the parent key image; with no mediaType on the part the mime type is unknown.

Input:

```text
[{"type":"image","image":{"type":"data","data":"iVBORw0KGgo="}},{"type":"image","image":{"type":"data","data":"iVBORw0KGgo="},"mediaType":"image/png"}]
```

Output:

```text
[{"type":"image","image":{"type":"data","data":"[stripped unknown 8 bytes]"}},{"type":"image","image":{"type":"data","data":"[stripped image/png 8 bytes]"},"mediaType":"image/png"}]
```

Tokens: (e) unknown, 8 bytes, (e) image/png, 8 bytes.

#### `vercel_tagged_data_url_and_link`

Tagged data keeps URLs too: a base64 data URL that is the whole value gets rule (b) with its own mime type, and an https link stays.

Input:

```text
[{"type":"file","data":{"type":"data","data":"data:application/pdf;base64,JVBERi0="},"mediaType":"application/pdf"},{"type":"file","data":{"type":"data","data":"https://example.com/a.pdf"},"mediaType":"application/pdf"}]
```

Output:

```text
[{"type":"file","data":{"type":"data","data":"[stripped application/pdf 5 bytes]"},"mediaType":"application/pdf"},{"type":"file","data":{"type":"data","data":"https://example.com/a.pdf"},"mediaType":"application/pdf"}]
```

Tokens: (b) application/pdf, 5 bytes.

#### `a_wrapped_base64_data_url_under_a_url_key_is_one_rule_b_token`

A base64 run wrapped at a newline (base64.encodebytes, a MIME encoder) goes on over the next line, so rule (b)'s pattern matches the whole value: a key that keeps URLs leaves it to rule (b), which replaces it with its own mime type and size, under image and tagged data alike. A plain data beside mediaType keeps no URLs, so rule (e) replaces it whole there, as before.

Input:

```text
[{"type":"image","image":"data:image/png;base64,iVBO\nRw0KGgo="},{"type":"image","image":{"type":"data","data":"data:image/png;base64,iVBO\nRw0KGgo="}},{"type":"file","data":"data:image/png;base64,iVBO\nRw0KGgo=","mediaType":"image/png"},{"type":"file","data":{"type":"data","data":"data:image/png;base64,iVBO\nRw0KGgo="},"mediaType":"image/png"}]
```

Output:

```text
[{"type":"image","image":"[stripped image/png 8 bytes]"},{"type":"image","image":{"type":"data","data":"[stripped image/png 8 bytes]"}},{"type":"file","data":"[stripped image/png unknown bytes]","mediaType":"image/png"},{"type":"file","data":{"type":"data","data":"[stripped image/png 8 bytes]"},"mediaType":"image/png"}]
```

Tokens: (b) image/png, 8 bytes, (b) image/png, 8 bytes, (e) image/png, unknown bytes, (b) image/png, 8 bytes.

#### `a_percent_encoded_data_url_in_prose`

A data URL percent-encoded whole, as encodeURIComponent or Python's quote writes it into a link, is a rule (b) token in prose: its media type percent-decoded (image/svg+xml from image%2Fsvg%2Bxml), its run sized once %2B, %2F and %3D are decoded. The hex digits may be in lower case, a / may be left as it is, and parameters in the header (%3Bname%3Da.png) are skipped as in a data URL.

Input:

```text
see data%3Aimage%2Fpng%3Bbase64%2CiVBORw0KGgo%3D here, data%3Aimage%2Fsvg%2Bxml%3Bbase64%2C%2B%2B%2B%2B%2F%2F%2F%2FAA%3D%3D and data%3Aimage%2fpng%3Bbase64%2C%2b%2b%2b%2b%2f%2f%2f%2fAA%3D%3D and data%3Aimage/png%3Bname%3Da.png%3Bbase64%2C%2B%2B%2B%2B////AA%3D%3D
```

Output:

```text
see [stripped image/png 8 bytes] here, [stripped image/svg+xml 7 bytes] and [stripped image/png 7 bytes] and [stripped image/png 7 bytes]
```

Tokens: (b) image/png, 8 bytes, (b) image/svg+xml, 7 bytes, (b) image/png, 7 bytes, (b) image/png, 7 bytes.

#### `a_percent_encoded_data_url_in_json_and_under_keys`

In a JSON string the percent-encoded data URL is replaced where it sits, so a proxy link keeps the text around it, under image_url.url and under image alike. Under a key that keeps URLs, a value that is one percent-encoded data URL, or one and a final line break, is replaced whole with its own mime type and size. A plain data beside mediaType is a rule (e) token, as a data URL is there. A percent-encoded data URL glued to a data URL stops where the next data: starts.

Input:

```text
[{"type":"image_url","image_url":{"url":"https://proxy.example/fetch?u=data%3Aimage%2Fpng%3Bbase64%2CiVBORw0KGgo%3D&w=1"}},{"type":"image","image":"data%3Aimage%2Fpng%3Bbase64%2CiVBORw0KGgo%3D"},{"type":"image","image":{"type":"data","data":"data%3aimage%2fpng%3bbase64%2ciVBORw0KGgo%3d\n"}},{"type":"image","image":"https://proxy.example/fetch?u=data%3Aimage%2Fpng%3Bbase64%2CiVBORw0KGgo%3D"},{"type":"file","data":"data%3Aimage%2Fpng%3Bbase64%2CiVBORw0KGgo%3D","mediaType":"image/png"},{"type":"text","text":"data%3Aa%2Fb%3Bbase64%2CQUFBdata:a/b;base64,QkJD"}]
```

Output:

```text
[{"type":"image_url","image_url":{"url":"https://proxy.example/fetch?u=[stripped image/png 8 bytes]&w=1"}},{"type":"image","image":"[stripped image/png 8 bytes]"},{"type":"image","image":{"type":"data","data":"[stripped image/png 8 bytes]"}},{"type":"image","image":"https://proxy.example/fetch?u=[stripped image/png 8 bytes]"},{"type":"file","data":"[stripped image/png unknown bytes]","mediaType":"image/png"},{"type":"text","text":"[stripped a/b 3 bytes][stripped a/b 3 bytes]"}]
```

Tokens: (b) image/png, 8 bytes, (b) image/png, 8 bytes, (b) image/png, 8 bytes, (b) image/png, 8 bytes, (e) image/png, unknown bytes, (b) a/b, 3 bytes, (b) a/b, 3 bytes.

#### `a_percent_encoded_run_ends_at_any_other_escape`

The accepted costs of percent_pattern: its run takes only the escapes %0A, %0D, %2B and %2F (and the harmless %0B, %0F, %2A and %2D), so any other escape, an encoded space included, ends it; a twice-encoded data URL (data%253A) is no token; and a data URL with a plain scheme and a percent-encoded run, which no encoder writes, ends its run at the first escape.

Input:

```text
data%3Aa%2Fb%3Bbase64%2CQUFB%20QkJD and data%253Aa%252Fb%253Bbase64%252CQUFB and data:a%2Fb;base64,QUFB%2BQkJD
```

Output:

```text
[stripped a/b 3 bytes]%20QkJD and data%253Aa%252Fb%253Bbase64%252CQUFB and [stripped unknown 3 bytes]%2BQkJD
```

Tokens: (b) a/b, 3 bytes, (b) unknown, 3 bytes.

#### `a_percent_encoded_data_url_wrapped_before_it_was_encoded`

Python's quote(data_url, safe="") of a data URL whose payload is base64.encodebytes output writes each line break as %0A (or %0D%0A), and the run goes on over them, so the payload is replaced whole and sized with the encoded line breaks removed. A padded run ends at its padding, so a final encoded line break after it stays, as a raw one does outside a key that keeps URLs. Under image, a value that is the data URL and one final %0A or %0D%0A is replaced whole, as one with a raw final line break is.

Input:

```text
[{"type":"text","text":"see data%3Aimage%2Fpng%3Bbase64%2CAAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8gISIjJCUmJygpKissLS4vMDEyMzQ1Njc4%0AOTo7%0A thanks"},{"type":"image","image":"data%3Aimage%2Fpng%3Bbase64%2CAAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8gISIjJCUmJygpKissLS4vMDEyMzQ1Njc4%0AOTo7%0A"},{"type":"image_url","image_url":{"url":"https://proxy.example/fetch?u=data%3aimage%2fpng%3bbase64%2cCgsMDQ4PEBESExQVFhcYGRobHB0eHyAhIiMkJSYnKCkqKywtLi8wMTIzNDU2Nzg5Ojs8PT4%2fQEFC%0d%0aQ0RFRg%3d%3d%0d%0a&w=1"}}]
```

Output:

```text
[{"type":"text","text":"see [stripped image/png 60 bytes] thanks"},{"type":"image","image":"[stripped image/png 60 bytes]"},{"type":"image_url","image_url":{"url":"https://proxy.example/fetch?u=[stripped image/png 61 bytes]%0d%0a&w=1"}}]
```

Tokens: (b) image/png, 60 bytes, (b) image/png, 60 bytes, (b) image/png, 61 bytes.

#### `a_base64_data_url_that_ends_in_one_line_break_under_a_url_key`

base64.encodebytes ends its output with a newline. Under a key that keeps URLs, a value that is one data URL and one final line break (a newline, or a carriage return and newline) is one rule (b) token, replaced whole with the line break, so it gets its mime type and size: under image, tagged data, a wrapped run and a string in an array under image alike. Two final line breaks are no such value, so that one is a rule (e) token. A plain data beside mediaType keeps no URLs, so it stays rule (e). Outside such a key rule (b) replaces the data URL alone and the line break stays.

Input:

```text
[{"type":"image","image":"data:image/png;base64,iVBORw0KGgo=\n"},{"type":"image","image":{"type":"data","data":"data:image/png;base64,iVBORw0KGgo=\r\n"}},{"type":"image","image":"data:image/png;base64,AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8gISIjJCUmJygpKissLS4vMDEyMzQ1Njc4\nOTo7\n"},{"type":"image","image":["data:image/png;base64,iVBORw0KGgo=\n"]},{"type":"image","image":"data:image/png;base64,iVBORw0KGgo=\n\n"},{"type":"file","data":"data:image/png;base64,iVBORw0KGgo=\n","mediaType":"image/png"},{"type":"image_url","image_url":{"url":"data:image/png;base64,iVBORw0KGgo=\n"}}]
```

Output:

```text
[{"type":"image","image":"[stripped image/png 8 bytes]"},{"type":"image","image":{"type":"data","data":"[stripped image/png 8 bytes]"}},{"type":"image","image":"[stripped image/png 60 bytes]"},{"type":"image","image":["[stripped image/png 8 bytes]"]},{"type":"image","image":"[stripped unknown unknown bytes]"},{"type":"file","data":"[stripped image/png unknown bytes]","mediaType":"image/png"},{"type":"image_url","image_url":{"url":"[stripped image/png 8 bytes]\n"}}]
```

Tokens: (b) image/png, 8 bytes, (b) image/png, 8 bytes, (b) image/png, 60 bytes, (b) image/png, 8 bytes, (e) unknown, unknown bytes, (e) image/png, unknown bytes, (b) image/png, 8 bytes.

#### `a_percent_encoded_data_url_under_a_url_key_is_replaced_whole`

A data URL that is not base64 holds no rule (b) token, so under a key that keeps URLs it is a rule (e) token, tagged or not, the scheme in any case: the same Vercel payload is stripped whichever way it is written.

Input:

```text
[{"type":"file","data":{"type":"data","data":"data:image/png,%89PNG"},"mediaType":"image/png"},{"type":"file","data":"data:image/png,%89PNG","mediaType":"image/png"},{"type":"image","image":"DATA:image/png,%89PNG"},{"type":"image","image":{"type":"data","data":"DATA:image/png,%89PNG"}}]
```

Output:

```text
[{"type":"file","data":{"type":"data","data":"[stripped image/png unknown bytes]"},"mediaType":"image/png"},{"type":"file","data":"[stripped image/png unknown bytes]","mediaType":"image/png"},{"type":"image","image":"[stripped unknown unknown bytes]"},{"type":"image","image":{"type":"data","data":"[stripped unknown unknown bytes]"}}]
```

Tokens: (e) image/png, unknown bytes, (e) image/png, unknown bytes, (e) unknown, unknown bytes, (e) unknown, unknown bytes.

#### `a_broken_base64_run_under_a_url_key_is_replaced_whole`

Rule (b) matches data:image/png;base64, with an empty run and stops before @@@, so it does not reach the end of the value: the value is a rule (e) token, tagged or not.

Input:

```text
[{"type":"image","image":"data:image/png;base64,@@@"},{"type":"image","image":{"type":"data","data":"data:image/png;base64,@@@"}},{"type":"file","data":"data:image/png;base64,@@@","mediaType":"image/png"},{"type":"file","data":{"type":"data","data":"data:image/png;base64,@@@"},"mediaType":"image/png"}]
```

Output:

```text
[{"type":"image","image":"[stripped unknown unknown bytes]"},{"type":"image","image":{"type":"data","data":"[stripped unknown unknown bytes]"}},{"type":"file","data":"[stripped image/png unknown bytes]","mediaType":"image/png"},{"type":"file","data":{"type":"data","data":"[stripped image/png unknown bytes]"},"mediaType":"image/png"}]
```

Tokens: (e) unknown, unknown bytes, (e) unknown, unknown bytes, (e) image/png, unknown bytes, (e) image/png, unknown bytes.

#### `a_link_followed_by_a_data_url_under_a_url_key_is_replaced_whole`

A value that starts with a URL scheme but holds data: after it is no URL a key that keeps URLs leaves to rule (b): it is a rule (e) token, replaced whole with the key's usual mime type, whether the data URL after the link is wrapped, percent-encoded or in upper case, under image or tagged data. The part rules make such a value a blob too.

Input:

```text
[{"type":"image","image":"https://x/a.png\ndata:image/png;base64,iVBO\nRw0KGgo="},{"type":"image","image":"https://x/a.png\ndata:image/png,%89PNG","mediaType":"image/png"},{"type":"file","data":{"type":"data","data":"https://x/a.png\nDATA:image/png;base64,iVBORw0KGgo="},"mediaType":"image/png"},{"type":"image","image":{"type":"data","data":"gs://b/a.png data:image/png;base64,iVBORw0KGgo="}}]
```

Output:

```text
[{"type":"image","image":"[stripped unknown unknown bytes]"},{"type":"image","image":"[stripped image/png unknown bytes]","mediaType":"image/png"},{"type":"file","data":{"type":"data","data":"[stripped image/png unknown bytes]"},"mediaType":"image/png"},{"type":"image","image":{"type":"data","data":"[stripped unknown unknown bytes]"}}]
```

Tokens: (e) unknown, unknown bytes, (e) image/png, unknown bytes, (e) image/png, unknown bytes, (e) unknown, unknown bytes.

#### `a_url_led_by_whitespace_under_a_url_key_is_replaced_whole`

A value led by a space starts with no URL scheme, so under image it is a rule (e) token whatever it holds, wrapped or percent-encoded.

Input:

```text
[{"type":"image","image":" data:image/png;base64,iVBO\nRw0KGgo="},{"type":"image","image":"\tdata:image/png,%89PNG"}]
```

Output:

```text
[{"type":"image","image":"[stripped unknown unknown bytes]"},{"type":"image","image":"[stripped unknown unknown bytes]"}]
```

Tokens: (e) unknown, unknown bytes, (e) unknown, unknown bytes.

#### `a_link_with_data_colon_in_its_path_under_a_url_key`

The search for data: has no word boundary, so a link with metadata: in its path is replaced whole under image, the accepted false positive of the part rules too. Outside a key that keeps URLs the same link holds no rule (b) token and stays.

Input:

```text
[{"type":"image","image":"https://e/metadata:x.png"},{"type":"image_url","image_url":{"url":"https://e/metadata:x.png"}}]
```

Output:

```text
[{"type":"image","image":"[stripped unknown unknown bytes]"},{"type":"image_url","image_url":{"url":"https://e/metadata:x.png"}}]
```

Tokens: (e) unknown, unknown bytes.

#### `a_link_followed_by_a_wrapped_data_url_in_a_json_string`

Outside a key that keeps URLs, rule (b) replaces the wrapped data URL after the link, its run going on over the newline, so the link stays and nothing of the payload is left. Led by a space and wrapped at a carriage return and newline, the same data URL is replaced alone too.

Input:

```text
{"messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"https://x/a.png\ndata:image/png;base64,iVBO\nRw0KGgo="}},{"type":"image_url","image_url":{"url":" data:image/png;base64,iVBO\r\nRw0KGgo="}}]}]}
```

Output:

```text
{"messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"https://x/a.png\n[stripped image/png 8 bytes]"}},{"type":"image_url","image_url":{"url":" [stripped image/png 8 bytes]"}}]}]}
```

Tokens: (b) image/png, 8 bytes, (b) image/png, 8 bytes.

#### `a_wrapped_data_url_in_prose`

Rule (b) in a string that is not JSON: the run goes on over a newline and over the spaces or tabs that indent the next line, so the whole payload is replaced and the prose around it stays.

Input:

```text
see data:image/png;base64,iVBO
Rw0K
	 Ggo= here
```

Output:

```text
see [stripped image/png 8 bytes] here
```

Tokens: (b) image/png, 8 bytes.

#### `a_wrapped_uppercase_data_url_in_prose`

The scheme is case-insensitive for a wrapped run too.

Input:

```text
see DATA:image/png;base64,iVBO
Rw0KGgo= here
```

Output:

```text
see [stripped image/png 8 bytes] here
```

Tokens: (b) image/png, 8 bytes.

#### `an_unpadded_run_takes_the_first_word_of_the_next_line`

A tiny unpadded run (76 base64 characters or fewer) cannot tell the next line's first word from more base64, so that word goes with it: the cost of leaving no wrapped payload behind. The rest of the line stays. A padded run ends at its padding, so the next line stays whole.

Input:

```text
data:image/png;base64,iVBORw0KGgo
Thanks, bye. data:image/png;base64,iVBORw0KGgo=
Thanks
```

Output:

```text
[stripped image/png unknown bytes], bye. [stripped image/png 8 bytes]
Thanks
```

Tokens: (b) image/png, unknown bytes, (b) image/png, 8 bytes.

#### `a_long_data_url_at_a_line_end_keeps_the_lines_after_it`

A run longer than 76 base64 characters on one line is no wrapped payload, since no encoder writes a longer line, so it ends at its line break even unpadded: a sign-off of one-word lines and a --- rule after it stay whole, and the size is the payload's alone.

Input:

```text
data:image/png;base64,AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8gISIjJCUmJygpKissLS4vMDEyMzQ1Njc4OTo7
Thanks
Best
Alex and data:image/png;base64,AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8gISIjJCUmJygpKissLS4vMDEyMzQ1Njc4OTo7
---
Next
```

Output:

```text
[stripped image/png 60 bytes]
Thanks
Best
Alex and [stripped image/png 60 bytes]
---
Next
```

Tokens: (b) image/png, 60 bytes, (b) image/png, 60 bytes.

#### `a_tiny_data_url_at_a_line_end_takes_the_one_word_lines_after_it`

The accepted cost of the 76-character guard: a tiny unpadded data URL at the end of a line goes on over each next line that is one base64 word, and its size is then unknown. A line with a character that is no base64 stops it there.

Input:

```text
data:image/gif;base64,R0lGODlhAQABAAAAACw
Thanks
Best
Alex, bye
```

Output:

```text
[stripped image/gif unknown bytes], bye
```

Tokens: (b) image/gif, unknown bytes.

#### `a_wrapped_data_url_in_a_quoted_reply`

After a line break, the &gt; of a quoted reply is skipped like an indent, so a wrapped payload in a quoted message is replaced whole and the quoted line after it stays.

Input:

```text
> see data:image/png;base64,ZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXp7fH1+f4CBgoOEhYaHiImKi4yNjo+QkZKTlJWWl5iZmpuc
> nZ6foKGio6SlpqeoqaqrrK2ur7CxsrO0tba3uLm6u7w=
> Thanks
```

Output:

```text
> see [stripped image/png 89 bytes]
> Thanks
```

Tokens: (b) image/png, 89 bytes.

#### `a_data_url_never_runs_into_the_next`

Each data: starts its own token: a run that goes on over a newline, or a run glued to the next data URL, stops where the next data: starts, so both payloads are replaced.

Input:

```text
data:image/png;base64,QUFB
data:image/png;base64,QkJC and data:image/png;base64,QUFBdata:image/png;base64,QkJC
```

Output:

```text
[stripped image/png 3 bytes]
[stripped image/png 3 bytes] and [stripped image/png 3 bytes][stripped image/png 3 bytes]
```

Tokens: (b) image/png, 3 bytes, (b) image/png, 3 bytes, (b) image/png, 3 bytes, (b) image/png, 3 bytes.

#### `a_whole_data_url_is_unchanged_by_the_continuation`

A data URL rule (b) consumes whole, alone or in prose, is replaced as before: a blank line or a space ends its run.

Input:

```text
{"url":"data:image/png;base64,iVBORw0KGgo="} data:image/png;base64,QUFB

Next data:image/png;base64,QUFB "x"
```

Output:

```text
{"url":"[stripped image/png 8 bytes]"} [stripped image/png 3 bytes]

Next [stripped image/png 3 bytes] "x"
```

Tokens: (b) image/png, 8 bytes, (b) image/png, 3 bytes, (b) image/png, 3 bytes.

#### `image_and_tagged_data_outside_their_parts_are_left_alone`

image counts only beside the type image, and tagged data only under the parent key data or image: an image string with no type, beside the type text or image_url, and a type data object at the top or under another key are left alone.

Input:

```text
[{"image":"iVBORw0KGgo="},{"type":"text","image":"iVBORw0KGgo="},{"type":"image_url","image":"iVBORw0KGgo="},{"type":"data","data":"iVBORw0KGgo="},{"x":{"type":"data","data":"iVBORw0KGgo="}}]
```

Output:

```text
[{"image":"iVBORw0KGgo="},{"type":"text","image":"iVBORw0KGgo="},{"type":"image_url","image":"iVBORw0KGgo="},{"type":"data","data":"iVBORw0KGgo="},{"x":{"type":"data","data":"iVBORw0KGgo="}}]
```

Tokens: none.

#### `tagged_data_outside_a_vercel_part_is_left_alone`

Tagged data counts only when the object holding it is a Vercel file or image part (holder_types): an envelope {"data":{"type":"data",...}} from another API, tagged data under image with no part around it, and tagged data in a text object are left alone; in a file part it is a token.

Input:

```text
[{"data":{"type":"data","data":"hello world"}},{"image":{"type":"data","data":"iVBORw0KGgo="}},{"type":"text","data":{"type":"data","data":"iVBORw0KGgo="}},{"type":"file","data":{"type":"data","data":"iVBORw0KGgo="},"mediaType":"image/png"}]
```

Output:

```text
[{"data":{"type":"data","data":"hello world"}},{"image":{"type":"data","data":"iVBORw0KGgo="}},{"type":"text","data":{"type":"data","data":"iVBORw0KGgo="}},{"type":"file","data":{"type":"data","data":"[stripped image/png 8 bytes]"},"mediaType":"image/png"}]
```

Tokens: (e) image/png, 8 bytes.

#### `langchain_v0_base64_block_without_a_mime_type`

Rule (e) through a base64 marker. A LangChain v0 block {"type":"image","source_type":"base64","data":...} with no mime_type: source_type base64 is the context for data, and the mime type is unknown.

Input:

```text
{"messages":[{"role":"user","content":[{"type":"text","text":"Describe this."},{"type":"image","source_type":"base64","data":"iVBORw0KGgo="}]}]}
```

Output:

```text
{"messages":[{"role":"user","content":[{"type":"text","text":"Describe this."},{"type":"image","source_type":"base64","data":"[stripped unknown 8 bytes]"}]}]}
```

Tokens: (e) unknown, 8 bytes.

#### `langchain_v0_base64_blocks_with_a_mime_type`

With a mime_type the mime type comes from it, for every block type.

Input:

```text
[{"type":"image","source_type":"base64","data":"iVBORw0KGgo=","mime_type":"image/png"},{"type":"audio","source_type":"base64","data":"UklGRg==","mime_type":"audio/wav"},{"type":"file","source_type":"base64","data":"JVBERi0=","mime_type":"application/pdf"}]
```

Output:

```text
[{"type":"image","source_type":"base64","data":"[stripped image/png 8 bytes]","mime_type":"image/png"},{"type":"audio","source_type":"base64","data":"[stripped audio/wav 4 bytes]","mime_type":"audio/wav"},{"type":"file","source_type":"base64","data":"[stripped application/pdf 5 bytes]","mime_type":"application/pdf"}]
```

Tokens: (e) image/png, 8 bytes, (e) audio/wav, 4 bytes, (e) application/pdf, 5 bytes.

#### `langchain_v0_blocks_with_no_base64_marker_are_left_alone`

Only source_type base64 is a marker. A url block keeps its link, data beside source_type url is not a token, and neither is data beside the type image alone; a block by id holds nothing to strip.

Input:

```text
[{"type":"image","source_type":"url","url":"https://example.com/a.png"},{"type":"image","source_type":"url","data":"iVBORw0KGgo="},{"type":"image","data":"iVBORw0KGgo="},{"type":"file","source_type":"id","id":"file-abc123"}]
```

Output:

```text
[{"type":"image","source_type":"url","url":"https://example.com/a.png"},{"type":"image","source_type":"url","data":"iVBORw0KGgo="},{"type":"image","data":"iVBORw0KGgo="},{"type":"file","source_type":"id","id":"file-abc123"}]
```

Tokens: none.

#### `a_base64_marker_reaches_data_alone`

source_type base64 is context for data in its own object and for no other key: result and b64_json beside it stay, with or without a data member.

Input:

```text
[{"source_type":"base64","result":"ok","b64_json":"yes"},{"type":"text","source_type":"base64","data":"iVBORw0KGgo=","result":"iVBORw0KGgo="}]
```

Output:

```text
[{"source_type":"base64","result":"ok","b64_json":"yes"},{"type":"text","source_type":"base64","data":"[stripped unknown 8 bytes]","result":"iVBORw0KGgo="}]
```

Tokens: (e) unknown, 8 bytes.

#### `the_vercel_and_langchain_v0_shapes_stripped_twice_change_nothing`

Complete replacements under image, tagged data and a v0 block's data are not tokens, so a second pass over these shapes changes nothing.

Input:

```text
[{"type":"image","image":"[stripped image/png 8 bytes]","mediaType":"image/png"},{"type":"file","data":{"type":"data","data":"[stripped application/pdf 5 bytes]"},"mediaType":"application/pdf"},{"type":"image","source_type":"base64","data":"[stripped unknown 8 bytes]"}]
```

Output:

```text
[{"type":"image","image":"[stripped image/png 8 bytes]","mediaType":"image/png"},{"type":"file","data":{"type":"data","data":"[stripped application/pdf 5 bytes]"},"mediaType":"application/pdf"},{"type":"image","source_type":"base64","data":"[stripped unknown 8 bytes]"}]
```

Tokens: none.

### Byte objects

When an SDK serializes a value that is not a string into an attribute (an input or output it records, a tool's arguments or result), every byte object in it is written as the replacement with the unknown mime, `[stripped unknown <N> bytes]`, where N is its size in bytes (see size), as a JSON string literal in the place the value had. The byte objects are the types listed below for each SDK, subclasses included, and in TypeScript those of another realm too (a vm context, an iframe). The mime is always unknown, never read from a sibling such as mediaType: a serializer writes each value on its own. A byte object at the root is serialized like any other value that is not a string, so the attribute holds the JSON string literal, quotes included. An object key is never a byte object. The strip then runs as on any value, and since the marker is a complete replacement it is never stripped again and is never context for rule (e) (see idempotence). Rule (d) and this rule meet at the Node Buffer. A Buffer is a Uint8Array, so the TypeScript SDK writes it as this marker; it must read each value from its holder, as JSON.stringify calls a Buffer's toJSON, which writes {"type":"Buffer","data":[...]}, before a replacer sees the value. Rule (d) is for a Buffer that became that object before an SDK saw it, in a string another library serialized (the AI SDK's ai.prompt), and for the sink. Both count the same bytes; rule (d) may also read a mime type from the enclosing object, which this rule never does.

**Size.** The size in bytes, never a count of items. Python: len of bytes and bytearray, nbytes of memoryview (so a memoryview cast to 4-byte items counts 4 per item); a released memoryview has no size, and its marker's size is unknown. TypeScript: byteLength of an ArrayBuffer, a SharedArrayBuffer and every ArrayBuffer view (ArrayBuffer.isView: each typed array, a Node Buffer and a DataView), the view's own length, not its buffer's.

- Python: `bytes`, `bytearray`, `memoryview`
- TypeScript: `ArrayBuffer`, `SharedArrayBuffer`, `every ArrayBuffer view (ArrayBuffer.isView): each typed array, Buffer and DataView`

#### `python_bytes_in_a_dict`

Value (python):

```text
{"image": b"\x89PNG"}
```

Attribute value:

```text
{"image":"[stripped unknown 4 bytes]"}
```

#### `python_bytearray_and_memoryview`

Value (python):

```text
[bytearray(b"abc"), memoryview(b"abcdef")[2:]]
```

Attribute value:

```text
["[stripped unknown 3 bytes]","[stripped unknown 4 bytes]"]
```

#### `python_memoryview_counts_bytes_not_items`

The view has 2 items of 4 bytes, so its size is 8. At the root, the attribute is the JSON string literal.

Value (python):

```text
memoryview(bytes(8)).cast("I")
```

Attribute value:

```text
"[stripped unknown 8 bytes]"
```

#### `python_bytes_beside_a_media_type`

The mime is unknown though mediaType names one, and the strip that follows leaves the marker: it is a complete replacement.

Value (python):

```text
{"type": "file", "data": b"\x89PNG", "mediaType": "image/png"}
```

Attribute value:

```text
{"type":"file","data":"[stripped unknown 4 bytes]","mediaType":"image/png"}
```

#### `python_empty_bytes`

Value (python):

```text
{"data": b""}
```

Attribute value:

```text
{"data":"[stripped unknown 0 bytes]"}
```

#### `typescript_uint8array`

Value (typescript):

```text
{ u: new Uint8Array(3) }
```

Attribute value:

```text
{"u":"[stripped unknown 3 bytes]"}
```

#### `typescript_node_buffer_is_a_byte_object`

A Buffer is written as the marker, never as {"type":"Buffer","data":[...]}, so its mime is unknown: compare vercel_buffer_in_ai_prompt, where rule (d) strips a Buffer the AI SDK serialized.

Value (typescript):

```text
{ type: "file", data: Buffer.from([137, 80, 78, 71]), mediaType: "image/png" }
```

Attribute value:

```text
{"type":"file","data":"[stripped unknown 4 bytes]","mediaType":"image/png"}
```

#### `typescript_typed_array_counts_bytes_not_items`

Two 2-byte items are 4 bytes. At the root, the attribute is the JSON string literal.

Value (typescript):

```text
new Uint16Array(2)
```

Attribute value:

```text
"[stripped unknown 4 bytes]"
```

#### `typescript_array_buffer_and_data_view`

A view counts its own length, not its buffer's.

Value (typescript):

```text
[new ArrayBuffer(5), new DataView(new ArrayBuffer(8), 2, 3)]
```

Attribute value:

```text
["[stripped unknown 5 bytes]","[stripped unknown 3 bytes]"]
```

#### Byte objects as attribute values

A byte object used directly as an OpenTelemetry attribute value (of a span, an event or a link), or anywhere inside one (an element of an array or a value of a mapping, at any depth), has no serializer around it: it becomes the marker as a bare string, `[stripped unknown <N> bytes]`, with no JSON quotes, and N its size by the size rule above. Every other value is kept. An OpenTelemetry array is homogeneous, so each array is looked at on its own once its elements are replaced. One that held a byte object and whose elements are then all strings is that array of strings. One that held a byte object beside any element that is then no string (a number, a bool, null, an array, a mapping) is instead one string: the JSON the SDK serializes the array to under the rule above, `[1,"[stripped unknown 2 bytes]"]`, its numbers written as that SDK writes them. An array that held no byte object is kept, its elements walked. The SDK then sets the walked value in the form its OpenTelemetry attribute API holds. OpenTelemetry Python holds a mapping and a nested array, so it sets them as they are. OpenTelemetry JS holds neither, nor an array whose elements, null aside, are not all strings, all numbers or all booleans. So a walked value that held a byte object and is then a mapping, or an array OpenTelemetry JS cannot hold, is set as one string: the JSON the SDK serializes the whole value to under the rule above, every byte object a quoted marker and every array an array. `{k: [1, bytes]}` is `{"k":[1,"[stripped unknown 2 bytes]"]}` and `[1, [1, bytes]]` is `[1,[1,"[stripped unknown 1 bytes]"]]`, each encoded once, never holding a mixed array's own JSON as a string. The sink does the same with an OTLP AnyValue: a bytes_value, alone or at any depth of array_value and kvlist_value, is the marker, N the number of bytes it holds, and an array_value that mixes a bytes_value with a value that is then no string is its compact JSON, an int_value written as a JSON number, a kvlist_value as an object and an empty AnyValue, which OTLP defines as an empty value, as null. A kvlist_value keeps every member in wire order, a duplicate key included, and a bytes_value in each is the marker, so its JSON names the key twice, as the kvlist_value held it; a JSON reader takes the last. In OTLP JSON a bytes_value is base64: the proto3 JSON mapping writes it in the standard alphabet with padding, and a parser accepts the standard or the URL-safe alphabet, padded or not, so N is the length it decodes to (`_-__` is 3 bytes, `iVBORw0KGgo` 8). This differs from the root of a serialized value (above), which is JSON and so quoted. generators/media_parts.py attribute_value and otlp_attribute_value are the reference, and the TypeScript examples run through the replacer the tests hold; each example's output is the attribute value the SDK sets: a string, an array of them, a mapping (Python and the sink), or an array's or a mapping's JSON.

##### `python_bytes_attribute`

Value (Python):

```text
b"\x89PNG"
```

Attribute value:

```text
[stripped unknown 4 bytes]
```

##### `python_byte_objects_in_an_array_attribute`

Value (Python):

```text
[b"ab", bytearray(3), memoryview(bytes(8)).cast("I")]
```

Attribute value:

```text
["[stripped unknown 2 bytes]", "[stripped unknown 3 bytes]", "[stripped unknown 8 bytes]"]
```

##### `python_byte_objects_beside_strings_in_an_array_attribute`

Strings and markers are all strings, so the array stays an array.

Value (Python):

```text
["a", b"ab"]
```

Attribute value:

```text
["a", "[stripped unknown 2 bytes]"]
```

##### `python_byte_objects_in_a_mapping_and_a_nested_array`

Value (Python):

```text
{"k": b"ab", "n": [[b"abc"], ["x"]], "i": 1}
```

Attribute value:

```text
{"k": "[stripped unknown 2 bytes]", "n": [["[stripped unknown 3 bytes]"], ["x"]], "i": 1}
```

##### `python_byte_object_beside_a_number`

An array of a number and a marker would not be homogeneous, so it is the array's JSON.

Value (Python):

```text
[1, b"ab"]
```

Attribute value:

```text
[1,"[stripped unknown 2 bytes]"]
```

##### `python_byte_object_in_a_mapping`

OpenTelemetry Python holds a mapping, so it is set as a mapping.

Value (Python):

```text
{"img": b"abc"}
```

Attribute value:

```text
{"img": "[stripped unknown 3 bytes]"}
```

##### `python_byte_object_beside_a_number_in_a_mapping`

The mixed array is its JSON, and the mapping around it stays a mapping.

Value (Python):

```text
{"k": [1, b"ab"]}
```

Attribute value:

```text
{"k": "[1,\"[stripped unknown 2 bytes]\"]"}
```

##### `python_byte_object_beside_a_number_in_a_nested_array`

The inner array is its JSON, so the outer one is an array of strings.

Value (Python):

```text
[[1, b"a"]]
```

Attribute value:

```text
["[1,\"[stripped unknown 1 bytes]\"]"]
```

##### `typescript_buffer_attribute`

Value (TypeScript):

```text
Buffer.from([137, 80, 78, 71])
```

Attribute value:

```text
[stripped unknown 4 bytes]
```

##### `typescript_byte_objects_in_an_array_attribute`

Value (TypeScript):

```text
[new Uint8Array(2), new ArrayBuffer(3)]
```

Attribute value:

```text
["[stripped unknown 2 bytes]", "[stripped unknown 3 bytes]"]
```

##### `typescript_byte_objects_beside_strings_in_an_array_attribute`

Value (TypeScript):

```text
[new Uint8Array(2), "x"]
```

Attribute value:

```text
["[stripped unknown 2 bytes]", "x"]
```

##### `typescript_byte_objects_in_a_mapping_and_a_nested_array`

OpenTelemetry JS holds no mapping, so the mapping is its JSON, one string. A Uint16Array of 2 items is 4 bytes.

Value (TypeScript):

```text
{ k: new Uint16Array(2), n: [[new DataView(new ArrayBuffer(3))], ["x"]] }
```

Attribute value:

```text
{"k":"[stripped unknown 4 bytes]","n":[["[stripped unknown 3 bytes]"],["x"]]}
```

##### `typescript_byte_object_in_a_nested_array`

OpenTelemetry JS holds no nested array, so the array is its JSON.

Value (TypeScript):

```text
[[new Uint8Array(3)], ["x"]]
```

Attribute value:

```text
[["[stripped unknown 3 bytes]"],["x"]]
```

##### `typescript_byte_object_beside_a_number`

Value (TypeScript):

```text
[1, new Uint8Array(2)]
```

Attribute value:

```text
[1,"[stripped unknown 2 bytes]"]
```

##### `typescript_byte_object_beside_a_number_in_a_mapping`

The mapping is its JSON, encoded once, so the mixed array in it is an array, not its own JSON as a string.

Value (TypeScript):

```text
{ k: [1, new Uint8Array(2)] }
```

Attribute value:

```text
{"k":[1,"[stripped unknown 2 bytes]"]}
```

##### `typescript_byte_object_beside_a_number_in_a_nested_array`

The inner array is its JSON, so the outer one is an array of strings, which OpenTelemetry JS holds.

Value (TypeScript):

```text
[[1, new Uint8Array(1)]]
```

Attribute value:

```text
["[1,\"[stripped unknown 1 bytes]\"]"]
```

##### `typescript_byte_object_beside_a_number_in_an_array_beside_a_number`

The inner array is its JSON, which leaves the outer one a number beside a string. OpenTelemetry JS cannot hold that array, so the whole value is its JSON, encoded once.

Value (TypeScript):

```text
[1, [1, new Uint8Array(1)]]
```

Attribute value:

```text
[1,[1,"[stripped unknown 1 bytes]"]]
```

##### `otlp_bytes_value`

An OTLP JSON AnyValue; the protobuf bytes_value is the same 8 bytes.

Value (OTLP JSON (the sink)):

```text
{"bytesValue":"iVBORw0KGgo="}
```

Attribute value:

```text
[stripped unknown 8 bytes]
```

##### `otlp_bytes_values_in_an_array_value`

Value (OTLP JSON (the sink)):

```text
{"arrayValue":{"values":[{"bytesValue":"QUJD"},{"bytesValue":""},{"stringValue":"plain"}]}}
```

Attribute value:

```text
["[stripped unknown 3 bytes]", "[stripped unknown 0 bytes]", "plain"]
```

##### `otlp_bytes_values_url_safe_and_unpadded`

A protobuf JSON parser reads _-\_\_ (URL-safe) as 3 bytes and iVBORw0KGgo (unpadded) as 8.

Value (OTLP JSON (the sink)):

```text
{"arrayValue":{"values":[{"bytesValue":"_-__"},{"bytesValue":"iVBORw0KGgo"}]}}
```

Attribute value:

```text
["[stripped unknown 3 bytes]", "[stripped unknown 8 bytes]"]
```

##### `otlp_bytes_values_in_a_kvlist_value_and_a_nested_array_value`

Value (OTLP JSON (the sink)):

```text
{"kvlistValue":{"values":[{"key":"k","value":{"bytesValue":"iVBORw0KGgo="}},{"key":"n","value":{"arrayValue":{"values":[{"arrayValue":{"values":[{"bytesValue":"QUJD"}]}}]}}},{"key":"i","value":{"intValue":"1"}}]}}
```

Attribute value:

```text
{"k": "[stripped unknown 8 bytes]", "n": [["[stripped unknown 3 bytes]"]], "i": 1}
```

##### `otlp_bytes_value_beside_an_int_value`

Value (OTLP JSON (the sink)):

```text
{"arrayValue":{"values":[{"intValue":"1"},{"bytesValue":"QUI="}]}}
```

Attribute value:

```text
[1,"[stripped unknown 2 bytes]"]
```

##### `otlp_bytes_value_beside_an_empty_any_value`

An AnyValue with no value set is an empty value, written as null.

Value (OTLP JSON (the sink)):

```text
{"arrayValue":{"values":[{},{"bytesValue":"QQ=="}]}}
```

Attribute value:

```text
[null,"[stripped unknown 1 bytes]"]
```

##### `otlp_bytes_values_in_a_kvlist_value_with_a_duplicate_key`

Both members named k are kept, in wire order, the bytes_value in the first one replaced.

Value (OTLP JSON (the sink)):

```text
{"arrayValue":{"values":[{"bytesValue":"QQ=="},{"kvlistValue":{"values":[{"key":"k","value":{"bytesValue":"YWI="}},{"key":"k","value":{"stringValue":"x"}}]}}]}}
```

Attribute value:

```text
["[stripped unknown 1 bytes]",{"k":"[stripped unknown 2 bytes]","k":"x"}]
```

## Input

| Source | Shape | Becomes | Modality | Paths | Fixtures | Notes |
| -- | -- | -- | -- | -- | -- | -- |
| `openai.chat` | `image_url.url = data:<mime>;base64,...` | blob | image | passthrough, openinference, laminar | `openinference-openai/image_data_url`, `openinference-js-openai/image_data_url` | The mime type comes from the data URL. OpenInference (Python and JS) flattens it into the message contents, and its input.value keeps the request JSON. |
| `openai.chat` | `image_url.url = http(s)://...` | uri | image | passthrough, openinference, openllmetry, laminar | `openinference-openai/image_https_url`, `openinference-js-openai/image_https_url`, `openllmetry/image_https_url` | OpenLLMetry before 0.62 writes the content array as a JSON string in gen_ai.prompt.N.content. From 0.62 it writes a native uri part. A URL of any other scheme but data (gs://, s3://, file://) is a uri the same way. A URL holding data:, in any case, past its start (a link followed by a data URL, or a data URL led by whitespace) is a blob with no byte_size (see part_shapes). |
| `openai.chat` | `image_url.url = "" \| __REDACTED__` | blob | image | passthrough, openllmetry, laminar | none | No recorded family writes it in a provider item (OpenInference writes \_\_REDACTED\_\_ in its flattened messages; see the OpenInference image row); covered by the SDK pass-through and sink unit tests. The URL was dropped upstream, so the blob has no byte_size and its stripped_reason is redacted_upstream. |
| `openai.chat` | `input_audio {data, format}` | blob | audio | passthrough, openllmetry, laminar | none | No recorded family writes it in a message key (OpenInference keeps it only in input.value; see the OpenInference raw-payload row); covered by the SDK pass-through unit tests. The mime type is audio/&lt;format&gt;. |
| `openai.chat` | `file {file_id}` | file / blob | from_mime | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. The modality comes from the filename extension alone; with no filename it is document. A file with no usable file_id, file_data or file_url (each missing, not a string, empty or \_\_REDACTED\_\_) becomes a blob with stripped_reason redacted_upstream, never a file part without a file_id. |
| `openai.chat` | `file {file_data, filename}` | blob | from_mime | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. The modality comes from the data URL's mime type, or from the filename extension. |
| `openai.responses` | `input_image {image_url \| file_id}` | blob / uri / file | image | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. A data URL becomes a blob, any other URL a uri, a file id a file. A URL holding data:, in any case, past its start (a link followed by a data URL, or a data URL led by whitespace) is a blob with no byte_size (see part_shapes). An empty or \_\_REDACTED\_\_ image_url or file_id, with no usable other, becomes a blob with stripped_reason redacted_upstream. |
| `openai.responses` | `input_file {file_id \| file_data \| file_url}` | file / blob / uri | from_mime | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. A file id becomes a file, file data a blob, a file URL a uri. A URL holding data:, in any case, past its start (a link followed by a data URL, or a data URL led by whitespace) is a blob with no byte_size (see part_shapes). With no usable file id, file data or file URL (each missing, not a string, empty or \_\_REDACTED\_\_), it becomes a blob with stripped_reason redacted_upstream. The modality comes from a data URL's mime type, else from the filename extension alone (never the file URL's); with no filename it is document. |
| `anthropic.messages` | `image / document with source.type = base64` | blob | from_mime | passthrough, openinference, openllmetry, laminar | `openinference-anthropic/image_base64`, `openinference-js-anthropic/image_base64` | The mime type comes from source.media_type. OpenInference Python flattens an image into a data URL in the message contents; OpenInference JS flattens it to image.media_type and image.type with no data at all (a blob with stripped_reason redacted_upstream). A document is dropped from the flattened messages, so it makes no part (see the OpenInference raw-payload row). |
| `anthropic.messages` | `image / document with source.type = url` | uri / blob | from_mime | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. An empty or \_\_REDACTED\_\_ url becomes a blob with stripped_reason redacted_upstream, keeping source.media_type. A URL holding data:, in any case, past its start (a link followed by a data URL, or a data URL led by whitespace) is a blob with no byte_size (see part_shapes). |
| `anthropic.messages` | `image / document with source.type = file` | file / blob | from_mime | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. An empty or \_\_REDACTED\_\_ file_id becomes a blob with stripped_reason redacted_upstream, keeping source.media_type. |
| `anthropic.messages` | `document with source.type = text \| content` | text | - | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. It is text to the model, so it becomes text parts. |
| `mistral.chat` | `input_audio = base64 string` | blob | audio | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. Mistral's audio chunk {"type":"input_audio","input_audio":"&lt;base64&gt;"} (inputAudio in a request object from its TypeScript SDK) names no format, so the blob has no mime type. Mistral images are data URLs in image_url, the openai.chat image_url rows. |
| `langchain.messages` | `v1 standard content block image / audio / video / file / text-plain with base64` | blob | from_mime | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. The block {"type":"image","base64":...,"mime_type":...}. The mime type comes from mime_type; with none, the modality comes from the block type (file and text-plain are document). A block by url or file_id is the reference rows below. |
| `langchain.messages` | `v1 standard content block image / audio / video / file with url` | uri / blob | from_mime | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through and sink unit tests. A url that is not a data URL is a uri, its link kept; a data URL is a blob under the data URL rules, mime_type the hint; an empty or \_\_REDACTED\_\_ url, with no usable file_id, is a blob with stripped_reason redacted_upstream (a file block with a string file_id is the native file part of the file_id row instead). The modality comes from mime_type, then the block type (image, audio, video), then, for a file block, the URL path's extension, then document. A LangChain v0 block by url has this shape and is read the same way. |
| `langchain.messages` | `v1 standard content block image / audio / video / file with file_id` | file / blob | from_mime | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through and sink unit tests. A usable file_id is a file part. An image, audio or video block whose file_id is empty or \_\_REDACTED\_\_, with no usable url, is a blob with stripped_reason redacted_upstream. A file block whose file_id is usable, or is a string while the block has no other usable reference (no string base64, no usable url), has a native file part's shape and is read as one, so its file_id is kept as written, empty included, and its modality comes from its own valid modality member, then mime_type, else document; with a usable url or a string base64 beside an empty or \_\_REDACTED\_\_ file_id, the usable reference wins. OpenLLMetry and Laminar write these blocks in gen_ai.prompt.N.content. |
| `langchain.messages` | `v0 content block with source_type = base64` | generic | - | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through and sink unit tests. The block {"type":"image","source_type":"base64","data":...,"mime_type"?}. No rule maps it to a media part, so it stays as it came, and its data is stripped in place per raw_payloads: source_type base64 is the context for data, and the mime type comes from mime_type, else it is unknown. A v0 block by url is the v1 url row; a v0 block by id makes no part and holds nothing to strip. |
| `bedrock.converse` | `image / document / video / audio with source.bytes` | blob | from_mime | passthrough, laminar | none | No recorded family; covered by the SDK pass-through unit tests. The block {"image":{"format":"png","source":{"bytes":...}}}, with no type. An image's mime type is image/&lt;format&gt;; a video, audio or document format is not always a MIME subtype (three_gp, mp3, docx), so it gives none, and the modality comes from the block. A source by s3Location is not mapped yet and stays as it came. OpenLLMetry content is a block list only when every block has a type, so Bedrock content there stays text, with its bytes stripped per raw_payloads. |
| `gemini.generate_content` | `inline_data {mime_type, data}` | blob | from_mime | passthrough | none | No recorded family; covered by the SDK pass-through unit tests. |
| `gemini.generate_content` | `file_data {mime_type, file_uri}` | uri / blob | from_mime | passthrough | none | No recorded family; covered by the SDK pass-through unit tests. The modality comes from the mime type, else from the URI path's extension. A data URL becomes a blob, and an empty or \_\_REDACTED\_\_ file_uri a blob with stripped_reason redacted_upstream. A URL holding data:, in any case, past its start (a link followed by a data URL, or a data URL led by whitespace) is a blob with no byte_size (see part_shapes). |
| `openinference.llm` | `message_content.type = image, image.image.url = data URL \| http(s) \| __REDACTED__` | blob / uri | image | openinference | `openinference-openai/image_data_url`, `openinference-openai/image_https_url`, `openinference-openai/image_redacted`, `openinference-anthropic/image_base64`, `openinference-js-openai/image_data_url`, `openinference-js-openai/image_https_url`, `openinference-js-openai/image_redacted` | A data URL becomes a blob, an http(s) URL a uri, and \_\_REDACTED\_\_ a blob with stripped_reason redacted_upstream. Each takes image.media_type, when the item has a valid one, as its MIME type; a data URL's own valid media type wins over it. A URL holding data:, in any case, past its start (a link followed by a data URL, or a data URL led by whitespace) is a blob with no byte_size (see part_shapes). Python and JS; the JS instrumentor redacts above the same 32,000 characters. |
| `vercel.ai` | `image / file parts in ai.prompt.messages` | blob / uri | from_mime | vercel | `vercel-ai-v5/image_file`, `vercel-ai-v5/pdf_file`, `vercel-ai-v5/text_plain_file`, `vercel-ai-v5/audio_file`, `vercel-ai-v6/image_file`, `vercel-ai-v6/pdf_file`, `vercel-ai-v6/text_plain_file`, `vercel-ai-v6/audio_file` | The existing blob and uri mapping, with the modality rule. A blob is stripped. TypeScript SDK and sink. The AI SDK writes a file part as a part of type file with mediaType and base64 data in ai.prompt.messages (the model call), whatever the media type. A PDF and a text/plain file are not images. Data that starts with a URL scheme other than data (http, https, gs, s3, file), or v7 data tagged url, is a uri, the link kept, unless it holds data:, in any case, past its start, which makes a blob with no byte_size; a file part by URL with no mediaType takes its modality from the URL path's extension. A v7 tag no rule names is a blob with no byte_size. |
| `vercel.ai` | `image / file part whose data is neither a string nor v7 tagged data holding one` | no part | - | vercel | none | No recorded family writes it; covered by the TypeScript SDK and sink Vercel cases. It makes no part, never a bare {"type":"file"}; the message keeps its other parts, and any raw payload holding the bytes is stripped per raw_payloads. |
| `semconv.native` | `blob part with content` | blob | from_mime | native | `pydantic-ai/image_binary` | The same blob, stripped. pydantic-ai writes it in gen_ai.input.messages and pydantic_ai.all_messages. This applies to any OTel GenAI instrumentation that writes blob parts. |
| `semconv.native` | `uri part` | uri | from_mime | native | `openllmetry/image_https_url` | Rebuilt into its canonical shape (see part_shapes). A modality it has is kept, else it comes from the mime type, then the URI's filename extension, then document. OpenLLMetry 0.62 writes it in gen_ai.input.messages. |
| `semconv.native` | `file part` | file | from_mime | native | none | No recorded family; covered by the SDK pass-through unit tests. Rebuilt into its canonical shape (see part_shapes). A modality it has is kept, else it comes from the mime type, then document. |
| `openinference.llm` | `image.image.url = data:None;url,None` | blob | image | openinference | `openinference-anthropic/image_url` | What OpenInference's Anthropic instrumentor writes for an image with a url source; the URL itself is lost. The data URL names no mime type and holds no bytes, so the blob has neither mime_type nor byte_size, and its stripped_reason is redacted_upstream. |
| `laminar.openhands` | `ImageContent with image_urls in lmnr.span.input` | no part (raw payload stripped: `lmnr.span.input`) | - | laminar | `laminar/image_base64`, `laminar/image_https_url` | lmnr.span.input is a raw payload, not a message key, so it makes no part. A data URL in it is stripped per raw_payloads; an http(s) URL stays. Written on the conversation.send_message span's input, and the sink keeps it in InputValue. The LLM span drops the image when the model has no vision support. |
| `vercel.ai` | `file part with Buffer data in ai.prompt` | no part (raw payload stripped: `ai.prompt`) | - | vercel | `vercel-ai-v5/image_file`, `vercel-ai-v5/pdf_file`, `vercel-ai-v5/text_plain_file`, `vercel-ai-v5/audio_file`, `vercel-ai-v6/image_file`, `vercel-ai-v6/pdf_file`, `vercel-ai-v6/text_plain_file`, `vercel-ai-v6/audio_file` | On the operation span (ai.generateText) the prompt is JSON, and a file given as a Buffer is written as an object of type Buffer whose data is a JSON array of byte values, not base64. ai.prompt is a raw payload, so it makes no part; the Buffer object is replaced per raw_payloads, with byte_size the array length. The part comes from ai.prompt.messages on the model-call span (the image / file parts row). |
| `vercel.ai` | `image part with base64 image in ai.prompt` | no part (raw payload stripped: `ai.prompt`) | - | vercel | none | No recorded family writes it; the recorded image parts are Buffers (the Buffer row). Covered by the golden examples and the TypeScript SDK and sink unit tests. An image given as a base64 string is written {"type":"image","image":"&lt;base64&gt;","mediaType"?}. ai.prompt is a raw payload, so it makes no part; image is stripped per raw_payloads, mime type from mediaType, else unknown. An image that starts with a URL scheme stays a link, and a data URL in it is replaced with its own mime type. |
| `vercel.ai` | `file / image part with v7 tagged data in ai.prompt` | no part (raw payload stripped: `ai.prompt`) | - | vercel | none | No recorded family writes it; covered by the golden examples and the TypeScript SDK and sink unit tests. v7 writes the payload as {"type":"data","data":"&lt;base64&gt;"} under a file part's data or an image part's image. ai.prompt is a raw payload, so it makes no part; the inner data is stripped per raw_payloads, mime type from the part's mediaType, else unknown. A URL in it stays. A data URL that rule (b)'s pattern matches in full is replaced with its own mime type and size; any other data: string (wrapped, percent-encoded, or with a broken run) is replaced whole as a rule (e) token, with the part's mediaType, else unknown. |
| `vercel.ai_otel` | `blob part with modality image for a non-image file, in gen_ai.input.messages` | blob | from_mime | native | `vercel-ai-otel/image_file`, `vercel-ai-otel/pdf_file`, `vercel-ai-otel/text_plain_file`, `vercel-ai-otel/audio_file` | @ai-sdk/otel writes every file part as a blob with base64 content and labels application/pdf and text/plain as modality image (audio/wav is labelled audio). The modality is recomputed from the mime type, so these become document blobs. |
| `openinference.llm` | `message_content.type = image with no image.url (image.media_type and image.type only, or nothing)` | blob | image | openinference | `openinference-js-anthropic/image_base64`, `openinference-js-anthropic/image_url` | What OpenInference's JS Anthropic instrumentor writes for an image. A base64 source leaves image.media_type (the mime type) and image.type = base64 but no data; a url source leaves only message_content.type = image. The blob carries the mime type when given, no byte_size, and stripped_reason redacted_upstream. |
| `openinference.llm` | `media present only in input.value (audio input, PDF document)` | no part (raw payload stripped: `input.value`) | - | openinference | `openinference-openai/input_audio`, `openinference-js-openai/input_audio`, `openinference-anthropic/document_pdf`, `openinference-js-anthropic/document_pdf` | OpenInference (Python and JS) leaves OpenAI input_audio and an Anthropic base64 document out of the flattened messages, and keeps them only in the request JSON of input.value. No part is made; the raw payload is stripped per raw_payloads. |
| `openllmetry.openai` | `image as a data URL: the instrumentor drops the prompt content; nothing to normalize` | no part | - | openllmetry | `openllmetry/image_base64` | Before 0.62 the span keeps only gen_ai.prompt.0.role, with no content; 0.62 writes no gen_ai.input.messages at all. This holds for every recorded version. |
| `rius.sdk` | `byte object in a serialized value (Python bytes, bytearray, memoryview; TypeScript ArrayBuffer and its views, Buffer included)` | no part (raw payload stripped: `input.value`, `output.value`) | - | passthrough | none | No recorded family records one; covered by the SDK serialization unit tests. The SDK writes it as [stripped unknown &lt;N&gt; bytes] while serializing, per raw_payloads byte_objects, so no bytes reach the attribute. It makes no part. The same holds for a value recorded as output, and for a tool's arguments and result. |

## Output

| Source | Shape | Becomes | Modality | Paths | Fixtures | Notes |
| -- | -- | -- | -- | -- | -- | -- |
| `openai.chat` | `message.audio {data, transcript}` | blob | audio | passthrough, openllmetry, laminar | none | No recorded family writes it in a message key (OpenInference keeps it only in output.value; see the OpenInference raw-payload row); covered by the SDK pass-through unit tests. A text part with the transcript follows the blob. |
| `openai.responses` | `image_generation_call.result (base64)` | blob | image | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. |
| `openinference.llm` | `media present only in output.value (audio output)` | no part (raw payload stripped: `output.value`) | - | openinference | `openinference-openai/audio_output`, `openinference-js-openai/audio_output` | OpenInference (Python and JS) leaves an OpenAI message.audio response out of the flattened messages, and keeps it only in the response JSON of output.value. No part is made; the raw payload is stripped per raw_payloads. |
