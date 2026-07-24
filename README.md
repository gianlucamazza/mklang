# mklang

[![CI](https://github.com/gianlucamazza/mklang/actions/workflows/ci.yml/badge.svg)](https://github.com/gianlucamazza/mklang/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-gianlucamazza.github.io%2Fmklang-blue)](https://gianlucamazza.github.io/mklang/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](./LICENSE)

**A declarative language for LLM-driven state machines, with an agent-first
console to author and run them.** A `.mkl` file (mklang) describes an
agent as a set of states; an LLM _is_ the runtime that executes generative
steps. The document is the program; the [`mklang console`](#the-console) is how
you drive it. The host supplies the interpreter, optional tools, and optional
code-hook gates.

```
mklang : LangGraph  ::  a declarative spec : Python code
```

Two things to look at first: **the language** — states with prose faces and
natural-language gates as transitions — and **the console** — an agent-first TUI
that authors, commissions, and traces machines for you. Everything else (CLI,
MCP, scenario tests) is scaffolding around those two.

## See it in action

The two product surfaces — the **console** and the **language**:

| Console: agent-first TUI, commissioning, trace                                                                   | Language: gates, tools, reasoning loop                                                                                   |
| ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| [![Live mklang agent demo](./docs/assets/demos/agent.gif)](./docs/demos.md#agent-natural-language-commissioning) | [![mklang language demo](./docs/assets/demos/language.gif)](./docs/demos.md#language-gates-tools-and-the-reasoning-loop) |

Both recordings run the real surfaces against DeepSeek (the agent demo also hits
the live web). See the
[full WebM recordings, transcripts, and reproducibility notes](./docs/demos.md).

## The language

Each **state** has four faces:

| Face        | Answers        | Example                                       | Ref. interpreter        |
| ----------- | -------------- | --------------------------------------------- | ----------------------- |
| `structure` | what shape?    | "The output is an email reply, max 150 words" | → **system**            |
| `execution` | how to act?    | "Do not invent policies not in the KB facts"  | → **system**            |
| `prompt`    | what to think? | "Write a reply to {{ticket.body}}…"           | → **user** (+ `{{…}}`)  |
| `gates`     | when to exit?  | see below                                     | separate **judge** call |

Sticky policy goes in `execution`; turn data and `{{context}}` go in `prompt`.
There is no `system:` keyword — see [Best practices §3](./docs/guides/best-practices.md).

Real side effects (search, send, calc) are **`tool:` states** — host callables,
not prose in `execution`. See [`examples/react.mkl`](./examples/react.mkl) and
[`examples/triage.mkl`](./examples/triage.mkl).

The output of a state is stored in the shared context under its `output:` key, so
later states read it via `{{key}}`. Four **optional** faces unlock richer reasoning:
`reason` (traced chain-of-thought), `accumulate` (append to a list), fan-out
(`sample: N` / `over: {{list}}`), and `call` (run another machine) — see
[Reasoning architectures](#reasoning-architectures).

**Gates are the transitions.** A state's `gates` list is its transition table:
each gate is a natural-language condition the LLM judges, plus what happens next.

```yaml
gates:
  - when: the reply resolves the request and is in the required tone
    then: ok
    to: send
  - when: information from the KB is missing
    repair: 2 # re-run this state with feedback, up to 2 times
    to: gather
  - when: the request needs a human
    escalate: true
    to: human_review
```

Policies: `ok` (advance), `repair(N)` (self-correct with feedback), `escalate`
(route to a handler), `fail` (abort). A global step `budget` prevents runaway loops.

## The console

`mklang console` is the agent-first front door and the primary way to use the
language: type what you want, and the console's agent authors or picks a machine,
commissions it, and streams the run **state-by-state** as a live trace tree —
escalations and tool consent come back to you inline (human-in-the-loop is a
first-class part of the flow, not an afterthought).

```bash
pip install mklang        # the console ships in the core package since 0.15.0
mklang console
```

The agent itself **is** a machine
([`agent.mkl`](./src/mklang/data/console/agent.mkl)) — read it, lint it, swap it
with `--agent your_brain.mkl` (ADR 0015). It has no privileged powers the language
lacks: it commissions the same `.mkl` machines you write, over the same gates and
tiers. Sessions persist (`--continue`), agent replies render as Markdown, and the
brain declares host clocks `today` / `now` for wall-clock questions. Details:
[`docs/guides/console.md`](./docs/guides/console.md).

For project or folder analysis, the default brain first inspects the configured
workspace through bounded read-only tools (`list_workspace`,
`search_workspace`, `read_workspace_file`). It excludes hidden/build/vendor
directories, reports truncation, and separates observed facts from inferences;
it still has no shell, git, or generic write access.

## Design commitments

- **Document-first** — readable without the interpreter; prose-first for the
  common path. Production machines still need developer judgment for tools,
  hooks, and untrusted inputs (see SPEC threat model); the runtime delimits
  untrusted context structurally (SPEC §6), it does not judge it for you.
- **LLM-as-runtime** — non-deterministic by design; **gates** (prose + optional
  code hooks + budgets + trace) are the reliability mechanism. Prose-gate accuracy
  is an empirical claim, not a free lunch.
- **Prose, not types** — `structure` and gate conditions are natural language,
  judged by the LLM at runtime; optional `hook:` gates add host bool checks.
- **Provider-agnostic** — a `.mkl` never names a provider or model. States route by
  capability **tier** (`fast` / `balanced` / `reasoning`); the runtime maps each
  tier to a concrete model. Portability of the document is syntactic; whether
  different providers fire the same gates on the same run is measurable (see
  `scripts/gate_divergence.py`).
- **Spec + conformance** — an implementation-neutral [conformance suite](./conformance/README.md)
  pins interpreter semantics so a second runtime can match the language contract.
- **Language-agnostic runtime** — the spec assumes only "some host with an LLM".

## Reasoning architectures

Every modern reasoning/agentic pattern maps onto the core (states + gates + prose +
tiers + the optional faces). Full skeletons in [`SPEC.md §10`](./SPEC.md); operating
guidance in [`docs/guides/patterns.md`](./docs/guides/patterns.md).

Ten of these ship as **ready, general-purpose `std_*` machines** — parameterized
by context, callable from your machines (`call: std_refine`), runnable by name
(from the CLI or the console's `/run`):

```bash
mklang run std_self_consistency --set task="Estimate the risk of X"
```

See the [stdlib catalog](./docs/reference/stdlib.md) (ADR 0012). The patterns that need host
tools/hooks or static `call:` targets (ReAct, router, exact policy) stay as
authored examples.

| Architecture            | mklang constructs                                                |
| ----------------------- | ---------------------------------------------------------------- |
| Chain-of-Thought        | `reason: true`                                                   |
| ReAct                   | think → `tool` state (host callable) → observation `accumulate`d |
| Reflexion / self-refine | produce → self-judge gate → `repair`                             |
| Self-consistency        | `sample: N` → reducer state (majority)                           |
| Tree-of-Thought         | `sample: k` → score/select reducer → loop (depth via budget)     |
| Plan-and-Execute        | planner `parse: list` (0.3) → `over: {{steps}}` → reducer        |
| Debate / ensemble       | `over: {{personas}}` → synthesizer                               |
| Map-Reduce              | `over: {{chunks}}` → reducer                                     |
| Router-of-experts       | classify → `call` specialists                                    |
| Speculative cascade     | `tier: fast` draft → `escalate` → `tier: reasoning`              |
| Exact policy checks     | gate `hook:` host `(ctx, output) -> bool` (no LLM)               |

## Runtime configuration

The `.mkl` picks a **tier**; a host-side config picks the **model**. This is the
whole of "make it multi-provider":

```yaml
active: deepseek # deepseek | anthropic | openai | google | openrouter | xai | mistral | local
providers:
  deepseek:
    base_url: https://api.deepseek.com
    tiers:
      {
        fast: deepseek-chat,
        balanced: deepseek-chat,
        reasoning: deepseek-reasoner,
      }
  anthropic:
    tiers:
      {
        fast: claude-haiku-4-5,
        balanced: claude-sonnet-5,
        reasoning: claude-opus-4-8,
      }
  local:
    base_url: http://localhost:11434/v1
    tiers: { fast: qwen3:8b, balanced: qwen3:32b, reasoning: deepseek-r1:70b }
```

The example config defaults to **DeepSeek** (the path we live-test against). Flip
`active: anthropic` (or `openai` / `local` / …) and every example runs unchanged.
Blocks ship for **Anthropic, OpenAI, Google, DeepSeek, OpenRouter, xAI (Grok),
Mistral, and local** (Ollama/vLLM) — every non-Anthropic one is OpenAI-compatible,
so a single adapter serves them all. **OpenRouter** is a meta-provider: its
`vendor/model` ids let each tier target a different vendor through one endpoint.
Per-tier params (Anthropic adaptive-thinking + `effort`, OpenAI/xAI
`reasoning_effort`, …) live under `params`. Full map:
[`config/runtime.example.yaml`](./config/runtime.example.yaml).

## Install

```bash
pipx install 'mklang[mcp]'   # console TUI is in the core package; [mcp] adds the MCP server
mklang init --user           # scaffold config, .env, and a sample machine
# set DEEPSEEK_API_KEY (or another provider key) in the .env that init reported, then:
mklang console
```

`pip install mklang` works too. The full walk-through — including a first run
that needs **no API key** — is the
[Getting started guide](./docs/guides/getting-started.md). A one-shot
[`scripts/install.sh`](./scripts/install.sh) and an Arch Linux
[PKGBUILD](https://github.com/gianlucamazza/mklang/tree/main/packaging/arch)
are also available.

Editor validation for `.mkl` files works out of the box via the JSON Schema —
point yaml-language-server at
`https://raw.githubusercontent.com/gianlucamazza/mklang/main/schema/mklang.schema.json`.

## The CLI (for scripting and CI)

The console is the interactive surface; the `mklang` CLI is the scriptable one —
same interpreter, same machines. Drive a checkout through
[uv](https://docs.astral.sh/uv/) with no install step:

```bash
git clone https://github.com/gianlucamazza/mklang && cd mklang
cp .env.example .env            # set DEEPSEEK_API_KEY=… (or another provider key)
uv run mklang check examples/self_consistency.mkl
uv run mklang lint examples/self_consistency.mkl   # + static analysis
uv run mklang run examples/self_consistency.mkl \
  --set question.text="What is the capital of Australia?"
# default provider is deepseek; override with --provider anthropic|openai|…

# pause on budget, resume later (exit code 3 = suspended):
uv run mklang run examples/self_consistency.mkl --max-tokens 300 --checkpoint ck.json
uv run mklang resume ck.json --max-tokens 5000

# human-in-the-loop: escalate gates suspend; resume with the human decision:
uv run mklang run examples/expense_approval.mkl --checkpoint ck.json --hitl
uv run mklang resume ck.json --set human.reply="approved, cost center 42"
```

Every command, flag, and exit code: [CLI reference](./docs/reference/cli.md).
The `.mkl` picks tiers; `config/runtime.example.yaml` maps them to models
(`active: deepseek` by default); the key comes from `.env`. Same machine, any
provider.

### Test your machine without API keys

`mklang test` runs your machine against a script of named scenarios with a
**scripted LLM** (produce texts, judge picks) and scripted tools/hooks — fully
deterministic, no provider or key. It pins the paths you care about _before_ you
spend a token on a live run.

```bash
uv run mklang test examples/triage.mkl --script examples/triage.test.yaml
# PASS happy-path
# PASS kb-empty-escalates
```

Each scenario declares a scripted `llm:`/`tools:`/`hooks:`, optional host
`input:` context (untrusted by provenance, SPEC §6), and an `expect:`
(status, error, result, `at`, `trace` skeleton, context keys) — the same case
format the [conformance suite](./conformance/README.md) uses. A mismatch prints a
minimal diff (the first differing key, expected vs actual) and exits 1. See
[`examples/triage.test.yaml`](./examples/triage.test.yaml).

### MCP server (agentic hosts)

Agent hosts that speak [MCP](https://modelcontextprotocol.io) (Claude Code and
other clients) can **commission** a machine instead of embedding the library
([ADR 0011](./docs/adr/0011-mcp-server-surface.md)): the host requests a run and
gets back the result with full provenance (`trace` + `usage`).

```bash
pip install 'mklang[mcp]'
claude mcp add mklang -- mklang-mcp
```

The server auto-discovers config and keys through the same chain as the CLI
(project → user host → `/etc/mklang` → bundled example, ADR 0023); pass
`--config` only to pin a specific file. It exposes commissioning tools
(`run` / `resume`), discovery (`list_machines` / `describe_machine`), and `check`
(ADR 0011 + 0013). `run` accepts inline `.mkl` source or a path, with `inputs`
merged into the context (host inputs are untrusted by provenance and reach
prompts fenced — SPEC §6); `resume` takes an opaque handle or checkpoint file
(e.g. `{"human.reply": "…"}` for HITL, injected values equally tainted). Live
engine events stream as `mklang.event` logging notifications (ADR 0019).
In-memory sessions hold suspensions unless you pass `checkpoint_path`. Provider
keys resolve server-side from the environment, never over the wire.

## Files

- [`SPEC.md`](./SPEC.md) — the full language specification.
- [`schema/mklang.schema.json`](./schema/mklang.schema.json) — JSON Schema that
  validates the structure of a `.mkl` file (add
  `# yaml-language-server: $schema=../schema/mklang.schema.json` at the top of a
  `.mkl` for editor validation).
- [`config/runtime.example.yaml`](./config/runtime.example.yaml) — host-side
  runtime config: the `tier → model` map for each provider
  ([schema](./config/runtime.schema.json)).
- [`src/mklang/`](./src/mklang) — the reference interpreter (Python, multi-provider).
- [`docs/`](./docs) — `guides/` ([best practices](./docs/guides/best-practices.md),
  [patterns](./docs/guides/patterns.md), [authoring](./docs/guides/authoring.md),
  [console](./docs/guides/console.md), [install](./docs/guides/install.md)),
  `reference/` ([CLI](./docs/reference/cli.md), [stdlib](./docs/reference/stdlib.md),
  [cheatsheet](./docs/reference/cheatsheet.md),
  [architecture](./docs/reference/architecture.md)),
  [`demos.md`](./docs/demos.md), and the [ADR index](./docs/adr/README.md);
  plus [`ROADMAP.md`](./ROADMAP.md).
- `examples/` — runnable machines:
  - [`triage.mkl`](./examples/triage.mkl) — branching FSM + real `search_kb` / `send_reply` tools.
  - [`research.mkl`](./examples/research.mkl) — looping FSM (iterative Q&A, training knowledge).
  - [`research_web.mkl`](./examples/research_web.mkl) — research loop with `tool: search` (host-bound).
  - [`research_compress.mkl`](./examples/research_compress.mkl) — same + explicit notes compression.
  - [`news_search.mkl`](./examples/news_search.mkl) — topic → `tool: search` → news brief (`today` + recency).
  - [`expense_approval.mkl`](./examples/expense_approval.mkl) — divergent terminals + `fail`.
  - [`self_consistency.mkl`](./examples/self_consistency.mkl) — fan-out `sample` + reducer.
  - [`map_reduce.mkl`](./examples/map_reduce.mkl) + [`summarize_doc.mkl`](./examples/summarize_doc.mkl) — `over` + `call`.
  - [`react.mkl`](./examples/react.mkl) — reason/act/observe loop with `accumulate`.
  - [`hook_gates.mkl`](./examples/hook_gates.mkl) — deterministic code-hook gates (exact policy).

## Stack

- **Language spec:** `.mkl` = YAML validated by a JSON Schema; semantics fixed by
  [`SPEC.md`](./SPEC.md) and an implementation-neutral
  [conformance suite](./conformance/README.md).
- **Reference interpreter:** Python ≥ 3.11, dependencies `pyyaml`, `jsonschema`,
  `python-dotenv`, `openai` (the OpenAI-compatible adapter serves every
  non-Anthropic provider), `rich`, and `textual` (the console).
- **Providers:** DeepSeek / OpenAI / Google / OpenRouter / xAI / Mistral / local
  via one OpenAI-compatible adapter, plus a native Anthropic adapter (extra).
- **Surfaces:** the `textual` console TUI, the `mklang` CLI, and an optional
  stdio `mklang-mcp` server (extra `mklang[mcp]`).
- **Quality:** `ruff`, `mypy` (zero suppressions, a growing strict tier),
  `pytest` + `pytest-cov` (coverage gate, offline via MockLLM/scripted LLM),
  and the conformance suite — on an ubuntu 3.11–3.13 + macOS + Windows matrix.
- **Packaging:** `hatchling`; published to PyPI via GitHub OIDC Trusted
  Publishing; Arch [PKGBUILD](https://github.com/gianlucamazza/mklang/tree/main/packaging/arch).

## Status

**Language v0.3 / package 1.0.5** — core complete: states + gates + prose, tiers,
`reason` / `accumulate` / fan-out / `call` / `tool` / `parse: list` / code-hook
gates; multi-provider interpreter with entry-point plugins (tools, hooks,
providers, machines); resumable checkpoints + HITL; `mklang check` / `lint`
(`--llm` optional) / **`test`** / **`doctor`**; [conformance suite](./conformance/README.md);
machine **stdlib** (`std_*`); **MCP** host; **console** TUI (bundled by default);
structured web `search` (offline stub by default); host tool stub architecture for
`search` / `search_kb` / `send_reply` (ADR 0020); host clock conventions
`context.today` / `context.now`; sectioned produce system prompts from
`structure`+`execution`; output anti-cutoff + context budgets (ADR 0016–0019);
**untrusted-context delimiting** — provenance taint + `<data-NONCE>` fences in
produce and judge prompts (SPEC §6, ADR 0025);
[best practices](./docs/guides/best-practices.md). Gate judging follows the state tier
by default.

- **Live:** DeepSeek (default) and **OpenAI** green through the 1.0.x release
  matrices, including the blocking cross-provider gate-agreement check at
  **1.0** — the release gate runs the single `gate_divergence` machine; the
  [four-machine suite](./docs/experiments/gate-divergence.md) measured **1.0
  agreement per machine** (DeepSeek + OpenAI ×3). Anthropic unit-tested; live
  e2e still blocked (key/credits).
- **Release policy:** DeepSeek + OpenAI smoke and three-run gate agreement are
  blocking; other configured providers are reported without blocking. PyPI
  publication uses GitHub OIDC Trusted Publishing from the release workflow.
  Arch: [AUR `mklang`](https://aur.archlinux.org/packages/mklang) tracks the
  PyPI sdist pin.
- **1.0 posture:** SemVer from 1.0.0, spec **0.3** frozen
  ([ADR 0026](./docs/adr/0026-stability-and-deprecation-policy.md)); freeze is
  provisional on evidence ([ADR 0028](./docs/adr/0028-provisional-1.0-posture.md)).
  Authoring-loop `blind_spot = 0.0167` (no `test_machine` yet).
- **Open / later:** Anthropic live when the account has credit; five-reader
  distribution test; `on_truncate=continue` stitching; language-level context
  zones (ROADMAP).
- Roadmap and full release notes: [`ROADMAP.md`](./ROADMAP.md),
  [`CHANGELOG.md`](./CHANGELOG.md).

## License

[Apache-2.0](./LICENSE). Contributions welcome — see
[`CONTRIBUTING.md`](./CONTRIBUTING.md).
