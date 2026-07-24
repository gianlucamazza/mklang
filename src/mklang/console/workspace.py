"""Bounded, read-only inspection of a console workspace.

This module is deliberately independent from Textual and the brain machine. It
owns the workspace policy and resource budgets; ``console.tools`` only adapts
its results to the host-tool JSON-string contract.
"""

from __future__ import annotations

import codecs
import os
import re
from collections.abc import Iterator
from pathlib import Path


ANALYSIS_WORDS = (
    "analy",
    "analizz",
    "inspect",
    "ispezion",
    "review",
    "audit",
    "architett",
    "architecture",
    "understand",
    "comprend",
    "summar",
    "riassum",
)
TARGET_WORDS = (
    "project",
    "progetto",
    "repo",
    "repository",
    "workspace",
    "folder",
    "cartella",
    "directory",
    "codebase",
    "codice",
    "code",
    "file",
    "architett",
    "architecture",
)


def requires_workspace_inspection(message: str) -> bool:
    """Classify explicit project-analysis requests conservatively."""
    tokens = re.findall(r"[a-zà-ÿ0-9_]+", (message or "").casefold())
    return any(token.startswith(word) for token in tokens for word in ANALYSIS_WORDS) and any(
        token.startswith(word) for token in tokens for word in TARGET_WORDS
    )


