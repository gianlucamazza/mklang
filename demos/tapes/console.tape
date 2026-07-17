Output docs/assets/demos/console.webm
Output docs/assets/demos/console.txt

Require uv

Set Shell "bash"
Set Width 1200
Set Height 675
Set FontSize 20
Set FontFamily "JetBrains Mono"
Set LetterSpacing 0
Set LineHeight 1.0
Set Theme "Catppuccin Frappe"
Set Padding 20
Set Framerate 24
Set PlaybackSpeed 2.5
Set TypingSpeed 24ms
Set WaitTimeout 180s

Hide
Type "export XDG_STATE_HOME=/tmp/mklang-demo-state"
Enter
Type "rm -rf /tmp/mklang-demo-state /tmp/mklang-demo-machines && clear"
Enter
Show

Type "uv run mklang console --provider deepseek --workspace /tmp/mklang-demo-machines"
Enter
Wait+Screen@30s /Ready/
Sleep 1s

Type "/machines"
Enter
Wait+Screen@30s /std_self_consistency/
Sleep 2s

Type `/run std_self_consistency task="Which is larger: 9.11 or 9.9? Answer with the number only."`
Enter
Wait+Screen@180s /status.*done/
Sleep 3s

Type "/session"
Enter
Wait+Screen@30s /session/
Sleep 3s

Type "/quit"
Enter
Sleep 1s
