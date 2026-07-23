# Live demos

Two recordings for the two product surfaces — the **console** and the
**language**. Both run the real surfaces against DeepSeek; the agent demo also
hits the live web through the host `search` tool. They are generated from
versioned VHS tapes, not hand-edited terminal captures.

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

## Language: gates, tools, and the reasoning loop

<video autoplay loop muted playsinline controls width="100%">
  <source src="assets/demos/language.webm" type="video/webm">
  Your browser does not support embedded WebM video.
</video>

The language recording checks and lints `react.mkl`, then runs it: a real
reason → act → observe loop. Gates route on natural-language conditions, the
`calc` tool observation re-enters the context, the loop is bounded by the step
`budget`, and the `finalize` state escalates to the `reasoning` tier.
[Read the terminal transcript](assets/demos/language.txt).

More flows — the console's stdlib fan-out, `over:`/`call:` composition, HITL
suspend/resume, and keyless scenario tests — are covered in the guides and the
runnable [`examples/`](https://github.com/gianlucamazza/mklang/tree/main/examples).

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
