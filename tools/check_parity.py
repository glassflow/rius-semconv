"""Proves the generated constants match what each consumer ships.

    python tools/check_parity.py                     # SDKs + plugin, vs origin/main
    python tools/check_parity.py python              # a subset
    python tools/check_parity.py go --go-dir DIR     # the Rius backend
    python tools/check_parity.py plugin              # the coding-agent plugin
    python tools/check_parity.py --fetch             # git fetch each repo first
    python tools/check_parity.py --ref HEAD          # e.g. a CI checkout of main
    python tools/check_parity.py --cross             # also diff the two SDKs

Each consumer is read from a git ref (default origin/main) of a checkout, so a
stale local branch cannot make the check pass by accident. The SDKs default to
sibling checkouts, and so does the coding-agent plugin (rius-coding-agents);
point elsewhere with --python-repo / --typescript-repo / --plugin-repo. The
backend has no default location: pass --go-dir, its semconv package directory
(the one holding semconv.go) inside a git checkout. With no consumer named,
the check covers both SDKs and the plugin, plus the backend when --go-dir is
given.

What is compared, per consumer:

  Python      out/python/_semconv_generated.py against src/rius/semconv.py.
  TypeScript  out/typescript/semconv.generated.ts against src/semconv.ts.
              Both are EVALUATED (Python exec, Node) and compared by value:
              every name the generated module defines must exist in the SDK
              with an equal value, and every data name the SDK defines must
              be covered by the generated module. Private tables the SDK keeps
              unexported count as covered when the names match.
  Go          out/go/semconv_generated.go against the backend's semconv.go,
              constants only. Every shared name must agree; a backend name
              the registry does not generate must be explained in
              tools/go_reference_only.yaml (normalizer input, legacy spellings)
              or decided in registry/usage_keys.yaml (usage keys).
  Plugin      out/python/_semconv_generated.py against its vendored copy,
              scripts/rius_cc/_semconv_generated.py. It has no hand-written
              module, so it must vendor: no copy at the ref fails.

Once a consumer vendors the generated file (it exists at the ref), the check
switches to comparing that file byte for byte. A consumer's sync script may
start the copy with two comment lines naming the release it came from
("# Vendored from rius-semconv v1.2.0 ..." or the // form); the bytes after
them are compared. A difference means the consumer is pinned to an older
registry version, which is allowed, so it is a warning unless --strict. For the
backend, when the copy is current, the constants its hand-written semconv.go
still declares must each be classified, as above, and none may repeat a
generated one. For the plugin, every name its code reads from the vendored
module (`semconv.NAME`, or imported from it) must still be generated, even
when the copy lags: a registry change that drops or renames one would break
the plugin's next re-vendor, so it fails here first, regardless of --strict.

Exit 0 when every requested consumer passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import re
import subprocess
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from generators.registry import Registry  # noqa: E402
from tools.parity import (  # noqa: E402
    ToolMissing,
    compare,
    compare_go,
    cross_compare,
    go_constants,
    python_surface,
    ts_surface,
)

CONSUMERS = {
    "python": {
        "repo": ROOT.parent / "rius-sdk-python",
        "reference": "src/rius/semconv.py",
        "vendored": "src/rius/_semconv_generated.py",
        "generated": ROOT / "out" / "python" / "_semconv_generated.py",
    },
    "typescript": {
        "repo": ROOT.parent / "rius-sdk-typescript",
        "reference": "src/semconv.ts",
        "vendored": "src/semconv.generated.ts",
        "generated": ROOT / "out" / "typescript" / "semconv.generated.ts",
    },
    # Given as the package directory (--go-dir), not a repository: the paths
    # below are relative to it.
    "go": {
        "repo": None,
        "reference": "semconv.go",
        "vendored": "semconv_generated.go",
        "generated": ROOT / "out" / "go" / "semconv_generated.go",
    },
    # Vendors only: no hand-written module re-exports the generated one, its
    # code imports it directly. `sources` is the tree whose Python must only
    # read names the generated module still defines.
    "plugin": {
        "repo": ROOT.parent / "rius-coding-agents",
        "reference": None,
        "vendored": "scripts/rius_cc/_semconv_generated.py",
        "generated": ROOT / "out" / "python" / "_semconv_generated.py",
        "sources": "scripts",
    },
}
# The generated Python module's name, as a consumer imports it.
GENERATED_MODULE = "_semconv_generated"
GO_GAPS = ROOT / "tools" / "go_reference_only.yaml"
# The two comment lines a consumer's sync script puts above a vendored copy,
# the first naming the release it came from.
VENDOR_HEADER = re.compile(
    r"\A(?:#|//) Vendored from rius-semconv (?P<tag>\S+) [^\n]*\n(?:#|//)[^\n]*\n"
)


def git(repo: pathlib.Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=check
    )


def split_vendor_header(text: str) -> tuple[str | None, str]:
    """The release a vendored copy names in its header, and the copy without
    the header. (None, text) when there is no header."""
    m = VENDOR_HEADER.match(text)
    return (m.group("tag"), text[m.end() :]) if m else (None, text)


def read_at(repo: pathlib.Path, ref: str, path: str) -> str | None:
    result = git(repo, "show", f"{ref}:{path}", check=False)
    return result.stdout if result.returncode == 0 else None


def locate(lang: str, path: pathlib.Path) -> tuple[pathlib.Path, str] | None:
    """The git checkout to read, and the prefix of the consumer's files in it.
    An SDK is given as its checkout; the backend as its semconv package
    directory, anywhere inside its checkout."""
    if lang != "go":
        return path, ""
    if not path.is_dir():
        return None
    top = git(path, "rev-parse", "--show-toplevel", check=False)
    if top.returncode != 0:
        return None
    prefix = git(path, "rev-parse", "--show-prefix").stdout.strip()
    return pathlib.Path(top.stdout.strip()), prefix


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def listing(label: str, names: list) -> None:
    print(f"{label}: {len(names)}")
    for n in names:
        print(f"  {n}")


def check_python_or_ts(lang: str, reference: str, generated: str) -> bool:
    if lang == "python":
        ref = python_surface(reference)
        gen = python_surface(generated)
        is_private = lambda n: n.startswith("_")  # noqa: E731
    else:
        ts_ref = ts_surface(reference)
        ts_gen = ts_surface(generated)
        ref = {n: v for n, (v, _exported) in ts_ref.items()}
        gen = {n: v for n, (v, _exported) in ts_gen.items()}
        is_private = lambda n: not ts_ref[n][1]  # noqa: E731
    report = compare(ref, gen, private=is_private)
    shared = len(set(ref) & set(gen)) - len(report.changed)
    print(f"generated names: {len(gen)}   matching the SDK: {shared}")
    listing("CHANGED (same name, different value)", report.changed)
    listing("NOT IN SDK (registry emits it, SDK lacks it)", report.not_in_sdk)
    listing("UNCOVERED (SDK data the registry lacks)", report.uncovered_public)
    listing("REORDERED (same entries, different order; the first listed wins)", report.reordered)
    for name in report.reordered:
        print(f"  {name}: {describe_order(ref[name], gen[name])}")
    if report.uncovered_private:
        listing("uncovered private tables (warning only)", report.uncovered_private)
    for name in report.changed:
        print(f"  {name}: {describe_change(ref[name], gen[name])}")
    return report.ok


def describe_order(sdk: object, generated: object) -> str:
    """Where two equal tables' orders first part, for a reordered name."""
    keys = [list(v.get("__enum__", v)) if isinstance(v, dict) else [] for v in (sdk, generated)]
    for i, (s, g) in enumerate(zip(*keys, strict=False)):
        if s != g:
            return f"entry {i + 1} is {s!r} in the SDK, {g!r} in the generated module"
    return "a nested table is ordered differently"


