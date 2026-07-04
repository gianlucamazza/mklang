"""mklang — reference interpreter for the mklang language (core v0.2)."""

from .model import Gate, Machine, State, parse_machine
from .engine import RunResult, run

__version__ = "0.2.0"
__all__ = ["Gate", "Machine", "State", "parse_machine", "run", "RunResult"]
