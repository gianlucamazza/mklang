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

import contextlib
import json
import os
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import yaml

from .. import host
from ..checkpoint import taint_frame
from ..config import load_provider
from ..engine import run as run_machine_engine
from ..llm.base import LLM
from ..paths import project_machine_root
from ..registry import base_registry, load_project_registry
from .capabilities import capability_key, metadata_for, redact
from .workspace import WorkspaceInspector


class Bridge(Protocol):
    """The UI seam. `emit` must be thread-safe; `ask`/`confirm` may block."""

    def emit(self, event: dict) -> None: ...

    def ask(self, question: str) -> str: ...

    def confirm(self, prompt: str) -> bool: ...


def _default_build_llm(prov):
    from ..providers import build_llm

    return build_llm(prov)


def _obs(payload: dict) -> str:
    payload.setdefault("untrusted", True)
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
    # Control-flow-taint policy for commissioned machines (ADR 0030). Same default
    # as the CLI: record the tainted effect, let the operator opt into refusing it.
    on_untrusted_flow: str = "report"
    build_llm: Callable[[object], LLM] | None = None
    cancel_requested: Callable[[], object] | None = None
    audit: Callable[[dict], object] | None = None
    task: dict = field(default_factory=dict)
    task_persist: Callable[[], object] | None = None
    _consented: set = field(default_factory=set)
    _close_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self):
        self.workspace = Path(self.workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.machine_root = project_machine_root(self.workspace)
        self.inspector = WorkspaceInspector(self.workspace)
        self.prov = load_provider(self.config, self.provider, cwd=self.workspace)
        self.llm = (self.build_llm or _default_build_llm)(self.prov)
        # The console has one authoritative workspace. Bind the data-tool
        # backend to it instead of allowing runtime.yaml/MKLANG_FS_ROOT to
        # silently redirect commissioned machines elsewhere.
        from .. import fs

        self._previous_fs_backend = fs.current_fs_backend()
        backend_name, _ = fs.resolve_backend_name()
        fs.configure_fs(
            fs.LocalFSBackend(self.workspace) if backend_name == "local" else fs.StubFSBackend()
        )
        self._fs_bound = True

    def close(self) -> None:
        """Release the provider client once, if the adapter exposes a lifecycle hook."""
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        close = getattr(self.llm, "close", None)
        if callable(close):
            close()
        if getattr(self, "_fs_bound", False):
            from .. import fs

            fs.configure_fs(self._previous_fs_backend)
            fs.allow_writes(False)
            self._fs_bound = False

    def _audit(self, event: str, **fields: object) -> None:
        if self.audit is None:
            return
        # Audit must never change the machine's execution semantics.
        with contextlib.suppress(Exception):
            self.audit(redact({"event": event, **fields}))

    # -- registry ----------------------------------------------------------

    def _registry(self) -> dict:
        return {**base_registry(), **load_project_registry(self.workspace, validate=False)}

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
            "list_workspace": self.list_workspace,
            "read_workspace_file": self.read_workspace_file,
            "search_workspace": self.search_workspace,
            "update_task": self.update_task,
        }

    @property
    def consented(self) -> set[str]:
        """Granted capability keys, exposed without leaking storage internals."""
        return self._consented

    def restore_consented(self, grants: list[str] | set[str]) -> None:
        self._consented.update(grants)

    # -- read-only project inspection -------------------------------------

    def workspace_context(self, _input: dict | None = None) -> dict:
        """Return a compact deterministic snapshot for the console brain."""
        return self.inspector.snapshot()

    @staticmethod
    def _decode_workspace_request(input: dict) -> dict:
        raw = input.get("request") if isinstance(input, dict) else None
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str) and raw.strip():
            try:
                value = json.loads(raw)
            except ValueError:
                return {"path": raw}
            return value if isinstance(value, dict) else {}
        return input if isinstance(input, dict) else {}

    def list_workspace(self, input: dict) -> str:
        request = self._decode_workspace_request(input)
        return _obs(self.inspector.list(request.get("path", ""), request.get("depth", 1)))

    def read_workspace_file(self, input: dict) -> str:
        request = self._decode_workspace_request(input)
        return _obs(self.inspector.read(request.get("path", ""), request.get("max_bytes")))

    def search_workspace(self, input: dict) -> str:
        request = self._decode_workspace_request(input)
        return _obs(
            self.inspector.search(
                request.get("query", ""),
                request.get("path", ""),
                request.get("max_results"),
                request.get("case_sensitive", False),
            )
        )

    # -- discovery ---------------------------------------------------------

    def list_machines(self, _input: dict) -> str:
        reg = self._registry()
        rows = [
            {
                "name": name,
                "result": m.result,
                "budget": m.budget,
                "context_keys": sorted(m.context),
                "tools": [
                    {"name": s.tool, **metadata_for(s.tool).__dict__}
                    for s in m.states.values()
                    if s.kind == "tool"
                ],
            }
            for name, m in sorted(reg.items())
        ]
        return _obs({"machines": rows})

    def describe_machine(self, input: dict) -> str:
        name = str(input.get("name") or "").strip()
        reg = self._registry()
        if name not in reg:
            return _obs({"error": f"unknown machine '{name}'", "known": sorted(reg)})
        return _obs(host.describe_machine(reg[name]))

    def read_machine(self, input: dict) -> str:
        name = str(input.get("name") or "").strip()
        path = self._existing_machine_path(name)
        if path is not None and path.is_file():
            try:
                return path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                return _obs({"error": f"cannot read machine '{name}': {exc}"})
        return _obs({"error": f"no machine file '{name}' in the workspace"})

    # -- authoring ---------------------------------------------------------

    def check_machine(self, input: dict) -> str:
        source = input.get("source")
        name = str(input.get("name") or "").strip()
        if source:
            return _obs(host.check_machine(source=source))
        path = self._existing_machine_path(name)
        if path is None or not path.is_file():
            return _obs({"error": f"no source given and no machine file '{name}'"})
        return _obs(host.check_machine(path=str(path)))

    def write_machine(self, input: dict) -> str:
        name = str(input.get("name") or "").strip()
        source = str(input.get("source") or "")
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
        if path.exists() and not self.bridge.confirm(
            f"[high-risk] overwrite {path.name} in the workspace?"
        ):
            self._audit("write-denied", machine=name, path=path.name, reason="overwrite declined")
            return _obs({"error": "overwrite declined by the user"})
        checked = host.check_machine(source=source)
        if not checked.get("ok"):
            self._audit("machine-write-failed", machine=name, path=path.name, check=checked)
            return _obs(
                {"error": "machine validation failed; file was not changed", "check": checked}
            )
        temporary: str | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
            ) as handle:
                handle.write(source)
                handle.flush()
                os.fsync(handle.fileno())
                temporary = handle.name
            os.replace(temporary, path)
        except OSError as exc:
            if temporary:
                with contextlib.suppress(OSError):
                    os.unlink(temporary)
            self._audit("machine-write-failed", machine=name, path=path.name, error=str(exc))
            return _obs({"error": f"cannot write machine atomically: {exc}", "check": checked})
        self._audit(
            "machine-written", machine=name, path=path.name, bytes=len(source.encode("utf-8"))
        )
        return _obs({"written": path.name, "check": checked})

    def update_task(self, input: dict) -> str:
        """Update the persistent task ledger without granting new capabilities."""
        request = self._decode_workspace_request(input)
        if not request:
            return _obs({"error": "task update must be a non-empty JSON object"})
        allowed = {
            "goal",
            "phase",
            "plan",
            "progress",
            "blocked_reason",
            "artifacts",
            "verification",
        }
        unknown = sorted(set(request) - allowed)
        if unknown:
            return _obs({"error": f"unknown task fields: {', '.join(unknown)}"})
        phases = {"planning", "executing", "verifying", "waiting", "blocked", "complete"}
        if "phase" in request and request["phase"] not in phases:
            return _obs({"error": f"invalid task phase {request['phase']!r}"})
        if "progress" in request and (
            not isinstance(request["progress"], int) or not 0 <= request["progress"] <= 100
        ):
            return _obs({"error": "task progress must be an integer between 0 and 100"})
        for key in ("plan", "artifacts", "verification"):
            if key in request and not isinstance(request[key], list):
                return _obs({"error": f"task {key} must be a list"})
        for key in ("goal", "blocked_reason"):
            if key in request and not isinstance(request[key], str):
                return _obs({"error": f"task {key} must be a string"})
        self.task.update(request)
        self.task["action_count"] = int(self.task.get("action_count", 0)) + 1
        self._audit("task-updated", task=self.task)
        if self.task_persist is not None:
            self.task_persist()
        return _obs({"task": self.task})

    def _workspace_path(self, name: str) -> Path | None:
        """Resolve a machine name/filename inside the canonical machine root."""
        if not name:
            return None
        fname = name if name.endswith(".mkl") else f"{name}.mkl"
        parts = Path(fname).parts
        if any(part.startswith(".") or part in WorkspaceInspector.IGNORED_DIRS for part in parts):
            return None
        candidate = (self.machine_root / fname).resolve()
        if not candidate.is_relative_to(self.machine_root):
            return None
        return candidate

    def _legacy_workspace_path(self, name: str) -> Path | None:
        """Resolve a legacy root-level machine without using it for new writes."""
        path = self._workspace_path(name)
        if path is None:
            return None
        legacy = (self.workspace / path.relative_to(self.machine_root)).resolve()
        return legacy if legacy.is_relative_to(self.workspace) else None

    def _existing_machine_path(self, name: str) -> Path | None:
        """Prefer canonical machines, then accept an existing root-level file."""
        canonical = self._workspace_path(name)
        if canonical is None:
            return None
        if canonical.is_file():
            return canonical
        legacy = self._legacy_workspace_path(name)
        return legacy if legacy is not None and legacy.is_file() else canonical

    # -- execution ---------------------------------------------------------

    def run_machine(self, input: dict) -> str:
        budget_field = input.get("cost_budget")
        if input.get("request"):
            # One-blob form for machine authors: a single state output carries
            # {"target": …, "inputs": {…}, "cost_budget"?} as one JSON object.
            # A `parse: json` state hands over the decoded object itself, so the
            # blob arrives either already parsed or as the text to parse — the
            # same two shapes `_decode_workspace_request` accepts.
            raw = input["request"]
            req: object = raw
            if not isinstance(raw, dict):
                try:
                    req = json.loads(raw)
                except (TypeError, ValueError) as e:
                    return _obs({"error": f"request is not valid JSON: {e}"})
            if not isinstance(req, dict):
                return _obs({"error": "request must be a JSON object"})
            target = str(req.get("target") or "").strip()
            inputs = req.get("inputs") or {}
            budget_field = req.get("cost_budget", budget_field)
        else:
            target = str(input.get("target") or "").strip()
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
        try:
            registered_tools, registered_hooks, _warnings = host.check_prepared(
                self.prov, machine, reg
            )
        except host.PrepareError as exc:
            return _obs(
                {
                    "error": "machine preflight failed",
                    "errors": exc.errors,
                    "warnings": exc.warnings,
                }
            )
        used_tools = sorted({s.tool for s in machine.states.values() if s.kind == "tool"})
        required_grants = {capability_key(target, tool) for tool in used_tools}
        self._audit(
            "capability-check", machine=target, tools=used_tools, grants=sorted(required_grants)
        )
        if used_tools and not required_grants <= self._consented:
            # One-time per session (SPEC §11). Wording must read as a yes/no
            # gate, not a terminal error — users often misread this as failure.
            tools_txt = ", ".join(used_tools)
            high_risk = any(
                not metadata_for(tool).read_only
                or metadata_for(tool).external_egress
                or metadata_for(tool).irreversible
                or metadata_for(tool).sensitivity in {"high", "unknown"}
                for tool in used_tools
            )
            prefix = "[high-risk] " if high_risk else ""
            if not self.bridge.confirm(
                f"{prefix}Consent: machine '{target}' will call host tool(s) [{tools_txt}]. "
                f"Allow these scoped capabilities once for the session?"
            ):
                self._audit("capability-denied", machine=target, tools=used_tools)
                return _obs({"error": "run declined by the user", "tools": used_tools})
            self._consented.update(required_grants)
            self._audit(
                "capability-granted",
                machine=target,
                tools=used_tools,
                grants=sorted(required_grants),
            )
        from .. import fs

        previous_write_override = fs.write_override()
        if "write_file" in used_tools:
            # Interactive consent above is the coding-tool write grant (ADR 0024);
            # headless surfaces need --allow-write / MKLANG_FS_WRITE=1 instead.
            fs.allow_writes(True)
        ctx = dict(machine.context)
        for k, v in inputs.items():
            host.set_path(ctx, k, v)
        host.inject_host_defaults(ctx)  # e.g. context.today when declared
        cost_budget: int | None = None
        if budget_field is not None and budget_field != "":
            try:
                cost_budget = int(budget_field)
            except (TypeError, ValueError):
                return _obs({"error": "cost_budget must be an integer"})
            if cost_budget <= 0:
                return _obs({"error": "cost_budget must be positive"})
        else:
            cost_budget = self.default_cost_budget
        try:
            res = run_machine_engine(
                machine,
                ctx,
                reg,
                self.llm,
                self.prov.tiers,
                self.prov.judge_override(),
                tier_params=self.prov.params,
                cost_budget=cost_budget,
                tools=registered_tools,
                hooks=registered_hooks,
                suspendable=True,
                escalate_suspend=True,
                on_event=lambda e: self.bridge.emit({"run": target, **e}),
                on_truncate=self.on_truncate,
                on_untrusted_flow=self.on_untrusted_flow,
                cancel_requested=self.cancel_requested,
            )
        finally:
            fs.allow_writes(previous_write_override)
        self._audit(
            "machine-finished", machine=target, status=res.status, error=res.error, usage=res.usage
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
            # The reply crossed the host boundary like any other injected value:
            # untrusted by provenance (ADR 0025), and the confirmation that clears
            # this suspension's control-flow taint (ADR 0030).
            taint_frame(res.frames[-1], ["human.reply"])
            previous_write_override = fs.write_override()
            if "write_file" in used_tools:
                fs.allow_writes(True)
            try:
                res = run_machine_engine(
                    machine,
                    dict(machine.context),
                    reg,
                    self.llm,
                    self.prov.tiers,
                    self.prov.judge_override(),
                    tier_params=self.prov.params,
                    cost_budget=cost_budget,
                    tools=registered_tools,
                    hooks=registered_hooks,
                    suspendable=True,
                    escalate_suspend=True,
                    resume=res.frames,
                    on_event=lambda e: self.bridge.emit({"run": target, **e}),
                    on_truncate=self.on_truncate,
                    on_untrusted_flow=self.on_untrusted_flow,
                    cancel_requested=self.cancel_requested,
                )
            finally:
                fs.allow_writes(previous_write_override)
        # Compact + honest observation for the brain (ADR 0015/0017/0018):
        # propagate produce truncation; never silent-cut the result string.
        return _obs(host.compact_run_observation(res))

    # -- human -------------------------------------------------------------

    def ask_user(self, input: dict) -> str:
        question = input.get("question") or "the machine needs your input"
        self._audit("human-input-requested", question=str(question))
        reply = self.bridge.ask(question)
        self._audit("human-input-received", reply=reply)
        return reply
