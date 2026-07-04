"""Dataclasses for an mklang machine, and parsing from a plain dict (post-YAML)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Gate:
    when: str
    kind: str  # "ok" | "repair" | "escalate" | "fail"
    to: str | None = None
    repair: int | None = None


@dataclass
class State:
    id: str
    kind: str  # "generative" | "call"
    gates: list[Gate]
    output: str
    tier: str | None = None
    # generative
    structure: str | None = None
    prompt: str | None = None
    execution: str | None = None
    reason: bool = False
    accumulate: bool = False
    sample: int | None = None
    over: str | None = None
    # call
    call: str | None = None
    input: dict | None = None

    @property
    def is_fanout(self) -> bool:
        return self.sample is not None or self.over is not None


@dataclass
class Machine:
    name: str
    entry: str
    budget: int
    states: dict[str, State]
    default_tier: str = "balanced"
    result: str | None = None
    context: dict = field(default_factory=dict)
    version: str | None = None  # the `mklang:` spec-version field (advisory)


def parse_gate(d: dict) -> Gate:
    if "then" in d:
        return Gate(d["when"], "ok", d.get("to"))
    if "repair" in d:
        return Gate(d["when"], "repair", d.get("to"), repair=d["repair"])
    if "escalate" in d:
        return Gate(d["when"], "escalate", d.get("to"))
    if "fail" in d:
        return Gate(d["when"], "fail", None)
    raise ValueError(f"gate has no policy (then/repair/escalate/fail): {d!r}")


def parse_state(sid: str, d: dict) -> State:
    kind = "call" if "call" in d else "generative"
    return State(
        id=sid,
        kind=kind,
        gates=[parse_gate(g) for g in d["gates"]],
        output=d["output"],
        tier=d.get("tier"),
        structure=d.get("structure"),
        prompt=d.get("prompt"),
        execution=d.get("execution"),
        reason=bool(d.get("reason", False)),
        accumulate=bool(d.get("accumulate", False)),
        sample=d.get("sample"),
        over=d.get("over"),
        call=d.get("call"),
        input=d.get("input"),
    )


def parse_machine(d: dict) -> Machine:
    states = {sid: parse_state(sid, sd) for sid, sd in d["states"].items()}
    return Machine(
        name=d["machine"],
        entry=d["entry"],
        budget=d["budget"],
        states=states,
        default_tier=d.get("default_tier", "balanced"),
        result=d.get("result"),
        context=d.get("context") or {},
        version=d.get("mklang"),
    )
