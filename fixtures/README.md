# Recorded spans

Real spans from the instrumentors Rius normalizes, recorded once and shared by
every normalizer: the Python SDK, the TypeScript SDK and the sink. Each
recording comes with the result the normalizers are expected to produce from
it. Every consumer runs the recordings through its own normalizer and must
produce exactly that result, so the three agree with each other without ever
being compared directly. When one disagrees, the expected result says which
side changes.

## Layout

```
fixtures/
  _recording.py        shared by every Python recorder: OTLP/JSON encoding,
                       deterministic ids and times, file writing
  _replay.py           a stored scenario back into OpenTelemetry ReadableSpans
  <family>/
    record.py          drives the instrumentor against a scripted provider
    manifest.json      pins, one line per scenario, where the expected result
                       came from, when it was last re-recorded
    <family>-<version>.json            the raw recording
    <family>-<version>.expected.json   the expected normalized result
```

A family is one instrumentor (`openinference-openai`), named after the package
and keyed by its version, so a new instrumentor release is a new recording
beside the old one rather than a replacement.

## The recording file

```json
{"recordings": [
  {"scenario": "chat",
   "resource": {"attributes": [...]},
   "spans": [{"scope": {"name": "...", "version": "..."}, "span": {...}}]}
]}
```

Each `span` is the protobuf JSON mapping of
`opentelemetry.proto.trace.v1.Span` (OTLP/JSON), so any language can decode it
with its own OTLP types. Attributes and event attributes are sorted by key. To
make a re-recording byte-identical in the pinned environment:

- **ids** are renumbered: each trace id becomes `…0001`, `…0002` and each span
  id `…0001`, `…0002`, in start order. Parent links are kept.
- **times** are replaced by their rank in the scenario's timeline, one
  millisecond apart from 1700000000000000000. Ordering and nesting are kept,
  and a first-token event still lands after its span's start, so time to first
  chunk is still derivable (it reads as 1 ms per step).
- an `exception` event's `exception.stacktrace` is replaced by
  `<stacktrace elided>`.
- a span's status message is cut where a Python traceback starts
  (`Traceback (most recent call last):`). LangChain appends the formatted
  traceback there, with machine paths in it.
- every UUID in a string value becomes `00000000-0000-0000-0000-<n>`, numbered
  by first appearance in the scenario (frameworks such as LangChain write
  per-run ids into JSON payloads).
- the resource's `service.instance.id` is fixed (`recorder`).

A value the instrumentor *measures* (pydantic-ai writes a time-to-first-chunk
in seconds into an attribute) is made deterministic in the recorder itself, by
pinning the clock it reads, never by editing the recording afterwards. The
manifest says so when a recorder does this.

The rius SDK is never involved in a recording: these are the instrumentor's
raw spans.

## The expected result

The same shape, plus the normalizer that produced it:

```json
{"normalizer": {"package": "glassflow-rius", "version": "1.0.0", "commit": "<sha>"},
 "recordings": [...]}
```

Span ids, parents and times are exactly the recording's, so a consumer matches
each expected span to its raw span by id. What it holds is the span after
normalization and before masking: what the normalizer hands to the exporter.

Where it comes from (`expected.source` in the manifest):

- `python-sdk`: families the SDKs cover. Produced by `tools/expect_python.py`
  with the Python SDK (the reference implementation) installed from a named
  commit, then **reviewed by hand** before it is committed.
- `sink`: families only the sink normalizes (OpenLLMetry, Laminar), produced by
  the sink.

## Writing a recorder

`_recording.py` holds everything a recorder shares:

- `ScriptedProvider(httpx)`: the scripted provider. `answer(url, *responses)`
  queues responses, each answering exactly one request in order, and a
  scenario fails if any is left unused. `transport()` gives a mock transport
  for clients that accept one; `intercept_all()` answers every request in the
  process, for libraries that build their HTTP clients internally (passing
  `client=` would end up serialized in the span). Pass the httpx module the
  client uses: openai >= 3 and anthropic >= 1 use the `httpx2` fork.
- `sse(events)`: a server-sent-events body for streaming responses.
- `recorder_resource()`: the provider's resource, with a fixed instance id.
- `record_all(scenarios, exporter, script, packages, argv)`: runs every
  scenario and writes the recording and the environment.

Enable only the instrumentor under test. A combination (LangChain with the
openai instrumentor, LiteLLM with it) produces extra spans for the same call
and is recorded as its own family.

## Recording a family

1. Make a virtualenv holding exactly the manifest's pins (Python version
   included).
2. `python record.py <family>-<version>.json <environment.json>`. The second
   file gets the Python version and package pins for the manifest.
3. Run it twice and compare: the two outputs must be byte-identical.
4. Produce the expected result, in a virtualenv with the Python SDK installed
   from the commit you name:
   `python tools/expect_python.py --sdk-commit <sha> fixtures/<family>/<file>.json`
5. Review the expected result against the recording, scenario by scenario:
   `python tools/review_expected.py --unchanged fixtures/<family>/<file>.json`
   lists what the normalizer removed, added, changed and left alone. Write
   anything surprising into the pull request.
6. `python tools/check_fixtures.py` must be clean.
