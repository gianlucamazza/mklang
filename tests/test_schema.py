import glob
from pathlib import Path

import pytest

from mklang.loader import load_dict, validate_dict

_REPO_SCHEMA = Path("schema/mklang.schema.json")
_PKG_SCHEMA = Path("src/mklang/data/mklang.schema.json")


def test_schema_copies_are_byte_identical():
    """The packaged schema copy must match the repo source byte-for-byte.

    ``schema/mklang.schema.json`` is the source of truth; the packaging copy at
    ``src/mklang/data/mklang.schema.json`` is force-included in the wheel
    (pyproject ``force-include``) so a pip-installed interpreter validates .mkl
    files identically. Nothing pins them together but this test — a schema edit
    that lands in only one copy makes installs behave differently from the repo.
    """
    repo = _REPO_SCHEMA.read_bytes()
    pkg = _PKG_SCHEMA.read_bytes()
    assert repo == pkg, (
        f"{_PKG_SCHEMA} is out of sync with the source {_REPO_SCHEMA}; "
        f"re-sync from the repo copy:\n    cp {_REPO_SCHEMA} {_PKG_SCHEMA}"
    )


@pytest.mark.parametrize("path", sorted(glob.glob("examples/*.mkl")))
def test_examples_validate(path):
    validate_dict(load_dict(path))


def test_at_least_the_v02_examples_present():
    names = set(glob.glob("examples/*.mkl"))
    assert any("self_consistency" in n for n in names)
    assert any("map_reduce" in n for n in names)
    assert any("react" in n for n in names)
