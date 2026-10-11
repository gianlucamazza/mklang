# Evidence releases

Each dated release directory is an immutable snapshot of raw experiment rows,
environment metadata, derived summaries, and a checksum manifest. Generate a
release from raw JSONL with:

```bash
python scripts/build_evidence_release.py evidence/2026-10-evidence-release
```

The directory must contain at least one raw experiment `.jsonl` file plus
`environments.json`, `summary.json`, and `REPORT.md`. `costs.jsonl` is the
USD ledger (not an experiment-result row); the builder skips it for schema
validation and still checksums it in the manifest. The builder validates every
experiment row against the experiment schema and writes `manifest.json`
atomically. Existing manifests require an explicit `--force` replacement after
revalidation.

Do not hand-edit derived reports or claim live-provider coverage from offline
self-checks. Missing providers and failed runs remain explicit rows. The dated
directory is not complete until the raw rows, environment metadata, derived
summary/report, and manifest have all been independently checked. A later
`evidence-live.yml` dispatch refuses to start unless every prior live run id
is already on a committed `costs.jsonl` row.
