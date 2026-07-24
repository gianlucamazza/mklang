"""The mklang console TUI (ADR 0015 M1): agent-first, brain-as-machine.

Textual TUI, bundled by default since 0.15.0. The engine runs on a worker
thread; `TextualBridge` marshals events into the UI and blocks the worker on
human questions (HITL escalations, tool consent) answered through the main
input line. Nothing here adds semantics: the brain is `agent.mkl`, the hands
are `ConsoleTools`, and the run tree is the `on_event` stream.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import replace as dc_replace
from typing import TYPE_CHECKING, Any, Protocol
from datetime import datetime
from pathlib import Path

import yaml

from ..checkpoint import save_checkpoint
from ..engine import RunResult
from ..engine import run as run_engine
from ..hooks import load_hook_registry
from ..loader import validate_dict
from ..model import Machine, parse_machine
from . import render as log_render
from .tools import ConsoleTools
from .workspace import requires_workspace_inspection

if TYPE_CHECKING:
    from textual.app import App

    from .session import Session
    from ..llm.base import LLM


class _BridgeApp(Protocol):
    """The part of the local Textual app needed by the worker bridge."""

    shutting_down: bool
    session: "Session"

    def call_from_thread(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> Any: ...

    def render_event(self, event: dict) -> object: ...

    def enter_answer_mode(self, question: str) -> object: ...


def load_brain(agent_path: str | None = None) -> Machine:
    """The bundled agent.mkl, or a user-supplied brain honoring the tool contract."""
    if agent_path is not None:
        text = Path(agent_path).read_text(encoding="utf-8")
    else:
        from importlib.resources import files

        text = files("mklang").joinpath("data/console/agent.mkl").read_text(encoding="utf-8")
    doc = yaml.safe_load(text)
    validate_dict(doc)
    return parse_machine(doc)


def build_app(
    config: str,
    provider: str | None,
    workspace: str,
    agent_path: str | None = None,
    build_llm: "Callable[[object], LLM] | None" = None,
    session_base: str | None = None,
    continue_session: bool = False,
    session_id: str | None = None,
) -> "App":
    """Construct the Textual app (imported lazily so the core stays TUI-free)."""
    from rich.console import RenderableType
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical
    from textual.suggester import SuggestFromList
    from textual.widgets import Footer, Header, Input, RichLog, Static

    from .session import Session, default_base
    from .widgets import ActivityTree, Inspector

    brain = load_brain(agent_path)
    base = Path(session_base) if session_base else default_base()

    class TextualBridge:
        """Bridge impl: emit from any thread; ask/confirm block the worker."""

        app: _BridgeApp
        _reply: str | None
        always_yes: bool

        def __init__(self, app: _BridgeApp):
            self.app = app
            self._reply = None
            self._event = threading.Event()
            self.always_yes = False

        def emit(self, event: dict) -> None:
            if self.app.shutting_down:
                return
            self.app.call_from_thread(self.app.render_event, event)

        def ask(self, question: str) -> str:
            if self.app.shutting_down:
                return ""
            self._event.clear()
            # Re-check through a local: shutdown can flip from another thread,
            # which per-expression narrowing cannot see.
            app = self.app
            if app.shutting_down:
                return ""
            self.app.call_from_thread(self.app.enter_answer_mode, question)
            self._event.wait()
            return self._reply or ""

        def confirm(self, prompt: str) -> bool:
            if self.always_yes:
                return True
            # Accept common yes tokens (EN/IT). Default is no if the user hits enter.
            reply = (
                self.ask(f"{prompt}  → type y / yes / sì / always yes  (Enter = no)")
                .strip()
                .lower()
            )
            if reply in ("always yes", "always_yes", "always-yes", "sempre sì", "sempre si"):
                self.always_yes = True
                self.app.session.always_yes = True
                self.app.session.save_state()
                return True
            return reply in (
                "y",
                "yes",
                "s",
                "si",
                "sì",
            )

        def deliver(self, reply: str) -> None:
            self._reply = reply
            self._event.set()

        def cancel(self) -> None:
            """Release a worker blocked on a human answer during shutdown."""
            self._reply = None
            self._event.set()

    class ConsoleApp(App):
        TITLE = "mklang console"
        CSS = """
        Screen { layout: vertical; }
        #body { height: 1fr; }
        #main { width: 2fr; }
        #log { height: 1fr; padding: 0 1; scrollbar-gutter: stable; }
        #activity { height: 11; border-top: solid $panel; padding: 0 1; }
        #activity.hidden { display: none; }
        #status { height: 1; padding: 0 1; color: $text-muted; background: $boost; }
        #prompt { height: 3; border-top: solid $primary; }
        #inspector { width: 40%; border-left: solid $panel; }
        """
        BINDINGS = [
            ("ctrl+c", "quit", "Quit"),
            ("f2", "toggle_inspector", "Inspector"),
            ("ctrl+t", "toggle_activity", "Activity"),
            ("ctrl+g", "cancel_run", "Stop"),
            ("ctrl+l", "clear_log", "Clear"),
        ]

        def __init__(self):
            super().__init__()
            self.bridge = TextualBridge(self)
            self.cancel_event = threading.Event()
            self.tools = ConsoleTools(
                config=config,
                provider=provider,
                bridge=self.bridge,
                workspace=Path(workspace),
                build_llm=build_llm,
                cancel_requested=self.cancel_event.is_set,
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
            self.bridge.always_yes = self.session.always_yes
            self.answer_mode = False
            self.running = False
            self.shutting_down = False
            self._worker_done = threading.Event()
            self._worker_done.set()
            self.activity_visible = True
            self.inspector_visible = False
            self.log_history: list[str] = []  # plain mirror of the log, for tests

        def compose(self) -> ComposeResult:
            yield Header(show_clock=False)
            yield Static("", id="status")
            with Horizontal(id="body"):
                with Vertical(id="main"):
                    # markup=False: untrusted content never rides Rich tags via write(str).
                    # Chrome uses Text.from_markup / Markdown renderables instead.
                    yield RichLog(id="log", wrap=True, markup=False)
                    yield ActivityTree()
                    from .commands import COMMANDS

                    yield Input(
                        placeholder="Ask the agent or type / for commands",
                        id="prompt",
                        suggester=SuggestFromList(
                            [f"/{command.name}" for command in COMMANDS], case_sensitive=False
                        ),
                    )
                yield Inspector()
            yield Footer()

        def action_toggle_inspector(self) -> None:
            self.inspector_visible = not self.inspector_visible
            self.apply_responsive_layout()

        def action_toggle_activity(self) -> None:
            self.activity_visible = not self.activity_visible
            self.query_one(ActivityTree).set_class(not self.activity_visible, "hidden")

        def action_cancel_run(self) -> None:
            if not self.running or self.answer_mode:
                return
            self.cancel_event.set()
            self.log_chrome(
                "[yellow]Stop requested — waiting for the current state to finish…[/yellow]"
            )
            self.update_status("stopping")

        async def action_quit(self) -> None:
            """Stop the active run cleanly before Textual tears down its event loop."""
            self._begin_shutdown()
            await self._wait_for_worker()
            self.exit()

        async def on_unmount(self) -> None:
            """Cover SIGINT and other exits which bypass the ``quit`` action."""
            self._begin_shutdown()
            await self._wait_for_worker()

        def _begin_shutdown(self) -> None:
            if self.shutting_down:
                return
            self.shutting_down = True
            self.cancel_event.set()
            self.bridge.cancel()
            try:
                self.tools.close()
            except Exception:
                # Shutdown must still release the console if a third-party
                # provider implements a broken optional close hook.
                pass

        async def _wait_for_worker(self) -> None:
            import asyncio

            while not self._worker_done.is_set():
                await asyncio.sleep(0.01)

        def _run_thread_worker(self, work: Callable[[], object]) -> None:
            """Start work and track the backing thread, not only Textual's task."""
            self._worker_done.clear()

            def tracked_work():
                try:
                    return work()
                finally:
                    self._worker_done.set()

            self.run_worker(tracked_work, thread=True, exclusive=True)

        def action_clear_log(self) -> None:
            self.query_one("#log", RichLog).clear()
            self.log_history.clear()

        def on_mount(self) -> None:
            self.log_chrome(
                "[b]Ready.[/b] Ask the agent what should happen, or type [cyan]/help[/cyan]."
            )
            if self.history:
                self.log_chrome(
                    f"[dim]resumed session with {len(self.history)} chars of history[/dim]"
                )
            self.update_status("ready")
            self.query_one(Inspector).show_session(
                self.session, self.spent_in, self.spent_out, self.tools._consented
            )
            self.apply_responsive_layout()
            self.query_one("#prompt", Input).focus()

        def on_resize(self, _event: object) -> None:
            self.apply_responsive_layout()

        def apply_responsive_layout(self) -> None:
            body = self.query_one("#body")
            main = self.query_one("#main")
            panel = self.query_one(Inspector)
            body.remove_class("inspector-wide", "inspector-narrow")
            if not self.inspector_visible:
                main.display = True
                panel.display = True
                panel.styles.visibility = "hidden"
                panel.styles.width = 0
            elif self.size.width >= 100:
                body.add_class("inspector-wide")
                main.display = True
                panel.display = True
                panel.styles.visibility = "visible"
                panel.styles.width = "40%"
                panel.styles.min_width = 32
                panel.styles.max_width = 46
            else:
                body.add_class("inspector-narrow")
                main.display = False
                panel.display = True
                panel.styles.visibility = "visible"
                panel.styles.width = "100%"
                panel.styles.min_width = 0
                panel.styles.max_width = None

        # -- rendering -----------------------------------------------------

        def log_write(self, renderable: RenderableType, mirror: str) -> None:
            """Write a Rich renderable and append a plain-text mirror for tests."""
            self.query_one("#log", RichLog).write(renderable)
            self.log_history.append(mirror)

        def log_chrome(self, markup: str) -> None:
            """Internal-only Rich markup (no untrusted interpolation)."""
            self.log_write(log_render.chrome(markup), markup)

        def log_plain(self, body: str, *, label_markup: str, mirror_label: str) -> None:
            """Chrome label + plain untrusted body."""
            self.log_write(
                log_render.labeled_plain(label_markup, body),
                f"{mirror_label} {body}" if body else mirror_label,
            )

        def log_markdown(self, body: str, *, label_markup: str, mirror_label: str) -> None:
            """Chrome label + CommonMark body (agent prose)."""
            self.log_write(
                log_render.labeled_markdown(label_markup, body),
                f"{mirror_label} {body}" if body else mirror_label,
            )

        def log_fenced(
            self,
            body: str,
            *,
            label_markup: str | None = None,
            mirror_label: str = "",
            lang: str = "",
        ) -> None:
            """Fenced code (JSON / machine source); optional chrome label."""
            if label_markup:
                self.log_write(
                    log_render.labeled_fenced(label_markup, body, lang=lang),
                    f"{mirror_label} {body}" if mirror_label else body,
                )
            else:
                self.log_write(log_render.fenced(body, lang=lang), body)

        def update_status(self, state: str | None = None) -> None:
            state = state or ("running" if self.running else "ready")
            self.query_one("#status", Static).update(
                f"{state.upper()} · {self.tools.prov.name} · tokens {self.spent_in}+{self.spent_out} "
                f"· session {self.session.id}"
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
            # Question text is untrusted (brain / tool / HITL); keep it plain.
            self.log_plain(question, label_markup="[yellow]⏸ [/yellow]", mirror_label="⏸")
            box = self.query_one("#prompt", Input)
            # Consent prompts include "type y"; keep a short generic placeholder.
            box.placeholder = "answer here, then Enter…"
            box.disabled = False
            box.focus()

        def on_input_submitted(self, event: Input.Submitted) -> None:
            text = event.value.strip()
            box = self.query_one("#prompt", Input)
            box.value = ""
            if self.answer_mode:
                self.answer_mode = False
                box.placeholder = "Ask the agent or type / for commands"
                self.log_plain(text, label_markup="[yellow]you:[/yellow] ", mirror_label="you:")
                box.disabled = True
                self.bridge.deliver(text)
                return
            if not text:
                return
            if text.startswith("/"):
                self.handle_slash(text)
                return
            self.log_plain(text, label_markup="[b cyan]you:[/b cyan] ", mirror_label="you:")
            self.session.append({"t": "user", "text": text})
            self.query_one(ActivityTree).new_turn(text[:60])
            box.disabled = True
            self.running = True
            self.cancel_event.clear()
            self.update_status("running")
            self._run_thread_worker(lambda: self.turn(text))

        # -- slash commands (operator affordances, bypass the brain) ---------

        def handle_slash(self, text: str) -> None:
            import json as _json

            from ..checkpoint import load_checkpoint
            from ..cli import _coerce

            from .commands import BY_NAME, help_text, parse_command

            try:
                cmd, args = parse_command(text)
            except ValueError as exc:
                self.log_plain(
                    str(exc),
                    label_markup="[red]command error:[/red] ",
                    mirror_label="command error:",
                )
                return
            if cmd == "/help":
                self.log_fenced(help_text())
            elif cmd == "/machines":
                rows = _json.loads(self.tools.list_machines({}))["machines"]
                for r in rows:
                    # Name/keys are host data but still not interpolated into markup tags.
                    keys = ", ".join(r["context_keys"]) or "—"
                    suffix = f" · result={r['result']} · budget={r['budget']} · keys={keys}"
                    self.log_write(
                        log_render.bold_name_line(r["name"], suffix),
                        f"  {r['name']}{suffix}",
                    )
                if not rows:
                    self.log_chrome("[dim]no machines[/dim]")
            elif cmd == "/run" and args:
                target = args[0]
                inputs = {}
                for kv in args[1:]:
                    if "=" in kv:
                        k, v = kv.split("=", 1)
                        inputs[k] = _coerce(v)
                self.log_plain(
                    f"{target} {inputs or ''}".rstrip(),
                    label_markup="[b cyan]/run[/b cyan] ",
                    mirror_label="/run",
                )
                self.query_one(ActivityTree).new_turn(f"/run {target}")
                self.query_one("#prompt", Input).disabled = True
                self.running = True
                self.cancel_event.clear()
                self.update_status("running")
                self._run_thread_worker(lambda: self.slash_run(target, inputs))
            elif cmd == "/check" and args:
                verdict = _json.loads(self.tools.check_machine({"name": args[0]}))
                payload = _json.dumps(verdict, ensure_ascii=False, indent=2)
                self.log_fenced(payload, lang="json")
            elif cmd == "/read" and args:
                source = self.tools.read_machine({"name": args[0]})
                self.log_fenced(source, lang="yaml")
            elif cmd == "/budget" and args:
                try:
                    budget = int(args[0])
                    if budget <= 0:
                        raise ValueError
                    self.tools.default_cost_budget = budget
                    self.log_chrome(f"[dim]default cost budget → {args[0]} tokens[/dim]")
                except ValueError:
                    self.log_chrome("[red]/budget needs an integer[/red]")
            elif cmd == "/session":
                self.log_chrome(
                    f"[dim]session {self.session.id} · {self.session.dir} · "
                    f"tokens {self.spent_in}+{self.spent_out}[/dim]"
                )
            elif cmd == "/resume":
                cks = sorted(self.session.checkpoints_dir.glob("*.json"))
                if not args:
                    if not cks:
                        self.log_chrome("[dim]no parked checkpoints in this session[/dim]")
                    for i, ck in enumerate(cks):
                        self.log_plain(ck.name, label_markup=f"  [[{i}]] ", mirror_label=f"  [{i}]")
                    return
                try:
                    ck_doc = load_checkpoint(cks[int(args[0])])
                except (IndexError, ValueError, OSError) as e:
                    self.log_plain(
                        str(e),
                        label_markup="[red]cannot resume:[/red] ",
                        mirror_label="cannot resume:",
                    )
                    return
                name = cks[int(args[0])].name
                self.log_plain(
                    name, label_markup="[b cyan]/resume[/b cyan] ", mirror_label="/resume"
                )
                self.query_one(ActivityTree).new_turn("/resume")
                self.query_one("#prompt", Input).disabled = True
                self._run_thread_worker(lambda: self.slash_resume(ck_doc))
            elif cmd == "/quit":
                self.exit()
            elif cmd in ("/run", "/check", "/read", "/budget"):
                self.log_plain(
                    f"usage: {BY_NAME[cmd].usage}",
                    label_markup="[red]missing argument:[/red] ",
                    mirror_label="missing argument:",
                )
            else:
                self.log_chrome(f"[red]unknown command {cmd} — try /help[/red]")

        def slash_run(self, target: str, inputs: dict) -> None:
            import json as _json

            obs = self.tools.run_machine({"target": target, "inputs": _json.dumps(inputs)})
            if not self.shutting_down:
                self.call_from_thread(self.finish_slash, obs)

        def slash_resume(self, ck: dict) -> None:
            steps = ck["frames"][0].get("steps", 0)
            machine = dc_replace(brain, budget=steps + 8)
            res = self._run_brain(machine, dict(machine.context), resume=ck["frames"])
            if not self.shutting_down:
                self.call_from_thread(self.finish_turn, "(resumed turn)", res)

        def finish_slash(self, observation: str) -> None:
            if self.shutting_down:
                return
            # Observations are JSON envelopes — fence them, do not full-MD parse.
            self.log_fenced(
                observation,
                label_markup="[b green]result:[/b green]",
                mirror_label="result:",
                lang="json",
            )
            self.session.append({"t": "slash-result", "text": observation})
            self.session.save_state()
            self.running = False
            self.update_status("ready")
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
                hooks=load_hook_registry(),
                suspendable=True,
                resume=resume,
                on_event=self.bridge.emit,
                cancel_requested=self.cancel_event.is_set,
            )

        def turn(self, user_message: str) -> None:
            # Full history stays on the session for audit; only a windowed view
            # is injected into the brain (ADR 0017 console history budget).
            from .session import history_for_brain

            from .. import host as host_mod

            ctx = {
                **brain.context,
                "user_message": user_message,
                "history": history_for_brain(self.history),
                "observation": [],
                "workspace_context": self.tools.workspace_context(),
                "workspace_brief": "",
                "workspace_required": requires_workspace_inspection(user_message),
            }
            host_mod.inject_host_defaults(ctx)  # brain may declare context.today
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
            if not self.shutting_down:
                self.call_from_thread(self.finish_turn, user_message, res)

        def finish_turn(self, user_message: str, res: RunResult) -> None:
            if self.shutting_down:
                return
            if res.status == "done":
                body = str(res.result or "")
                self.log_markdown(
                    body, label_markup="[b green]agent:[/b green]", mirror_label="agent:"
                )
                self.history += f"\nuser: {user_message}\nagent: {res.result}"
            else:
                detail = f"{res.error} (at {res.at})"
                self.log_plain(
                    detail,
                    label_markup=f"[b red]agent {res.status}:[/b red] ",
                    mirror_label=f"agent {res.status}:",
                )
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
            self.running = False
            self.update_status("ready")
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
