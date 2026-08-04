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

The agent recording is a free-language, multi-turn session:

1. Raise the session cost budget (`/budget`) so the live path has room.
2. Ask in natural language to `RUN news_search` for this week's open-source AI
   models with a short linked brief — the brain commissions the workspace
   machine and requests host capability consent for `search` (or a turn-budget
   continue) once; the tape answers `always yes` so further session confirms
   stay unattended.
3. After the sourced brief, chain a follow-up turn that distills a one-line
   takeaway — no slash commands involved for the work itself.

[Read the terminal transcript](assets/demos/agent.txt).

## Language: gates, tools, and the reasoning loop

<video autoplay loop muted playsinline controls width="100%">
  <source src="assets/demos/language.webm" type="video/webm">
  Your browser does not support embedded WebM video.
</video>

The language recording walks the recommended CLI path on `react.mkl`:

1. `mklang check` — schema + semantic OK.
2. `mklang lint --strict` — zero findings.
3. `mklang run` — a real reason → act (`calc` host tool) → observe loop.
   Gates route on natural-language conditions, the tool observation re-enters
   the context, the step `budget` bounds the loop, and `finalize` escalates to
   the `reasoning` tier. The result is the arithmetic answer (153).

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

Regeneration runs through the **Demo assets** GitHub Actions workflow, on the first
of each month and on demand, because it performs live provider calls. It skips the
render entirely when nothing is stale. The workflow opens or updates a review PR,
where a human reviewer confirms readability, pacing, accuracy, and the absence of
sensitive information.

Two of those hashes are checked differently, and the difference is deliberate:

- **Asset hashes block.** `demo_assets.py check-drift` fails if a published recording
  does not match the manifest — the guarantee that nothing here was edited by hand.
- **Source hashes do not.** A moved source means these recordings _might_ be out of
  date; only a person or a re-render can say whether they are. `check-drift` reports it
  and passes, `demo_assets.py staleness` answers the same question for the scheduled
  workflow, and `demo_assets.py manifest` re-pins offline when the answer is "these are
  still accurate".

What replaces the blocking source check is a claim the schedule can keep: the recordings
are never older than `MAX_AGE_DAYS`. The manifest's `generated_at` moves only when an
asset actually changes, so re-pinning cannot quietly reset that clock.
