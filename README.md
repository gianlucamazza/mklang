# mklang

[![CI](https://github.com/gianlucamazza/mklang/actions/workflows/ci.yml/badge.svg)](https://github.com/gianlucamazza/mklang/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-docs.mklang.dev-blue)](https://docs.mklang.dev/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](./LICENSE)

**A declarative language for LLM-driven state machines, with an agent-first
console to author and run them.** A `.mkl` file (mklang) describes an
agent as a set of states; an LLM _is_ the runtime that executes generative
steps. The document is the program; the [`mklang console`](#the-console) is how
you drive it. The host supplies the interpreter, optional tools, and optional
code-hook gates.

**Models generate. Machines decide what happens next.** mklang makes
probabilistic LLM computation governable through declarative control flow:
states produce, gates judge, and the machine routes to the next state, repair,
escalation, tool, or failure. The topology is explicit and traceable; the
judge's accuracy and cross-provider stability remain empirical questions.

### Why mklang?

- **Explicit control flow** — states, gates, repairs, escalations, and effects are visible in one document.
- **Provider-independent program document** — the `.mkl` artifact does not embed a vendor or model.
- **Measurable behavioural stability** — routing can be compared across providers and tracked over time.

```yaml
machine: greet
entry: answer
states:
  answer:
    prompt: "Greet the user in one sentence."
    output: reply
    gates:
      - when: the reply is a greeting
        then: ok
        to: END
```

**mklang vs Python/LangGraph.** Python/LangGraph is application code that constructs
and runs a graph; mklang is a portable document/spec interpreted by an LLM runtime.
The trade-off is declarative portability and inspectable control flow in exchange for
less host-language expressiveness.

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

Each **state** has four faces: `structure` (what shape?), `prompt` (what to
think? — the `{{…}}`-interpolated task), `execution` (how to act? — sticky
policy, never side effects), and `gates` (when to exit?). Sticky policy goes in
`execution`; turn data and `{{context}}` go in `prompt`. The one-page version
of the whole language is the [cheatsheet](./docs/reference/cheatsheet.md); the
face → LLM-channel mapping is [Best practices §3](./docs/guides/best-practices.md).

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
  pins interpreter semantics so a second runtime can match the language's
  **mechanical** contract: same machine, same oracle verdicts, same trace. Cases
  run against a scripted LLM, so conformance says nothing about which gate a
  model will fire — two conformant runtimes can still diverge in production
  ([what conformance does and does not guarantee](./conformance/README.md#what-conformance-does-and-does-not-guarantee)).
- **Language-agnostic runtime** — the spec assumes only "some host with an LLM".

## Reasoning architectures

Every modern reasoning/agentic pattern — chain-of-thought, ReAct,
self-consistency, Tree-of-Thought, plan-and-execute, debate, map-reduce,
router-of-experts, speculative cascade — maps onto the core (states + gates +
prose + tiers + the optional faces). The construct-by-construct map is the
cookbook in [`SPEC.md §10`](./SPEC.md); operating guidance in
[`docs/guides/patterns.md`](./docs/guides/patterns.md).

Ten of these ship as **ready, general-purpose `std_*` machines** — parameterized
by context, callable from your machines (`call: std_refine`), runnable by name
(from the CLI or the console's `/run`):

```bash
mklang run std_self_consistency --set task="Estimate the risk of X"
```

See the [stdlib catalog](./docs/reference/stdlib.md) (ADR 0012). The patterns that need host
tools/hooks or static `call:` targets (ReAct, router, exact policy) stay as
authored examples.

## Runtime configuration

The `.mkl` picks a **tier**; a host-side config picks the **model**. This is the
whole of "make it multi-provider":

```yaml
active: deepseek # anthropic | openai | google | openrouter | xai | mistral | local
providers:
  deepseek:
    tiers: { fast: deepseek-v4-flash, balanced: deepseek-v4-flash, reasoning: deepseek-v4-flash }
  anthropic:
    tiers: { fast: claude-haiku-4-5, balanced: claude-sonnet-5, reasoning: claude-opus-4-8 }
  local:
    base_url: http://localhost:11434/v1
    tiers: { fast: qwen3:8b, balanced: qwen3:32b, reasoning: deepseek-r1:70b }
```

The example config defaults to **DeepSeek V4 Flash** (the path we live-test
against); flip `active:` and every example runs unchanged. Blocks ship for
Anthropic, OpenAI, Google, DeepSeek, Hetzner Inference, OpenRouter, xAI, Mistral, and local
(Ollama/vLLM); per-tier params (adaptive thinking, `reasoning_effort`, …) live
under `params`. Full map, per-provider notes included:
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
uv run mklang test examples/triage.mkl --script examples/triage.test.yaml  # no key needed
uv run mklang run examples/self_consistency.mkl \
  --set question.text="What is the capital of Australia?"
```

`mklang test` pins the paths you care about against a scripted LLM —
deterministic, no provider or key — _before_ you spend a token on a live run.
Suspensions are first-class: budget exhaustion and `escalate` gates can
checkpoint (`--checkpoint`, `--hitl`; exit code 3) and `mklang resume` picks the
run back up, human reply included. Every command, flag, and exit code:
[CLI reference](./docs/reference/cli.md).

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
(ADR 0023) and exposes commissioning tools (`run` / `resume`, inline source or
path), discovery (`list_machines` / `describe_machine`), and `check`
(ADR 0011 + 0013). Live engine events stream as `mklang.event` logging
notifications (ADR 0019); provider keys resolve server-side from the
environment, never over the wire.

The full documentation lives at [docs.mklang.dev](https://docs.mklang.dev/) —
spec, guides, CLI and stdlib reference, ADRs. Runnable machines are in
[`examples/`](./examples) (each pattern has one, with its scenario test; the
[authoring guide](./docs/guides/authoring.md) says which to copy).

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

**Two version lines** — the language spec and the reference interpreter are versioned
independently (see [SPEC §1](./SPEC.md) and
[ADR 0026](./docs/adr/0026-stability-and-deprecation-policy.md)):

| Line | Version | Meaning |
|---|---|---|
| **Language spec** | **0.4** | Additive changes allowed; the language surface is frozen pending evidence (ADR 0028) |
| **Reference package** | **1.3.1** | Stable interpreter, typed, zero mypy suppressions, 90%+ coverage, CI-gated |

A `.mkl` file declares its spec version via `mklang: "0.4"`. The package version
is what you `pip install`; the spec version is what you write in your machine.

Core complete: states + gates + prose, tiers,
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
produce and judge prompts (SPEC §6, ADR 0025); **total gate transitions** — the
fused judge may answer _none of the above_ instead of being forced to name a
condition, and `lint` requires a catch-all (SPEC §5 _Totality_);
**control-flow taint** — a transition chosen by a judge reading external data is
marked, and reaching an effectful `tool:` under it is recorded or refused
(`--untrusted-flow halt`, SPEC §6 / ADR 0030);
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
- **Spec posture:** additive-only changes since 0.3; the language surface is
  frozen pending evidence ([ADR 0028](./docs/adr/0028-provisional-1.0-posture.md)).
  Authoring-loop `blind_spot = 0.0167` (no `test_machine` yet).
- **Evidence status:** gate-divergence has a seven-machine DeepSeek/OpenAI
  boundary-corpus run, but results vary by date and Anthropic remains unmeasured;
  repair-convergence has one small DeepSeek run with negative observed lift.
  These are research observations, not reliability guarantees. The next
  milestone is the reproducible **Evidence Release**: provider matrix, raw
  JSONL, metrics, limits, and the five-reader comprehension test.
- **Open / later:** Anthropic live when the account has credit; five-reader
  distribution test; `on_truncate=continue` stitching; language-level context
  zones (ROADMAP).
- Roadmap and full release notes: [`ROADMAP.md`](./ROADMAP.md),
  [`CHANGELOG.md`](./CHANGELOG.md).

## Running one of these in production

Three sentences, and only these, describe the family (one name, two products):

1. **mklang** is an open language for LLM-driven state machines (judgement).
2. **[mklang platform](https://mklang.dev/)** is the durable host: orchestrator,
   credentials, signed deploy, human queue.
3. A **pilot** is delivery-led: one real workflow cut over into production here — not self-serve.

This repository is (1). The language name stays usable by anyone under Apache-2.0; the
commercial designation is **mklang platform**, not bare “mklang”. The other half —
triggers, retries, credentials, who may deploy, and what happens when the process dies
between an effect and the record of it — is deliberately not here. The platform is a
separate commercial product (Phase 1: design partners, onboarding is a person). Its
licence is stated on [mklang.dev](https://mklang.dev/); the language stays Apache-2.0.

## License

[Apache-2.0](./LICENSE). Contributions welcome — see
[`CONTRIBUTING.md`](./CONTRIBUTING.md).
