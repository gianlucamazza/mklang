Output docs/assets/demos/test.webm
Output docs/assets/demos/test.txt

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
Set PlaybackSpeed 1.15
Set TypingSpeed 28ms
Set WaitTimeout 60s

Hide
Type "clear"
Enter
Show

Type "uv run mklang check examples/triage.mk"
Enter
Wait+Screen /OK.*triage/
Sleep 1s

Type "uv run mklang test examples/triage.mk --script examples/triage.test.yaml"
Enter
Wait+Screen /passed=2/
Sleep 3s
