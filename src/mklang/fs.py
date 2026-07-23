"""Filesystem data tools for `tool:` states (class 3, BP §13 / ADR 0024).

Coding-tool workspace model: reads are live by default, confined to a
workspace root resolved as explicit :func:`configure_fs` > ``MKLANG_FS_ROOT``
> process cwd. Writes on real disk additionally require an explicit grant
(``--allow-write`` / ``MKLANG_FS_WRITE=1`` / :func:`allow_writes`).
``MKLANG_FS_BACKEND=stub`` forces the offline refusal tier (CI, tests).
Observations are JSON strings so tool states stay ``(dict) -> str``.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Protocol

from .tool_obs import tool_obs

if TYPE_CHECKING:
    from .toolconfig import ToolsConfig

_log = logging.getLogger("mklang.fs")

MAX_LIST_ENTRIES = 200
DEFAULT_READ_BYTES = 65_536
MAX_READ_BYTES = 262_144
MAX_WRITE_BYTES = 262_144

# Data formats only — `.mk` stays with the console's write_machine (BP §13.7),
# executables and dotfiles are never writable.
ALLOWED_WRITE_SUFFIXES = frozenset(
    {
        ".txt",
        ".md",
        ".csv",
        ".tsv",
        ".json",
        ".jsonl",
        ".yaml",
        ".yml",
        ".xml",
        ".toml",
        ".log",
        ".html",
    }
)

_STUB_HOW = (
    "filesystem tools are offline — unset MKLANG_FS_BACKEND (workspace defaults to the "
    "current directory) or set MKLANG_FS_ROOT=/abs/path"
)
_WRITE_HOW = "filesystem writes are disabled — pass --allow-write or set MKLANG_FS_WRITE=1"


class FSError(Exception):
    """Refusal or failure inside a backend; message becomes the envelope error."""


def _normalize_rel(rel: str, *, allow_empty: bool = False) -> str:
    """Validate a relative path from the machine; return the normalized form.

    Refuses absolute paths (POSIX and Windows drives), ``..`` segments, and any
    dotfile segment (protects ``.env`` / ``.git`` when the root is a project).
    """
    raw = str(rel or "").strip().replace("\\", "/")
    if not raw:
        if allow_empty:
            return ""
        raise FSError("empty path")
    if raw.startswith("/") or PurePosixPath(raw).is_absolute():
        raise FSError(f"absolute paths are not allowed: {raw!r}")
    if len(raw) >= 2 and raw[1] == ":" and raw[0].isalpha():
        raise FSError(f"absolute paths are not allowed: {raw!r}")
    parts = []
    for seg in raw.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            raise FSError(f"path escapes the workspace: {rel!r}")
        if seg.startswith("."):
            raise FSError(f"dotfile segments are not allowed: {seg!r}")
        parts.append(seg)
    if not parts and not allow_empty:
        raise FSError("empty path")
    return "/".join(parts)


def _replace_with_retry(tmp: Path, target: Path, attempts: int = 10) -> None:
    """Atomic rename with a bounded retry for Windows sharing violations.

    ``os.replace`` is atomic on every platform, but on Windows a replace onto a
    target that another replace is concurrently swapping raises a transient
    ``PermissionError`` (sharing violation). POSIX renames never see this, so
    the retry loop only ever spins on Windows."""
    for attempt in range(attempts):
        try:
            os.replace(tmp, target)
            return
        except PermissionError:
            if os.name != "nt" or attempt == attempts - 1:
                raise
            time.sleep(0.01 * (attempt + 1))


def _check_write(rel: str, data: bytes, *, max_bytes: int) -> None:
    suffix = PurePosixPath(rel).suffix.lower()
    if suffix not in ALLOWED_WRITE_SUFFIXES:
        allowed = " ".join(sorted(ALLOWED_WRITE_SUFFIXES))
        raise FSError(f"suffix {suffix or '(none)'!r} is not writable (allowed: {allowed})")
    if len(data) > max_bytes:
        raise FSError(f"content is {len(data)} bytes — write cap is {max_bytes}")


class FSBackend(Protocol):
    def list(self, rel: str) -> dict:
        """Return {path, entries, count, truncated} for a directory."""
        ...

    def read(self, rel: str, max_bytes: int) -> dict:
        """Return {path, content, bytes, truncated} for a file."""
        ...

    def write(self, rel: str, content: str, overwrite: bool) -> dict:
        """Return {path, bytes, written, existed} after writing a file."""
        ...


class StubFSBackend:
    """Offline default tier: honest refusal with enable instructions."""

    def list(self, rel: str) -> dict:
        raise FSError(_STUB_HOW)

    def read(self, rel: str, max_bytes: int) -> dict:
        raise FSError(_STUB_HOW)

    def write(self, rel: str, content: str, overwrite: bool) -> dict:
        raise FSError(_STUB_HOW)


class LocalFSBackend:
    """Real disk under a confined workspace root (``stub: false``).

    Confinement follows the console `_workspace_path` pattern: join, resolve,
    refuse unless the result stays under the resolved root — which also covers
    symlinks whose target lands outside. TOCTOU races are out of scope (ADR 0024).
    """

    def __init__(
        self,
        root: str | os.PathLike,
        *,
        max_read_bytes: int = MAX_READ_BYTES,
        max_write_bytes: int = MAX_WRITE_BYTES,
    ):
        self.root = Path(root).expanduser().resolve()
        self.max_read_bytes = max_read_bytes
        self.max_write_bytes = max_write_bytes

    def _confined(self, candidate: Path) -> bool:
        """True when a RESOLVED path stays in the workspace and hits no dotfile.

        The lexical checks in `_normalize_rel` gate the requested path; this
        gates what it actually points at, so a visible symlink cannot smuggle
        in `.env` or a target outside the root.
        """
        if not candidate.is_relative_to(self.root):
            return False
        return not any(part.startswith(".") for part in candidate.relative_to(self.root).parts)

    def _resolve(self, rel: str, *, allow_empty: bool = False) -> tuple[str, Path]:
        norm = _normalize_rel(rel, allow_empty=allow_empty)
        if not self.root.is_dir():
            raise FSError(f"workspace root is not a directory: {self.root}")
        candidate = (self.root / norm).resolve() if norm else self.root
        if not self._confined(candidate):
            raise FSError(f"path escapes the workspace: {rel!r}")
        return norm, candidate

    def list(self, rel: str) -> dict:
        norm, target = self._resolve(rel, allow_empty=True)
        if not target.is_dir():
            raise FSError(f"no such directory: {rel!r}")
        entries: list[dict[str, str | int]] = []
        for child in sorted(target.iterdir(), key=lambda p: p.name):
            if child.name.startswith(".") or not self._confined(child.resolve()):
                continue
            if child.is_dir():
                entries.append({"name": child.name, "kind": "dir"})
            elif child.is_file():
                entries.append({"name": child.name, "kind": "file", "bytes": child.stat().st_size})
        truncated = len(entries) > MAX_LIST_ENTRIES
        return {
            "path": norm,
            "entries": entries[:MAX_LIST_ENTRIES],
            "count": len(entries),
            "truncated": truncated,
        }

    def read(self, rel: str, max_bytes: int) -> dict:
        norm, target = self._resolve(rel)
        if not target.is_file():
            raise FSError(f"no such file: {rel!r}")
        cap = min(max_bytes, self.max_read_bytes)
        size = target.stat().st_size
        with open(target, "rb") as fh:
            data = fh.read(cap)
        return {
            "path": norm,
            "content": data.decode("utf-8", errors="replace"),
            "bytes": size,
            "truncated": size > cap,
        }

    def write(self, rel: str, content: str, overwrite: bool) -> dict:
        norm, target = self._resolve(rel)
        data = content.encode("utf-8")
        _check_write(norm, data, max_bytes=self.max_write_bytes)
        existed = target.exists()
        if existed and not overwrite:
            raise FSError(f"{norm!r} exists — pass overwrite: true")
        # Parents of a confined final path are confined by construction.
        target.parent.mkdir(parents=True, exist_ok=True)
        # mkstemp: unique name per call (concurrent same-target writes must
        # not collide) and 0600 by default, like the checkpoint precedent.
        fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.")
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            _replace_with_retry(tmp, target)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return {"path": norm, "bytes": len(data), "written": True, "existed": existed}


_backend: FSBackend | None = None
_writes_allowed: bool | None = None


def configure_fs(backend: FSBackend | None) -> None:
    """Bind (or clear) the process-wide fs backend used by the three tools."""
    global _backend
    _backend = backend


def current_fs_backend() -> FSBackend | None:
    return _backend


def allow_writes(enabled: bool | None) -> None:
    """Grant (or revoke) disk writes; ``None`` falls back to ``MKLANG_FS_WRITE``."""
    global _writes_allowed
    _writes_allowed = enabled


def writes_allowed_with_source(tc: "ToolsConfig | None" = None) -> tuple[bool, str]:
    """Write grant + source: runtime grant > set env > config > off.

    A *set, non-empty* ``MKLANG_FS_WRITE`` decides either way, so
    ``MKLANG_FS_WRITE=0`` is an explicit off that beats a config
    ``write: true``; unset falls through to ``tools.fs.write``."""
    from .toolconfig import current_tools

    if _writes_allowed is not None:
        return _writes_allowed, "runtime"
    env = (os.environ.get("MKLANG_FS_WRITE") or "").strip().lower()
    if env:
        return env in ("1", "true", "yes", "on"), "env"
    tc = tc if tc is not None else current_tools()
    if tc.fs_write is not None:
        return tc.fs_write, "config"
    return False, "default"


def writes_allowed() -> bool:
    return writes_allowed_with_source()[0]


def resolve_workspace_with_source(tc: "ToolsConfig | None" = None) -> tuple[Path, str]:
    """Workspace root + source: ``MKLANG_FS_ROOT`` > ``tools.fs.workspace`` > cwd."""
    from .toolconfig import current_tools

    root = (os.environ.get("MKLANG_FS_ROOT") or "").strip()
    if root:
        return Path(root).expanduser().resolve(), "env"
    tc = tc if tc is not None else current_tools()
    if tc.fs_workspace:
        return Path(tc.fs_workspace).expanduser().resolve(), "config"
    return Path.cwd(), "default"


def resolve_workspace() -> Path:
    return resolve_workspace_with_source()[0]


def resolve_backend_name(tc: "ToolsConfig | None" = None) -> tuple[str, str]:
    """Backend name + source: env > ``tools.fs.backend`` config > local (ADR 0024).

    Unknown names degrade to ``stub`` — an unrecognized value must never
    silently reach real disk."""
    from .toolconfig import current_tools

    env = (os.environ.get("MKLANG_FS_BACKEND") or "").strip().lower()
    if env:
        return ("local" if env == "local" else "stub"), "env"
    tc = tc if tc is not None else current_tools()
    if tc.fs_backend:
        return ("local" if tc.fs_backend.strip().lower() == "local" else "stub"), "config"
    return "local", "default"


def _backend_from_settings() -> FSBackend:
    """Lazy binding (live-by-default per ADR 0024): env > config > local."""
    name, _source = resolve_backend_name()
    if name == "local":
        return LocalFSBackend(resolve_workspace())
    return StubFSBackend()


def _current() -> FSBackend:
    return _backend if _backend is not None else _backend_from_settings()


def _is_stub(backend: FSBackend) -> bool:
    # Only real disk reports stub: false (search.py precedent).
    return not isinstance(backend, LocalFSBackend)


def list_files(inp: dict) -> str:
    """Host tool entry: list a workspace directory ('' = workspace root)."""
    rel = str(inp.get("path") or "").strip()
    backend = _current()
    stub = _is_stub(backend)
    try:
        payload = backend.list(rel)
        _log.info("list_files %s (%d entries)", payload["path"] or ".", payload["count"])
        return tool_obs("list_files", stub=stub, error=None, **payload)
    except FSError as e:
        return tool_obs(
            "list_files", stub=stub, error=str(e), path=rel, entries=[], count=0, truncated=False
        )
    except Exception as e:  # never crash the machine on a tool boundary
        return tool_obs(
            "list_files",
            stub=stub,
            error=f"list failed: {e}",
            path=rel,
            entries=[],
            count=0,
            truncated=False,
        )


def read_file(inp: dict) -> str:
    """Host tool entry: read a workspace file (UTF-8, size-capped)."""
    rel = str(inp.get("path") or "").strip()
    backend = _current()
    stub = _is_stub(backend)

    def err(msg: str) -> str:
        return tool_obs(
            "read_file", stub=stub, error=msg, path=rel, content="", bytes=0, truncated=False
        )

    try:
        max_bytes = int(inp.get("max_bytes") or DEFAULT_READ_BYTES)
    except (TypeError, ValueError):
        return err("max_bytes must be an integer")
    max_bytes = max(1, min(max_bytes, MAX_READ_BYTES))
    try:
        payload = backend.read(rel, max_bytes)
        _log.info("read_file %s (%d bytes)", payload["path"], payload["bytes"])
        return tool_obs("read_file", stub=stub, error=None, **payload)
    except FSError as e:
        return err(str(e))
    except Exception as e:  # never crash the machine on a tool boundary
        return err(f"read failed: {e}")


def write_file(inp: dict) -> str:
    """Host tool entry: write a workspace file (grant-gated on real disk)."""
    rel = str(inp.get("path") or "").strip()
    backend = _current()
    stub = _is_stub(backend)

    def err(msg: str) -> str:
        return tool_obs(
            "write_file", stub=stub, error=msg, path=rel, bytes=0, written=False, existed=False
        )

    content = inp.get("content")
    if content is None:
        return err("missing content")
    overwrite_raw = inp.get("overwrite")
    overwrite = (
        overwrite_raw
        if isinstance(overwrite_raw, bool)
        else str(overwrite_raw or "").strip().lower() in ("1", "true", "yes", "on")
    )
    if isinstance(backend, LocalFSBackend) and not writes_allowed():
        return err(_WRITE_HOW)
    try:
        payload = backend.write(rel, str(content), overwrite)
        _log.info("write_file %s (%d bytes)", payload["path"], payload["bytes"])
        return tool_obs("write_file", stub=stub, error=None, **payload)
    except FSError as e:
        return err(str(e))
    except Exception as e:  # never crash the machine on a tool boundary
        return err(f"write failed: {e}")
