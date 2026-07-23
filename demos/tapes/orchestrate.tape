Output docs/assets/demos/orchestrate.webm
Output docs/assets/demos/orchestrate.txt

Require uv

Set Shell "bash"
Set Width 1200
Set Height 675
Set FontSize 22
Set FontFamily "JetBrains Mono"
Set LetterSpacing 0
Set LineHeight 1.0
Set Theme "Catppuccin Frappe"
Set Padding 24
Set Framerate 24
Set PlaybackSpeed 1.25
Set TypingSpeed 28ms
Set WaitTimeout 120s

Hide
Type "clear"
Enter
Show

# Orchestrator-worker: `over:` fans out one summarize_doc sub-run per chunk,
# then a reducer state (`combine`) merges the per-chunk summaries.
Type "uv run mklang check examples/map_reduce.mk examples/summarize_doc.mk"
Enter
Wait+Screen /files=2/
Sleep 1s

Type `uv run mklang run examples/map_reduce.mk --provider deepseek --set chunks='["mklang models an agent as a declarative state machine; the document is the program.","An LLM is the runtime: each generative state is one produce call, judged by gates.","Gates are natural-language transitions; call and over compose machines into orchestrators."]'`
Enter
Wait+Screen@120s /DONE.*map_reduce.*provider deepseek/
Wait+Screen@120s /Result/
Sleep 3s
