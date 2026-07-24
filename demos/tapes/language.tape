Output docs/assets/demos/language.webm
Output docs/assets/demos/language.txt

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
Set WaitTimeout 180s

Hide
Type "clear"
Enter
Show

# The language: a real reason -> tool -> observe -> loop machine (react.mkl).
Type "uv run mklang check examples/react.mkl"
Enter
Wait+Screen /OK.*react/
Sleep 1s

Type "uv run mklang lint --strict examples/react.mkl"
Enter
Wait+Screen /findings=0/
Sleep 1s

# Run it: gates route on natural-language conditions; the calc tool observation
# re-enters context; the loop is bounded by budget; finalize escalates to the
# reasoning tier.
Type `uv run mklang run examples/react.mkl --format text --provider deepseek --set question.text="A shelf holds 7 boxes of 24 books each; 15 books are then removed. How many books remain?"`
Enter
Wait+Screen@180s /DONE.*react.*provider deepseek/
Wait+Screen@90s /Result/
Sleep 3s
