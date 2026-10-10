---
title: mklang playground
emoji: 🧩
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: 6.30.0
app_file: app.py
python_version: "3.12"
license: apache-2.0
short_description: Keyless offline mklang check, lint, format, and test
---

# mklang playground (keyless / offline)

A public [Hugging Face Space](https://huggingface.co/docs/hub/spaces-overview)
for **[mklang](https://github.com/gianlucamazza/mklang)** that stays on the
deterministic host path. It is meant to run on **cpu-basic**. It does not
take an LLM or provider API key and it does not call a model over the network.

## What it does

- **Parse** an inline `.mkl` document (YAML → JSON Schema → host dataclass).
- **Check + lint** the same document (`mklang check` plus static analysis; no
  `--llm` judge probe).
- **Format** by parsing YAML and dumping it again (comments are dropped).
- **Run bundled examples** through the scripted `mklang test` harness
  (`hello`, `triage` and their `*.test.yaml` scenarios).
- **Run bundled conformance cases** (`linear`, `parse-json`,
  `hook-before-prose`, `escalate-ask`). A suspended case shows the in-memory
  **checkpoint** envelope; nothing is written to disk.

Produce texts, judge picks, tools, and hooks all come from the fixture files
in this folder. That is the same offline path CI uses.

## What it does not do

- **No Path B.** [Issue #123](https://github.com/gianlucamazza/mklang/issues/123)
  tracks the opt-in Noul-only Jev host judge (`judge: jev-*`). That adapter is
  not the default, and the measured spike reports `production_ready: false`.
  This Space does not expose it, does not accept `TYPESAFE_API_KEY`, and does
  not call Jev / Noul / Choice-as-`judge:`.
- **No live `mklang run`.** Provider-backed execution needs a key and a
  network model call. That is out of scope here.
- **No secrets, no telemetry.** Analytics flags are off; the app does not
  collect keys or phone home.

Issue #123 is a Path B tracker, not a playground spec. This Space follows
that issue by **leaving Path B out** and only showing what mklang can do
offline.

## Run it locally

From a clone of [gianlucamazza/mklang](https://github.com/gianlucamazza/mklang):

```bash
# install the in-tree package + the Space's Gradio pin
pip install -e .
pip install 'gradio==6.30.0'

python spaces/playground/app.py
```

With the repo's `uv` workflow:

```bash
uv run --with 'gradio==6.30.0' python spaces/playground/app.py
```

Then open the printed local URL (typically `http://127.0.0.1:7860`).

Smoke test (imports the app and runs one example callback; does **not**
start a server):

```bash
uv run python spaces/playground/test_smoke.py
# or, via the repo suite:
uv run --extra dev pytest -q tests/repo/test_playground_space.py
```

## License

Apache-2.0, matching the [mklang repository](https://github.com/gianlucamazza/mklang).
