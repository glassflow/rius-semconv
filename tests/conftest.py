import copy
import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from generators.registry import Registry, load_data  # noqa: E402


@pytest.fixture(scope="session")
def base_data():
    """The real registry, loaded once. Tests mutate a deep copy."""
    return load_data()


@pytest.fixture
def data(base_data):
    return copy.deepcopy(base_data)


@pytest.fixture
def registry(base_data):
    return Registry(copy.deepcopy(base_data))


def node_can_run_typescript() -> bool:
    node = shutil.which("node")
    if node is None:
        return False
    probe = subprocess.run(
        [node, "--experimental-transform-types", "--no-warnings", "-e", ""],
        capture_output=True,
    )
    return probe.returncode == 0


requires_node = pytest.mark.skipif(
    not node_can_run_typescript(),
    reason="needs Node >= 22.7 for --experimental-transform-types",
)
requires_go = pytest.mark.skipif(shutil.which("go") is None, reason="needs the Go toolchain")
