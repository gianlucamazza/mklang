Output docs/assets/demos/cli.webm
Output docs/assets/demos/cli.txt

Require uv

Set Shell "bash"
Set Width 1200
Set Height 675
Set FontSize 22
Set FontFamily "JetBrains Mono"
Set Theme "Catppuccin Frappe"
Set Padding 24
Set Framerate 24
Set PlaybackSpeed 1.15
Set TypingSpeed 28ms
Set WaitTimeout 60s

Hide
Type "clear"
Enter
Show

Type "uv run mklang check examples/summarize_doc.mk"
Enter
Wait+Screen /OK.*summarize_doc/
Sleep 1s

Type "uv run mklang lint --strict examples/summarize_doc.mk"
Enter
Wait+Screen /findings=0/
Sleep 1s

Type `uv run mklang run examples/summarize_doc.mk --provider deepseek --set text="Gates and traces make AI workflows auditable."`
Enter
Wait+Screen@60s /DONE.*summarize_doc.*provider deepseek/
Wait+Screen@60s /Result/
Sleep 3s
