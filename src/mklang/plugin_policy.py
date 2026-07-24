"""Optional host allowlist for Python entry-point plugins.

The default remains backwards-compatible (all installed plugins are eligible),
while production hosts can set ``MKLANG_ALLOWED_PLUGINS`` to a comma-separated
allowlist of entry-point names.
"""

from __future__ import annotations

import os


def allowed_plugin(name: str) -> bool:
    raw = os.environ.get("MKLANG_ALLOWED_PLUGINS", "").strip()
    if not raw:
        return True
    allowed = {item.strip() for item in raw.split(",") if item.strip()}
    return name in allowed
