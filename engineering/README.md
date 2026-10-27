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
