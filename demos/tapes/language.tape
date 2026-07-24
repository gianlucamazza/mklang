Output docs/assets/demos/language.webm
Output docs/assets/demos/language.txt

Require python

Set Shell "bash"
Set Width 1200
Set Height 675
Set FontSize 22
Set FontFamily "JetBrains Mono"
Set Padding 24
Set PlaybackSpeed 2
Set WaitTimeout 180s

# The language: a real reason -> tool -> observe -> loop machine (react.mkl).
Type "PYTHONPATH=src python -m mklang.cli run examples/react.mkl --format text --provider deepseek --set question.text=Calculate_7_times_24_minus_15_books"
Enter
Wait+Screen@180s /provider deepseek/
Wait+Screen@90s /153/
Sleep 3s

Type "clear"
Enter
Type "PYTHONPATH=src python -m mklang.cli check examples/react.mkl"
Enter
Wait+Screen /OK.*react/
Sleep 1s
Type "PYTHONPATH=src python -m mklang.cli lint --strict examples/react.mkl"
Enter
Wait+Screen /findings=0/
Sleep 1s
