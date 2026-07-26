"""Worker↔UI bridge for the console: emit from any thread; ask/confirm block the worker."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from .session import Session


class _BridgeApp(Protocol):
    """The part of the local Textual app needed by the worker bridge."""

    shutting_down: bool
    session: "Session"

    def call_from_thread(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> Any: ...

    def render_event(self, event: dict) -> object: ...

    def enter_answer_mode(self, question: str) -> object: ...


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
        high_risk = prompt.startswith("[high-risk] ")
        display_prompt = prompt.removeprefix("[high-risk] ")
        if self.always_yes and not high_risk:
            return True
        # Accept common yes tokens (EN/IT). Default is no if the user hits enter.
        reply = (
            self.ask(f"{display_prompt}  → type y / yes / sì / always yes  (Enter = no)")
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
