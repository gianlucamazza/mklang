"""Console widgets (ADR 0015 M3a): the live activity tree and the inspector.

Both are fed from the main thread (the bridge marshals engine events with
call_from_thread), so no locking is needed here.
"""

from __future__ import annotations

import json

from textual.widgets import RichLog, Static, TabbedContent, TabPane, Tree


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

    def _reset_maps(self) -> None:
        self._brain_open = None  # the brain state currently in flight
        self._run_nodes = {}  # (tag, depth) -> run node
        self._state_nodes = {}  # (tag, depth, state) -> state node

    def new_turn(self, title: str) -> None:
        """One turn on display at a time — history lives in the transcript."""
        self.clear()
        self._reset_maps()
        self._turn_node = self.root.add(f"[b]{title}[/b]", expand=True)

    def _parent_for(self, e: dict):
        tag = e.get("run")
        depth = e.get("depth", 0)
        if tag is None:  # brain event
            return self._turn_node
        if depth == 0:
            return self._brain_open or self._turn_node
        return self._state_nodes.get((tag, depth - 1, None)) or self._run_nodes.get(
            (tag, depth - 1)
        )

    def feed(self, e: dict) -> None:
        if self._turn_node is None:
            self.new_turn("turn")
        tag = e.get("run")
        depth = e.get("depth", 0)
        kind = e["type"]
        if kind == "run-start":
            parent = self._parent_for(e)
            if parent is None:
                return
            node = parent.add(f"▶ [b]{e['machine']}[/b]", expand=True)
            self._run_nodes[(tag, depth)] = node
        elif kind == "state-start":
            parent = self._run_nodes.get((tag, depth)) or self._turn_node
            node = parent.add(f"◐ {e['state']} [dim]{e['kind']}·{e['tier']}[/dim]")
            self._state_nodes[(tag, depth, e["state"])] = node
            self._state_nodes[(tag, depth, None)] = node  # the in-flight state
            if tag is None:
                self._brain_open = node
        elif kind == "state-done":
            node = self._state_nodes.get((tag, depth, e["state"]))
            if node is not None:
                arrow = f"→ {e['to']}" if e.get("to") else f"({e.get('policy')})"
                node.set_label(f"● {e['state']} [dim]{e.get('policy')}[/dim] {arrow}")
        elif kind == "branch-done":
            node = self._state_nodes.get((tag, depth, e["state"]))
            if node is not None:
                node.add_leaf(f"· branch {e.get('index')}")


class Inspector(TabbedContent):
    """Side panel: the last run's blackboard, its trace, and session facts."""

    def __init__(self):
        super().__init__(id="inspector")

    def compose(self):
        with TabPane("Context", id="tab-context"):
            yield RichLog(id="inspector-context", wrap=True, markup=False)
        with TabPane("Trace", id="tab-trace"):
            yield RichLog(id="inspector-trace", wrap=True, markup=False)
        with TabPane("Session", id="tab-session"):
            yield Static("", id="inspector-session")

    def show_result(self, res) -> None:
        ctx_log = self.query_one("#inspector-context", RichLog)
        ctx_log.clear()
        ctx_log.write(json.dumps(res.context, ensure_ascii=False, indent=2, default=str))
        trace_log = self.query_one("#inspector-trace", RichLog)
        trace_log.clear()
        for step in res.trace:
            trace_log.write(
                f"{step.get('step')}. {step['state']} [{step.get('policy')}] "
                f"gate={step.get('gate')!r} -> {step.get('to')}"
            )

    def show_session(self, session, spent_in: int, spent_out: int, consented) -> None:
        self.query_one("#inspector-session", Static).update(
            f"session: {session.id}\n"
            f"dir: {session.dir}\n"
            f"workspace: {session.workspace}\n"
            f"tokens: {spent_in}+{spent_out}\n"
            f"consented tools: {', '.join(sorted(consented)) or '—'}"
        )
