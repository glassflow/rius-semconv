"""check_parity.py end to end, against throwaway git repos standing in for
the Python SDK: the pre-swap semantic mode and the post-swap vendored mode."""

import subprocess

import pytest

from conftest import ROOT
from tools import check_parity

GENERATED = (ROOT / "out" / "python" / "_semconv_generated.py").read_text()


def make_repo(path, files):
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    for rel, text in files.items():
        f = path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"],
        check=True,
    )
    return path


def run(repo, *extra):
    return check_parity.main(["python", "--ref", "HEAD", "--python-repo", str(repo), *extra])


def test_semantic_mode_passes_when_values_agree(tmp_path):
    # Helpers the SDK adds on top are functions, which parity ignores.
    sdk = GENERATED + "\n\ndef helper() -> None:\n    return None\n"
    assert run(make_repo(tmp_path / "sdk", {"src/rius/semconv.py": sdk})) == 0


def test_semantic_mode_fails_on_a_changed_value(tmp_path, capsys):
    sdk = GENERATED.replace('CHAIN_SPAN_NAME = "chain"', 'CHAIN_SPAN_NAME = "workflow"')
    assert run(make_repo(tmp_path / "sdk", {"src/rius/semconv.py": sdk})) == 1
    assert "CHAIN_SPAN_NAME: SDK 'workflow', generated 'chain'" in capsys.readouterr().out


def test_semantic_mode_fails_on_an_uncovered_constant(tmp_path, capsys):
    sdk = GENERATED + '\nNEW_KEY = "new.key"\n'
    assert run(make_repo(tmp_path / "sdk", {"src/rius/semconv.py": sdk})) == 1
    assert "NEW_KEY" in capsys.readouterr().out


def test_vendored_mode_compares_bytes(tmp_path):
    files = {
        "src/rius/semconv.py": "from ._semconv_generated import *\n",
        "src/rius/_semconv_generated.py": GENERATED,
    }
    assert run(make_repo(tmp_path / "sdk", files)) == 0


@pytest.mark.parametrize("comment", ["#", "//"])
def test_vendored_mode_reads_past_the_vendor_header(tmp_path, capsys, comment):
    """A consumer's sync script prepends two comment lines naming the release
    it vendored; the bytes after them are what is compared."""
    header = (
        f"{comment} Vendored from rius-semconv v1.2.0 out/python/_semconv_generated.py by\n"
        f"{comment} scripts/sync-semconv.sh. Do not edit: change the registry in rius-semconv.\n"
    )
    files = {
        "src/rius/semconv.py": "from ._semconv_generated import *\n",
        "src/rius/_semconv_generated.py": header + GENERATED,
    }
    assert run(make_repo(tmp_path / "sdk", files), "--strict") == 0
    out = capsys.readouterr().out
    assert "vendored src/rius/_semconv_generated.py (rius-semconv v1.2.0): identical" in out


def test_a_vendor_header_does_not_hide_an_edit(tmp_path):
    header = "# Vendored from rius-semconv v1.2.0 out/python/_semconv_generated.py by\n# x\n"
    files = {
        "src/rius/semconv.py": "from ._semconv_generated import *\n",
        "src/rius/_semconv_generated.py": header + GENERATED + "# edited\n",
    }
    assert run(make_repo(tmp_path / "sdk", files), "--strict") == 1


@pytest.mark.parametrize("strict, expected", [(False, 0), (True, 1)])
def test_vendored_lag_is_a_warning_unless_strict(tmp_path, strict, expected):
    files = {
        "src/rius/semconv.py": "from ._semconv_generated import *\n",
        "src/rius/_semconv_generated.py": GENERATED + "# older\n",
    }
    repo = make_repo(tmp_path / "sdk", files)
    assert run(repo, *(["--strict"] if strict else [])) == expected


def test_unresolvable_ref_fails(tmp_path):
    repo = make_repo(tmp_path / "sdk", {"README": "x"})
    assert check_parity.main(["python", "--ref", "no-such-ref", "--python-repo", str(repo)]) == 1


def test_go_needs_an_explicit_dir(capsys):
    with pytest.raises(SystemExit) as exc:
        check_parity.main(["go", "--ref", "HEAD"])
    assert exc.value.code == 2
    assert "go needs --go-dir" in capsys.readouterr().err


def test_no_consumer_named_skips_go_without_a_dir(tmp_path, capsys):
    sdk = make_repo(tmp_path / "sdk", {"src/rius/semconv.py": GENERATED})
    check_parity.main(["--ref", "HEAD", "--python-repo", str(sdk), "--typescript-repo", str(sdk)])
    out = capsys.readouterr().out
    assert "=== python:" in out and "=== typescript:" in out
    assert "=== go:" not in out


GENERATED_GO = (ROOT / "out" / "go" / "semconv_generated.go").read_text()


def run_go(directory, *extra):
    return check_parity.main(["go", "--ref", "HEAD", "--go-dir", str(directory), *extra])


@pytest.mark.parametrize("package", ["internal/deep/semconv", "."])
def test_go_reads_the_package_directory_anywhere_in_the_checkout(tmp_path, capsys, package):
    repo = make_repo(tmp_path / "backend", {f"{package}/semconv.go": GENERATED_GO})
    assert run_go(repo / package) == 0
    assert "go: PASS" in capsys.readouterr().out


def test_go_fails_on_a_changed_value(tmp_path, capsys):
    drifted = GENERATED_GO.replace('"gen_ai.request.model"', '"gen_ai.request.modelX"')
    assert drifted != GENERATED_GO
    repo = make_repo(tmp_path / "backend", {"pkg/semconv/semconv.go": drifted})
    assert run_go(repo / "pkg" / "semconv") == 1
    assert "CHANGED (same name, different value): 1" in capsys.readouterr().out


def test_go_vendored_file_in_the_package_directory_is_compared_by_bytes(tmp_path, capsys):
    files = {
        "pkg/semconv/semconv.go": "package semconv\n",
        "pkg/semconv/semconv_generated.go": GENERATED_GO,
    }
    repo = make_repo(tmp_path / "backend", files)
    assert run_go(repo / "pkg" / "semconv") == 0
    assert "vendored pkg/semconv/semconv_generated.go: identical" in capsys.readouterr().out


def test_go_vendored_still_classifies_the_hand_written_constants(tmp_path, capsys):
    """The generated file no longer says what the hand-written one holds, so
    each of its constants must still be generated-or-explained."""
    files = {
        "pkg/semconv/semconv.go": 'package semconv\n\nconst (\n\tEndUserID = "enduser.id"\n'
        '\tNewInput = "new.input"\n)\n',
        "pkg/semconv/semconv_generated.go": GENERATED_GO,
    }
    repo = make_repo(tmp_path / "backend", files)
    assert run_go(repo / "pkg" / "semconv") == 1
    out = capsys.readouterr().out
    assert "vendored pkg/semconv/semconv_generated.go: identical" in out
    assert "NewInput" in out
    assert "EndUserID" not in out.split("UNCLASSIFIED")[1].split("backend only")[0]


def test_go_vendored_with_only_classified_hand_written_constants_passes(tmp_path):
    files = {
        "pkg/semconv/semconv.go": 'package semconv\n\nconst EndUserID = "enduser.id"\n',
        "pkg/semconv/semconv_generated.go": GENERATED_GO,
    }
    repo = make_repo(tmp_path / "backend", files)
    assert run_go(repo / "pkg" / "semconv") == 0


def test_go_dir_outside_a_checkout_fails(tmp_path, capsys):
    assert run_go(tmp_path / "missing") == 1
    assert "is not a directory in a git checkout" in capsys.readouterr().out
