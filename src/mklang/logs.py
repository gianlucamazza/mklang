"""Process logging for the mklang host (best practices §12).

Configures the ``mklang.*`` logger hierarchy with a single named stderr
handler. Two invariants: host logs go to stderr only (never to MCP logging
notifications — those carry ``mklang.event`` run events), and logging is
never a ``.mkl`` language face. Run semantics stay on trace/events.

Level resolution: ``--log-level`` flag > ``MKLANG_LOG_LEVEL`` env > WARNING.
"""

from __future__ import annotations

import logging
import os
import sys

LEVELS = ("debug", "info", "warning", "error")

_HANDLER_NAME = "mklang-process"
_FORMAT = "%(levelname)s %(name)s: %(message)s"


def setup_process_logging(cli_level: str | None = None) -> None:
    """Attach (or retune) the stderr handler on the ``mklang`` logger.

    Idempotent: repeated calls (the test suite invokes ``main()`` many times
    per process) find the named handler and only update the level. The root
    logger is left untouched and propagation stays on, so pytest's ``caplog``
    keeps seeing every record.
    """
    bad_env = None
    level_name = cli_level
    if level_name is None:
        env = os.environ.get("MKLANG_LOG_LEVEL", "")
        if env:
            if env.lower() in LEVELS:
                level_name = env.lower()
            else:
                bad_env = env
    if level_name is None:
        level_name = "warning"

    logger = logging.getLogger("mklang")
    logger.setLevel(getattr(logging, level_name.upper()))
    handler = next((h for h in logger.handlers if h.name == _HANDLER_NAME), None)
    if handler is None:
        handler = logging.StreamHandler(sys.stderr)
        handler.set_name(_HANDLER_NAME)
        handler.setFormatter(logging.Formatter(_FORMAT))
        logger.addHandler(handler)

    if bad_env is not None:
        logging.getLogger("mklang.logs").warning(
            "MKLANG_LOG_LEVEL=%r is not one of %s — using warning", bad_env, "/".join(LEVELS)
        )
