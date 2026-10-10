"""Import the playground and run one bundled callback. No Gradio server."""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import app  # noqa: E402


def test_import_does_not_launch_server() -> None:
    assert callable(app.run_example)
    assert callable(app.parse_source)
    assert callable(app.check_source)
    assert callable(app.format_source)
    assert callable(app.run_conformance)
    # `demo.launch` is only for `python app.py`, never on import.
    assert app.demo is None or not getattr(app.demo, "is_running", False)


def test_hello_accepted_first_try() -> None:
    payload = json.loads(app.run_example("hello", "accepted-first-try"))
    assert payload["ok"] is True
    assert payload["passed"] is True
    assert payload["mismatches"] == []
    assert payload["result"]["status"] == "done"
    assert payload["result"]["result"] == ("A state machine is a model of states and transitions.")
    assert payload["example"] == "hello"
    assert payload["scenario"] == "accepted-first-try"


def main() -> int:
    test_import_does_not_launch_server()
    test_hello_accepted_first_try()
    print("playground smoke: ok (hello / accepted-first-try)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
