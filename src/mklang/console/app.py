"""The mklang console TUI (ADR 0015 M1): agent-first, brain-as-machine.

Requires the `mklang[console]` extra (Textual). The engine runs on a worker
thread; `TextualBridge` marshals events into the UI and blocks the worker on
human questions (HITL escalations, tool consent) answered through the main
input line. Nothing here adds semantics: the brain is `agent.mk`, the hands
are `ConsoleTools`, and the run tree is the `on_event` stream.
"""

from __future__ import annotations

import threading
from dataclasses import replace as dc_replace
from datetime import datetime
from pathlib import Path

import yaml

from ..checkpoint import save_checkpoint
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
    session_base: str | None = None,
    continue_session: bool = False,
    session_id: str | None = None,
):
    """Construct the Textual app (imported lazily so the core stays TUI-free)."""
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical
    from textual.widgets import Footer, Header, Input, RichLog, Static

    from .session import DEFAULT_BASE, Session
    from .widgets import ActivityTree, Inspector

    brain = load_brain(agent_path)
    base = Path(session_base) if session_base else DEFAULT_BASE

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
            # Accept common yes tokens (EN/IT). Default is no if the user hits enter.
            return self.ask(f"{prompt}  → type y / yes / sì  (Enter = no)").strip().lower() in (
                "y",
                "yes",
                "s",
                "si",
                "sì",
            )

        def deliver(self, reply: str) -> None:
            self._reply = reply
            self._event.set()

    class ConsoleApp(App):
        TITLE = "mklang console"
        CSS = """
        #body { height: 1fr; }
        #main { width: 2fr; }
        #log { height: 2fr; }
        #activity { height: 1fr; border-top: solid $panel; }
        #status { height: 1; color: $text-muted; }
        #inspector { width: 1fr; display: none; border-left: solid $panel; }
        """
        BINDINGS = [
            ("ctrl+c", "quit", "Quit"),
            ("f2", "toggle_inspector", "Inspector"),
            ("ctrl+l", "clear_log", "Clear"),
        ]

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
            if session_id:
                self.session = Session.load(base / session_id)
            elif continue_session:
                self.session = Session.latest(base) or Session.create(
                    base, workspace=str(self.tools.workspace), brain=brain.name
                )
            else:
                self.session = Session.create(
                    base, workspace=str(self.tools.workspace), brain=brain.name
                )
            self.history = self.session.history
            self.spent_in = self.session.spent_in
            self.spent_out = self.session.spent_out
            self.tools._consented.update(self.session.consented)
            self.answer_mode = False
            self.log_history: list[str] = []  # plain mirror of the log, for tests

        def compose(self) -> ComposeResult:
            yield Header()
            with Horizontal(id="body"):
                with Vertical(id="main"):
                    yield RichLog(id="log", wrap=True, markup=True)
                    yield ActivityTree()
                    yield Static("", id="status")
                    yield Input(placeholder="what should happen? (ctrl+c quits)", id="prompt")
                yield Inspector()
            yield Footer()

        def action_toggle_inspector(self) -> None:
            panel = self.query_one(Inspector)
            panel.display = not panel.display

        def action_clear_log(self) -> None:
            self.query_one("#log", RichLog).clear()

        def on_mount(self) -> None:
            self.log_line(
                f"[b]mklang console[/b] · brain={brain.name} · "
                f"provider={self.tools.prov.name} · workspace={self.tools.workspace} · "
                f"session={self.session.id}"
            )
            if self.history:
                self.log_line(
                    f"[dim]resumed session with {len(self.history)} chars of history[/dim]"
                )
            self.update_status()
            self.query_one("#prompt", Input).focus()

        # -- rendering -----------------------------------------------------

        def log_line(self, text: str) -> None:
            self.query_one("#log", RichLog).write(text)
            self.log_history.append(text)

        def update_status(self) -> None:
            self.query_one("#status", Static).update(
                f"session tokens: {self.spent_in}+{self.spent_out} · "
                f"provider {self.tools.prov.name} · {self.session.id}"
            )

        def render_event(self, e: dict) -> None:
            self.session.append({"t": "event", **e})
            if e["type"] == "state-done":
                tokens = e.get("tokens") or {}
                self.spent_in += tokens.get("input_tokens", 0)
                self.spent_out += tokens.get("output_tokens", 0)
                self.update_status()
            self.query_one(ActivityTree).feed(e)

        # -- human input ----------------------------------------------------

        def enter_answer_mode(self, question: str) -> None:
            self.answer_mode = True
            self.log_line(f"[yellow]⏸ {question}[/yellow]")
            box = self.query_one("#prompt", Input)
            # Consent prompts include "type y"; keep a short generic placeholder.
            box.placeholder = "answer here, then Enter…"
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
            if text.startswith("/"):
                self.handle_slash(text)
                return
            self.log_line(f"[b cyan]you:[/b cyan] {text}")
            self.session.append({"t": "user", "text": text})
            self.query_one(ActivityTree).new_turn(text[:60])
            box.disabled = True
            self.run_worker(lambda: self.turn(text), thread=True, exclusive=True)

        # -- slash commands (operator affordances, bypass the brain) ---------

        def handle_slash(self, text: str) -> None:
            import json as _json

            from ..checkpoint import load_checkpoint
            from ..cli import _coerce

            parts = text.split()
            cmd, args = parts[0].lower(), parts[1:]
            if cmd == "/help":
                self.log_line(
                    "[dim]/machines · /run <name> [k=v…] · /check <name> · /read <name> · "
                    "/budget <n> · /resume [n] · /session · /quit — plain text goes to the "
                    "agent; F2 inspector, ctrl+l clear[/dim]"
                )
            elif cmd == "/machines":
                rows = _json.loads(self.tools.list_machines({}))["machines"]
                for r in rows:
                    self.log_line(
                        f"  [b]{r['name']}[/b] · result={r['result']} · "
                        f"budget={r['budget']} · keys={', '.join(r['context_keys']) or '—'}"
                    )
            elif cmd == "/run" and args:
                target = args[0]
                inputs = {}
                for kv in args[1:]:
                    if "=" in kv:
                        k, v = kv.split("=", 1)
                        inputs[k] = _coerce(v)
                self.log_line(f"[b cyan]/run[/b cyan] {target} {inputs or ''}")
                self.query_one(ActivityTree).new_turn(f"/run {target}")
                self.query_one("#prompt", Input).disabled = True
                self.run_worker(lambda: self.slash_run(target, inputs), thread=True, exclusive=True)
            elif cmd == "/check" and args:
                verdict = _json.loads(self.tools.check_machine({"name": args[0]}))
                self.log_line(_json.dumps(verdict, ensure_ascii=False, indent=2))
            elif cmd == "/read" and args:
                self.log_line(self.tools.read_machine({"name": args[0]}))
            elif cmd == "/budget" and args:
                try:
                    self.tools.default_cost_budget = int(args[0])
                    self.log_line(f"[dim]default cost budget → {args[0]} tokens[/dim]")
                except ValueError:
                    self.log_line("[red]/budget needs an integer[/red]")
            elif cmd == "/session":
                self.log_line(
                    f"[dim]session {self.session.id} · {self.session.dir} · "
                    f"tokens {self.spent_in}+{self.spent_out}[/dim]"
                )
            elif cmd == "/resume":
                cks = sorted(self.session.checkpoints_dir.glob("*.json"))
                if not args:
                    if not cks:
                        self.log_line("[dim]no parked checkpoints in this session[/dim]")
                    for i, ck in enumerate(cks):
                        self.log_line(f"  [{i}] {ck.name}")
                    return
                try:
                    ck = load_checkpoint(cks[int(args[0])])
                except (IndexError, ValueError, OSError) as e:
                    self.log_line(f"[red]cannot resume: {e}[/red]")
                    return
                self.log_line(f"[b cyan]/resume[/b cyan] {cks[int(args[0])].name}")
                self.query_one(ActivityTree).new_turn("/resume")
                self.query_one("#prompt", Input).disabled = True
                self.run_worker(lambda: self.slash_resume(ck), thread=True, exclusive=True)
            elif cmd == "/quit":
                self.exit()
            else:
                self.log_line(f"[red]unknown command {cmd} — try /help[/red]")

        def slash_run(self, target: str, inputs: dict) -> None:
            import json as _json

            obs = self.tools.run_machine({"target": target, "inputs": _json.dumps(inputs)})
            self.call_from_thread(self.finish_slash, obs)

        def slash_resume(self, ck: dict) -> None:
            steps = ck["frames"][0].get("steps", 0)
            machine = dc_replace(brain, budget=steps + 8)
            res = self._run_brain(machine, dict(machine.context), resume=ck["frames"])
            self.call_from_thread(self.finish_turn, "(resumed turn)", res)

        def finish_slash(self, observation: str) -> None:
            self.log_line(f"[b green]result:[/b green] {observation}")
            self.session.append({"t": "slash-result", "text": observation})
            self.session.save_state()
            box = self.query_one("#prompt", Input)
            box.disabled = False
            box.focus()

        # -- the agent turn (worker thread) ----------------------------------

        def _run_brain(self, machine, ctx, resume=None):
            return run_engine(
                machine,
                ctx,
                {machine.name: machine},
                self.tools.llm,
                self.tools.prov.tiers,
                self.tools.prov.judge_override(),
                tier_params=self.tools.prov.params,
                tools=self.tools.as_tool_registry(),
                suspendable=True,
                resume=resume,
                on_event=self.bridge.emit,
            )

        def turn(self, user_message: str) -> None:
            # Full history stays on the session for audit; only a windowed view
            # is injected into the brain (ADR 0017 console history budget).
            from .session import history_for_brain

            ctx = {
                **brain.context,
                "user_message": user_message,
                "history": history_for_brain(self.history),
                "observation": [],
            }
            machine = brain
            res = self._run_brain(machine, ctx)
            # Budget exhaustion is a UI moment: extend and resume, or park a
            # checkpoint in the session for a later /resume (ADR 0015).
            while res.status == "suspended" and res.error == "budget-exhausted":
                if not self.bridge.confirm(
                    f"turn budget exhausted ({machine.budget} steps) — continue with +8?"
                ):
                    ck = self.session.checkpoints_dir / f"turn-{datetime.now():%H%M%S}.json"
                    save_checkpoint(
                        ck, machine.name, "<console-brain>", res.error, res.frames, None
                    )
                    break
                machine = dc_replace(machine, budget=machine.budget + 8)
                res = self._run_brain(machine, dict(machine.context), resume=res.frames)
            self.call_from_thread(self.finish_turn, user_message, res)

        def finish_turn(self, user_message: str, res) -> None:
            if res.status == "done":
                self.log_line(f"[b green]agent:[/b green] {res.result}")
                self.history += f"\nuser: {user_message}\nagent: {res.result}"
            else:
                self.log_line(f"[b red]agent {res.status}:[/b red] {res.error} (at {res.at})")
            self.session.append(
                {"t": "agent", "status": res.status, "text": str(res.result or res.error)}
            )
            panel = self.query_one(Inspector)
            panel.show_result(res)
            panel.show_session(self.session, self.spent_in, self.spent_out, self.tools._consented)
            self.session.history = self.history
            self.session.spent_in = self.spent_in
            self.session.spent_out = self.spent_out
            self.session.consented = sorted(self.tools._consented)
            self.session.save_state()
            box = self.query_one("#prompt", Input)
            box.disabled = False
            box.focus()

    return ConsoleApp()


def main(
    config: str,
    provider: str | None,
    workspace: str,
    agent_path: str | None,
    continue_session: bool = False,
    session_id: str | None = None,
) -> int:
    app = build_app(
        config,
        provider,
        workspace,
        agent_path,
        continue_session=continue_session,
        session_id=session_id,
    )
    app.run()
    return 0
