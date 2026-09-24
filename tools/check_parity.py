"""Proves the generated constants match what each consumer ships.

    python tools/check_parity.py                     # all three, vs origin/main
    python tools/check_parity.py python typescript   # a subset
    python tools/check_parity.py --fetch             # git fetch each repo first
    python tools/check_parity.py --ref HEAD          # e.g. a CI checkout of main
    python tools/check_parity.py --cross             # also diff the two SDKs

Each consumer is read from a git ref (default origin/main) of a sibling
checkout, so a stale local branch cannot make the check pass by accident.
Point elsewhere with --python-repo / --typescript-repo / --go-repo.

What is compared, per consumer:

  Python      out/python/_semconv_generated.py against src/rius/semconv.py.
  TypeScript  out/typescript/semconv.generated.ts against src/semconv.ts.
              Both are EVALUATED (Python exec, Node) and compared by value:
              every name the generated module defines must exist in the SDK
              with an equal value, and every data name the SDK defines must
              be covered by the generated module. Private tables the SDK keeps
              unexported count as covered when the names match.
  Go          out/go/semconv_generated.go against argus-core's semconv.go,
              constants only. Every shared name must agree; an argus-core name
              the registry does not generate must be explained in
              tools/go_reference_only.yaml (normalizer input, legacy spellings).

Once a consumer vendors the generated file (it exists at the ref), the check
switches to comparing that file byte for byte. A difference there means the
consumer is pinned to an older registry version, which is allowed, so it is a
warning unless --strict.

Exit 0 when every requested consumer passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

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
    "go": {
        "repo": ROOT.parent / "argus-core",
        "reference": "packages/argus-core/semconv/semconv.go",
        "vendored": "packages/argus-core/semconv/semconv_generated.go",
        "generated": ROOT / "out" / "go" / "semconv_generated.go",
    },
}
GO_GAPS = ROOT / "tools" / "go_reference_only.yaml"


def git(repo: pathlib.Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=check
    )


def read_at(repo: pathlib.Path, ref: str, path: str) -> str | None:
    result = git(repo, "show", f"{ref}:{path}", check=False)
    return result.stdout if result.returncode == 0 else None


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
    if report.uncovered_private:
        listing("uncovered private tables (warning only)", report.uncovered_private)
    for name in report.changed:
        print(f"  {name}: {describe_change(ref[name], gen[name])}")
    return report.ok


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


def check_go(reference: str, generated: str) -> bool:
    gaps = yaml.safe_load(GO_GAPS.read_text())["names"]
    ref, gen = go_constants(reference), go_constants(generated)
    report = compare_go(ref, gen, gaps)
    shared = len(set(ref) & set(gen)) - len(report.changed)
    print(f"argus-core constants: {len(ref)}   generated: {len(gen)}   shared and equal: {shared}")
    listing("CHANGED (same name, different value)", report.changed)
    listing("RENAMED (generated name, argus-core name)", report.renamed)
    listing("UNCLASSIFIED (argus-core only, not in go_reference_only.yaml)", report.unclassified)
    by_class: dict[str, list[str]] = {}
    for name in report.classified:
        by_class.setdefault(gaps[name]["class"], []).append(name)
    print(f"argus-core only, classified: {len(report.classified)}")
    for cls, names in sorted(by_class.items()):
        print(f"  {cls}: {', '.join(names)}")
    print(f"new to argus-core when it migrates: {len(report.generated_only)}")
    print(f"  {', '.join(report.generated_only)}")
    if report.stale_gaps:
        listing("stale go_reference_only.yaml entries (warning only)", report.stale_gaps)
    return report.ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="check_parity.py")
    parser.add_argument("consumers", nargs="*", metavar="CONSUMER")
    parser.add_argument("--ref", default="origin/main", help="git ref to read (origin/main)")
    for lang, spec in CONSUMERS.items():
        parser.add_argument(f"--{lang}-repo", default=str(spec["repo"]))
    parser.add_argument("--fetch", action="store_true", help="git fetch origin in each repo first")
    parser.add_argument("--strict", action="store_true", help="fail on a stale vendored file")
    parser.add_argument("--cross", action="store_true", help="also diff the two SDKs directly")
    args = parser.parse_args(argv)

    wanted = [c for c in args.consumers if c != "all"] or list(CONSUMERS)
    unknown = [c for c in wanted if c not in CONSUMERS]
    if unknown:
        parser.error(f"unknown consumer(s): {', '.join(unknown)}")

    ok = True
    references: dict[str, str] = {}
    for lang in wanted:
        spec = CONSUMERS[lang]
        repo = pathlib.Path(getattr(args, f"{lang}_repo"))
        section(f"{lang}: {repo.name} @ {args.ref}")
        if args.fetch:
            git(repo, "fetch", "--quiet", "origin")
        sha = git(repo, "rev-parse", "--short", args.ref, check=False).stdout.strip()
        if not sha:
            print(f"FAIL: cannot resolve {args.ref} in {repo}")
            ok = False
            continue
        print(f"commit: {sha}")
        generated = spec["generated"].read_text()

        vendored = read_at(repo, args.ref, spec["vendored"])
        if vendored is not None:
            same = vendored == generated
            print(f"vendored {spec['vendored']}: {'identical' if same else 'DIFFERS'}")
            if not same:
                print("  the consumer is pinned to another registry version (lag is allowed)")
                ok = ok and not args.strict
            print(f"{lang}: {'PASS' if same else 'LAGGING'}")
            continue

        reference = read_at(repo, args.ref, spec["reference"])
        if reference is None:
            print(f"FAIL: {spec['reference']} not found at {args.ref}")
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
