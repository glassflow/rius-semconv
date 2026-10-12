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
- the resource's `service.instance.id` is fixed (`recorder`).

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

## Recording a family

1. Make a virtualenv holding exactly the manifest's pins (Python version
   included).
2. `python record.py <family>-<version>.json <environment.json>`. The second
   file gets the Python version and package pins for the manifest.
3. Run it twice and compare: the two outputs must be byte-identical.
4. Produce the expected result, in a virtualenv with the Python SDK installed
   from the commit you name:
   `python tools/expect_python.py --sdk-commit <sha> fixtures/<family>/<file>.json`
5. Review the expected result against the recording, scenario by scenario, and
   write anything surprising into the pull request.
6. `python tools/check_fixtures.py` must be clean.
