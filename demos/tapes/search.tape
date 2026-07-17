Output docs/assets/demos/search.webm
Output docs/assets/demos/search.txt

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
Set WaitTimeout 90s

Hide
Type "clear"
Enter
Show

Type `uv run mklang run examples/news_search.mk --provider deepseek --set topic="open-source AI models"`
Enter
Wait+Screen@90s /DONE.*news_search.*provider deepseek/
Wait+Screen@90s /Result/
Sleep 4s
