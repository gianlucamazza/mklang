"""Process-scoped store for suspended runs, keyed by opaque handles (ADR 0011).

Frames never touch the disk: the full blackboard stays in memory, and provider
objects are held live so a resume rebuilds nothing.
"""

from __future__ import annotations

import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass

from ..config import ProviderConfig
from ..llm.base import LLM
from ..model import Machine

MAX_ENTRIES = 64


@dataclass
class Session:
    machine: Machine
    registry: dict[str, Machine]
    llm: LLM
    prov: ProviderConfig
    tools: dict
    hooks: dict
    frames: list[dict]
    cost_budget: int | None
    hitl: bool
    reason: str | None
    # Where the machine came from, for durable (file) checkpoints: a filesystem
    # path / bundled name, or the inline source text. At most one is set.
    origin_path: str | None = None
    origin_source: str | None = None
    # Output anti-cutoff policy for this session (ADR 0018); resume reuses it.
    on_truncate: str = "report"


class SessionStore:
    """FIFO-capped, thread-safe (FastMCP runs sync tools from a thread pool)."""

    def __init__(self, max_entries: int = MAX_ENTRIES):
        self._max = max_entries
        self._lock = threading.Lock()
        self._sessions: OrderedDict[str, Session] = OrderedDict()

    def put(self, session: Session) -> str:
        handle = uuid.uuid4().hex
        with self._lock:
            self._sessions[handle] = session
            while len(self._sessions) > self._max:
                self._sessions.popitem(last=False)
        return handle

    def get(self, handle: str) -> Session | None:
        with self._lock:
            return self._sessions.get(handle)

    def delete(self, handle: str) -> None:
        with self._lock:
            self._sessions.pop(handle, None)