def describe_change(sdk: object, generated: object) -> str:
    """Name the members that differ, rather than printing two whole sets."""
    if isinstance(sdk, dict) and isinstance(generated, dict):
        a = set(sdk.get("__set__", sdk))
        b = set(generated.get("__set__", generated))
        if "__set__" in sdk or a != b:
            return f"only in SDK {sorted(a - b)}, only generated {sorted(b - a)}"
        diff = sorted(k for k in a if sdk[k] != generated[k])
        return f"values differ for {diff}"
    return f"SDK {sdk!r}, generated {generated!r}"


def go_gaps() -> dict[str, dict]:
    """Every backend-only constant with an explanation: go_reference_only.yaml,
    plus the usage keys registry/usage_keys.yaml decides (its `go` field)."""
    gaps = dict(yaml.safe_load(GO_GAPS.read_text())["names"])
    for entry in Registry.load().usage_keys["keys"]:
        if "go" in entry:
            gaps[entry["go"]] = {"class": f"usage_key ({entry['decision']})"}
    return gaps


def used_names(source: str) -> set[str]:
    """The names a Python file reads from the generated module: attributes of
    a name it binds the module to (`from . import _semconv_generated as
    semconv`, then `semconv.KEY`), and names it imports from it."""
    tree = ast.parse(source)
    aliases: set[str] = set()
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[-1] == GENERATED_MODULE:
                used.update(a.name for a in node.names if a.name != "*")
            else:
                aliases.update(a.asname or a.name for a in node.names if a.name == GENERATED_MODULE)
        elif isinstance(node, ast.Import):
            aliases.update(
                a.asname
                for a in node.names
                if a.asname and a.name.split(".")[-1] == GENERATED_MODULE
            )
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in aliases
        ):
            used.add(node.attr)
    return used


