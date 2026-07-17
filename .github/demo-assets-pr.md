Automated regeneration of the canonical CLI and console demos using live
DeepSeek calls.

Preview the generated GIFs:

- [CLI demo](https://raw.githubusercontent.com/gianlucamazza/mklang/automation/demo-assets/docs/assets/demos/cli.gif)
- [Console demo](https://raw.githubusercontent.com/gianlucamazza/mklang/automation/demo-assets/docs/assets/demos/console.gif)

Automated validation covers source and asset hashes, required transcript
markers, known failure output, secret leakage, dimensions, duration, audio, and
size limits.

## Human visual review

- [ ] Text is readable on desktop and mobile.
- [ ] Commands and output are not clipped or obscured.
- [ ] Pacing makes the workflow understandable.
- [ ] Commands still represent the recommended usage.
- [ ] Live output is truthful and free of errors.
- [ ] No secrets, personal data, or sensitive terminal content is visible.

GitHub does not recursively trigger workflows for events created with the
repository `GITHUB_TOKEN`; the generation job therefore performs the complete
automated validation before opening this PR.
