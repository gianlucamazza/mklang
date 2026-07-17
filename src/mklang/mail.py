"""Mail / reply-delivery backends for the `send_reply` host tool (ADR 0020).

Default is an honest **stub**: records intent, does **not** claim real delivery
(``sent: false``, ``delivery: "stub"``). Fake backend records in-memory and
reports ``delivery: "fake"`` with ``sent: true`` for demo paths. Production
hosts replace the tool via entry points (SMTP, ticket API, …).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Protocol

from .tool_obs import tool_obs


def _preview(body: str, limit: int = 120) -> str:
    return body if len(body) <= limit else body[: limit - 3] + "..."


@dataclass
class OutboundMessage:
    to: str
    body: str
    chars: int
    preview: str


class MailBackend(Protocol):
    def send(self, *, to: str, body: str) -> dict:
        """Return delivery fields: sent, recorded, delivery, and optional error."""
        ...


class StubMailBackend:
    """Default: record intent only — never claim real send."""

    def send(self, *, to: str, body: str) -> dict:
        return {
            "sent": False,
            "recorded": True,
            "delivery": "stub",
            "error": None,
            "note": "Stub only — no message left the host. Bind a real mail/ticket tool for production.",
        }


@dataclass
class FakeMailBackend:
    """In-memory recorder for tests/demos. delivery=fake, sent=true, still stub."""

    outbox: list[OutboundMessage] = field(default_factory=list)

    def send(self, *, to: str, body: str) -> dict:
        preview = _preview(body)
        self.outbox.append(OutboundMessage(to=to, body=body, chars=len(body), preview=preview))
        return {
            "sent": True,
            "recorded": True,
            "delivery": "fake",
            "error": None,
            "note": "Fake mail backend — message kept in process memory only.",
        }


_backend: MailBackend | None = None


def configure_mail(backend: MailBackend | None) -> None:
    """Bind (or clear) the process-wide mail backend used by :func:`send_reply`."""
    global _backend
    _backend = backend


def current_mail_backend() -> MailBackend | None:
    return _backend


def _backend_from_env() -> MailBackend:
    name = (os.environ.get("MKLANG_MAIL_BACKEND") or "").strip().lower()
    if name == "fake":
        return FakeMailBackend()
    return StubMailBackend()


def send_reply(inp: dict) -> str:
    """Host tool: structured reply delivery (stub/fake by default)."""
    body = str(inp.get("body") or inp.get("draft") or "").strip()
    to = str(inp.get("to") or "customer").strip()
    if not body:
        return tool_obs(
            "send_reply",
            stub=True,
            error="empty body",
            to=to,
            body="",
            chars=0,
            preview="",
            sent=False,
            recorded=False,
            delivery="stub",
        )

    backend = _backend if _backend is not None else _backend_from_env()
    preview = _preview(body)
    try:
        meta = backend.send(to=to, body=body)
        if not isinstance(meta, dict):
            return tool_obs(
                "send_reply",
                stub=True,
                error="backend returned non-dict result",
                to=to,
                chars=len(body),
                preview=preview,
                sent=False,
                recorded=False,
                delivery="stub",
            )
        delivery = str(meta.get("delivery") or "stub")
        # Only a non-stub live backend would set stub=False; reference has none.
        is_stub = delivery in ("stub", "fake")
        return tool_obs(
            "send_reply",
            stub=is_stub,
            error=meta.get("error"),
            to=to,
            chars=len(body),
            preview=preview,
            sent=bool(meta.get("sent")),
            recorded=bool(meta.get("recorded", True)),
            delivery=delivery,
            note=meta.get("note"),
        )
    except Exception as e:  # never crash the machine on a tool boundary
        return tool_obs(
            "send_reply",
            stub=True,
            error=f"send failed: {e}",
            to=to,
            chars=len(body),
            preview=preview,
            sent=False,
            recorded=False,
            delivery="stub",
        )
