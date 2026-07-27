Automated regeneration of the canonical demo recordings using live DeepSeek
calls (plus live Tavily web search for the agent demo).

Preview the generated GIFs:

- [Agent demo](https://raw.githubusercontent.com/gianlucamazza/mklang/automation/demo-assets/docs/assets/demos/agent.gif)
- [Language demo](https://raw.githubusercontent.com/gianlucamazza/mklang/automation/demo-assets/docs/assets/demos/language.gif)

WebM + plain-text transcripts land in the same directory (`agent.*`, `language.*`).

Automated validation covers source and asset hashes, required transcript
markers, known failure output, secret leakage, dimensions, duration, audio, and
size limits.

## Human visual review

- [ ] Text is readable on desktop and mobile.
- [ ] JetBrains Mono renders with normal tracking and aligned monospace columns.
- [ ] Rich and Textual borders, symbols, and bold text render correctly.
- [ ] Commands and output are not clipped or obscured.
- [ ] Pacing makes the workflow understandable.
- [ ] Commands still represent the recommended usage (agent: free-language +
      consent; language: check → lint → run).
- [ ] Live output is truthful and free of errors.
- [ ] Agent brief shows multi-turn continuity (news → takeaway).
- [ ] Language run shows `DONE react`, a numeric Result, and step count.
- [ ] No secrets, personal data, or sensitive terminal content is visible.

GitHub does not recursively trigger workflows for events created with the
repository `GITHUB_TOKEN`; the generation job therefore performs the complete
automated validation before opening this PR.
