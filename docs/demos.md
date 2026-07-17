# Live demos

These six recordings exercise the real `mklang` CLI and Textual console. All
but the deterministic test demo run against DeepSeek; the search and agent
demos also hit the live web through the host `search` tool. They are generated
from versioned VHS tapes, not hand-edited terminal captures.

## CLI: check, lint, run

<video autoplay loop muted playsinline controls width="100%">
  <source src="assets/demos/cli.webm" type="video/webm">
  Your browser does not support embedded WebM video.
</video>

The CLI recording checks and lints a machine before running it with a live
provider. [Read the terminal transcript](assets/demos/cli.txt).

## Console: interactive run

<video autoplay loop muted playsinline controls width="100%">
  <source src="assets/demos/console.webm" type="video/webm">
  Your browser does not support embedded WebM video.
</video>

The console recording starts a clean workspace, lists the commissionable
machines with `/machines`, runs `std_self_consistency` — a five-sample
fan-out with majority vote — on the classic "9.11 vs 9.9" trap, and inspects
the session with `/session`.
[Read the terminal transcript](assets/demos/console.txt).

## Agent: natural-language commissioning

<video autoplay loop muted playsinline controls width="100%">
  <source src="assets/demos/agent.webm" type="video/webm">
  Your browser does not support embedded WebM video.
</video>

The agent recording is a free-language, multi-turn session: the first request
makes the agent brain commission `news_search` (live web via the host `search`
tool) and report a sourced brief; the follow-up turn chains on that context to
distill a one-line takeaway — no slash commands involved.
[Read the terminal transcript](assets/demos/agent.txt).

## HITL: suspend and resume

<video autoplay loop muted playsinline controls width="100%">
  <source src="assets/demos/hitl.webm" type="video/webm">
  Your browser does not support embedded WebM video.
</video>

The HITL recording runs `expense_approval` with `--hitl`: an escalate gate
suspends the run and writes a checkpoint, then `mklang resume` injects the
manager's reply and completes it.
[Read the terminal transcript](assets/demos/hitl.txt).

## Search: chained states with live web

<video autoplay loop muted playsinline controls width="100%">
  <source src="assets/demos/search.webm" type="video/webm">
  Your browser does not support embedded WebM video.
</video>

The search recording runs `news_search` end to end: the machine plans a query,
calls the host `search` tool (Tavily), judges whether the notes are usable, and
finalizes a sourced brief — a chained multi-state flow with real side effects.
[Read the terminal transcript](assets/demos/search.txt).

## Tests: deterministic scenarios

<video autoplay loop muted playsinline controls width="100%">
  <source src="assets/demos/test.webm" type="video/webm">
  Your browser does not support embedded WebM video.
</video>

The test recording checks `triage.mk`, then runs its scripted scenarios with
`mklang test` — the LLM, judges, and tools are all scripted, so this command
needs no provider or API key.
[Read the terminal transcript](assets/demos/test.txt).

## Reproducibility and review

The canonical sources are [`demos/tapes/`](https://github.com/gianlucamazza/mklang/tree/main/demos/tapes)
and [`scripts/demo_assets.py`](https://github.com/gianlucamazza/mklang/blob/main/scripts/demo_assets.py).
The pinned toolchain installs and verifies JetBrains Mono before rendering. The
script renders WebM recordings, derives compact GIF previews, validates
dimensions, duration, size, transcripts, and secret leakage, then records exact
source, toolchain, and asset hashes in `manifest.json`.

Regeneration is intentionally manual through the **Demo assets** GitHub Actions
workflow because it performs live provider calls. The workflow opens or updates
a review PR; automated checks catch source drift, while a human reviewer confirms
readability, pacing, accuracy, and the absence of sensitive information.
