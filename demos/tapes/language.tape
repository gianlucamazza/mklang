Output docs/assets/demos/language.webm
Output docs/assets/demos/language.txt

Require python

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
Set TypingSpeed 18ms
Set WaitTimeout 240s

# Language surface: check → lint → run (matches docs/demos.md).
# Isolate react.mkl so sibling example machines do not flood shadow warnings.

Hide
Type "rm -rf /tmp/mklang-lang && mkdir -p /tmp/mklang-lang && cp examples/react.mkl /tmp/mklang-lang/ && clear"
Enter
Show

Type "PYTHONPATH=src python -m mklang.cli check /tmp/mklang-lang/react.mkl"
Enter
Wait+Screen@30s /OK .*react\.mkl/
Sleep 1s

Type "PYTHONPATH=src python -m mklang.cli lint --strict /tmp/mklang-lang/react.mkl"
Enter
Wait+Screen@30s /findings=0/
Sleep 1s

Type "PYTHONPATH=src python -m mklang.cli run /tmp/mklang-lang/react.mkl --format text --provider deepseek --set question.text=Calculate_7_times_24_minus_15"
Enter
Wait+Screen@240s /DONE react/
Wait+Screen@30s /Result/
Wait+Screen@30s /153/
Sleep 3s
