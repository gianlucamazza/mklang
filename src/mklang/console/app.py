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
from . import render as log_render
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
    from rich.console import RenderableType
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
                    # markup=False: untrusted content never rides Rich tags via write(str).
                    # Chrome uses Text.from_markup / Markdown renderables instead.
                    yield RichLog(id="log", wrap=True, markup=False)
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
            self.log_history.clear()

        def on_mount(self) -> None:
            # Banner values are host-local (brain name, provider, paths, session id).
            self.log_chrome(
                f"[b]mklang console[/b] · brain={brain.name} · "
                f"provider={self.tools.prov.name} · workspace={self.tools.workspace} · "
                f"session={self.session.id}"
            )
            if self.history:
                self.log_chrome(
                    f"[dim]resumed session with {len(self.history)} chars of history[/dim]"
                )
            self.update_status()
            self.query_one("#prompt", Input).focus()

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
            self, body: str, *, label_markup: str | None = None, mirror_label: str = "", lang: str = ""
        ) -> None:
            """Fenced code (JSON / machine source); optional chrome label."""
            if label_markup:
                self.log_write(
                    log_render.labeled_fenced(label_markup, body, lang=lang),
                    f"{mirror_label} {body}" if mirror_label else body,
                )
            else:
                self.log_write(log_render.fenced(body, lang=lang), body)

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
            # Question text is untrusted (brain / tool / HITL); keep it plain.
            self.log_plain(question, label_markup="[yellow]⏸ [/yellow]", mirror_label="⏸")
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
            self.run_worker(lambda: self.turn(text), thread=True, exclusive=True)

        # -- slash commands (operator affordances, bypass the brain) ---------

        def handle_slash(self, text: str) -> None:
            import json as _json

            from ..checkpoint import load_checkpoint
            from ..cli import _coerce

            parts = text.split()
            cmd, args = parts[0].lower(), parts[1:]
            if cmd == "/help":
                help_text = (
                    "/machines · /run <name> [k=v…] · /check <name> · /read <name> · "
                    "/budget <n> · /resume [n] · /session · /quit — plain text goes to the "
                    "agent; F2 inspector, ctrl+l clear"
                )
                self.log_chrome(f"[dim]{help_text}[/dim]")
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
                self.run_worker(lambda: self.slash_run(target, inputs), thread=True, exclusive=True)
            elif cmd == "/check" and args:
                verdict = _json.loads(self.tools.check_machine({"name": args[0]}))
                payload = _json.dumps(verdict, ensure_ascii=False, indent=2)
                self.log_fenced(payload, lang="json")
            elif cmd == "/read" and args:
                source = self.tools.read_machine({"name": args[0]})
                self.log_fenced(source, lang="yaml")
            elif cmd == "/budget" and args:
                try:
                    self.tools.default_cost_budget = int(args[0])
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
                        self.log_plain(
                            ck.name, label_markup=f"  [[{i}]] ", mirror_label=f"  [{i}]"
                        )
                    return
                try:
                    ck = load_checkpoint(cks[int(args[0])])
                except (IndexError, ValueError, OSError) as e:
                    self.log_plain(str(e), label_markup="[red]cannot resume:[/red] ", mirror_label="cannot resume:")
                    return
                name = cks[int(args[0])].name
                self.log_plain(name, label_markup="[b cyan]/resume[/b cyan] ", mirror_label="/resume")
                self.query_one(ActivityTree).new_turn("/resume")
                self.query_one("#prompt", Input).disabled = True
                self.run_worker(lambda: self.slash_resume(ck), thread=True, exclusive=True)
            elif cmd == "/quit":
                self.exit()
            else:
                self.log_chrome(f"[red]unknown command {cmd} — try /help[/red]")

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
            # Observations are JSON envelopes — fence them, do not full-MD parse.
            self.log_fenced(
                observation,
                label_markup="[b green]result:[/b green]",
                mirror_label="result:",
                lang="json",
            )
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

            from .. import host as host_mod

            ctx = {
                **brain.context,
                "user_message": user_message,
                "history": history_for_brain(self.history),
                "observation": [],
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
            self.call_from_thread(self.finish_turn, user_message, res)

        def finish_turn(self, user_message: str, res) -> None:
            if res.status == "done":
                body = str(res.result or "")
                self.log_markdown(body, label_markup="[b green]agent:[/b green]", mirror_label="agent:")
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
