# PYTHON_ARGCOMPLETE_OK
"""`mklang` command-line interface: run and check machines."""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path
from uuid import uuid4

from . import __version__, host
from .checkpoint import load_checkpoint, save_checkpoint, taint_frame, verify_hash
from .config import ProviderConfig
from .engine import RunResult, run
from .llm.base import LLM
from .loader import load_machine, semantic_check
from .model import Machine
from .logs import LEVELS, setup_process_logging
from .registry import base_registry, load_registry
from .presentation import (
    CommandResult,
    Diagnostic,
    emit_json,
    emit_machines_text,
    emit_result,
    emit_run_text,
    output_format,
)


_log = logging.getLogger("mklang.cli")


def _build_llm(prov):
    from .providers import build_llm

    return build_llm(prov)


def _coerce(value: str) -> object:
    """JSON-parse a --set value (so lists/objects/numbers work); fall back to str."""
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return value


def _apply_sets(ctx: dict, sets: list[str]) -> dict:
    for kv in sets or []:
        if "=" not in kv:
            raise ValueError(f"invalid --set {kv!r}; expected k.path=value")
        key, value = kv.split("=", 1)
        if not key.strip():
            raise ValueError("invalid --set: key cannot be empty")
        host.set_path(ctx, key, _coerce(value))
    return ctx


def _prepare(
    args: argparse.Namespace, machine_path: str
) -> tuple[ProviderConfig, LLM, dict, Machine, dict, dict] | int:
    """Shared run/resume setup. Returns (prov, llm, registry, machine, tools, hooks) or exit code."""
    try:
        p = host.prepare_path(
            args.config,
            args.provider,
            machine_path,
            strict=getattr(args, "strict", False),
            build_llm=_build_llm,
        )
    except host.PrepareError as err:
        if output_format(args.format, structured_default=True) == "json":
            emit_json(
                CommandResult(
                    command=args.cmd,
                    ok=False,
                    diagnostics=[
                        Diagnostic("warning", w, code="prepare-warning", path=machine_path)
                        for w in err.warnings
                    ]
                    + [
                        Diagnostic("error", e, code=f"prepare-{err.kind}", path=machine_path)
                        for e in err.errors
                    ],
                ).json_value()
            )
            return 2
        for w in err.warnings:
            print(f"# warning: {w}", file=sys.stderr)
        label = "ERROR" if err.kind == "load" else "error"
        for e in err.errors:
            print(f"{machine_path}: {label}: {e}", file=sys.stderr)
        return 2
    for w in p.warnings:
        print(f"# warning: {w}", file=sys.stderr)
    return p.prov, p.llm, p.registry, p.machine, p.tools, p.hooks


def _emit(
    res: RunResult,
    checkpoint_path: str | Path | None,
    machine: Machine,
    machine_path: str,
    cost_budget: int | None,
    args: argparse.Namespace,
    provider: str,
    hitl: bool = False,
) -> int:
    """Print the result JSON; write a checkpoint on suspension. Exit: 0 done, 3 suspended, 1 halt."""
    out = host.build_output(res)
    if res.status == "suspended":
        # A suspended run always carries reason + frames, and the callers only
        # enable suspension when a checkpoint path is set.
        assert checkpoint_path is not None and res.error is not None and res.frames is not None
        save_checkpoint(
            checkpoint_path, machine.name, machine_path, res.error, res.frames, cost_budget, hitl
        )
        out["checkpoint"] = str(checkpoint_path)
        if output_format(args.format, structured_default=True) != "json":
            print(
                f"# suspended ({res.error}) — checkpoint written to {checkpoint_path}",
                file=sys.stderr,
            )
    if output_format(args.format, structured_default=True) == "json":
        emit_json(out)
    else:
        emit_run_text(out, machine=machine.name, provider=provider, color=args.color)
    if res.status == "done":
        return 0
    return 3 if res.status == "suspended" else 1


