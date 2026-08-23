# Plugin quickstart

Extend mklang with custom tools, hooks, machines, and providers — all via
packaging entry points. No core changes, no monkey-patching.

## The four plugin groups

| Group | What it adds | Signature | Entry in `pyproject.toml` |
|---|---|---|---|
| `mklang.tools` | Host callables for `tool:` states | `(dict) → str` | [below](#tools) |
| `mklang.hooks` | Code-hook gates (LLM-free predicates) | `(dict, Any) → bool` | [below](#hooks) |
| `mklang.machines` | Reusable `.mkl` machines | `dict` or `() → dict` | [below](#machines) |
| `mklang.providers` | LLM adapter for a new provider | subclass of `LLM` | [below](#providers) |

## 1. A custom tool

A tool is a `(dict) → str` callable that a `tool:` state invokes.

```toml
# pyproject.toml
[project]
name = "my-mklang-plugins"
version = "0.1.0"

[project.entry-points."mklang.tools"]
my_calculator = "my_plugins.tools:my_calculator"
```

```python
# my_plugins/tools.py
def my_calculator(inp: dict) -> str:
    """Evaluate a math expression. Input: {"expr": "sqrt(2)"}.

    Returns a plain string — the observation deposited in context.
    """
    import math
    expr = inp.get("expr", "").strip()
    try:
        result = eval(expr, {"__builtins__": {}}, {"sqrt": math.sqrt, "pow": pow})
        return str(result)
    except Exception as e:
        return f"error: {e}"
```

Use it in a machine:

```yaml
my_calc:
  tool: my_calculator
  input: { expr: "{{expression}}" }
  output: result
  gates:
    - when: otherwise
      then: ok
      to: END
```

### Tool conventions

- I/O tools (search, send, file write) should return the **stub envelope**
  (ADR 0020): `{"tool": "name", "stub": false, "result": "…"}`.
- Pure offline tools (calc, date) can return a plain string.
- Tools are **host-provided** — the `.mkl` never imports code.

## 2. A custom hook

A hook is a `(context, output) → bool` predicate that evaluates a gate
**without the LLM** (ADR 0006).

```toml
[project.entry-points."mklang.hooks"]
is_business_hours = "my_plugins.hooks:is_business_hours"
```

```python
# my_plugins/hooks.py
from datetime import datetime, timezone

def is_business_hours(ctx: dict, output: object) -> bool:
    """True when the current UTC hour is 9–17."""
    now = datetime.now(timezone.utc)
    return 9 <= now.hour < 17
```

Use it in a gate:

```yaml
gates:
  - when: it is business hours
    hook: is_business_hours
    then: ok
    to: auto_approve
  - when: otherwise
    escalate: true
    to: human_review
```

## 3. A custom machine

A machine plugin registers a `.mkl` document (dict) or a zero-arg factory
returning one.

```toml
[project.entry-points."mklang.machines"]
my_review = "my_plugins.machines:my_review_machine"
```

```python
# my_plugins/machines.py
def my_review_machine():
    return {
        "machine": "my_review",
        "entry": "review",
        "budget": 6,
        "states": {
            "review": {
                "structure": "a one-line approval or rejection",
                "prompt": "Review: {{content}}",
                "output": "verdict",
                "gates": [
                    {"when": "the content is acceptable", "then": "ok", "to": "END"},
                    {"when": "otherwise", "repair": 1, "to": "review"},
                ],
            }
        },
    }
```

The machine is then runnable by name:

```bash
mklang run my_review --set content="hello world"
```

Or callable from another machine:

```yaml
call: std_refine
input: { text: "{{draft}}" }
output: refined
```

### Plugin precedence

The registry merges layers in this order (later wins):

```
stdlib ← plugins ← system ← user ← local
```

A plugin machine named `std_research` would **shadow** the bundled one — use
distinct names to avoid surprises.

## 4. A custom provider

Provider plugins register an LLM adapter. The adapter must subclass
`mklang.llm.base.LLM`.

```toml
[project.entry-points."mklang.providers"]
my_provider = "my_plugins.providers:MyProvider"
```

```python
# my_plugins/providers.py
from mklang.llm.base import LLM

class MyProvider(LLM):
    """Adapter for a custom OpenAI-compatible endpoint."""

    def produce(self, prompt, *, guidance=None, policy=None, reason=False):
        # Return (reasoning_text_or_none, output_text)
        ...

    def judge(self, conditions, output, reasoning=None, context=None):
        # Return {"choice": k} where k is 1-based or N+1 for "none"
        ...
```

The reference interpreter ships adapters for OpenAI-compatible endpoints
(`openai_compat`) and Anthropic (`anthropic`). A custom provider plugs in
the same way.

## 5. Plugin policy

Plugins are subject to the `MKLANG_ALLOWED_PLUGINS` environment variable.
If set, only plugin names in the comma-separated allowlist are loaded:

```bash
export MKLANG_ALLOWED_PLUGINS="my_calculator,my_review"
```

An empty value (the default) allows all plugins. This is a safety gate for
production environments.

## 6. Distributing your plugin

```bash
# Build
pip install build
python -m build

# Publish
pip install twine
twine upload dist/*
```

Consumers install and get the entry points automatically:

```bash
pip install my-mklang-plugins
mklang machines   # your machine appears in the list
```

## Reference: built-in plugins

| Group | Name | Description |
|---|---|---|
| `mklang.tools` | `calc` | Safe arithmetic expression evaluator |
| `mklang.tools` | `search` | Web search (offline stub by default) |
| `mklang.tools` | `search_kb` | Knowledge-base lookup (stub) |
| `mklang.tools` | `send_reply` | Customer reply sender (stub) |
| `mklang.tools` | `list_files` | List workspace directory |
| `mklang.tools` | `read_file` | Read workspace file |
| `mklang.tools` | `write_file` | Write workspace file |
| `mklang.hooks` | `always_true` | Always returns True |
| `mklang.hooks` | `always_false` | Always returns False |
| `mklang.hooks` | `amount_le_100` | Amount ≤ 100 (demo) |
| `mklang.hooks` | `has_receipt` | Receipt present (demo) |
| `mklang.hooks` | `auto_approve_ok` | Auto-approve logic (demo) |
| `mklang.providers` | `anthropic` | Anthropic API adapter |

Parametric hooks (no plugin needed): `eq:key:value`, `neq:key:value`,
`write_failed`.