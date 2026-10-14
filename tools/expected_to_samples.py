"""Turn the fixtures' expected results into samples for `weaver registry live-check`.

    python tools/expected_to_samples.py [--out <samples.json>] [<expected.json> ...]

With no files, reads every fixtures/*/*.expected.json. Weaver's live-check reads
its own sample JSON, not OTLP/JSON, so each recording's resource becomes a
resource sample and each span a span sample, its events as span events.
Attribute types are taken from the OTLP value field, so an int stays an int
even where JSON could not tell (`intValue` is a string in OTLP/JSON).

A key under a prefix in fixtures/passthrough.yaml is left out, unless model/
defines it: those are extras the normalizers carry through untouched and the
registry deliberately does not model, each with its reason in that file. A key
model/ defines is always checked, so an entry can never hide one. Over every
expected result (no files named), an entry that matches no left-out key is
stale and fails the run.

The gen_ai.* usage spellings other producers write (pydantic-ai's
gen_ai.usage.details.*, gen_ai.aggregated_usage.*) are left out the same way:
this registry may not define gen_ai.* keys, so they are decided in the
`normalizer_inputs` of templates/params.yaml instead, and
tools/check_usage_keys.py checks those decisions.

The sink families' *.expected-row.json are not converted: they hold ClickHouse
rows whose attribute maps store every value as a string, so live-check would
report a type mismatch on every int, double and boolean key.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
PASSTHROUGH = FIXTURES / "passthrough.yaml"
MODEL = ROOT / "model"
PARAMS = ROOT / "templates" / "params.yaml"

KINDS = {
    "SPAN_KIND_INTERNAL": "internal",
    "SPAN_KIND_SERVER": "server",
    "SPAN_KIND_CLIENT": "client",
    "SPAN_KIND_PRODUCER": "producer",
    "SPAN_KIND_CONSUMER": "consumer",
}
SCALARS = {
    "stringValue": "string",
    "boolValue": "boolean",
    "intValue": "int",
    "doubleValue": "double",
}


def value(otlp: dict) -> tuple[object, str | None]:
    """An OTLP/JSON AnyValue as a JSON value and its Weaver type.

    An empty array has no element type to report, so its type is None and
    Weaver accepts it against any array type.
    """
    for field, type_ in SCALARS.items():
        if field in otlp:
            v = otlp[field]
            if type_ == "int":
                v = int(v)
            elif type_ == "double":
                v = float(v)
            return v, type_
    if "arrayValue" in otlp:
        items = [value(x) for x in otlp["arrayValue"].get("values", [])]
        types = {t for _, t in items}
        if not items:
            return [], None
        if len(types) != 1:
            raise ValueError(f"mixed array element types {sorted(map(str, types))}")
        return [v for v, _ in items], f"{types.pop()}[]"
    raise ValueError(f"unsupported OTLP value {sorted(otlp)}")


def attributes(otlp: list[dict], skip) -> list[dict]:
    out = []
    for a in otlp or []:
        if skip(a["key"]):
            continue
        v, type_ = value(a["value"])
        sample = {"name": a["key"], "value": v}
        if type_:
            sample["type"] = type_
        out.append(sample)
    return out


def samples(expected: dict, skip) -> list[dict]:
    out = []
    for recording in expected["recordings"]:
        resource = recording.get("resource") or {}
        out.append({"resource": {"attributes": attributes(resource.get("attributes"), skip)}})
        for entry in recording["spans"]:
            span = entry["span"]
            events = [
                {"name": e["name"], "attributes": attributes(e.get("attributes"), skip)}
                for e in span.get("events", [])
            ]
            out.append(
                {
                    "span": {
                        "name": span["name"],
                        "kind": KINDS.get(span.get("kind"), "internal"),
                        "attributes": attributes(span.get("attributes"), skip),
                        "span_events": events,
                    }
                }
            )
    return out


def load_passthrough(path: pathlib.Path = PASSTHROUGH) -> list[dict]:
    entries = yaml.safe_load(path.read_text())["passthrough"]
    for e in entries:
        if not e.get("prefix") or not (e.get("reason") or "").strip():
            raise ValueError(f"{path.name}: every entry needs a prefix and a reason: {e}")
    return entries


def model_keys(model: pathlib.Path = MODEL) -> set[str]:
    """Every key model/ defines or references; a template's key ends in a dot."""
    keys = set()
    for f in model.rglob("*.yaml"):
        doc = yaml.safe_load(f.read_text()) or {}
        for a in doc.get("attributes") or []:
            template = str(a.get("type", "")).startswith("template[")
            keys.add(a["key"] + "." if template else a["key"])
        for group in doc.get("attribute_groups") or []:
            for a in group.get("attributes") or []:
                keys.add(a.get("ref") or a.get("key"))
    return keys


def sidecar_inputs(params: pathlib.Path = PARAMS) -> list[str]:
    """The gen_ai.* inputs the params sidecar decides: keys, and prefixes ending in a dot."""
    entries = yaml.safe_load(params.read_text())["params"]["normalizer_inputs"]
    return [e.get("key") or e["prefix"] for e in entries]


def is_defined(key: str, defined: set[str]) -> bool:
    return key in defined or any(d.endswith(".") and key.startswith(d) for d in defined)


def expected_files() -> list[pathlib.Path]:
    return sorted(FIXTURES.glob("*/*.expected.json"))


def convert(
    files: list[pathlib.Path],
    passthrough: list[dict],
    defined: set[str],
    sidecar: list[str],
    check_unused: bool,
) -> tuple[list[dict], list[str]]:
    """The samples for every file, and one line per stale allowlist entry."""
    prefixes = [e["prefix"] for e in passthrough]
    used: set[str] = set()

    def skip(key: str) -> bool:
        if is_defined(key, defined):
            return False
        if any(key == s or (s.endswith(".") and key.startswith(s)) for s in sidecar):
            return True
        hits = [p for p in prefixes if key.startswith(p)]
        used.update(hits)
        return bool(hits)

    out = []
    for f in files:
        out.extend(samples(json.loads(f.read_text()), skip))

    errors = []
    if check_unused:
        for p in prefixes:
            if p not in used:
                errors.append(f"{PASSTHROUGH.name}: {p!r} matches no key left out; drop it")
    return out, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="*", type=pathlib.Path)
    parser.add_argument("--out", type=pathlib.Path)
    args = parser.parse_args(argv)

    files = args.files or expected_files()
    out, errors = convert(
        files, load_passthrough(), model_keys(), sidecar_inputs(), check_unused=not args.files
    )
    for e in errors:
        print(e, file=sys.stderr)
    if errors:
        return 1
    text = json.dumps(out, indent=1, ensure_ascii=False) + "\n"
    if args.out:
        args.out.write_text(text)
        print(f"{len(out)} samples from {len(files)} expected results", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
