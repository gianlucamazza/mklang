"""Every YAML skeleton in SPEC.md §10 must validate against the schema."""

import re
from pathlib import Path

import yaml

from mklang.loader import validate_dict


def _blocks_under_section(md: str, header: str) -> list[str]:
    body = md.split(header, 1)[1]
    body = re.split(r"\n## ", body, maxsplit=1)[0]  # stop at the next top-level section
    return re.findall(r"```yaml\n(.*?)```", body, re.S)


def _as_machine(d) -> dict | None:
    """Wrap a cookbook fragment into a minimal valid-shaped machine."""
    if not isinstance(d, dict):
        return None
    if "states" in d:  # a (partial) machine
        m = dict(d)
        m.setdefault("machine", "demo")
        m.setdefault("entry", next(iter(m["states"])))
        m.setdefault("budget", 10)
        return m
    if "gates" in d:  # a single state
        return {"machine": "demo", "entry": "s", "budget": 10, "states": {"s": d}}
    if d and all(isinstance(v, dict) and "gates" in v for v in d.values()):  # a state map
        return {"machine": "demo", "entry": next(iter(d)), "budget": 10, "states": d}
    return None


def test_cookbook_skeletons_validate():
    md = Path("SPEC.md").read_text(encoding="utf-8")
    blocks = _blocks_under_section(md, "## 10.")
    validated = 0
    for block in blocks:
        machine = _as_machine(yaml.safe_load(block))
        if machine is None:
            continue
        validate_dict(machine)  # raises on any schema violation
        validated += 1
    assert validated >= 4, f"expected several cookbook machines, validated {validated}"
