"""`mklang doctor`: diagnose the resolved setup (config layer, env, keys, tools, machines)."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from . import host
from .config import ProviderConfig
from .presentation import CommandResult, emit_result, output_format


def _doctor_load_config(config_arg: str | None) -> tuple[dict | None, str, Path, list[dict], bool]:
    """Load and shape-check the resolved runtime config.

    Returns ``(cfg_or_None, layer, path, items, ok)``. ``cfg`` is None when the
    file is unreadable or fails the structural providers/active check.
    """
    import yaml

    from .paths import resolve_config_with_layer

    resolved, layer = resolve_config_with_layer(config_arg)
    try:
        cfg = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return (
            None,
            layer,
            resolved,
            [
                {
                    "name": f"config {resolved} · layer={layer}",
                    "status": "error",
                    "errors": [str(exc)],
                }
            ],
            False,
        )
    valid = (
        isinstance(cfg, dict)
        and isinstance(cfg.get("providers"), dict)
        and cfg.get("active") in cfg["providers"]
    )
    if valid:
        assert isinstance(cfg, dict)
        return (
            cfg,
            layer,
            resolved,
            [
                {
                    "name": f"config {resolved} · layer={layer} · active={cfg['active']}",
                    "status": "ok",
                }
            ],
            True,
        )
    return (
        None,
        layer,
        resolved,
        [
            {
                "name": f"config {resolved} · layer={layer}",
                "status": "error",
                "errors": ["must define `providers` and an `active` provider among them"],
            }
        ],
        False,
    )


def _doctor_schema_items(cfg: dict, resolved: Path) -> list[dict]:
    """Schema findings for a loaded config (warnings only — never fail the doctor)."""
    import jsonschema

    from .paths import bundled_config_schema

    schema = json.loads(bundled_config_schema().read_text(encoding="utf-8"))
    violations = [
        f"{'/'.join(str(p) for p in err.path) or '<root>'}: {err.message}"
        for err in jsonschema.Draft7Validator(schema).iter_errors(cfg)
    ]
    if not violations:
        return []
    return [
        {
            "name": f"schema {resolved.name} · {len(violations)} finding(s)",
            "status": "warning",
            "warnings": violations,
        }
    ]


def _doctor_env_item() -> dict:
    """Which .env layers the runtime loaded (project / user)."""
    from .config import load_env_files

    project_env, user_env = load_env_files()
    return {
        "name": f"env project={project_env or '-'} · user={user_env or '-'}",
        "status": "ok",
    }


def _doctor_provider_key_items(cfg: dict, active: str) -> tuple[list[dict], bool]:
    """Per-provider API-key readiness; fails only when the *active* key is missing."""
    items: list[dict] = []
    ok = True
    for pname, block in cfg["providers"].items():
        if not isinstance(block, dict):
            status = "error" if pname == active else "warning"
            items.append(
                {
                    "name": f"provider {pname} · invalid block",
                    "status": status,
                    "errors" if status == "error" else "warnings": [
                        "provider configuration must be a mapping"
                    ],
                }
            )
            if pname == active:
                ok = False
            continue
        env_var = (block or {}).get("api_key_env", "")
        # The run-time readiness contract, not a reimplementation of it.
        prov = ProviderConfig(
            name=pname,
            tiers={},
            api_key=os.environ.get(env_var, "") if env_var else "",
            api_key_env=env_var,
        )
        if host.missing_key_message(prov) is None:
            note = "set" if prov.api_key else "optional"
            status = "ok"
        else:
            note = "missing"
            status = "error" if pname == active else "warning"
            if pname == active:
                ok = False
        items.append({"name": f"key {pname} · {env_var or '-'} · {note}", "status": status})
    return items, ok


def _doctor_tool_backend_items(cfg: dict | None) -> list[dict]:
    """What the runtime would bind for search/kb/mail/fs (ADR 0016 resolvers)."""
    from . import fs, kb, mail, search
    from .toolconfig import parse_tools_block

    items: list[dict] = []
    tc = parse_tools_block(cfg or {})
    search_backend, search_src = search.resolve_backend_name(tc)
    search_status = "ok"
    if search_backend == "tavily" and not os.environ.get("TAVILY_API_KEY"):
        search_status = "warning"
        search_backend += " · TAVILY_API_KEY missing"
    items.append(
        {
            "name": f"tools search · backend={search_backend} · source={search_src}",
            "status": search_status,
        }
    )
    for tool, mod in (("kb", kb), ("mail", mail)):
        backend, src = mod.resolve_backend_name(tc)
        items.append({"name": f"tools {tool} · backend={backend} · source={src}", "status": "ok"})
    fs_backend, fs_src = fs.resolve_backend_name(tc)
    fs_env_raw = (os.environ.get("MKLANG_FS_BACKEND") or "").strip().lower()
    if fs_backend == "stub":
        unknown = ""
        if fs_src == "env" and fs_env_raw not in ("stub", "none", "off"):
            unknown = f" ({fs_env_raw!r} unknown — falls back to stub)"
        fs_desc, fs_status = f"stub · source={fs_src}{unknown}", "warning" if unknown else "ok"
    else:
        ws, ws_src = fs.resolve_workspace_with_source(tc)
        write, write_src = fs.writes_allowed_with_source(tc)
        fs_status = "ok" if ws.is_dir() else "warning"
        missing = "" if ws.is_dir() else " (missing)"
        fs_desc = (
            f"local · source={fs_src} · workspace={ws}{missing} ({ws_src}) · "
            f"write={'on' if write else 'off'} ({write_src})"
        )
    items.append({"name": f"tools fs · backend={fs_desc}", "status": fs_status})
    return items


def _doctor_machine_and_state_items() -> list[dict]:
    """Machine discovery roots + host state directories."""
    from .paths import host_paths, machine_layers
    from .registry import load_stdlib_registry

    hp = host_paths()
    items: list[dict] = []
    project_machines = Path("machines")
    machine_roots = [("project", project_machines)] if project_machines.is_dir() else []
    machine_roots += [(name, root) for name, root in reversed(machine_layers())]
    for lname, root in machine_roots:
        count = len(list(root.glob("*.mkl"))) if root.is_dir() else 0
        items.append({"name": f"machines {lname} {root} · {count} file", "status": "ok"})
    items.append({"name": f"machines stdlib · {len(load_stdlib_registry())}", "status": "ok"})
    items.append({"name": f"state sessions {hp.sessions}", "status": "ok"})
    items.append({"name": f"state checkpoints {hp.checkpoints}", "status": "ok"})
    return items


def cmd_doctor(args: argparse.Namespace) -> int:
    """Diagnose the resolved setup: which layer wins for config, env, keys, machines."""
    items: list[dict] = []
    ok = True
    cfg, layer, resolved, config_items, cfg_ok = _doctor_load_config(args.config)
    items.extend(config_items)
    ok = ok and cfg_ok
    if cfg is not None:
        items.extend(_doctor_schema_items(cfg, resolved))
    items.append(_doctor_env_item())
    active: str | None = None
    if cfg is not None:
        active = str(cfg["active"])
        key_items, keys_ok = _doctor_provider_key_items(cfg, active)
        items.extend(key_items)
        ok = ok and keys_ok
    items.extend(_doctor_tool_backend_items(cfg))
    items.extend(_doctor_machine_and_state_items())
    result = CommandResult(
        command="doctor",
        ok=ok,
        items=items,
        summary={"layer": layer, "active": active or "-", "ok": ok},
    )
    emit_result(result, fmt=output_format(args.format), color=args.color)
    return 0 if ok else 1
