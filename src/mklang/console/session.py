"""Console session persistence (ADR 0015 M2c): plain JSON files, crash-tolerant.

A session directory holds `state.json` (rewritten atomically at each turn's
end), `transcript.jsonl` (streaming append: turns and run events), and
`checkpoints/` for suspended runs. Nothing beyond the standard library.

Brain prompt history is windowed separately (ADR 0017): the full transcript and
``Session.history`` remain the audit trail; only the view passed into
``agent.mk`` is capped.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


def default_base() -> Path:
    from ..paths import host_paths

    return host_paths().sessions


DEFAULT_BASE = default_base()

# Prompt-side budget for the brain's {{history}} (not the on-disk audit).
HISTORY_CHARS = 8_000
HISTORY_TURNS = 12
_TURN_SPLIT = re.compile(r"(?=^user: )", re.M)


@dataclass
class Session:
    dir: Path
    history: str = ""
    spent_in: int = 0
    spent_out: int = 0
    consented: list[str] = field(default_factory=list)
    workspace: str = ""
    brain: str = ""

    # -- lifecycle ---------------------------------------------------------

    @classmethod
    def create(
        cls, base: Path | str = DEFAULT_BASE, workspace: str = "", brain: str = ""
    ) -> "Session":
        sid = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
        d = Path(base) / sid
        (d / "checkpoints").mkdir(parents=True, exist_ok=True)
        s = cls(dir=d, workspace=workspace, brain=brain)
        s.save_state()
        return s

    @classmethod
    def load(cls, d: Path | str) -> "Session":
        d = Path(d)
        st = json.loads((d / "state.json").read_text(encoding="utf-8"))
        return cls(
            dir=d,
            history=st.get("history", ""),
            spent_in=st.get("spent_in", 0),
            spent_out=st.get("spent_out", 0),
            consented=list(st.get("consented", [])),
            workspace=st.get("workspace", ""),
            brain=st.get("brain", ""),
        )

    @classmethod
    def latest(cls, base: Path | str = DEFAULT_BASE) -> "Session | None":
        base = Path(base)
        if not base.is_dir():
            return None
        candidates = sorted(p for p in base.iterdir() if (p / "state.json").is_file())
        return cls.load(candidates[-1]) if candidates else None

    # -- persistence -------------------------------------------------------

    @property
    def id(self) -> str:
        return self.dir.name

    @property
    def checkpoints_dir(self) -> Path:
        return self.dir / "checkpoints"

    def save_state(self) -> None:
        payload = {
            "history": self.history,
            "spent_in": self.spent_in,
            "spent_out": self.spent_out,
            "consented": sorted(self.consented),
            "workspace": self.workspace,
            "brain": self.brain,
        }
        tmp = self.dir / "state.json.tmp"
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.dir / "state.json")

    def append(self, record: dict) -> None:
        with (self.dir / "transcript.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def history_for_brain(
    history: str,
    *,
    max_chars: int = HISTORY_CHARS,
    max_turns: int = HISTORY_TURNS,
) -> str:
    """Window conversation history for injection into the brain prompt.

    Keeps the **last** ``max_turns`` user/agent blocks and hard-caps characters.
    When anything is dropped, prefixes an explicit ``…[history_truncated…]…``
    marker so the model (and authors) can see the cut. The full history stays
    in ``Session.history`` / transcript for audit — this is prompt-only.
    """
    text = (history or "").strip()
    if not text:
        return ""
    # Turn blocks are written as "user: …\nagent: …" (see app.finish_turn).
    blocks = [b.strip() for b in _TURN_SPLIT.split(text) if b.strip()]
    if not blocks:
        return _tail_chars(text, max_chars, truncated=False)

    truncated_turns = False
    if max_turns > 0 and len(blocks) > max_turns:
        blocks = blocks[-max_turns:]
        truncated_turns = True
    body = "\n".join(blocks)
    if max_chars > 0 and len(body) > max_chars:
        return _tail_chars(body, max_chars, truncated=True)
    if truncated_turns:
        return f"…[history_truncated, kept last {max_turns} turns]…\n{body}"
    return body


def _tail_chars(text: str, max_chars: int, *, truncated: bool) -> str:
    if max_chars <= 0:
        return "…[history_truncated]…"
    if not truncated and len(text) <= max_chars:
        return text
    marker = "…[history_truncated]…"
    if len(marker) >= max_chars:
        return marker[:max_chars]
    return marker + text[-(max_chars - len(marker)) :]
