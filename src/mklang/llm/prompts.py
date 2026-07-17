"""Reference-interpreter prompt assembly (host, not language).

Produce calls map language faces to LLM roles:

* ``structure`` + ``execution`` → **system** (durable contract + policy)
* ``prompt`` (interpolated) → **user** (turn task + data)

Judge calls use :data:`JUDGE_SYSTEM` in ``base.py`` (separate, gate-only role).
Neither ``structure`` nor ``execution`` is interpolated — put ``{{…}}`` only in
``prompt`` so untrusted/turn data never enters the system channel.
"""

from __future__ import annotations

from ..model import State

_DEFAULT_EXECUTION = "No additional operational policy."

_PRODUCE_SYSTEM = """\
You are executing exactly one state of an mklang state machine.

## Output contract (structure)
{structure}

## Operational policy (execution)
{execution}

## Rules
- Emit only the content required by the output contract.
- No preamble, no postscript, no markdown fences unless the contract asks for them.
- Do not invent tools, side effects, or facts not grounded in the user message.\
"""


def build_produce_system(state: State) -> str:
    """Build the provider system message for a generative state produce call."""
    structure = (state.structure or "").strip() or "(unspecified)"
    execution = (state.execution or "").strip() or _DEFAULT_EXECUTION
    return _PRODUCE_SYSTEM.format(structure=structure, execution=execution)
