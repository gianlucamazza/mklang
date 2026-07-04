import glob

import pytest

from mklang.loader import load_dict, validate_dict


@pytest.mark.parametrize("path", sorted(glob.glob("examples/*.mk")))
def test_examples_validate(path):
    validate_dict(load_dict(path))


def test_at_least_the_v02_examples_present():
    names = set(glob.glob("examples/*.mk"))
    assert any("self_consistency" in n for n in names)
    assert any("map_reduce" in n for n in names)
    assert any("react" in n for n in names)
