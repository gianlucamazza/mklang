"""The mklang console TUI (ADR 0015 M1): agent-first, brain-as-machine.

Requires the `mklang[console]` extra (Textual). The engine runs on a worker
thread; `TextualBridge` marshals events into the UI and blocks the worker on
human questions (HITL escalations, tool consent) answered through the main
input line. Nothing here adds semantics: the brain is `agent.mk`, the hands
are `ConsoleTools`, and the run tree is the `on_event` stream.
"""

from __future__ import annotations

import threading
from pathlib import Path

import yaml

from ..engine import run as run_engine
from ..loader import validate_dict
from ..model import Machine, parse_machine
from .tools import ConsoleTools


def load_brain(agent_path: str | None = None) -> Machine:
    """The bundled agent.mk, or a user-supplied brain honoring the tool contract."""
    if agent_path is not None:
        text = Path(agent_path).read_text(encoding="utf-8")
    else:
        from importlib.resources import files

        text = files("mklang").joinpath("data/console/agent.mk").read_text(encoding="utf-8")
    doc = yaml.safe_load(text)
    validate_dict(doc)
    return parse_machine(doc)


def build_app(
    config: str,
    provider: str | None,
    workspace: str,
    agent_path: str | None = None,
    build_llm=None,
):
    """Construct the Textual app (imported lazily so the core stays TUI-free)."""
    from textual.app import App, ComposeResult
    from textual.containers import Vertical
    from textual.widgets import Footer, Input, RichLog, Static

    brain = load_brain(agent_path)

    class TextualBridge:
        """Bridge impl: emit from any thread; ask/confirm block the worker."""

        def __init__(self, app: "ConsoleApp"):
            self.app = app
            self._reply: str | None = None
            self._event = threading.Event()

        def emit(self, event: dict) -> None:
            self.app.call_from_thread(self.app.render_event, event)

        def ask(self, question: str) -> str:
            self._event.clear()
            self.app.call_from_thread(self.app.enter_answer_mode, question)
            self._event.wait()
            return self._reply or ""

        def confirm(self, prompt: str) -> bool:
            return self.ask(f"{prompt} [y/N]").strip().lower() in ("y", "yes", "s", "si", "sì")

        def deliver(self, reply: str) -> None:
            self._reply = reply
            self._event.set()

    class ConsoleApp(App):
        TITLE = "mklang console"
        CSS = """
        #log { height: 1fr; }
        #status { height: 1; color: $text-muted; }
        """
        BINDINGS = [("ctrl+c", "quit", "Quit")]

        def __init__(self):
            super().__init__()
            self.bridge = TextualBridge(self)
            self.tools = ConsoleTools(
                config=config,
                provider=provider,
                bridge=self.bridge,
                workspace=Path(workspace),
                build_llm=build_llm,
            )
            self.history = ""
            self.spent_in = 0
            self.spent_out = 0
            self.answer_mode = False

        def compose(self) -> ComposeResult:
            yield Vertical(
                RichLog(id="log", wrap=True, markup=True),
                Static("", id="status"),
                Input(placeholder="what should happen? (ctrl+c quits)", id="prompt"),
                Footer(),
            )

        def on_mount(self) -> None:
            self.log_line(
                f"[b]mklang console[/b] · brain={brain.name} · "
                f"provider={self.tools.prov.name} · workspace={self.tools.workspace}"
            )
            self.update_status()
            self.query_one("#prompt", Input).focus()

        # -- rendering -----------------------------------------------------

        def log_line(self, text: str) -> None:
            self.query_one("#log", RichLog).write(text)

        def update_status(self) -> None:
            self.query_one("#status", Static).update(
                f"session tokens: {self.spent_in}+{self.spent_out} · provider {self.tools.prov.name}"
            )

        def render_event(self, e: dict) -> None:
            pad = "  " * (e.get("depth", 0) + 1)
            run_tag = f"[dim]{e.get('run', e.get('machine', ''))}[/dim]"
            if e["type"] == "run-start":
                self.log_line(f"{pad}▶ {run_tag} run {e['machine']} (entry {e['entry']})")
            elif e["type"] == "state-start":
                self.log_line(f"{pad}◐ {run_tag} {e['state']} [{e['kind']}·{e['tier']}]…")
            elif e["type"] == "state-done":
                tokens = e.get("tokens") or {}
                self.spent_in += tokens.get("input_tokens", 0)
                self.spent_out += tokens.get("output_tokens", 0)
                arrow = f"→ {e.get('to')}" if e.get("to") else f"({e.get('policy')})"
                self.log_line(f"{pad}● {run_tag} {e['state']} [{e.get('policy')}] {arrow}")
                self.update_status()
            elif e["type"] == "branch-done":
                self.log_line(f"{pad}· {run_tag} branch {e.get('index')} done")

        # -- human input ----------------------------------------------------

        def enter_answer_mode(self, question: str) -> None:
            self.answer_mode = True
            self.log_line(f"[yellow]⏸ {question}[/yellow]")
            box = self.query_one("#prompt", Input)
            box.placeholder = "your answer…"
            box.disabled = False
            box.focus()

        def on_input_submitted(self, event) -> None:
            text = event.value.strip()
            box = self.query_one("#prompt", Input)
            box.value = ""
            if self.answer_mode:
                self.answer_mode = False
                box.placeholder = "what should happen? (ctrl+c quits)"
                self.log_line(f"[yellow]you:[/yellow] {text}")
                box.disabled = True
                self.bridge.deliver(text)
                return
            if not text:
                return
            self.log_line(f"[b cyan]you:[/b cyan] {text}")
            box.disabled = True
            self.run_worker(lambda: self.turn(text), thread=True, exclusive=True)

        # -- the agent turn (worker thread) ----------------------------------

        def turn(self, user_message: str) -> None:
            ctx = {
                **brain.context,
                "user_message": user_message,
                "history": self.history,
                "observation": [],
            }
            res = run_engine(
                brain,
                ctx,
                {brain.name: brain},
                self.tools.llm,
                self.tools.prov.tiers,
                self.tools.prov.judge_override(),
                tier_params=self.tools.prov.params,
                tools=self.tools.as_tool_registry(),
                on_event=self.bridge.emit,
            )
            self.call_from_thread(self.finish_turn, user_message, res)

        def finish_turn(self, user_message: str, res) -> None:
            if res.status == "done":
                self.log_line(f"[b green]agent:[/b green] {res.result}")
                self.history += f"\nuser: {user_message}\nagent: {res.result}"
            else:
                self.log_line(f"[b red]agent {res.status}:[/b red] {res.error} (at {res.at})")
            box = self.query_one("#prompt", Input)
            box.disabled = False
            box.focus()

    return ConsoleApp()


def main(config: str, provider: str | None, workspace: str, agent_path: str | None) -> int:
    app = build_app(config, provider, workspace, agent_path)
    app.run()
    return 0
