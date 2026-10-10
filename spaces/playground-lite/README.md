---
title: mklang playground lite
emoji: 🧩
colorFrom: blue
colorTo: indigo
sdk: static
license: apache-2.0
short_description: Keyless offline mklang playground in the browser
---

# mklang playground lite (keyless / offline / static)

A **static** Hugging Face Space: Gradio-Lite (`@gradio/lite@5.45.0` from
jsDelivr) + Pyodide 0.27.3 runs the keyless playground **in the visitor's
browser**. No Gradio server, no cpu-basic Space, no PRO plan.

Same UI and logic as [`spaces/playground/`](../playground/): parse, check +
lint, format, bundled `mklang test` scenarios, and bundled conformance
cases (including the in-memory checkpoint on `escalate-ask`).

## What it does

- **Parse** an inline `.mkl` document (YAML → JSON Schema → host dataclass).
- **Check + lint** (`mklang check` plus static analysis; no `--llm`).
- **Format** by parsing YAML and dumping it again (comments are dropped).
- **Run bundled examples** through the scripted harness (`hello`, `triage`).
- **Run bundled conformance cases** (`linear`, `parse-json`,
  `hook-before-prose`, `escalate-ask`).

mklang is installed from the committed wheel
`mklang-1.3.7-py3-none-any.whl` with `micropip.install(..., deps=False)`.
Only Pyodide's `pyyaml` and `jsonschema` (plus their Pyodide wheels) are
loaded besides the wheel. `openai`, `textual`, and `rich` are **not**
installed and are **not** imported on this path.

## What it does not do

- **No Path B.** [Issue #123](https://github.com/gianlucamazza/mklang/issues/123)
  tracks the opt-in Noul-only Jev host judge (`judge: jev-*`).
  `production_ready: false`. This Space does not expose it.
- **No live `mklang run`.** No API key field, no provider call.
- **No secrets, no telemetry.**

`@gradio/lite` / Pyodide load from jsDelivr (the UI runtime). After that,
parse / check / scripted runs stay in-browser. That is not a model call.

## Dependency audit (Pyodide 0.27.3, the runtime `@gradio/lite@5.45.0` ships)

Declared `mklang` runtime dependencies from `pyproject.toml`, plus the
packages parse/check/lint actually import:

| Package | Pure Python or Pyodide 0.27.3 wheel? | Needed for parse / lint / format / scripted run? |
| --- | --- | --- |
| **mklang** | yes — pure-Python wheel (`py3-none-any`), committed here | **yes** (installed with `deps=False`) |
| **pyyaml** | yes — in Pyodide 0.27.3 (`pyyaml` 6.0.2) | **yes** |
| **jsonschema** | yes — in Pyodide 0.27.3 (pulls `attrs`, `referencing`, `rpds-py`, `pyrsistent`) | **yes** |
| python-dotenv | yes — `py3-none-any` on PyPI; **not** in Pyodide 0.27.3 | **no** (lazy; only provider `.env` loading) |
| openai | package is pure Python; native `jiter` is **not** in Pyodide 0.27.3 | **no** (lazy; live `mklang run` only) |
| rich | yes — in Pyodide 0.27.3 | **no** (CLI / TUI presentation) |
| textual | yes — `py3-none-any` on PyPI; **not** in Pyodide 0.27.3 | **no** (console TUI) |

Stopped packages that would block a **full** `micropip.install("mklang")`
on this Pyodide (native extras of unused deps): **jiter** (openai). The
Lite Space does **not** install those. It uses `deps=False` and the lazy
core imports. That is not a feature fake: parse / check / lint / scripted
test never called them.

Wheel pin: `mklang-1.3.7-py3-none-any.whl`  
SHA-256: `f795823af5b9c52c5a9744d57c84e2ae860400a2f88c952c2cfcc8617fefc702`

`@gradio/lite@5.45.0` also needs `huggingface-hub` (a Gradio dep, not
mklang). The stock jsDelivr worker resolves `huggingface-hub>=0.33.5,<1`,
which current PyPI cannot install in Pyodide 0.27.3 (native `hf-xet` /
micropip dash-name). lite.js blob-wraps that cross-origin worker, so this
folder ships Gradio's published PINNED_HF_HUB worker as
`webworker-patched.js` (rewrites the req to `huggingface-hub==0.35.0`,
[gradio#12262](https://github.com/gradio-app/gradio/issues/12262)) and
`index.html` redirects Worker/SharedWorker — including the blob wrapper —
to that same-origin file. The worker also accepts `follow_symlinks` on
the `os.link` mock so filelock 4.x can import. The UI still loads
`@gradio/lite@5.45.0` from jsDelivr.

## Run it locally

From a clone of [gianlucamazza/mklang](https://github.com/gianlucamazza/mklang):

```bash
python -m http.server 8765 --directory spaces/playground-lite
```

Open `http://127.0.0.1:8765/` (or `/index.html`). First load downloads
Pyodide + Gradio-Lite (often 10–20s); after that, Parse / Check / Run are
local.

CPython smoke of the same callbacks (no browser, no server):

```bash
uv run python -c "import runpy, sys; sys.path.insert(0, 'spaces/playground-lite'); import app; print(app.parse_source(app.load_example_source('hello'))[:80])"
uv run --extra dev pytest -q tests/repo/test_playground_lite.py tests/host/test_core_imports.py
```

## License

Apache-2.0, matching the [mklang repository](https://github.com/gianlucamazza/mklang).
