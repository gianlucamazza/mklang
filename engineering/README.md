# Engineering distribution

Pinned development-only distribution of mklang-engineering. `upstream.json` records
source and hashes. Do not edit copies independently. The owning repository's registry
is `requirements/registry.json`; specification, ADR and operational status stay canonical.

```sh
uv run --with jsonschema python engineering/tools/requirements.py .
uv run --with jsonschema python engineering/tools/requirements.py . --format markdown
```

0 = valid; 1 = invalid registry/reference/evidence; 2 = input/invocation error.
No network access or private credentials are required by the validator. Counts measure
mapping coverage, not correctness. Update IDs additively; never renumber historical IDs.

## Proposed 0.2.0 migration

This branch vendors local review candidate `4c3795f63e656435c0dccb057964e4c7a2f1c3b5` built on Engineering PR #3
`de295e0e436171e65be93d8ccce46d22ebb1a025`, with only trailing schema whitespace
normalized. It is not a released distribution.
The validator and schema move together; requirements and runtime semantics do not
change. Review upstream integration/release before adopting this pin. Local hashes
are checked by `python engineering/check_distribution.py`; cross-repository
compatibility is recorded in the Engineering candidate review package.
