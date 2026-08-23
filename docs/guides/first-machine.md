# Your first machine in three minutes

A hands-on walkthrough from zero to a running state machine. No theory required
up front — read the [SPEC](../../SPEC.md) and [Best practices](best-practices.md)
later.

## Prerequisites

```bash
pipx install 'mklang[mcp]'   # or: pip install 'mklang[mcp]'
mklang --version              # ≥ 1.2.0
```

## 1. Scaffold

```bash
mkdir my-first && cd my-first
mklang init --user
```

This creates `~/.config/mklang/runtime.yaml`, `~/.config/mklang/.env`, and a
sample machine at `~/.local/share/mklang/machines/hello.mkl`.

## 2. Set a provider key

```bash
echo "DEEPSEEK_API_KEY=sk-…" >> ~/.config/mklang/.env
```

Any provider works — see
[`runtime.example.yaml`](../../config/runtime.example.yaml) for the full list.

## 3. Run the sample (no API key needed)

```bash
mklang test ~/.local/share/mklang/machines/hello.mkl \
    --script ~/.local/share/mklang/machines/hello.test.yaml
```

This uses a **scripted LLM** (no network, fully deterministic). You should see:

```
PASS accepted-first-try
PASS repair-fires-then-accepted
```

## 4. Run for real

```bash
mklang run ~/.local/share/mklang/machines/hello.mkl \
    --set task="explain what a state machine is"
```

Output:

```
# hello · provider=deepseek · tiers={fast: …, balanced: …, reasoning: …}
DONE hello · provider deepseek
Result ──────────────────────────────────────────────────────────
A state machine is a mathematical model of computation …
tokens 120+48 · steps 1
```

If the answer is unsatisfactory, the `repair` gate re-runs the state with
feedback and tries again (up to `budget: 4` total steps).

## 5. Write your own

Copy the skeleton below into `greeting.mkl`:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/gianlucamazza/mklang/main/schema/mklang.schema.json
mklang: "0.4"
machine: greeting
entry: respond
budget: 4
result: answer

context:
  name: ""

states:
  respond:
    structure: a friendly greeting, one sentence, max 30 words
    prompt: Greet the person named {{name}}.
    output: answer
    gates:
      - when: the greeting uses the person's name
        then: ok
        to: END
      - when: otherwise
        repair: 2
        to: respond
```

```bash
mklang run greeting.mkl --set name="Alice"
```

## What just happened?

```
┌──────────┐   gate OK    ┌─────┐
│  respond  │ ──────────→ │ END │
│ (LLM gen) │ ←────────── │     │
└──────────┘   repair     └─────┘
```

1. The engine enters `respond`, renders the `prompt` with `name=Alice`, and
   calls the LLM.
2. The LLM's output is stored in context as `{{answer}}`.
3. The **gate judge** (an LLM call) evaluates: _"does the greeting use the
   person's name?"_
4. If yes → `to: END` (run done). If no → `repair: 2` re-runs `respond` with
   feedback, up to two more times. If the budget is exhausted → `otherwise`
   accepts the best attempt.

## Next steps

| Goal | Where |
|---|---|
| Understand every language construct | [SPEC](../../SPEC.md) |
| Write correct machines | [Authoring guide](authoring.md) |
| Tune reliability and cost | [Patterns](patterns.md) |
| Use tools (search, file I/O) | [Best practices §5](best-practices.md#5-tools) |
| Compose machines (`call: std_refine`) | [Stdlib reference](../reference/stdlib.md) |
| Interactive TUI | [Console guide](console.md) |

## Error quick reference

When a run halts, the CLI prints an error code and a hint. Common codes:

| Error | What it means | Fix |
|---|---|---|
| `budget-exhausted` | Ran out of steps | Increase `budget:` or reduce repair loops |
| `loop-ceiling` | A state entered too many times | Add `max_visits:` or an exit gate |
| `no-gate-matched` | No gate was true, no `otherwise` | Add `when: otherwise` as the last gate |
| `judge-unparseable` | Judge model was too verbose | Use a non-reasoning model for judging |
| `call-failed` | A sub-machine halted | Check the sub-run trace |
| `parse-json` | LLM output was not valid JSON | Be more explicit in `structure:` about the expected JSON shape |

For the full list, see [SPEC §7](../../SPEC.md#7-budget-termination-errors).