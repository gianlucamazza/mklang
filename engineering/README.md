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

## Released 0.2.0 pin

This repository vendors released tag `0.2.0` at
`862809c8e9a099711f1a13af4ddcfc8a64be76df`
(https://github.com/gianlucamazza/mklang-engineering/releases/tag/0.2.0).
Vendored file bytes are unchanged from the previous pin
`4c3795f63e656435c0dccb057964e4c7a2f1c3b5`. The validator and schema move
together; requirements and runtime semantics do not change. Local hashes are
checked by `python engineering/check_distribution.py`.
