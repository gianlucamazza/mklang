Output docs/assets/demos/agent.webm
Output docs/assets/demos/agent.txt

Require python

Set Shell "bash"
Set Width 1200
Set Height 675
Set FontSize 18
Set FontFamily "JetBrains Mono"
Set LetterSpacing 0
Set LineHeight 1.0
Set Theme "Catppuccin Frappe"
Set Padding 16
Set Framerate 24
# Live web + multi-turn agent latency varies; higher playback keeps README embeds short.
Set PlaybackSpeed 4
Set TypingSpeed 20ms
Set WaitTimeout 180s

Hide
Type "export XDG_STATE_HOME=/tmp/mklang-agent-state"
Enter
Type "rm -rf /tmp/mklang-agent-state /tmp/mklang-agent-machines && mkdir -p /tmp/mklang-agent-machines && cp examples/news_search.mkl /tmp/mklang-agent-machines/ && clear"
Enter
Show

Type "PYTHONPATH=src python -m mklang.cli console --provider deepseek --workspace /tmp/mklang-agent-machines"
Enter
Wait+Screen@30s /Ready/
Sleep 800ms

# Raise the console cost budget so the live search + multi-turn path cannot stall.
Type "/budget 100000"
Enter
Wait+Screen@30s /default cost budget/
Sleep 800ms

# Turn 1: free-language commission of news_search (live web via host search).
# Imperative RUN keeps the brain on the commission path; "links" keeps search real.
Type "RUN news_search now. Topic: this week's open-source AI models. Short brief with links."
Enter
# Consent is the happy path; budget-continue is the fallback under thrash.
Wait+Screen@180s /capabilities once|turn budget exhausted/
Sleep 800ms
# "always yes" grants this confirm and auto-approves further session confirms
# (extra budget continues and later tool consent) so the tape stays linear.
Type "always yes"
Enter
Wait+Screen@180s /READY[\s\S]*console_agent[\s\S]*done/
# Hold so the brief (or its last lines) is visible before the follow-up turn.
Sleep 5s

# Turn 2: multi-turn chain — distill a one-line takeaway from prior context.
# Wait for the *second* brain completion (not the prior READY + typed text).
Type "Now boil that down to a single headline takeaway."
Enter
Wait+Screen@180s /boil that down[\s\S]*console_agent[\s\S]*done/
Sleep 4s

Type "/quit"
Enter
Sleep 1s
