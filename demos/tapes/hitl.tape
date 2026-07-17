Output docs/assets/demos/hitl.webm
Output docs/assets/demos/hitl.txt

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
Set WaitTimeout 60s

Hide
Type "rm -f /tmp/mklang-demo-ck.json && clear"
Enter
Show

Type `uv run mklang run examples/expense_approval.mk --provider deepseek --hitl --checkpoint /tmp/mklang-demo-ck.json --set report.text="Team dinner with a client, 240 EUR, itemized receipt attached"`
Enter
Wait+Screen@60s /SUSPENDED.*expense_approval/
Wait+Screen@60s /Checkpoint/
Sleep 2s

Type `uv run mklang resume /tmp/mklang-demo-ck.json --provider deepseek --set manager_note="Approved: client dinner, within policy"`
Enter
Wait+Screen@60s /DONE.*expense_approval.*provider deepseek/
Wait+Screen@60s /Result/
Sleep 3s