def check_plugin_usage(
    repo: pathlib.Path, ref: str, sources: str, vendored_path: str, generated: str
) -> bool:
    """Every name the plugin reads from the vendored module is still generated."""
    listed = git(repo, "ls-tree", "-r", "--name-only", ref, "--", sources).stdout.split()
    defined = set(python_surface(generated, raw=True))
    users: dict[str, list[str]] = {}
    for path in listed:
        if not path.endswith(".py") or path == vendored_path:
            continue
        for name in used_names(read_at(repo, ref, path) or ""):
            users.setdefault(name, []).append(path)
    missing = sorted(f"{name} ({', '.join(users[name])})" for name in set(users) - defined)
    print(f"generated names the plugin reads: {len(users)}")
    listing("MISSING (the plugin reads it, the registry no longer generates it)", missing)
    return not missing


def check_go(reference: str, generated: str) -> bool:
    gaps = go_gaps()
    ref, gen = go_constants(reference), go_constants(generated)
    report = compare_go(ref, gen, gaps)
    shared = len(set(ref) & set(gen)) - len(report.changed)
    print(f"backend constants: {len(ref)}   generated: {len(gen)}   shared and equal: {shared}")
    listing("CHANGED (same name, different value)", report.changed)
    listing("RENAMED (generated name, backend name)", report.renamed)
    listing(
        "UNCLASSIFIED (backend only, not in go_reference_only.yaml or usage_keys.yaml)",
        report.unclassified,
    )
    by_class: dict[str, list[str]] = {}
    for name in report.classified:
        by_class.setdefault(gaps[name]["class"], []).append(name)
    print(f"backend only, classified: {len(report.classified)}")
    for cls, names in sorted(by_class.items()):
        print(f"  {cls}: {', '.join(names)}")
    print(f"new to the backend when it migrates: {len(report.generated_only)}")
    print(f"  {', '.join(report.generated_only)}")
    if report.stale_gaps:
        listing("stale go_reference_only.yaml entries (warning only)", report.stale_gaps)
    return report.ok


