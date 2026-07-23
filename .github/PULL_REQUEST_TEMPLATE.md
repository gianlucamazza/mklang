<!-- Keep layer discipline (CONTRIBUTING.md): a LANGUAGE change lands as
SPEC.md → schema (+ bundled copy) → interpreter → conformance case → examples
→ tests → docs, in that order. Interpreter-only changes skip SPEC/schema/conformance. -->

## Summary

<!-- What and why. Link the ADR if the change records a decision. -->

## Checklist

- [ ] `uv run --extra dev --extra mcp --extra console pytest -q --cov=mklang` (coverage gate ≥88)
- [ ] `uv run --all-extras mypy` (zero suppressions) and `ruff check`
- [ ] Language change: SPEC + schema + conformance case updated (or N/A)
- [ ] `CHANGELOG.md` entry (and `ROADMAP.md` if a roadmap item shipped)
- [ ] Touched a demo-pinned source file: `demo_assets.py manifest` re-pinned (or N/A)