def _default_checkpoint(machine_path: str) -> Path:
    """A fresh checkpoint path under the XDG state root (ADR 0023)."""
    from .paths import host_paths

    directory = host_paths().checkpoints
    directory.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return directory / f"{Path(machine_path).stem}-{stamp}-{uuid4().hex[:6]}.json"


def _bind_fs(args: argparse.Namespace) -> str | None:
    """Apply --workspace / --allow-write to the fs tools; error message on bad root."""
    from .fs import LocalFSBackend, allow_writes, configure_fs

    if getattr(args, "workspace", None):
        root = Path(args.workspace).expanduser()
        if not root.is_dir():
            return f"--workspace {args.workspace}: not a directory"
        configure_fs(LocalFSBackend(root))
    if getattr(args, "allow_write", False):
        allow_writes(True)
    return None


def cmd_run(args: argparse.Namespace) -> int:
    fs_err = _bind_fs(args)
    if fs_err:
        return _input_error(args, fs_err)
    if args.hitl and not args.checkpoint:
        # The suspension must land somewhere; without an explicit path it goes
        # to the state root, and the suspension message prints where.
        args.checkpoint = str(_default_checkpoint(args.machine))
    if args.max_tokens is not None and args.max_tokens <= 0:
        return _input_error(args, "--max-tokens must be a positive integer")
    prep = _prepare(args, args.machine)
    if isinstance(prep, int):
        return prep
    prov, llm, registry, machine, tools, hooks = prep
    try:
        ctx = _apply_sets(dict(machine.context), args.set)
    except ValueError as exc:
        return _input_error(args, str(exc), hint="Use --set task=\"value\" or --set items='[1,2]'.")
    host.inject_host_defaults(ctx)  # fill declared empty context.today, etc.
    if output_format(args.format, structured_default=True) != "json":
        print(f"# {machine.name} · provider={prov.name} · tiers={prov.tiers}", file=sys.stderr)
    res = run(
        machine,
        ctx,
        registry,
        llm,
        prov.tiers,
        prov.judge_override(),
        tier_params=prov.params,
        cost_budget=args.max_tokens,
        tools=tools,
        hooks=hooks,
        suspendable=args.checkpoint is not None,
        escalate_suspend=args.hitl,
        on_truncate=getattr(args, "on_truncate", "report"),
    )
    return _emit(
        res,
        args.checkpoint,
        machine,
        args.machine,
        args.max_tokens,
        args,
        prov.name,
        hitl=args.hitl,
    )


def cmd_resume(args: argparse.Namespace) -> int:
    if args.max_tokens is not None and args.max_tokens <= 0:
        return _input_error(args, "--max-tokens must be a positive integer")
    try:
        ck = load_checkpoint(args.checkpoint)
    except (OSError, ValueError) as e:
        return _input_error(args, f"{args.checkpoint}: {e}")
    machine_path = args.machine or ck["machine_path"]
    try:
        hash_ok = verify_hash(ck, machine_path)
    except OSError as e:
        return _input_error(args, f"{machine_path}: {e}")
    if not hash_ok:
        if not args.force:
            return _input_error(
                args,
                f"{machine_path}: machine changed since checkpoint (sha256 mismatch)",
                hint="Use --force to resume anyway only after reviewing the change.",
            )
        _log.warning("%s changed since checkpoint — resuming anyway", machine_path)
    prep = _prepare(args, machine_path)
    if isinstance(prep, int):
        return prep
    prov, llm, registry, machine, tools, hooks = prep
    cost_budget = args.max_tokens if args.max_tokens is not None else ck.get("cost_budget")
    if ck.get("reason") == "cost-exhausted" and cost_budget is not None:
        old = ck.get("cost_budget")
        if old is not None and cost_budget <= old:
            _log.warning(
                "cost budget %s is not above the exhausted %s — the run will "
                "suspend again immediately",
                cost_budget,
                old,
            )
    out_path = args.checkpoint_out or args.checkpoint
    hitl = ck.get("hitl", False) or args.hitl
    # A human reply lands in the innermost frame's context (the suspended run);
    # host-injected values are untrusted (ADR 0025).
    try:
        _apply_sets(ck["frames"][-1]["ctx"], args.set)
    except ValueError as exc:
        return _input_error(args, str(exc))
    taint_frame(ck["frames"][-1], [kv.split("=", 1)[0] for kv in args.set or []])
    if output_format(args.format, structured_default=True) != "json":
        print(
            f"# {machine.name} · resume · provider={prov.name} · tiers={prov.tiers}",
            file=sys.stderr,
        )
    res = run(
        machine,
        dict(machine.context),
        registry,
        llm,
        prov.tiers,
        prov.judge_override(),
        tier_params=prov.params,
        cost_budget=cost_budget,
        tools=tools,
        hooks=hooks,
        suspendable=True,
        escalate_suspend=hitl,
        resume=ck["frames"],
        on_truncate=getattr(args, "on_truncate", "report"),
    )
    return _emit(res, out_path, machine, machine_path, cost_budget, args, prov.name, hitl=hitl)


