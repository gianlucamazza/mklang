# Live demos

These recordings exercise the real `mklang` CLI and Textual console against
DeepSeek. They are generated from versioned VHS tapes, not hand-edited terminal
captures.

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

The console recording starts a clean workspace, runs the standard chain-of-thought
machine, waits for completion, and exits normally.
[Read the terminal transcript](assets/demos/console.txt).

## Reproducibility and review

The canonical sources are [`demos/tapes/`](https://github.com/gianlucamazza/mklang/tree/main/demos/tapes)
and [`scripts/demo_assets.py`](https://github.com/gianlucamazza/mklang/blob/main/scripts/demo_assets.py).
The script renders WebM recordings, derives compact GIF previews, validates
dimensions, duration, size, transcripts, and secret leakage, then records exact
source and asset hashes in `manifest.json`.

Regeneration is intentionally manual through the **Demo assets** GitHub Actions
workflow because it performs live provider calls. The workflow opens or updates
a review PR; automated checks catch source drift, while a human reviewer confirms
readability, pacing, accuracy, and the absence of sensitive information.
