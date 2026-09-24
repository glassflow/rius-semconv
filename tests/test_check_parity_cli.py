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