def _input_error(args: argparse.Namespace, message: str, *, hint: str = "") -> int:
    result = CommandResult(
        command=args.cmd,
        ok=False,
        diagnostics=[Diagnostic("error", message, code="invalid-input", hint=hint)],
    )
    fmt = output_format(args.format)
    emit_result(result, fmt=fmt, color=args.color, stderr=fmt == "text")
    return 2


def cmd_lint(args: argparse.Namespace) -> int:
    from .lint import lint_machine

    llm = prov = None
    if args.llm:
        from .config import load_provider

        prov = load_provider(args.config, args.provider)
        missing = host.missing_key_message(prov)
        if missing:
            return _input_error(args, missing)
        llm = _build_llm(prov)
        print(
            f"# --llm probe: provider={prov.name} · advisory only, non-deterministic "
            f"(ADR 0010) — never a --strict error source",
            file=sys.stderr,
        )
    ok = True
    findings_total = 0
    items: list[dict] = []
    for path in args.machines:
        item = {
            "path": path,
            "status": "ok",
            "errors": [],
            "warnings": [],
            "findings": [],
            "llm_findings": [],
        }
        registry = {**base_registry(), **load_registry(Path(path).parent, validate=False)}
        try:
            machine = load_machine(path)
        except Exception as e:  # surface any load/validation failure
            item["status"] = "error"
            item["errors"].append(f"schema: {getattr(e, 'message', str(e))}")
            items.append(item)
            ok = False
            continue
        errors, warnings = semantic_check(machine, registry, strict=args.strict)
        findings = lint_machine(machine)
        findings_total += len(findings)
        item["warnings"].extend(warnings)
        item["errors"].extend(errors)
        item["findings"].extend(findings)
        if llm is not None and prov is not None and not errors:
            from .llmlint import llm_lint_machine

            for f in llm_lint_machine(
                machine,
                llm,
                prov.tiers,
                prov.judge_override(),
                samples=args.llm_samples,
                repeats=args.llm_repeats,
                tier_params=prov.params,
            ):
                item["llm_findings"].append(f)
        if errors:
            ok = False
            item["status"] = "error"
        elif findings:
            item["status"] = "warning"
        items.append(item)
    result = CommandResult(
        command="lint",
        ok=ok and not (args.strict and findings_total),
        items=items,
        summary={"files": len(items), "findings": findings_total},
    )
    emit_result(result, fmt=output_format(args.format), color=args.color)
    if not ok:
        return 1
    return 1 if (args.strict and findings_total) else 0