def check_go_hand_written(reference: str, generated: str) -> bool:
    """Beside a vendored generated file, the backend's hand-written constants
    must each be explained: none may repeat a generated name or value, and
    every one must be classified like a backend-only constant."""
    report = compare_go(go_constants(reference), go_constants(generated), go_gaps())
    duplicated = sorted(set(go_constants(reference)) & set(go_constants(generated)))
    print(f"hand-written constants beside it: {len(go_constants(reference))}")
    listing("DUPLICATED (declared in both files)", duplicated)
    listing("RENAMED (generated name, backend name)", report.renamed)
    listing(
        "UNCLASSIFIED (backend only, not in go_reference_only.yaml or usage_keys.yaml)",
        report.unclassified,
    )
    return not (duplicated or report.renamed or report.unclassified)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="check_parity.py")
    parser.add_argument("consumers", nargs="*", metavar="CONSUMER")
    parser.add_argument("--ref", default="origin/main", help="git ref to read (origin/main)")
    for lang in ("python", "typescript", "plugin"):
        parser.add_argument(f"--{lang}-repo", default=str(CONSUMERS[lang]["repo"]))
    parser.add_argument("--go-dir", help="the backend's semconv package directory, in a checkout")
    parser.add_argument("--fetch", action="store_true", help="git fetch origin in each repo first")
    parser.add_argument("--strict", action="store_true", help="fail on a stale vendored file")
    parser.add_argument("--cross", action="store_true", help="also diff the two SDKs directly")
    args = parser.parse_args(argv)

    named = [c for c in args.consumers if c != "all"]
    wanted = named or [c for c in CONSUMERS if c != "go" or args.go_dir is not None]
    unknown = [c for c in wanted if c not in CONSUMERS]
    if unknown:
        parser.error(f"unknown consumer(s): {', '.join(unknown)}")
    if "go" in wanted and args.go_dir is None:
        parser.error("go needs --go-dir: the backend has no default location")

    ok = True
    references: dict[str, str] = {}
    for lang in wanted:
        spec = CONSUMERS[lang]
        given = pathlib.Path(args.go_dir if lang == "go" else getattr(args, f"{lang}_repo"))
        section(f"{lang}: {given} @ {args.ref}")
        located = locate(lang, given)
        if located is None:
            print(f"FAIL: {given} is not a directory in a git checkout")
            ok = False
            continue
        repo, prefix = located
        vendored_path = prefix + spec["vendored"]
        if args.fetch:
            git(repo, "fetch", "--quiet", "origin")
        sha = git(repo, "rev-parse", "--short", args.ref, check=False).stdout.strip()
        if not sha:
            print(f"FAIL: cannot resolve {args.ref} in {repo}")
            ok = False
            continue
        print(f"commit: {sha}")
        generated = spec["generated"].read_text()

        vendored = read_at(repo, args.ref, vendored_path)
        if vendored is None and spec["reference"] is None:
            print(f"FAIL: {vendored_path} not found at {args.ref}: {lang} must vendor")
            ok = False
            continue
        if vendored is not None:
            tag, vendored = split_vendor_header(vendored)
            same = vendored == generated
            source = f" (rius-semconv {tag})" if tag else ""
            print(f"vendored {vendored_path}{source}: {'identical' if same else 'DIFFERS'}")
            if not same:
                print("  the consumer is pinned to another registry version (lag is allowed)")
                ok = ok and not args.strict
            hand_written = (
                read_at(repo, args.ref, prefix + spec["reference"])
                if lang == "go" and same
                else None
            )
            if hand_written is not None and not check_go_hand_written(hand_written, generated):
                print(f"{lang}: FAIL")
                ok = False
                continue
            if "sources" in spec and not check_plugin_usage(
                repo, args.ref, spec["sources"], vendored_path, generated
            ):
                print(f"{lang}: FAIL")
                ok = False
                continue
            print(f"{lang}: {'PASS' if same else 'LAGGING'}")
            continue

        reference_path = prefix + spec["reference"]
        reference = read_at(repo, args.ref, reference_path)
        if reference is None:
            print(f"FAIL: {reference_path} not found at {args.ref}")
            ok = False
            continue
        references[lang] = reference
        try:
            passed = (
                check_go(reference, generated)
                if lang == "go"
                else check_python_or_ts(lang, reference, generated)
            )
        except ToolMissing as e:
            print(f"FAIL: {e}")
            passed = False
        print(f"{lang}: {'PASS' if passed else 'FAIL'}")
        ok = ok and passed

    if args.cross and {"python", "typescript"} <= set(references):
        section("cross: rius-sdk-python vs rius-sdk-typescript (report only)")
        diff = cross_compare(
            python_surface(references["python"]), ts_surface(references["typescript"])
        )
        listing("same name, different value", diff.differ)
        listing("Python only", diff.python_only)
        listing("TypeScript only", diff.typescript_only)

    print(f"\nPARITY: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
