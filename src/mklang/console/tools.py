"""Console host tools (ADR 0015): the brain machine's hands.

Pure host callables on top of the host seam — no TUI import. The console
injects a `Bridge` (emit / ask / confirm); tests inject a fake one, so the
whole layer is verifiable offline. Per the engine's tool contract, every tool
takes a dict of rendered string values and returns an observation string.

Safety: `write_machine` is confined to the workspace directory (resolved-path
prefix check); running a machine whose states invoke host tools requires an
explicit one-time consent per tool set (SPEC §11 applies to the console too).
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import yaml

from .. import host
from ..config import load_provider
from ..engine import run as run_machine_engine
from ..llm.base import LLM
from ..registry import base_registry, load_registry


class Bridge(Protocol):
    """The UI seam. `emit` must be thread-safe; `ask`/`confirm` may block."""

    def emit(self, event: dict) -> None: ...

    def ask(self, question: str) -> str: ...

    def confirm(self, prompt: str) -> bool: ...


def _default_build_llm(prov):
    from ..providers import build_llm

    return build_llm(prov)


def _obs(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


@dataclass
class ConsoleTools:
    config: str | None
    provider: str | None
    bridge: Bridge
    workspace: Path
    default_cost_budget: int | None = None
    # Output anti-cutoff policy for commissioned machines (ADR 0018).
    on_truncate: str = "report"
    build_llm: Callable[[object], LLM] | None = None
    cancel_requested: Callable[[], object] | None = None
    _consented: set = field(default_factory=set)
    _close_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self):
        self.workspace = Path(self.workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.prov = load_provider(self.config, self.provider)
        self.llm = (self.build_llm or _default_build_llm)(self.prov)

    def close(self) -> None:
        """Release the provider client once, if the adapter exposes a lifecycle hook."""
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        close = getattr(self.llm, "close", None)
        if callable(close):
            close()

    # -- registry ----------------------------------------------------------

    def _registry(self) -> dict:
        return {**base_registry(), **load_registry(self.workspace, validate=False)}

    def as_tool_registry(self) -> dict:
        """The tool map handed to the brain machine's run(tools=...)."""
        return {
            "list_machines": self.list_machines,
            "describe_machine": self.describe_machine,
            "read_machine": self.read_machine,
            "check_machine": self.check_machine,
            "write_machine": self.write_machine,
            "run_machine": self.run_machine,
            "ask_user": self.ask_user,
        }

    # -- discovery ---------------------------------------------------------

    def list_machines(self, _input: dict) -> str:
        reg = self._registry()
        rows = [
            {
                "name": name,
                "result": m.result,
                "budget": m.budget,
                "context_keys": sorted(m.context),
            }
            for name, m in sorted(reg.items())
        ]
        return _obs({"machines": rows})

    def describe_machine(self, input: dict) -> str:
        name = (input.get("name") or "").strip()
        reg = self._registry()
        if name not in reg:
            return _obs({"error": f"unknown machine '{name}'", "known": sorted(reg)})
        return _obs(host.describe_machine(reg[name]))

    def read_machine(self, input: dict) -> str:
        name = (input.get("name") or "").strip()
        path = self._workspace_path(name)
        if path is not None and path.is_file():
            return path.read_text(encoding="utf-8")
        return _obs({"error": f"no machine file '{name}' in the workspace"})

    # -- authoring ---------------------------------------------------------

    def check_machine(self, input: dict) -> str:
        source = input.get("source")
        name = (input.get("name") or "").strip()
        if source:
            return _obs(host.check_machine(source=source))
        path = self._workspace_path(name)
        if path is None or not path.is_file():
            return _obs({"error": f"no source given and no machine file '{name}'"})
        return _obs(host.check_machine(path=str(path)))

    def write_machine(self, input: dict) -> str:
        name = (input.get("name") or "").strip()
        source = input.get("source") or ""
        if not name:
            # Derive the filename from the document's own `machine:` field, so a
            # single authored-source output is enough to save.
            try:
                doc = yaml.safe_load(source)
            except yaml.YAMLError as e:
                return _obs({"error": f"source is not valid YAML: {e}"})
            if not isinstance(doc, dict) or not str(doc.get("machine") or "").strip():
                return _obs({"error": "source has no `machine:` name to derive a filename from"})
            name = str(doc["machine"]).strip()
        path = self._workspace_path(name)
        if path is None:
            return _obs({"error": f"'{name}' escapes the workspace — write refused"})
        if path.exists() and not self.bridge.confirm(f"overwrite {path.name} in the workspace?"):
            return _obs({"error": "overwrite declined by the user"})
        path.write_text(source, encoding="utf-8")
        checked = host.check_machine(source=source)
        return _obs({"written": path.name, "check": checked})

    def _workspace_path(self, name: str) -> Path | None:
        """Resolve a machine name/filename inside the workspace; None if it escapes."""
        if not name:
            return None
        fname = name if name.endswith(".mkl") else f"{name}.mkl"
        candidate = (self.workspace / fname).resolve()
        if not candidate.is_relative_to(self.workspace):
            return None
        return candidate

    # -- execution ---------------------------------------------------------

    def run_machine(self, input: dict) -> str:
        budget_field = input.get("cost_budget")
        if input.get("request"):
            # One-blob form for machine authors: a single state output carries
            # {"target": …, "inputs": {…}, "cost_budget"?} as one JSON object.
            try:
                req = json.loads(input["request"])
            except ValueError as e:
                return _obs({"error": f"request is not valid JSON: {e}"})
            if not isinstance(req, dict):
                return _obs({"error": "request must be a JSON object"})
            target = str(req.get("target") or "").strip()
            inputs = req.get("inputs") or {}
            budget_field = req.get("cost_budget", budget_field)
        else:
            target = (input.get("target") or "").strip()
            try:
                inputs = json.loads(input.get("inputs") or "{}")
            except ValueError as e:
                return _obs({"error": f"inputs is not valid JSON: {e}"})
        if not isinstance(inputs, dict):
            return _obs({"error": "inputs must be a JSON object"})
        reg = self._registry()
        machine = reg.get(target)
        if machine is None:
            return _obs({"error": f"unknown machine '{target}'", "known": sorted(reg)})
        used_tools = sorted({s.tool for s in machine.states.values() if s.kind == "tool"})
        if used_tools and not set(used_tools) <= self._consented:
            # One-time per session (SPEC §11). Wording must read as a yes/no
            # gate, not a terminal error — users often misread this as failure.
            tools_txt = ", ".join(used_tools)
            if not self.bridge.confirm(
                f"Consent: machine '{target}' will call host tool(s) [{tools_txt}] "
                f"(e.g. live web search). Allow this once for the session?"
            ):
                return _obs({"error": "run declined by the user", "tools": used_tools})
            self._consented.update(used_tools)
        if "write_file" in used_tools:
            # Interactive consent above is the coding-tool write grant (ADR 0024);
            # headless surfaces need --allow-write / MKLANG_FS_WRITE=1 instead.
            from ..fs import allow_writes

            allow_writes(True)
        ctx = dict(machine.context)
        for k, v in inputs.items():
            host.set_path(ctx, k, v)
        host.inject_host_defaults(ctx)  # e.g. context.today when declared
        cost_budget = int(budget_field) if budget_field else self.default_cost_budget
        from ..hooks import load_hook_registry
        from ..tools import load_tool_registry

        res = run_machine_engine(
            machine,
            ctx,
            reg,
            self.llm,
            self.prov.tiers,
            self.prov.judge_override(),
            tier_params=self.prov.params,
            cost_budget=cost_budget,
            tools=load_tool_registry(),
            hooks=load_hook_registry(),
            suspendable=True,
            escalate_suspend=True,
            on_event=lambda e: self.bridge.emit({"run": target, **e}),
            on_truncate=self.on_truncate,
            cancel_requested=self.cancel_requested,
        )
        # HITL: broker every escalation to the human, then resume in place.
        while res.status == "suspended" and res.error == "escalated":
            last = res.trace[-1] if res.trace else {}
            reply = self.bridge.ask(
                f"'{target}' escalated at {res.at}: {last.get('gate', 'needs a decision')}\n"
                f"last output: {last.get('output', '')}"
            )
            # A suspended run always carries checkpoint frames.
            assert res.frames is not None
            host.set_path(res.frames[-1]["ctx"], "human.reply", reply)
            res = run_machine_engine(
                machine,
                dict(machine.context),
                reg,
                self.llm,
                self.prov.tiers,
                self.prov.judge_override(),
                tier_params=self.prov.params,
                cost_budget=cost_budget,
                tools=load_tool_registry(),
                hooks=load_hook_registry(),
                suspendable=True,
                escalate_suspend=True,
                resume=res.frames,
                on_event=lambda e: self.bridge.emit({"run": target, **e}),
                on_truncate=self.on_truncate,
                cancel_requested=self.cancel_requested,
            )
        # Compact + honest observation for the brain (ADR 0015/0017/0018):
        # propagate produce truncation; never silent-cut the result string.
        return _obs(host.compact_run_observation(res))

    # -- human -------------------------------------------------------------

    def ask_user(self, input: dict) -> str:
        return self.bridge.ask(input.get("question") or "the machine needs your input")
