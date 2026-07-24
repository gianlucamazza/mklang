Output docs/assets/demos/agent.webm
Output docs/assets/demos/agent.txt

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
Set PlaybackSpeed 3
Set TypingSpeed 24ms
Set WaitTimeout 180s

Hide
Type "export XDG_STATE_HOME=/tmp/mklang-agent-state"
Enter
Type "rm -rf /tmp/mklang-agent-state /tmp/mklang-agent-machines && mkdir -p /tmp/mklang-agent-machines && cp examples/news_search.mkl /tmp/mklang-agent-machines/ && clear"
Enter
Show

Type "uv run mklang console --provider deepseek --workspace /tmp/mklang-agent-machines"
Enter
Wait+Screen@30s /Ready/
Sleep 1s

Type "Find this week's news about open-source AI models and give me a short brief with links."
Enter
Wait+Screen@120s /capabilities once/
Sleep 1s
Type "yes"
Enter
Wait+Screen@180s /READY[\s\S]*console_agent[\s\S]*done/
Sleep 3s

Type "Now boil that down to a single headline takeaway."
Enter
Wait+Screen@180s /READY[\s\S]*boil that down/
Sleep 4s

Type "/quit"
Enter
Sleep 1s
