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
- Every native media part in a message key (blob, uri or file) is always rebuilt into its canonical shape: members in the pinned order, extra members dropped, and every member that is unknown omitted. The only exception is a uri part whose uri is not a string, or a file part whose file_id is not a string: it is left as it came. Any string is a usable uri or file_id, the empty string included. Every other normalized media part carries a modality.
- Parts are rebuilt only in a message-key value that parses as JSON and nests at most 1000 levels deep. Arrays and objects count together from the value's root, which is level 1: the message array, a message, its parts array and a tool call part are 4 levels. A value nested deeper (a tool call whose arguments add 997 more arrays makes 1001 levels) is left as it came, every part in it included; at 1000 levels its parts are rebuilt. The implementation counts the depth itself and never relies on its parser's or its language's recursion limit. The strip still runs on a value left this way.
- The modality that the part already has is kept, when it is one of modalities (any other value is ignored), except for a blob whose content is a string and a uri holding a data URL (below). Otherwise it is taken from the MIME type. Failing that, a provider item whose kind names a modality takes it from the kind: an image, image_url, input_image or image_generation_call item is image, an input_audio item audio, a document item document. A LangChain v1 block of type image, audio or video is that modality, and of type file or text-plain document; a Bedrock Converse image, video, audio or document block is that modality. An OpenAI file or input_file item names none; its modality comes from the extension of its filename member alone (never from a file_url), and with no filename, or an empty one, it is document. A Gemini file_data, a native uri and a Vercel file part by URL take it from the extension of their URI's path (see extensions), the Vercel part whether its URL is a plain string or v7's {"type":"url"} data; a Vercel image part is an image. Otherwise it is document. So an Anthropic document by URL ending in .png is a document, an OpenAI input_file named a.png is an image, and an input_file by a file_url ending in .png with no filename is a document. A native file part with no valid modality and no MIME type gets document; no member of it is read for an extension. Any other part with no MIME type and no other hint also gets document.
- A blob whose `content` is a string is rebuilt with stripped_reason not_captured and a byte_size taken from the content under the size rule of the strip (omitted when the size is unknown). Its modality comes from its MIME type first, then from the modality it has, then document: a PDF blob labelled image is a document. A content string that is itself a data URL follows the data URL rules below, with the part's mime_type as the hint and the same modality order. A blob in a message key never carries content.
- A blob with no string `content` keeps a stripped_reason that is one of stripped_reasons. Otherwise its stripped_reason is redacted_upstream when it has no content member or a null one, and not_captured when its content is any other value. It keeps a byte_size that is a whole, non-negative number no larger than 2^53 - 1 (8, 8.0 and 8e0 alike, written 8); any other byte_size is omitted.
- A uri part, or a provider uri such as a Gemini file_data, whose URI is a data URL is never a uri: it becomes a blob under the data URL rules below. A native uri part takes that blob's modality as a blob whose content is a string does: from the MIME type first, then the modality it has, then document.
- In a provider media item, a URL or a file id that is empty, or that is the \_\_REDACTED\_\_ marker an instrumentor writes in its place, was dropped upstream. When the item has no other usable reference (one that is neither empty nor \_\_REDACTED\_\_), it becomes a blob with the stripped_reason redacted_upstream and no byte_size. It keeps the MIME type the item gives (an Anthropic source's media_type, a Gemini file_data's mime_type, a Vercel part's mediaType) and takes its modality by the rule above, so an image_url or input_image is image. This covers an image_url's url, an input_image's image_url and file_id, an Anthropic url or file source, a Gemini file_data's file_uri, a Vercel part's v7 {"type":"url"} data, and an OpenAI file or input_file's file_id, file_data and file_url (an empty file_data counts as dropped too, since its item has nothing else to point to). An OpenAI file or input_file with no usable reference becomes this blob too when it has no reference member at all, or only ones that are not strings (a file_id of 5 or null): its type file would otherwise collide with a native file part. A usable reference wins: an input_image whose image_url is \_\_REDACTED\_\_ and whose file_id is usable is a file, and an OpenAI file with an empty file_id and non-empty file_data is a blob of that data. It matches OpenInference's \_\_REDACTED\_\_ on the flattened path. So no provider item this rule covers is left as a part of type file without a file_id. A native uri or file part is no provider item: its empty uri or file_id is kept. Nor is a reference not yet mapped to a part (a LangChain v1 image, audio or video block by url or file_id, a Bedrock Converse source by s3Location): it stays as it came, empty or not. A LangChain v1 file block by file_id has a native file part's shape and is read as one. A LangChain v1 file block by url is not mapped yet either and stays as it came.
- A URL of any scheme other than data: is a uri, its link kept as written: http, https, gs, s3, file and any other scheme alike. Only a data: URL, or inline data, becomes a blob. Where one value may hold either a URL or bare base64 (a Vercel file part's data or image part's image, as a plain string or as v7's {"type":"data"} data), it is a URL when it starts with a scheme: an ASCII letter, then any ASCII letters, digits, `+`, `-` or `.`, then a colon. Base64 holds no colon, so the two never meet; anything else is base64. A value v7 tags {"type":"url"} is a URL whatever it holds. The strip reads these values the same way: rule (e) leaves a value that starts with a scheme to rule (b) (raw_payloads, rule (e)'s url_scheme and keeps_urls).
- A Vercel file part whose data, or image part whose image, is neither a string nor v7 tagged data holding one makes no part: it is dropped from its message's parts, never written as a bare {"type":"file"} or {"type":"image"}, and any raw payload holding its bytes is stripped per raw_payloads. So is a v7 {"type":"text"} whose text is not a string. A v7 tag no rule here names becomes a blob with the stripped_reason not_captured and no byte_size, keeping the part's mediaType: its size was never measured.
- When a part has duplicate `type` members, the last one wins, as in a standard JSON decoder. The strip is different: there, a condition on `type` holds when any member qualifies.
- A base64 data URL (rule (b)'s pattern matching the whole string) becomes a blob with the stripped_reason not_captured. Its mime type is the URL's when that is a valid token/token MIME type, else the hint (a native part's mime_type). Its byte_size is that of the base64 run under the size rule of the strip: an empty run is 0 bytes, and an invalid run has no byte_size.
- A provider item's bare base64 payload (an input_audio data, a Mistral input_audio or inputAudio string, an Anthropic base64 source's data, a LangChain v1 block's base64, a Bedrock Converse source's bytes, an image_generation_call result, a Gemini inline_data data, a Vercel file part's data or image part's image, a non-empty OpenAI file_data) becomes a blob with the stripped_reason not_captured, its byte_size under the size rule of the strip: an empty string is 0 bytes, never redacted_upstream. A payload that is itself a data URL follows the data URL rules. An OpenAI file or input_file with no usable file_id, file_data or file_url was dropped upstream (above).
- A data URL that is not base64 (`data:<mime>,<payload>`) becomes a blob with the stripped_reason not_captured and no byte_size. Its mime type is the text after `data:` up to the first `;` or `,`, when that is a valid token/token MIME type, else the hint; its payload is everything after the first comma. This rule also covers a URL that names base64 but whose run does not match rule (b), such as `data:image/png;base64,@@`. When its payload is empty or `None`, it becomes a blob with the stripped_reason redacted_upstream.
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

## Raw payloads

**Source rule.** Normalized message parts come only from message keys: gen_ai.input.messages, gen_ai.output.messages and gen_ai.system_instructions, or the flattened instrumentor message keys each normalizer already maps (OpenInference llm.input_messages.\* and llm.output_messages.\*, OpenLLMetry gen_ai.prompt.\* and gen_ai.completion.\*, Vercel ai.prompt.messages). Raw request and response payloads are never mined to rebuild parts.

Message keys (a key ending in `.` is a prefix): `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`, `llm.input_messages.`, `llm.output_messages.`, `gen_ai.prompt.`, `gen_ai.completion.`, `ai.prompt.messages`.

Raw payloads, never mined for parts: `input.value`, `output.value`, `lmnr.span.input`, `lmnr.span.output`, `ai.prompt`, `pydantic_ai.all_messages`, `InputValue`, `OutputValue`.

**Strip rule.** Each media token (found by the detection rules below) is replaced in place. Every other byte of the string stays identical: normalizers must not parse and re-serialize the JSON. Byte equality across the Python SDK, the TypeScript SDK and the Go sink depends on this. Message parts in gen_ai.\*.messages keep the stripped blob part shape instead; the replacement string is only for raw payloads.

**Scope.** The SDKs strip every string value, and every element of a string-array value, of the span attributes, the span event attributes and the span link attributes. They do not strip resource or scope attributes: a span processor cannot rewrite them. The sink applies the same rules to its stored columns InputValue, OutputValue, InputMessages and OutputMessages and to the values of SpanAttributes. tools/check_fixtures.py scans more than the strip covers: it also scans the resource and scope attributes of a recording. That scan is a check, not a strip rule, and media in those attributes would still be a bug. An SDK may bound the work it spends on one very large value. Past that bound no media survives, but byte identity with the other implementations is not promised.

**Order.** A normalizer first builds parts from the message keys (the source rule). Stripping runs last, over every string attribute in scope, including the message-key attributes it keeps and the gen_ai.\*.messages it produced. A stripped blob part carries no content, so nothing in it matches; a text part holding a data URL gets rule (b) in place. So in a message key (and in the sink's InputMessages and OutputMessages columns) a blob part never has a content member, while in any other attribute or column a blob part's content may be a complete replacement, the one rule (e) writes there. The fixture check holds expected results to exactly this: a normalized blob part carries no content. Within one pass, every rule reads the text as it was before the pass: rule (e) takes its context and its mime type from each object's member values as they were, never from a sibling the same pass has already rewritten (see members). A walker that rewrites the document in place must keep reading the original values.

**JSON candidates.** A string value is a JSON candidate when, after trimming leading space, tab, newline and carriage return (ASCII only: U+00A0 and other Unicode spaces are not trimmed), it starts with `{` or `[`. A candidate parses when the whole string is one RFC 8259 JSON value, with only those four whitespace characters around it (no NaN, Infinity, comments or trailing commas; duplicate keys are allowed, and every one is read, see members), nested at most 64 levels deep. Arrays and objects count together, from the candidate's root: the root array or object is level 1, and a candidate nested deeper than 64 levels does not parse. A JSON document in a string inside JSON continues the same count: its root is one level below the deepest array or object holding that string, so a nested document that goes past 64 does not parse (rule (b) only, for it), while the document around it still does. The limit is explicit: an implementation counts the depth itself and never relies on its parser's or its language's recursion limit, so no input makes the strip fail. When it parses, rules (d), (e) and (b) apply to the values inside it; a string value inside it that is itself a JSON candidate is processed by the same rules, recursively, at its escaped location, its own document starting with no parent key and no enclosing object: nothing outside it is context for rule (e), and rule (d) inside it takes no mime type from outside. When it does not parse (a truncated payload, say), only rule (b) applies, to the string as it is (for a string inside JSON, to its unescaped value). A string that is not a candidate gets rule (b) only. Object keys are never matched.

**Precedence.** Values are visited in document order. At each value rule (d) is tried, then (e), then (b), and the first that matches wins. A value inside a replaced token is never visited: once (e) replaces a string, (b) does not look inside it, and nothing inside a replaced Buffer object is looked at. An array element inherits the parent key of its array, so `{"audio":[{"data":"..."}]}` matches (e) through the parent key audio; in the same way, the enclosing object rule (d) takes its mime type from is the nearest object holding the Buffer, directly or through arrays, and so is the holder whose mime type a typed key with holder_mime reads. A string that a typed key with keeps_urls leaves alone, because it starts with a URL scheme, is no (e) token, so (b) is tried on it: a data URL there is replaced with its own mime type, and any other URL stays.

**Idempotence.** Every implementation follows this rule: a string that is already a complete replacement, `[stripped <mime> <byte_size> bytes]` whose mime is unknown or matches mime_pattern in full (exactly the mimes a replacement can hold) and whose byte_size is ASCII digits or unknown, is never stripped again, by rule (e) or rule (b). Nor is a complete replacement ever context for rule (e): as the value of a sibling (a mime key, format or output_format) it counts neither for whether rule (e) fires nor for the mime type it chooses. So a Buffer that rule (d) turned into a replacement in one pass (`{"mediaType": {"type":"Buffer","data":[1]},"data":"QUFB"}`) makes no token of its siblings in the next. With both, strip(strip(x)) is strip(x) for every x except one class: a JSON candidate that does not parse before pass 1 and does parse after it. Elsewhere the sink re-strips what an SDK already stripped and gets the same bytes. In that class a second pass may strip more. It needs malformed JSON whose only defect sits inside a rule (b) data URL (an invalid escape such as `\d` in a mime type): pass 1 can only apply rule (b), which removes the defect, and pass 2 then parses the candidate and rules (d) and (e) fire on what pass 1 left, a partial replacement for instance. No media survives in either pass, and only the replacement text differs. See `a_second_pass_after_the_candidate_starts_to_parse`. A string that only looks like one is still a token: `[stripped image/png lots bytes]`, or `[stripped a b 3 bytes]` (rule e), or `[stripped data:image/png;base64,... 1 bytes]`, whose data URL rule (b) replaces.

**Spans.** Every span is on the original text; nothing is re-serialized. (d) The object token, from its `{` to its matching `}`, is replaced by the replacement as a JSON string literal, quotes included. (e) The string literal, quotes included, is replaced by the replacement as a JSON string literal, quotes included. (b) In a JSON string, only the URL's characters are replaced: the replacement goes inside the existing quotes, with no quotes added. (b) In a string that is not JSON (or did not parse), the URL's characters are replaced by the replacement, with no quotes. Rules (b) and (e) read a JSON string's unescaped value, so a span starts at the first raw character of its first character and ends after the last raw character of its last, escapes included (`data:image\/png` is read as `data:image/png`). Text written into a JSON string is escaped for its level with the minimal escapes JSON.stringify writes, and no others: `\"` for a quote, `\\` for a backslash, `\b` `\f` `\n` `\r` `\t`, `\u00xx` (lowercase hex) for any other control character, `\udxxx` for a lone surrogate. In a JSON string nested in a JSON string, the inner replacement is escaped once per level, and every byte outside the replaced tokens is kept as it was, including escapes the re-encoder would not write (`\u0022`, `\/`).

**Byte size.** Rule (e) computes it on the string's unescaped value, and rule (b) on its base64 run, the same way. Remove space, tab, newline and carriage return. When what is left is not valid base64, byte_size is unknown. Valid means: every character before the padding is from one alphabet, `A-Z a-z 0-9 + /` or `A-Z a-z 0-9 - _` (never `+` or `/` together with `-` or `_`); the padding is at most two `=`, only at the end; and the length, padding counted, is a multiple of 4 (so unpadded base64 is not valid). For valid base64, byte_size is length times 3 / 4, minus the number of `=`. Rule (d) takes the length of its data array.

**Members.** Every member of an object is visited, in document order, duplicate keys included. A condition on a key holds when any member with that key meets it (a type equal to Buffer, blob or base64 or to one of a typed key's types, a non-empty data array, a sibling), and a value read from a key (a mime type, a format, a Buffer's data array) is that of the first member with that key, in document order, that qualifies. Rule (e) applies to each member under one of its keys that qualifies, duplicates included, all with the context and mime type computed from all the siblings: `{"mediaType":"image/png","data":"QUFB","data":"QkJC"}` strips both data values. A sibling counts as context only when its value is a non-empty string that is not a complete replacement (see idempotence), the same rule as mime selection. Context and mime type are read from the member values as they were before the pass, so document order does not matter: in `{"mediaType":"data:image/png;base64,QUFB","data":"QkJC"}` mediaType is context, though rule (b) rewrites it in the same pass, and data is a token whichever comes first; its mime type is unknown, since the original mediaType is not a valid mime. `format` is not a sibling key: it counts only under the parent key input_audio or audio (which is context already), where it names audio/&lt;format&gt;, and elsewhere a format sibling is ignored; output_format counts anywhere. The mime type is chosen by the order of the mime key list, not by document order: the first mime key in list order whose value is a non-empty valid mime (see replacement) wins; else the first mime format, in order, whose sibling is a non-empty string, not a complete replacement, and whose mime is valid; else unknown. When a rule (e) key holds an array directly, each string element is its own token (when it is non-empty and not already a complete replacement), with the same context and mime type; any other element is visited as usual, with that key as its parent key.

**Regex dialect.** The pattern of rule (b), rule (e)'s url_scheme and the replacement's mime_pattern use only constructs Python re, JavaScript RegExp and Go RE2 read the same way: literal characters, character classes with explicit ASCII members and ranges, the escapes `\t` `\n` `\f` `\r`, capturing groups, and the quantifiers `*`, `+` and `{m,n}`. No `\s`, `\d`, `\w`, `\b`, lookaround, backreference, non-capturing group or inline flag: the case-insensitive scheme is written `[dD][aA][tT][aA]:`, and the repeated RFC 2397 parameter is a capturing group. Neither the mime class nor the parameter class holds `;` or `:`. RFC 2045 lists `:` as a tspecial, so it cannot appear in an unquoted mime type or parameter token, and excluding it keeps the search linear: an attempt starts only at a `data:` and never reads past the next `:` (the one in the next `data:`), so no stretch of text is read by more than two attempts, and inside an attempt the text splits into mime and parameters in exactly one way, so backtracking gives back each character at most once. Rule (b) finds matches left to right without overlap (Python finditer, JavaScript matchAll, Go FindAllStringSubmatchIndex). mime_pattern must match the whole value: Python re.fullmatch, or `^` and `$` around it in JavaScript and Go (where, without the m flag, `$` is the end of the text; in Python `$` also matches before a final newline, so use fullmatch). url_scheme must match at the start of the unescaped value and need not reach its end: Python re.match, or `^` before it in JavaScript and Go.

**Implementers.** Do not write the replacement, or any escape, with a standard library JSON encoder: Go's json.Marshal, for example, writes `<`, `>`, `&` and U+2028 as `\u003c`, `\u003e`, `\u0026` and `\u2028`, which no other implementation writes. Do not compute byte_size with a strict standard library base64 decoder either: decoders differ on whitespace, URL-safe input and padding. The escaping rules (spans), the size rules (byte_size) and the mime rule (replacement) here are exhaustive: write exactly what they say, and keep every other byte as it was. Read JSON with a parser that keeps the span of every value on the text and every duplicate member (members), and that counts the depth itself (json_candidate).

**Reference.** generators/media_parts.py strip_raw_payload(raw, text) is the reference implementation: the one function a normalizer author reproduces. It returns the stripped string; strip(raw, text) also returns the tokens it replaced (rule, mime, byte_size), in document order. The golden examples below are its tests, and every normalizer's.

**Replacement.** The text `[stripped <mime> <byte_size> bytes]`, with `unknown` for a mime type or size that is not known: `[stripped image/png 67 bytes]`, `[stripped unknown unknown bytes]`. Rules (d) and (e) write it as a JSON string literal, quotes included; rule (b) writes the bare text, inside the quotes already there in a JSON string. A mime type goes in only when the whole of it matches `[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+` (token/token); anything else is `unknown`.

A data URL inside other text: only the token is replaced, so `see data:image/png;base64,iVBORw0KGgo= here` becomes `see [stripped image/png 8 bytes] here`.

| Token | Replaced | Mime | Byte size |
| -- | -- | -- | -- |
| A data URL (rule b), anywhere in a string | The URL characters alone, from data: (in any case) to the end of the base64 run, parameters included, with no quotes added. The text around it stays byte-identical; a string that is only the data URL becomes the replacement text. | The URL's media type when it is token/token; unknown when it names none, or anything else. | The base64 run's size, per byte_size; unknown when the run is not valid base64. |
| A base64 string value (rule e) | The string literal, quotes included, by the replacement as a JSON string literal; for an array under the key, each string element the same way. | The first of media_type, mediaType, mime_type, mimeType, in that order, that holds a token/token mime; else image/&lt;output_format&gt;; else audio/&lt;format&gt; under input_audio or audio; else, under a typed key with holder_mime (a Vercel v7 tagged data), the enclosing object's first such mime key; else unknown. | The unescaped value's size, per byte_size; unknown when it is not valid base64. |
| A Buffer object (rule d) | The whole object token, from { to its matching }, by the replacement as a JSON string literal. | The first of the enclosing object's media_type, mediaType, mime_type, mimeType, in that order, that holds a token/token mime; else unknown. | The length of the data array. |

**Detection rules.** The normalizers strip, and tools/check_fixtures.py refuses
in an expected result, every token these find (in a string holding JSON too):

| Rule | Name | Matches | Parameters |
| -- | -- | -- | -- |
| (b) | data URL | A data:&lt;mime&gt;[;&lt;parameter&gt;]\*;base64,&lt;base64&gt; token anywhere in a string, the scheme in any case (DATA:, Data:) and RFC 2397 parameters allowed before ;base64, (data:image/png;name=a.png;base64,...). The pattern finds each one: group 1 the mime type (empty when none), group 2 the last parameter (unused), group 3 the base64 run (standard or URL-safe). A whole-string data URL is the special case. | pattern: `[dD][aA][tT][aA]:([^;,:\t\n\f\r "]*)(;[^;,:\t\n\f\r "]*)*;base64,([A-Za-z0-9+/_-]*={0,2})` |
| (d) | Buffer object | An object {"type": "Buffer", "data": [...]} whose data is a non-empty array. | type: `Buffer`; array_key: `data`; mime_keys: `media_type`, `mediaType`, `mime_type`, `mimeType` |
| (e) | keyed base64 string | A non-empty string (or each string of an array) under one of the keys, when its object has one of the sibling keys with a non-empty string value that is not a complete replacement, or one of the base64 markers (a member with exactly that key and that string value, as in the LangChain v0 block {"type":"image","source_type":"base64","data":...}), or its object's parent key is one of the parent keys, or its object is the value of a source key and has type base64 (the Anthropic {"source":{"type":"base64","media_type":...,"data":...}}: the object holding data is the source itself, not the content block around it); a non-empty string under content when its object has type blob (the semconv blob part, as in a raw payload like pydantic_ai.all_messages: the raw-payload twin of the fixture check's rule that a normalized blob part carries no content); a non-empty string under a typed key when its object has one of that key's types and, for a typed key that names parent keys, its object's parent key is one of them (a LangChain v1 standard content block {"type":"image","base64":...,"mime_type":...}, Mistral's audio chunk {"type":"input_audio","input_audio":...}, which its TypeScript SDK spells inputAudio, a Vercel image part {"type":"image","image":...}, or the v7 tagged data {"type":"data","data":...} a Vercel file part's data or image part's image holds); and a non-empty string under one of the source bytes keys when its object is the value of a source key, whatever its type (the Bedrock Converse {"image":{"format":"png","source":{"bytes":...}}}: as for Anthropic, the object holding bytes is the source). A typed key with keeps_urls leaves a string that starts with a URL scheme (url_scheme) to rule (b), whatever other way its key qualifies: an http URL under a Vercel image stays, and a data URL there is replaced by rule (b) with its own mime type. A typed key with holder_mime takes its mime type, when its own object names none, from the mime keys of the nearest object holding it, as rule (d) does, so a tagged data reads its Vercel part's mediaType. Never a string that is already a complete replacement (see idempotence). See members for duplicate keys, siblings and arrays. | keys: `data`, `b64_json`, `result`, `base64`; sibling_keys: `media_type`, `mediaType`, `mime_type`, `mimeType`, `output_format`; parent_keys: `input_audio`, `audio`, `inline_data`, `inlineData`; source_key: `source`; source_type: `base64`; blob_type: `blob`; blob_key: `content`; base64_markers: `source_type` = `base64`; typed_keys: `base64` under type `image`, `audio`, `video`, `file`, `text-plain`, `input_audio` under type `input_audio`, `inputAudio` under type `input_audio`, `image` under type `image` (keeps URLs), `data` under type `data` and parent key `data`, `image` (keeps URLs) (the holder's mime); url_scheme: `[A-Za-z][A-Za-z0-9+.-]*:`; source_bytes_keys: `bytes`; mime_keys: `media_type`, `mediaType`, `mime_type`, `mimeType`; mime_formats: `output_format` gives `image/<value>`, `format` gives `audio/<value>` under `input_audio`, `audio` |

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

A data URL under image is left to rule (b), so it is replaced with the URL's own mime type, not the part's mediaType, and with its size.

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

Tagged data keeps URLs too: a data URL in it gets rule (b) with its own mime type, and an https link stays.

Input:

```text
[{"type":"file","data":{"type":"data","data":"data:application/pdf;base64,JVBERi0="},"mediaType":"application/pdf"},{"type":"file","data":{"type":"data","data":"https://example.com/a.pdf"},"mediaType":"application/pdf"}]
```

Output:

```text
[{"type":"file","data":{"type":"data","data":"[stripped application/pdf 5 bytes]"},"mediaType":"application/pdf"},{"type":"file","data":{"type":"data","data":"https://example.com/a.pdf"},"mediaType":"application/pdf"}]
```

Tokens: (b) application/pdf, 5 bytes.

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

## Input

| Source | Shape | Becomes | Modality | Paths | Fixtures | Notes |
| -- | -- | -- | -- | -- | -- | -- |
| `openai.chat` | `image_url.url = data:<mime>;base64,...` | blob | image | passthrough, openinference, laminar | `openinference-openai/image_data_url`, `openinference-js-openai/image_data_url` | The mime type comes from the data URL. OpenInference (Python and JS) flattens it into the message contents, and its input.value keeps the request JSON. |
| `openai.chat` | `image_url.url = http(s)://...` | uri | image | passthrough, openinference, openllmetry, laminar | `openinference-openai/image_https_url`, `openinference-js-openai/image_https_url`, `openllmetry/image_https_url` | OpenLLMetry before 0.62 writes the content array as a JSON string in gen_ai.prompt.N.content. From 0.62 it writes a native uri part. A URL of any other scheme but data (gs://, s3://, file://) is a uri the same way. |
| `openai.chat` | `image_url.url = "" \| __REDACTED__` | blob | image | passthrough, openllmetry, laminar | none | No recorded family writes it in a provider item (OpenInference writes \_\_REDACTED\_\_ in its flattened messages; see the OpenInference image row); covered by the SDK pass-through and sink unit tests. The URL was dropped upstream, so the blob has no byte_size and its stripped_reason is redacted_upstream. |
| `openai.chat` | `input_audio {data, format}` | blob | audio | passthrough, openllmetry, laminar | none | No recorded family writes it in a message key (OpenInference keeps it only in input.value; see the OpenInference raw-payload row); covered by the SDK pass-through unit tests. The mime type is audio/&lt;format&gt;. |
| `openai.chat` | `file {file_id}` | file / blob | from_mime | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. The modality comes from the filename extension alone; with no filename it is document. A file with no usable file_id, file_data or file_url (each missing, not a string, empty or \_\_REDACTED\_\_) becomes a blob with stripped_reason redacted_upstream, never a file part without a file_id. |
| `openai.chat` | `file {file_data, filename}` | blob | from_mime | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. The modality comes from the data URL's mime type, or from the filename extension. |
| `openai.responses` | `input_image {image_url \| file_id}` | blob / uri / file | image | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. A data URL becomes a blob, any other URL a uri, a file id a file. An empty or \_\_REDACTED\_\_ image_url or file_id, with no usable other, becomes a blob with stripped_reason redacted_upstream. |
| `openai.responses` | `input_file {file_id \| file_data \| file_url}` | file / blob / uri | from_mime | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. A file id becomes a file, file data a blob, a file URL a uri. With no usable file id, file data or file URL (each missing, not a string, empty or \_\_REDACTED\_\_), it becomes a blob with stripped_reason redacted_upstream. The modality comes from a data URL's mime type, else from the filename extension alone (never the file URL's); with no filename it is document. |
| `anthropic.messages` | `image / document with source.type = base64` | blob | from_mime | passthrough, openinference, openllmetry, laminar | `openinference-anthropic/image_base64`, `openinference-js-anthropic/image_base64` | The mime type comes from source.media_type. OpenInference Python flattens an image into a data URL in the message contents; OpenInference JS flattens it to image.media_type and image.type with no data at all (a blob with stripped_reason redacted_upstream). A document is dropped from the flattened messages, so it makes no part (see the OpenInference raw-payload row). |
| `anthropic.messages` | `image / document with source.type = url` | uri / blob | from_mime | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. An empty or \_\_REDACTED\_\_ url becomes a blob with stripped_reason redacted_upstream, keeping source.media_type. |
| `anthropic.messages` | `image / document with source.type = file` | file / blob | from_mime | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. An empty or \_\_REDACTED\_\_ file_id becomes a blob with stripped_reason redacted_upstream, keeping source.media_type. |
| `anthropic.messages` | `document with source.type = text \| content` | text | - | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. It is text to the model, so it becomes text parts. |
| `mistral.chat` | `input_audio = base64 string` | blob | audio | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. Mistral's audio chunk {"type":"input_audio","input_audio":"&lt;base64&gt;"} (inputAudio in a request object from its TypeScript SDK) names no format, so the blob has no mime type. Mistral images are data URLs in image_url, the openai.chat image_url rows. |
| `langchain.messages` | `v1 standard content block image / audio / video / file / text-plain with base64` | blob | from_mime | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. The block {"type":"image","base64":...,"mime_type":...}. The mime type comes from mime_type; with none, the modality comes from the block type (file and text-plain are document). An image, audio or video block by url or file_id is not mapped yet and stays as it came. A file block by file_id has a native file part's shape and is read as one; a file block by url is not mapped yet. |
| `langchain.messages` | `v0 content block with source_type = base64` | generic | - | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through and sink unit tests. The block {"type":"image","source_type":"base64","data":...,"mime_type"?}. No rule maps it to a media part, so it stays as it came, and its data is stripped in place per raw_payloads: source_type base64 is the context for data, and the mime type comes from mime_type, else it is unknown. A v0 block by url or by id is not mapped either, and holds nothing to strip. |
| `bedrock.converse` | `image / document / video / audio with source.bytes` | blob | from_mime | passthrough, laminar | none | No recorded family; covered by the SDK pass-through unit tests. The block {"image":{"format":"png","source":{"bytes":...}}}, with no type. An image's mime type is image/&lt;format&gt;; a video, audio or document format is not always a MIME subtype (three_gp, mp3, docx), so it gives none, and the modality comes from the block. A source by s3Location is not mapped yet and stays as it came. OpenLLMetry content is a block list only when every block has a type, so Bedrock content there stays text, with its bytes stripped per raw_payloads. |
| `gemini.generate_content` | `inline_data {mime_type, data}` | blob | from_mime | passthrough | none | No recorded family; covered by the SDK pass-through unit tests. |
| `gemini.generate_content` | `file_data {mime_type, file_uri}` | uri / blob | from_mime | passthrough | none | No recorded family; covered by the SDK pass-through unit tests. The modality comes from the mime type, else from the URI path's extension. A data URL becomes a blob, and an empty or \_\_REDACTED\_\_ file_uri a blob with stripped_reason redacted_upstream. |
| `openinference.llm` | `message_content.type = image, image.image.url = data URL \| http(s) \| __REDACTED__` | blob / uri | image | openinference | `openinference-openai/image_data_url`, `openinference-openai/image_https_url`, `openinference-openai/image_redacted`, `openinference-anthropic/image_base64`, `openinference-js-openai/image_data_url`, `openinference-js-openai/image_https_url`, `openinference-js-openai/image_redacted` | A data URL becomes a blob, an http(s) URL a uri, and \_\_REDACTED\_\_ a blob with stripped_reason redacted_upstream. Python and JS; the JS instrumentor redacts above the same 32,000 characters. |
| `vercel.ai` | `image / file parts in ai.prompt.messages` | blob / uri | from_mime | vercel | `vercel-ai-v5/image_file`, `vercel-ai-v5/pdf_file`, `vercel-ai-v5/text_plain_file`, `vercel-ai-v5/audio_file`, `vercel-ai-v6/image_file`, `vercel-ai-v6/pdf_file`, `vercel-ai-v6/text_plain_file`, `vercel-ai-v6/audio_file` | The existing blob and uri mapping, with the modality rule. A blob is stripped. TypeScript SDK and sink. The AI SDK writes a file part as a part of type file with mediaType and base64 data in ai.prompt.messages (the model call), whatever the media type. A PDF and a text/plain file are not images. Data that starts with a URL scheme other than data (http, https, gs, s3, file), or v7 data tagged url, is a uri, the link kept; a file part by URL with no mediaType takes its modality from the URL path's extension. A v7 tag no rule names is a blob with no byte_size. |
| `vercel.ai` | `image / file part whose data is neither a string nor v7 tagged data holding one` | no part | - | vercel | none | No recorded family writes it; covered by the TypeScript SDK and sink Vercel cases. It makes no part, never a bare {"type":"file"}; the message keeps its other parts, and any raw payload holding the bytes is stripped per raw_payloads. |
| `semconv.native` | `blob part with content` | blob | from_mime | native | `pydantic-ai/image_binary` | The same blob, stripped. pydantic-ai writes it in gen_ai.input.messages and pydantic_ai.all_messages. This applies to any OTel GenAI instrumentation that writes blob parts. |
| `semconv.native` | `uri part` | uri | from_mime | native | `openllmetry/image_https_url` | Rebuilt into its canonical shape (see part_shapes). A modality it has is kept, else it comes from the mime type, then the URI's filename extension, then document. OpenLLMetry 0.62 writes it in gen_ai.input.messages. |
| `semconv.native` | `file part` | file | from_mime | native | none | No recorded family; covered by the SDK pass-through unit tests. Rebuilt into its canonical shape (see part_shapes). A modality it has is kept, else it comes from the mime type, then document. |
| `openinference.llm` | `image.image.url = data:None;url,None` | blob | image | openinference | `openinference-anthropic/image_url` | What OpenInference's Anthropic instrumentor writes for an image with a url source; the URL itself is lost. The data URL names no mime type and holds no bytes, so the blob has neither mime_type nor byte_size, and its stripped_reason is redacted_upstream. |
| `laminar.openhands` | `ImageContent with image_urls in lmnr.span.input` | no part (raw payload stripped: `lmnr.span.input`) | - | laminar | `laminar/image_base64`, `laminar/image_https_url` | lmnr.span.input is a raw payload, not a message key, so it makes no part. A data URL in it is stripped per raw_payloads; an http(s) URL stays. Written on the conversation.send_message span's input, and the sink keeps it in InputValue. The LLM span drops the image when the model has no vision support. |
| `vercel.ai` | `file part with Buffer data in ai.prompt` | no part (raw payload stripped: `ai.prompt`) | - | vercel | `vercel-ai-v5/image_file`, `vercel-ai-v5/pdf_file`, `vercel-ai-v5/text_plain_file`, `vercel-ai-v5/audio_file`, `vercel-ai-v6/image_file`, `vercel-ai-v6/pdf_file`, `vercel-ai-v6/text_plain_file`, `vercel-ai-v6/audio_file` | On the operation span (ai.generateText) the prompt is JSON, and a file given as a Buffer is written as an object of type Buffer whose data is a JSON array of byte values, not base64. ai.prompt is a raw payload, so it makes no part; the Buffer object is replaced per raw_payloads, with byte_size the array length. The part comes from ai.prompt.messages on the model-call span (the image / file parts row). |
| `vercel.ai` | `image part with base64 image in ai.prompt` | no part (raw payload stripped: `ai.prompt`) | - | vercel | none | No recorded family writes it; the recorded image parts are Buffers (the Buffer row). Covered by the golden examples and the TypeScript SDK and sink unit tests. An image given as a base64 string is written {"type":"image","image":"&lt;base64&gt;","mediaType"?}. ai.prompt is a raw payload, so it makes no part; image is stripped per raw_payloads, mime type from mediaType, else unknown. An image that starts with a URL scheme stays a link, and a data URL in it is replaced with its own mime type. |
| `vercel.ai` | `file / image part with v7 tagged data in ai.prompt` | no part (raw payload stripped: `ai.prompt`) | - | vercel | none | No recorded family writes it; covered by the golden examples and the TypeScript SDK and sink unit tests. v7 writes the payload as {"type":"data","data":"&lt;base64&gt;"} under a file part's data or an image part's image. ai.prompt is a raw payload, so it makes no part; the inner data is stripped per raw_payloads, mime type from the part's mediaType, else unknown. A URL in it stays, and a data URL is replaced with its own mime type. |
| `vercel.ai_otel` | `blob part with modality image for a non-image file, in gen_ai.input.messages` | blob | from_mime | native | `vercel-ai-otel/image_file`, `vercel-ai-otel/pdf_file`, `vercel-ai-otel/text_plain_file`, `vercel-ai-otel/audio_file` | @ai-sdk/otel writes every file part as a blob with base64 content and labels application/pdf and text/plain as modality image (audio/wav is labelled audio). The modality is recomputed from the mime type, so these become document blobs. |
| `openinference.llm` | `message_content.type = image with no image.url (image.media_type and image.type only, or nothing)` | blob | image | openinference | `openinference-js-anthropic/image_base64`, `openinference-js-anthropic/image_url` | What OpenInference's JS Anthropic instrumentor writes for an image. A base64 source leaves image.media_type (the mime type) and image.type = base64 but no data; a url source leaves only message_content.type = image. The blob carries the mime type when given, no byte_size, and stripped_reason redacted_upstream. |
| `openinference.llm` | `media present only in input.value (audio input, PDF document)` | no part (raw payload stripped: `input.value`) | - | openinference | `openinference-openai/input_audio`, `openinference-js-openai/input_audio`, `openinference-anthropic/document_pdf`, `openinference-js-anthropic/document_pdf` | OpenInference (Python and JS) leaves OpenAI input_audio and an Anthropic base64 document out of the flattened messages, and keeps them only in the request JSON of input.value. No part is made; the raw payload is stripped per raw_payloads. |
| `openllmetry.openai` | `image as a data URL: the instrumentor drops the prompt content; nothing to normalize` | no part | - | openllmetry | `openllmetry/image_base64` | Before 0.62 the span keeps only gen_ai.prompt.0.role, with no content; 0.62 writes no gen_ai.input.messages at all. This holds for every recorded version. |

## Output

| Source | Shape | Becomes | Modality | Paths | Fixtures | Notes |
| -- | -- | -- | -- | -- | -- | -- |
| `openai.chat` | `message.audio {data, transcript}` | blob | audio | passthrough, openllmetry, laminar | none | No recorded family writes it in a message key (OpenInference keeps it only in output.value; see the OpenInference raw-payload row); covered by the SDK pass-through unit tests. A text part with the transcript follows the blob. |
| `openai.responses` | `image_generation_call.result (base64)` | blob | image | passthrough, openllmetry, laminar | none | No recorded family; covered by the SDK pass-through unit tests. |
| `openinference.llm` | `media present only in output.value (audio output)` | no part (raw payload stripped: `output.value`) | - | openinference | `openinference-openai/audio_output`, `openinference-js-openai/audio_output` | OpenInference (Python and JS) leaves an OpenAI message.audio response out of the flattened messages, and keeps it only in the response JSON of output.value. No part is made; the raw payload is stripped per raw_payloads. |
