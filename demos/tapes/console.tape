Output docs/assets/demos/console.webm
Output docs/assets/demos/console.txt

Require uv

Set Shell "bash"
Set Width 1200
Set Height 675
Set FontSize 20
Set FontFamily "JetBrains Mono"
Set Theme "Catppuccin Frappe"
Set Padding 20
Set Framerate 24
Set PlaybackSpeed 1.15
Set TypingSpeed 24ms
Set WaitTimeout 75s

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

Type `/run std_cot task="Name one benefit of auditable AI workflows in five words."`
Enter
Wait+Screen@75s /status.*done/
Sleep 4s

Type "/quit"
Enter
Sleep 1s
