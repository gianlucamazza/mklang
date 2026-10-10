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
pinned: true
---

# mklang playground (keyless, offline)

A [Hugging Face Space](https://huggingface.co/docs/hub/spaces-overview)
for **[mklang](https://github.com/gianlucamazza/mklang)** that uses only the
deterministic host, with no model in the loop. It runs on free **cpu-basic**
hardware. It does not take an LLM or provider API key, and it does not call a
model over the network.

## What it does

- **Parse** an inline `.mkl` document (YAML → JSON Schema → host dataclass).
- **Check + lint** the same document (`mklang check` plus static analysis,
  without the `--llm` judge probe).
- **Format** by parsing the YAML and writing it out again. Comments are
  dropped.
- **Run bundled examples** through the scripted `mklang test` harness
  (`hello`, `triage` and their `*.test.yaml` scenarios).
- **Run bundled conformance cases** (`linear`, `parse-json`,
  `hook-before-prose`, `escalate-ask`). A suspended case shows the in-memory
  **checkpoint** envelope. Nothing is written to disk.

The model texts, judge picks, tools and hooks all come from fixture files in
this Space. CI uses the same offline path.

## What it does not do

- **No hosted judge.** This Space does not call any hosted judge model and does not take a judge API key; judge picks come from the fixture files. mklang has an optional, opt-in hosted judge adapter. It is not the default, and [mklang's docs](https://github.com/gianlucamazza/mklang/blob/main/docs/what-mklang-is.md) say that adapter is not production-ready. That adapter sends the text it judges to the provider's API, which is one reason it stays out of this Space.
- **No live `mklang run`.** Provider-backed execution needs a key and a
  network model call, so it is out of scope here.
- **No secrets, no telemetry.** The app does not ask for or store keys, and it switches off Gradio analytics and Hugging Face Hub telemetry at start-up. Hugging Face hosts the Space, so its platform logs still apply.

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

Then open the local URL it prints (usually `http://127.0.0.1:7860`).

Smoke test (imports the app and runs one example callback; does **not**
start a server):

```bash
uv run python spaces/playground/test_smoke.py
# or, via the repo suite:
uv run --extra dev pytest -q tests/repo/test_playground_space.py
```

## License

Apache-2.0, matching the [mklang repository](https://github.com/gianlucamazza/mklang).

**Author**: [Gianluca Mazza](https://gianlucamazza.it). I take LLM systems into production: state, recovery, eval, cost.