class WorkspaceInspector:
    """Inspect visible project files below one resolved workspace root."""

    IGNORED_DIRS = frozenset(
        {
            ".git",
            ".hg",
            ".svn",
            ".venv",
            "venv",
            "node_modules",
            "dist",
            "build",
            "target",
            "__pycache__",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            "coverage",
            "site",
        }
    )
    INSTRUCTION_NAMES = frozenset({"AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md"})
    MARKER_NAMES = frozenset(
        {
            "README.md",
            "pyproject.toml",
            "package.json",
            "Cargo.toml",
            "go.mod",
            "Makefile",
            "Dockerfile",
        }
    )
    SENSITIVE_NAMES = frozenset(
        {"credentials.json", "secrets.json", "token.json", "service-account.json"}
    )
    SENSITIVE_SUFFIXES = frozenset(
        {".pem", ".key", ".p12", ".pfx", ".jks", ".db", ".sqlite", ".sqlite3"}
    )

    MAX_LIST_ENTRIES = 400
    MAX_READ_BYTES = 120_000
    MAX_SEARCH_RESULTS = 80
    MAX_SEARCH_FILES = 2_000
    MAX_SEARCH_BYTES = 64 * 1024 * 1024
    MAX_SNAPSHOT_FILES = 1_000
    MAX_SNAPSHOT_MARKERS = 100

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _candidate(self, rel: object, *, allow_root: bool = False) -> Path | None:
        raw = str(rel or "").strip().replace("\\", "/")
        if not raw:
            return self.root if allow_root else None
        if raw.startswith("/") or (len(raw) >= 2 and raw[1] == ":"):
            return None
        parts = [part for part in raw.split("/") if part not in ("", ".")]
        if any(part == ".." or part.startswith(".") for part in parts):
            return None
        candidate = (self.root.joinpath(*parts)).resolve()
        if not candidate.is_relative_to(self.root):
            return None
        relative_parts = candidate.relative_to(self.root).parts
        if any(part in self.IGNORED_DIRS or part.startswith(".") for part in relative_parts):
            return None
        return candidate

    def _relative(self, path: Path) -> str:
        # Workspace paths are part of the JSON contract; keep `/` separators
        # on Windows as well as POSIX so callers and tests see one portable form.
        return path.relative_to(self.root).as_posix() or "."

    def _sensitive(self, path: Path) -> bool:
        return (
            path.name.lower() in self.SENSITIVE_NAMES
            or path.suffix.lower() in self.SENSITIVE_SUFFIXES
        )

    def _visible_file(self, path: Path) -> bool:
        return not path.name.startswith(".") and not self._sensitive(path)

    @staticmethod
    def _decode_prefix(data: bytes) -> tuple[str, bool]:
        """Decode a bounded UTF-8 prefix without misclassifying a split codepoint."""
        try:
            return data.decode("utf-8"), False
        except UnicodeDecodeError as exc:
            last = data[-1] if data else 0
            incomplete_tail = 0x80 <= last <= 0xBF or 0xC2 <= last <= 0xF4
            if exc.end != len(data) or not incomplete_tail:
                raise
            decoder = codecs.getincrementaldecoder("utf-8")()
            return decoder.decode(data[: exc.start], final=False), True

    def _iter_files(self, root: Path, max_depth: int) -> Iterator[Path]:
        if not root.is_dir():
            return
        for current, dirs, files in os.walk(root, followlinks=False):
            current_path = Path(current)
            depth = len(current_path.relative_to(root).parts)
            dirs[:] = sorted(
                directory
                for directory in dirs
                if not directory.startswith(".") and directory not in self.IGNORED_DIRS
            )
            if depth >= max_depth:
                dirs[:] = []
            for name in sorted(files):
                path = current_path / name
                if self._visible_file(path) and self._candidate(self._relative(path)) is not None:
                    yield path

    def snapshot(self) -> dict:
        """Return bounded context metadata without reading file contents."""
        entries = []
        for child in sorted(self.root.iterdir(), key=lambda item: item.name):
            if child.name.startswith(".") or child.name in self.IGNORED_DIRS:
                continue
            entries.append({"path": child.name, "kind": "directory" if child.is_dir() else "file"})

        instruction_files: list[str] = []
        markers: list[str] = []
        scanned = 0
        truncated = False
        for path in self._iter_files(self.root, max_depth=3):
            scanned += 1
            if scanned > self.MAX_SNAPSHOT_FILES:
                truncated = True
                break
            rel = self._relative(path)
            if path.name in self.INSTRUCTION_NAMES:
                instruction_files.append(rel)
            if path.name in self.MARKER_NAMES:
                markers.append(rel)

        if len(instruction_files) > self.MAX_SNAPSHOT_MARKERS:
            instruction_files = instruction_files[: self.MAX_SNAPSHOT_MARKERS]
            truncated = True
        if len(markers) > self.MAX_SNAPSHOT_MARKERS:
            markers = markers[: self.MAX_SNAPSHOT_MARKERS]
            truncated = True
        return {
            "root": ".",
            "entries": entries[: self.MAX_LIST_ENTRIES],
            "entries_truncated": len(entries) > self.MAX_LIST_ENTRIES,
            "markers": sorted(set(markers)),
            "instruction_files": sorted(set(instruction_files)),
            "read_only": True,
            "ignored_dirs": sorted(self.IGNORED_DIRS),
            "sensitive_files_skipped": True,
            "truncated": truncated or len(entries) > self.MAX_LIST_ENTRIES,
        }

    def list(self, rel: object = "", depth: object = 1) -> dict:
        path = self._candidate(rel, allow_root=True)
        if path is None or not path.is_dir():
            return self._error(
                "list_workspace", rel, "invalid or unavailable workspace directory", entries=[]
            )
        try:
            bounded_depth = max(1, min(int(str(depth or 1)), 4))
        except (TypeError, ValueError):
            bounded_depth = 1
        candidates: list[Path] = []
        if bounded_depth == 1:
            candidates = sorted(path.iterdir(), key=lambda item: item.name)
        else:
            for current, dirs, files in os.walk(path, followlinks=False):
                current_path = Path(current)
                current_depth = len(current_path.relative_to(path).parts)
                dirs[:] = sorted(
                    directory
                    for directory in dirs
                    if not directory.startswith(".") and directory not in self.IGNORED_DIRS
                )
                if current_depth >= bounded_depth:
                    dirs[:] = []
                candidates.extend(current_path / name for name in [*dirs, *files])
            candidates.sort(key=lambda item: str(item.relative_to(path)))

        entries: list[dict[str, object]] = []
        sensitive_skipped = False
        for child in candidates:
            if child.name.startswith(".") or child.name in self.IGNORED_DIRS:
                continue
            if child.is_file() and self._sensitive(child):
                sensitive_skipped = True
                continue
            if self._candidate(self._relative(child)) is None:
                continue
            row: dict[str, object] = {
                "path": self._relative(child),
                "kind": "directory" if child.is_dir() else "file",
            }
            if child.is_file():
                try:
                    row["bytes"] = child.stat().st_size
                except OSError:
                    row["bytes"] = None
            entries.append(row)
        return {
            "tool": "list_workspace",
            "path": self._relative(path),
            "depth": bounded_depth,
            "entries": entries[: self.MAX_LIST_ENTRIES],
            "truncated": len(entries) > self.MAX_LIST_ENTRIES,
            "sensitive_files_skipped": sensitive_skipped,
            "error": None,
        }

    def read(self, rel: object, max_bytes: object = None) -> dict:
        relative = str(rel or "").strip()
        path = self._candidate(relative)
        try:
            limit = max(1, min(int(str(max_bytes or self.MAX_READ_BYTES)), self.MAX_READ_BYTES))
        except (TypeError, ValueError):
            return self._error(
                "read_workspace_file", relative, "max_bytes must be an integer", content=""
            )
        if path is None or not path.is_file():
            return self._error(
                "read_workspace_file", relative, "file is unavailable in the workspace", content=""
            )
        if self._sensitive(path):
            return self._error(
                "read_workspace_file",
                relative,
                "sensitive file skipped",
                content="",
                skipped_sensitive=True,
            )
        try:
            size = path.stat().st_size
            data = path.read_bytes()[:limit]
            text, split_codepoint = self._decode_prefix(data)
        except UnicodeDecodeError:
            return self._error(
                "read_workspace_file", relative, "binary or non-UTF-8 file skipped", content=""
            )
        except OSError as exc:
            return self._error("read_workspace_file", relative, str(exc), content="")
        return {
            "tool": "read_workspace_file",
            "path": relative,
            "content": text,
            "bytes": size,
            "truncated": size > limit or split_codepoint,
            "skipped_sensitive": False,
            "error": None,
        }

    def search(
        self,
        query: object,
        rel: object = "",
        max_results: object = None,
        case_sensitive: object = False,
    ) -> dict:
        needle_raw = str(query or "")
        if not needle_raw:
            return self._error("search_workspace", rel, "query is required", matches=[])
        root = self._candidate(rel, allow_root=True)
        if root is None or not root.is_dir():
            return self._error(
                "search_workspace", rel, "invalid or unavailable workspace directory", matches=[]
            )
        try:
            limit = max(
                1, min(int(str(max_results or self.MAX_SEARCH_RESULTS)), self.MAX_SEARCH_RESULTS)
            )
        except (TypeError, ValueError):
            limit = self.MAX_SEARCH_RESULTS
        needle = needle_raw if case_sensitive else needle_raw.lower()
        matches: list[dict[str, object]] = []
        files_scanned = 0
        bytes_scanned = 0
        truncated = False
        for path in self._iter_files(root, max_depth=8):
            if files_scanned >= self.MAX_SEARCH_FILES or bytes_scanned >= self.MAX_SEARCH_BYTES:
                truncated = True
                break
            files_scanned += 1
            try:
                remaining = self.MAX_SEARCH_BYTES - bytes_scanned
                file_size = path.stat().st_size
                read_limit = min(self.MAX_READ_BYTES, remaining)
                data = path.read_bytes()[:read_limit]
                bytes_scanned += len(data)
                text, split_codepoint = self._decode_prefix(data)
                if file_size > len(data) or split_codepoint:
                    truncated = True
            except (OSError, UnicodeDecodeError):
                continue
            for line_no, line in enumerate(text.splitlines(), 1):
                haystack = line if case_sensitive else line.lower()
                if needle in haystack:
                    matches.append(
                        {"path": self._relative(path), "line": line_no, "text": line[:500]}
                    )
                    if len(matches) >= limit:
                        truncated = True
                        break
            if truncated and len(matches) >= limit:
                break
        return {
            "tool": "search_workspace",
            "query": needle_raw,
            "matches": matches,
            "truncated": truncated,
            "files_scanned": files_scanned,
            "bytes_scanned": bytes_scanned,
            "error": None,
        }

    @staticmethod
    def _error(tool: str, path: object, message: str, **fields: object) -> dict:
        return {
            "tool": tool,
            "path": str(path or ""),
            **fields,
            "truncated": False,
            "error": message,
        }