def cmd_test(args: argparse.Namespace) -> int:
    """Run scenario tests against a machine with a scripted LLM (no API keys)."""
    import yaml

    from .scripttest import match_expectation, run_scenario

    registry = {**base_registry(), **load_registry(Path(args.machine).parent, validate=False)}
    try:
        machine = load_machine(args.machine)
    except Exception as e:  # surface any load/validation failure
        return _input_error(args, f"{args.machine}: schema error: {getattr(e, 'message', str(e))}")
    registry[machine.name] = machine

    try:
        doc = yaml.safe_load(Path(args.script).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        return _input_error(args, f"{args.script}: {e}")
    scenarios = (doc or {}).get("scenarios")
    if not scenarios:
        return _input_error(args, f"{args.script}: no `scenarios:` list")

    all_pass = True
    items: list[dict] = []
    for i, sc in enumerate(scenarios):
        name = sc.get("name", f"scenario[{i}]")
        expect = sc.get("expect")
        if expect is None:
            items.append(
                {
                    "scenario": name,
                    "status": "fail",
                    "mismatches": ["scenario has no `expect:` block"],
                }
            )
            all_pass = False
            continue
        try:
            result = run_scenario(machine, registry, sc)
        except Exception as e:  # a scenario error is a failure, not a crash
            items.append(
                {
                    "scenario": name,
                    "status": "fail",
                    "mismatches": [f"scenario raised {type(e).__name__}: {e}"],
                }
            )
            all_pass = False
            continue
        mismatches = match_expectation(result, expect)
        if not mismatches:
            items.append({"scenario": name, "status": "pass", "mismatches": []})
            continue
        all_pass = False
        items.append(
            {"scenario": name, "status": "fail", "mismatches": [str(m) for m in mismatches]}
        )
    passed = sum(i["status"] == "pass" for i in items)
    cmd_result = CommandResult(
        command="test",
        ok=all_pass,
        items=items,
        summary={"passed": passed, "failed": len(items) - passed},
    )
    emit_result(cmd_result, fmt=output_format(args.format), color=args.color)
    return 0 if all_pass else 1


def cmd_machines(args: argparse.Namespace) -> int:
    """List commissionable machines as JSON: bundled stdlib, plugins, and the
    .mkl files of a project directory (which shadow same-named bundled ones)."""
    from .registry import registry_with_sources

    if args.dir and not Path(args.dir).is_dir():
        return _input_error(args, f"machine directory does not exist: {args.dir}")
    reg, sources = registry_with_sources(args.dir)
    out = [host.describe_machine(reg[name], sources[name]) for name in sorted(reg)]
    if output_format(args.format, structured_default=True) == "json":
        emit_json(out)
    else:
        emit_machines_text(out, color=args.color)
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """Scaffold a project or user host without overwriting existing files."""
    from .paths import (
        bundled_config,
        bundled_config_schema,
        bundled_env_example,
        bundled_sample_machine,
        bundled_sample_test,
        host_paths,
    )

    if args.user:
        root = host_paths().config
        config_target = host_paths().user_config
        machines = host_paths().user_machines
        env_target = host_paths().user_env
    else:
        root = Path(args.dir).resolve()
        config_target = root / "config" / "runtime.yaml"
        machines = root / "machines"
        env_target = root / ".env"
    created: list[str] = []
    skipped: list[str] = []
    for directory in (config_target.parent, machines):
        if not directory.exists():
            directory.mkdir(parents=True, exist_ok=True)
            created.append(str(directory))
    templates = [
        (bundled_config(), config_target),
        (bundled_env_example(), env_target),
        (bundled_sample_machine(), machines / "hello.mkl"),
        (bundled_sample_test(), machines / "hello.test.yaml"),
    ]
    # Both modes get the schema next to runtime.yaml so the example's
    # yaml-language-server header validates in either location.
    templates.append((bundled_config_schema(), config_target.parent / "runtime.schema.json"))
    for source, target in templates:
        if target.exists():
            skipped.append(str(target))
        else:
            shutil.copyfile(source, target)
            created.append(str(target))
    result = CommandResult(
        command="init",
        ok=True,
        items=[{"name": p, "status": "ok"} for p in created]
        + [{"name": p, "status": "exists"} for p in skipped],
        summary={"created": len(created), "unchanged": len(skipped)},
    )
    emit_result(result, fmt=output_format(args.format), color=args.color)
    return 0


def _resolve_workspace(workspace: str | None) -> str:
    """Local ./machines when present, else the global XDG user machines root."""
    if workspace is not None:
        return workspace
    local = Path("./machines")
    if local.is_dir():
        return str(local)
    from .paths import host_paths

    return str(host_paths().user_machines)


def cmd_console(args: argparse.Namespace) -> int:
    """Launch the agent-first console TUI (ADR 0015)."""
    # Probe textual itself: console.app imports it lazily inside build_app, so
    # guarding only the module import would let a missing package escape to the
    # generic ERROR handler with no actionable hint.
    if importlib.util.find_spec("textual") is None:
        print(
            "the console needs the `textual` package (bundled by default since "
            "0.15.0) — reinstall mklang, or: pip install textual",
            file=sys.stderr,
        )
        return 2
    from .console.app import main as console_main
    from .config import load_provider

    missing = host.missing_key_message(load_provider(args.config, args.provider))
    if missing:
        # Fail before the TUI launches; otherwise the brain dies on its first turn.
        print(missing, file=sys.stderr)
        return 2
    return console_main(
        args.config,
        args.provider,
        _resolve_workspace(args.workspace),
        args.agent,
        continue_session=args.continue_session,
        session_id=args.session,
    )


def cmd_doctor(args: argparse.Namespace) -> int:
    """Diagnose the resolved setup: which layer wins for config, env, keys, machines."""
    import jsonschema
    import yaml

    from .config import ProviderConfig, load_env_files
    from .paths import (
        bundled_config_schema,
        host_paths,
        machine_layers,
        resolve_config_with_layer,
    )
    from .registry import load_stdlib_registry

    hp = host_paths()
    items: list[dict] = []
    ok = True
    resolved, layer = resolve_config_with_layer(args.config)
    cfg = None
    try:
        cfg = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        ok = False
        items.append(
            {"name": f"config {resolved} · layer={layer}", "status": "error", "errors": [str(exc)]}
        )
    else:
        valid = (
            isinstance(cfg, dict)
            and isinstance(cfg.get("providers"), dict)
            and cfg.get("active") in cfg["providers"]
        )
        if valid:
            items.append(
                {
                    "name": f"config {resolved} · layer={layer} · active={cfg['active']}",
                    "status": "ok",
                }
            )
        else:
            ok = False
            items.append(
                {
                    "name": f"config {resolved} · layer={layer}",
                    "status": "error",
                    "errors": ["must define `providers` and an `active` provider among them"],
                }
            )
            cfg = None
    if cfg:
        schema = json.loads(bundled_config_schema().read_text(encoding="utf-8"))
        violations = [
            f"{'/'.join(str(p) for p in err.path) or '<root>'}: {err.message}"
            for err in jsonschema.Draft7Validator(schema).iter_errors(cfg)
        ]
        if violations:
            items.append(
                {
                    "name": f"schema {resolved.name} · {len(violations)} finding(s)",
                    "status": "warning",
                    "warnings": violations,
                }
            )
    active = cfg["active"] if cfg else None
    project_env, user_env = load_env_files()
    items.append(
        {
            "name": f"env project={project_env or '-'} · user={user_env or '-'}",
            "status": "ok",
        }
    )
    if cfg:
        for pname, block in cfg["providers"].items():
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
    # Tool backends through the shared resolvers (ADR 0016) — the doctor
    # reports what the runtime would actually bind, plus the deciding layer.
    from . import fs, kb, mail, search
    from .toolconfig import parse_tools_block

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
    project_machines = Path("machines")
    machine_roots = [("project", project_machines)] if project_machines.is_dir() else []
    machine_roots += [(name, root) for name, root in reversed(machine_layers())]
    for lname, root in machine_roots:
        count = len(list(root.glob("*.mkl"))) if root.is_dir() else 0
        items.append({"name": f"machines {lname} {root} · {count} file", "status": "ok"})
    items.append({"name": f"machines stdlib · {len(load_stdlib_registry())}", "status": "ok"})
    items.append({"name": f"state sessions {hp.sessions}", "status": "ok"})
    items.append({"name": f"state checkpoints {hp.checkpoints}", "status": "ok"})
    result = CommandResult(
        command="doctor",
        ok=ok,
        items=items,
        summary={"layer": layer, "active": active or "-", "ok": ok},
    )
    emit_result(result, fmt=output_format(args.format), color=args.color)
    return 0 if ok else 1


def cmd_check(args: argparse.Namespace) -> int:
    ok = True
    items: list[dict] = []
    for path in args.machines:
        item = {"path": path, "status": "ok", "errors": [], "warnings": []}
        registry = {**base_registry(), **load_registry(Path(path).parent, validate=False)}
        try:
            machine = load_machine(path)
        except Exception as e:  # surface any load/validation failure
            msg = getattr(e, "message", str(e))
            item["status"] = "error"
            item["errors"].append(f"schema: {msg}")
            items.append(item)
            ok = False
            continue
        errors, warnings = semantic_check(machine, registry, strict=args.strict)
        item["warnings"].extend(warnings)
        item["errors"].extend(errors)
        if errors:
            ok = False
            item["status"] = "error"
        elif warnings:
            item["status"] = "warning"
        items.append(item)
    emit_result(
        CommandResult(command="check", ok=ok, items=items, summary={"files": len(items)}),
        fmt=output_format(args.format),
        color=args.color,
    )
    return 0 if ok else 1


def _getting_started() -> str:
    """The bare-`mklang` nudge: a short map for a first-time user."""
    return (
        f"mklang {__version__} — declarative LLM state machines.\n"
        "\n"
        "Get started:\n"
        "  mklang init          scaffold config, .env, and a sample machine\n"
        "  mklang test machines/hello.mkl --script machines/hello.test.yaml\n"
        "                       run the sample's scripted scenarios (no API key)\n"
        '  mklang run machines/hello.mkl --set task="say hello"\n'
        "  mklang console       interactive TUI\n"
        "  mklang doctor        check where config, keys, and machines resolve from\n"
        "\n"
        "Run `mklang --help` for all commands."
    )


def main(argv: list[str] | None = None) -> int:
    formatter = argparse.RawDescriptionHelpFormatter
    ap = argparse.ArgumentParser(
        prog="mklang",
        description="Author, validate, test, and run declarative LLM state machines.",
        epilog=(
            "Typical workflow:\n"
            "  mklang init\n"
            "  mklang test machines/hello.mkl --script machines/hello.test.yaml\n"
            "  mklang lint --strict machines/hello.mkl\n"
            "  mklang run machines/hello.mkl --set task=hello"
        ),
        formatter_class=formatter,
    )
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=False)

    def logging_args(parser):
        parser.add_argument(
            "--log-level",
            choices=LEVELS,
            default=None,
            help="process log level on stderr (default: MKLANG_LOG_LEVEL or warning)",
        )

    def presentation_args(parser, *, formats=("auto", "text", "json")):
        parser.add_argument(
            "--format",
            choices=formats,
            default="auto",
            help="output format (default: terminal-aware auto)",
        )
        parser.add_argument(
            "--color",
            choices=("auto", "always", "never"),
            default="auto",
            help="color policy for text output; NO_COLOR is honored",
        )

    r = sub.add_parser("run", help="execute a machine against a provider")
    r.add_argument("machine", help="machine path or registered machine name")
    r.add_argument("--config", default=None, help="runtime config (auto-discovered when omitted)")
    r.add_argument("--provider", default=None, help="override the config's `active` provider")
    r.add_argument("--set", action="append", default=[], metavar="k.path=value")
    r.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="cost budget: halt once total tokens reach this",
    )
    r.add_argument(
        "--checkpoint",
        default=None,
        metavar="PATH",
        help="on budget exhaustion suspend and write a resumable checkpoint here "
        "(contains the full context in plaintext; written 0600, see SPEC §11)",
    )
    r.add_argument(
        "--hitl",
        action="store_true",
        help="a fired escalate gate suspends for human review (checkpoint defaults "
        "to the XDG state root when --checkpoint is omitted); "
        "reply via `mklang resume --set`",
    )
    r.add_argument(
        "--strict",
        action="store_true",
        help="refuse to run a document whose mklang: version is unsupported "
        "(version-unsupported); default is a warning",
    )
    r.add_argument(
        "--workspace",
        default=None,
        metavar="DIR",
        help="workspace root for the fs data tools (default: MKLANG_FS_ROOT or the "
        "current directory — ADR 0024)",
    )
    r.add_argument(
        "--allow-write",
        action="store_true",
        help="grant write_file access to real disk under the workspace "
        "(default off in headless runs; MKLANG_FS_WRITE=1 is the env equivalent)",
    )
    r.add_argument(
        "--on-truncate",
        choices=("report", "halt"),
        default="report",
        help="when produce hits max_tokens/length: annotate the trace (report, default) "
        "or halt with state-error: output-truncated (halt) — ADR 0018",
    )
    presentation_args(r)
    logging_args(r)
    r.set_defaults(fn=cmd_run)

    s = sub.add_parser("resume", help="resume a suspended run from a checkpoint")
    s.add_argument("checkpoint", help="checkpoint JSON written by run/resume")
    s.add_argument("--config", default=None, help="runtime config (auto-discovered when omitted)")
    s.add_argument("--provider", default=None, help="override the config's `active` provider")
    s.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="k.path=value",
        help="inject values (e.g. the human reply) into the suspended run's context",
    )
    s.add_argument(
        "--hitl",
        action="store_true",
        help="keep suspending on escalate gates even if the checkpoint didn't record it",
    )
    s.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="new cost budget (total, including tokens spent before the suspend)",
    )
    s.add_argument("--machine", default=None, help="machine path override (if the .mkl moved)")
    s.add_argument(
        "--checkpoint",
        dest="checkpoint_out",
        default=None,
        metavar="PATH",
        help="where to write the checkpoint on re-suspension (default: overwrite the input)",
    )
    s.add_argument("--force", action="store_true", help="resume even if the machine file changed")
    s.add_argument(
        "--on-truncate",
        choices=("report", "halt"),
        default="report",
        help="produce truncation policy on resume (same as run; ADR 0018)",
    )
    presentation_args(s)
    logging_args(s)
    s.set_defaults(fn=cmd_resume)

    co = sub.add_parser("console", help="agent-first console TUI")
    co.add_argument("--config", default=None, help="runtime config (auto-discovered when omitted)")
    co.add_argument("--provider", default=None, help="override the config's `active` provider")
    co.add_argument(
        "--workspace",
        default=None,
        metavar="DIR",
        help="where authored machines live; writes are confined here "
        "(default: ./machines when present, else the XDG user machines dir)",
    )
    co.add_argument(
        "--agent",
        default=None,
        metavar="FILE.mkl",
        help="swap the console's brain with your own machine (same tool contract)",
    )
    co.add_argument(
        "--continue",
        dest="continue_session",
        action="store_true",
        help="reopen the most recent session (history, spend, consents)",
    )
    co.add_argument("--session", default=None, metavar="ID", help="reopen a specific session by id")
    co.set_defaults(fn=cmd_console)

    m = sub.add_parser("machines", help="list commissionable machines (stdlib, plugins) as JSON")
    m.add_argument(
        "--dir",
        default=None,
        metavar="DIR",
        help="also list the .mkl machines of a project directory",
    )
    presentation_args(m)
    logging_args(m)
    m.set_defaults(fn=cmd_machines)

    ini = sub.add_parser("init", help="scaffold project or user config without overwriting files")
    ini.add_argument(
        "--user", action="store_true", help="initialize the XDG user host instead of a project"
    )
    ini.add_argument(
        "--dir", default=".", metavar="DIR", help="project root (default: current directory)"
    )
    presentation_args(ini)
    logging_args(ini)
    ini.set_defaults(fn=cmd_init)

    d = sub.add_parser(
        "doctor", help="diagnose the resolved setup: config layer, env, keys, machine roots"
    )
    d.add_argument("--config", default=None, help="runtime config (auto-discovered when omitted)")
    presentation_args(d)
    logging_args(d)
    d.set_defaults(fn=cmd_doctor)

    c = sub.add_parser("check", help="validate machines (schema + semantics)")
    c.add_argument("machines", nargs="+")
    c.add_argument(
        "--strict",
        action="store_true",
        help="treat an unsupported mklang: version as an error (version-unsupported)",
    )
    presentation_args(c)
    logging_args(c)
    c.set_defaults(fn=cmd_check)

    li = sub.add_parser("lint", help="check + static analysis (dead gates, unread outputs, typos)")
    li.add_argument("machines", nargs="+")
    li.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 when static lint findings exist (--llm findings stay advisory)",
    )
    li.add_argument(
        "--llm",
        action="store_true",
        help="probe prose-gate ambiguity with a live judge (ADR 0010) — "
        "costs real tokens; advisory, non-deterministic",
    )
    li.add_argument("--config", default=None, help="runtime config (auto-discovered when omitted)")
    li.add_argument("--provider", default=None, help="override the config's `active` provider")
    li.add_argument(
        "--llm-samples",
        type=int,
        default=5,
        metavar="K",
        help="synthetic outputs per multi-gate state (default 5)",
    )
    li.add_argument(
        "--llm-repeats",
        type=int,
        default=3,
        metavar="R",
        help="judge repeats per synthetic output (default 3)",
    )
    presentation_args(li)
    logging_args(li)
    li.set_defaults(fn=cmd_lint)

    t = sub.add_parser(
        "test",
        help="run scenario tests against a machine with a scripted LLM (no API keys)",
    )
    t.add_argument("machine")
    t.add_argument(
        "--script",
        required=True,
        metavar="FILE",
        help="a .test.yaml of named scenarios (scripted llm/tools/hooks + expect)",
    )
    presentation_args(t)
    logging_args(t)
    t.set_defaults(fn=cmd_test)

    try:
        import argcomplete
    except ImportError:
        pass
    else:
        argcomplete.autocomplete(ap)

    args = ap.parse_args(argv)
    setup_process_logging(getattr(args, "log_level", None))
    if getattr(args, "fn", None) is None:
        print(_getting_started())
        return 0
    try:
        return args.fn(args)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        # Expected user errors should be handled by commands. This boundary keeps
        # plugin/config/session failures from dumping a traceback by default.
        if os.environ.get("MKLANG_DEBUG"):
            raise
        fmt = output_format(getattr(args, "format", "text"))
        result = CommandResult(
            command=args.cmd,
            ok=False,
            diagnostics=[
                Diagnostic(
                    "error",
                    str(exc),
                    code="unexpected-error",
                    hint="Set MKLANG_DEBUG=1 to include a traceback.",
                )
            ],
        )
        emit_result(result, fmt=fmt, color=getattr(args, "color", "auto"))
        return 2


if __name__ == "__main__":
    sys.exit(main())
