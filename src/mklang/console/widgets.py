"""Console widgets (ADR 0015 M3a): the live activity tree and the inspector.

Both are fed from the main thread (the bridge marshals engine events with
call_from_thread), so no locking is needed here.

Tree labels use plain ``rich.text.Text`` segments (see ``render.tree_*``) so
user text and LLM output previews never ride Rich markup interpolation.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from textual.containers import Vertical
from textual.widgets import RichLog, Static, TabbedContent, TabPane, Tree

if TYPE_CHECKING:
    from textual.widgets.tree import TreeNode

    from ..engine import RunResult
    from .session import Session as ConsoleSession

from . import render as log_render


class ActivityTree(Tree):
    """Live tree of the current turn: brain states at the top level, each
    commissioned run nested under the brain state that launched it, `call:`
    sub-runs nested by depth, fan-out branches as leaves."""

    def __init__(self):
        super().__init__("activity", id="activity")
        self.auto_expand = True
        self.show_root = False
        self._turn_node = None
        self._reset_maps()

    _turn_node: "TreeNode | None"
    _brain_open: "TreeNode | None"
    _run_nodes: dict[tuple, "TreeNode"]
    _state_nodes: dict[tuple, "TreeNode"]
    _state_kinds: dict[tuple, str]

    def _reset_maps(self) -> None:
        self._brain_open = None  # the brain state currently in flight
        self._run_nodes = {}  # (tag, depth) -> run node
        self._state_nodes = {}  # (tag, depth, state) -> state node
        self._state_kinds = {}

    def new_turn(self, title: str) -> None:
        """One turn on display at a time — history lives in the transcript."""
        self.clear()
        self._reset_maps()
        self._turn_node = self.root.add(log_render.tree_turn(title), expand=True)

    def _parent_for(self, e: dict) -> "TreeNode | None":
        tag = e.get("run")
        depth = e.get("depth", 0)
        if tag is None:  # brain event
            return self._turn_node
        if depth == 0:
            return self._brain_open or self._turn_node
        return self._state_nodes.get((tag, depth - 1, None)) or self._run_nodes.get(
            (tag, depth - 1)
        )

    @staticmethod
    def _enable_expand(node: "TreeNode | None") -> None:
        """Textual defaults allow_expand=True even for empty leaves — only opt in
        when a node actually gains children (nested run, preview, branch)."""
        if node is not None and not node.allow_expand:
            node.allow_expand = True

    def feed(self, e: dict) -> None:
        if self._turn_node is None:
            self.new_turn("turn")
        tag = e.get("run")
        depth = e.get("depth", 0)
        kind = e["type"]
        node: TreeNode | None
        if kind == "run-start":
            parent = self._parent_for(e)
            if parent is None:
                return
            self._enable_expand(parent)
            node = parent.add(
                log_render.tree_run(e.get("machine", "")),
                expand=True,
                allow_expand=True,
            )
            self._run_nodes[(tag, depth)] = node
        elif kind == "state-start":
            parent = self._run_nodes.get((tag, depth)) or self._turn_node
            if parent is None:  # cannot happen: the top of feed sets the turn node
                return
            # Leaves until something nests under them (commissioned run / preview).
            node = parent.add(
                log_render.tree_state_start(
                    e.get("state", ""), e.get("kind", ""), e.get("tier", "")
                ),
                expand=False,
                allow_expand=False,
            )
            self._state_nodes[(tag, depth, e["state"])] = node
            self._state_nodes[(tag, depth, None)] = node  # the in-flight state
            self._state_kinds[(tag, depth, e["state"])] = e.get("kind", "")
            if tag is None:
                self._brain_open = node
        elif kind == "state-done":
            node = self._state_nodes.get((tag, depth, e["state"]))
            if node is not None:
                node.set_label(
                    log_render.tree_state_done(e.get("state", ""), e.get("policy"), e.get("to"))
                )
                # Expandable only when there is something to show: nested run
                # children already present, and/or an output preview leaf.
                # Keep the default tree scannable. Full outputs live in Context;
                # previews are reserved for exceptional/truncated states.
                preview = (
                    e.get("output")
                    if e.get("truncated")
                    or e.get("policy")
                    in (
                        "fail",
                        "call-failed",
                        "no-gate-matched",
                        "judge-unparseable",
                    )
                    else None
                )
                if preview:
                    self._enable_expand(node)
                    node.add_leaf(log_render.tree_preview(preview))
                elif node.children:
                    self._enable_expand(node)
        elif kind == "branch-done":
            node = self._state_nodes.get((tag, depth, e["state"]))
            if node is not None:
                self._enable_expand(node)
                node.add_leaf(log_render.tree_branch(e.get("index")))
        elif kind == "run-finished":
            node = self._run_nodes.get((tag, depth))
            if node is not None:
                node.set_label(
                    log_render.tree_run_finished(
                        e.get("machine", ""), e.get("status", ""), e.get("error")
                    )
                )


class Inspector(Vertical):
    """Side panel: the last run's blackboard, its trace, and session facts."""

    def __init__(self):
        super().__init__(id="inspector")

    def compose(self):
        with TabbedContent(initial="tab-session", id="inspector-tabs"):
            with TabPane("Context", id="tab-context"):
                yield RichLog(id="inspector-context", wrap=True, markup=False)
            with TabPane("Trace", id="tab-trace"):
                yield RichLog(id="inspector-trace", wrap=True, markup=False)
            with TabPane("Session", id="tab-session"):
                yield Static("", id="inspector-session")

    def show_empty(self) -> None:
        """Keep the inspector informative before the first run."""
        self.query_one("#inspector-context", RichLog).write(
            Text("No run context yet. Submit a request to inspect the blackboard.", style="dim")
        )
        self.query_one("#inspector-trace", RichLog).write(
            Text("No trace yet. Live state transitions will appear here after a run.", style="dim")
        )

    def show_result(self, res: RunResult) -> None:
        ctx_log = self.query_one("#inspector-context", RichLog)
        ctx_log.clear()
        payload = json.dumps(res.context, ensure_ascii=False, indent=2, default=str)
        ctx_log.write(Syntax(payload, "json", word_wrap=True, background_color="default"))
        trace_log = self.query_one("#inspector-trace", RichLog)
        trace_log.clear()
        table = Table(
            show_header=True,
            header_style="bold cyan",
            expand=True,
            box=None,
            padding=(0, 1),
        )
        table.add_column("#", width=4)
        table.add_column("State")
        table.add_column("Policy")
        table.add_column("To")
        for step in res.trace:
            table.add_row(
                str(step.get("step", "")),
                str(step.get("state", "")),
                str(step.get("policy", "—")),
                str(step.get("to", "—")),
            )
        trace_log.write(table)

    def show_session(
        self, session: "ConsoleSession", spent_in: int, spent_out: int, consented: set
    ) -> None:
        info = Text()
        for label, value in (
            ("SESSION", session.id),
            ("DIRECTORY", session.dir),
            ("WORKSPACE", session.workspace),
            ("TOKENS", f"{spent_in}+{spent_out}"),
            ("CONSENTED TOOLS", ", ".join(sorted(consented)) or "—"),
        ):
            info.append(f"{label}\n", style="bold cyan")
            info.append(f"{value}\n\n")
        self.query_one("#inspector-session", Static).update(info)
