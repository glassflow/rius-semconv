"""Proves the generated semconv.py keeps the hand-written file's public surface.

The contract this checks, in order of how much it matters:

1. Every public constant name that exists in the reference file still exists
   in the generated one, with the same value. A dropped or changed constant
   is a hard failure: it is how a consumer silently stops emitting a key.
2. No new public name appears that the reference did not have. A hard failure
   too, in the other direction: the migration release must be a no-op.
3. The textual diff, reported but not failed on. The ticket wants
   byte-identical output; a reviewed diff is the accepted fallback.

"Public surface" means module-level assignments whose name does not start
with an underscore, plus the SpanKind enum members, plus the module-level
def names. Values are compared by their evaluated literal where the AST can
give one, and by rendered source otherwise (frozensets, tuples), so member
ORDER inside a set is not treated as a difference.

Run:  python tools/check_parity.py --reference <path-or-git-ref>
"""

from __future__ import annotations

import argparse
import ast
import difflib
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_REPO = ROOT.parent / "rius-sdk-python"
DEFAULT_REF = "origin/main:src/rius/semconv.py"


def read_reference(repo: pathlib.Path, ref: str) -> str:
    if ":" in ref and not pathlib.Path(ref).exists():
        return subprocess.run(
            ["git", "-C", str(repo), "show", ref],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    return pathlib.Path(ref).read_text()


def surface(source: str) -> dict[str, str]:
    """name -> a comparable rendering of its value."""
    tree = ast.parse(source)
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if not isinstance(t, ast.Name) or t.id.startswith("_"):
                    continue
                out[t.id] = _render(node.value)
        elif isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            out[f"def {node.name}"] = "<function>"
        elif isinstance(node, ast.ClassDef):
            out[f"class {node.name}"] = "<class>"
            for sub in node.body:
                if isinstance(sub, ast.Assign) and isinstance(sub.targets[0], ast.Name):
                    out[f"{node.name}.{sub.targets[0].id}"] = _render(sub.value)
    return out


def _render(value: ast.AST | None) -> str:
    """A rendering that ignores member order inside a set literal."""
    if value is None:
        return "<none>"
    try:
        literal = ast.literal_eval(value)
    except (ValueError, TypeError, SyntaxError):
        # frozenset({...}) and friends: unwrap the call and sort the members.
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
            inner = value.args[0] if value.args else None
            if isinstance(inner, ast.Set):
                members = sorted(ast.unparse(e) for e in inner.elts)
                return f"{value.func.id}({{{', '.join(members)}}})"
        return ast.unparse(value)
    if isinstance(literal, (set, frozenset)):
        return repr(sorted(literal))
    return repr(literal)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=str(DEFAULT_REPO))
    parser.add_argument("--reference", default=DEFAULT_REF)
    parser.add_argument("--generated", default=str(ROOT / "out" / "semconv.py"))
    parser.add_argument("--show-diff", action="store_true")
    args = parser.parse_args(argv)

    reference = read_reference(pathlib.Path(args.repo), args.reference)
    generated = pathlib.Path(args.generated).read_text()

    ref, gen = surface(reference), surface(generated)

    missing = sorted(set(ref) - set(gen))
    added = sorted(set(gen) - set(ref))
    changed = sorted(n for n in set(ref) & set(gen) if ref[n] != gen[n])

    print(f"reference: {args.reference}  ({len(ref)} public names)")
    print(f"generated: {args.generated}  ({len(gen)} public names)")
    for label, names in (("MISSING", missing), ("ADDED", added), ("CHANGED", changed)):
        print(f"\n{label}: {len(names)}")
        for n in names:
            if label == "CHANGED":
                print(f"  {n}\n    reference: {ref[n]}\n    generated: {gen[n]}")
            else:
                print(f"  {n}")

    diff = list(
        difflib.unified_diff(
            reference.splitlines(keepends=True),
            generated.splitlines(keepends=True),
            "reference",
            "generated",
        )
    )
    added_l = sum(1 for d in diff if d.startswith("+") and not d.startswith("+++"))
    removed_l = sum(1 for d in diff if d.startswith("-") and not d.startswith("---"))
    print(f"\ntextual diff: +{added_l} / -{removed_l} lines (not a failure condition)")
    if args.show_diff:
        sys.stdout.writelines(diff)

    ok = not (missing or added or changed)
    print("\nPARITY: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
