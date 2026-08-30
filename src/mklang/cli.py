# PYTHON_ARGCOMPLETE_OK
"""`mklang` command-line interface: run and check machines."""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import logging
import os
import shutil
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from . import __version__, host
from .checkpoint import load_checkpoint, save_checkpoint, taint_frame, verify_hash
from .cli_doctor import cmd_doctor
from .cli_parser import build_parser
from .config import ProviderConfig
from .engine import RunResult, run
from .llm.base import LLM
from .loader import load_machine, semantic_check
from .logs import setup_process_logging
from .model import Machine
from .presentation import (
    CommandResult,
    Diagnostic,
    emit_json,
    emit_machines_text,
    emit_result,
    emit_run_text,
    output_format,
)
from .registry import base_registry, load_path_registry

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
    """Shared run/resume setup.

    Returns (prov, llm, registry, machine, tools, hooks) or an exit code.
    """
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
    """Print the result JSON; write a checkpoint on suspension.

    Exit codes: 0 done, 3 suspended, 1 halt.
    """
    out = host.build_output(res)
    if res.status == "suspended":
        # A suspended run always carries reason + frames, and the callers only
        # enable suspension when a checkpoint path is set.
        assert checkpoint_path is not None and res.error is not None and res.frames is not None
        save_checkpoint(
            checkpoint_path,
            machine.name,
            machine_path,
            res.error,
            res.frames,
            cost_budget,
            hitl,
            step_budget=machine.budget,
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
        on_untrusted_flow=getattr(args, "untrusted_flow", "report"),
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
    if args.max_steps is not None and args.max_steps <= 0:
        return _input_error(args, "--max-steps must be a positive integer")
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
    if args.max_steps is not None:
        machine = replace(machine, budget=args.max_steps)
        previous_steps = max((int(f.get("steps", 0)) for f in ck["frames"]), default=0)
        if args.max_steps <= previous_steps:
            _log.warning(
                "step budget %s is not above the %s steps already spent — the run "
                "will suspend again immediately",
                args.max_steps,
                previous_steps,
            )
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
        on_untrusted_flow=getattr(args, "untrusted_flow", "report"),
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
        try:
            prov, llm, _ = host.prepare_provider(args.config, args.provider, build_llm=_build_llm)
        except host.PrepareError as err:
            result = CommandResult(
                command=args.cmd,
                ok=False,
                diagnostics=[
                    Diagnostic("error", message, code=f"prepare-{err.kind}")
                    for message in err.errors
                ],
            )
            fmt = output_format(args.format)
            emit_result(result, fmt=fmt, color=args.color, stderr=fmt == "text")
            return 2
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
        registry = {**base_registry(), **load_path_registry(path, validate=False)}
        try:
            machine = load_machine(path)
        except Exception as e:  # surface any load/validation failure
            item["status"] = "error"
            item["errors"].append(f"schema: {getattr(e, 'message', str(e))}")
            items.append(item)
            ok = False
            continue
        errors, warnings = semantic_check(machine, registry, strict=args.strict)
        try:
            source_text = Path(path).read_text(encoding="utf-8")
        except OSError:
            source_text = None
        findings = lint_machine(machine, source=source_text, registry=registry)
        findings_total += len(findings)
        # `note:` findings stay advisory under --strict (escalate policy); structural
        # smells (dead gates, repair-only, unresolved templates) still fail --strict.
        strict_hits = sum(1 for f in findings if not str(f).startswith("note:"))
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
        if args.strict and strict_hits:
            ok = False
        items.append(item)
    result = CommandResult(
        command="lint",
        ok=ok,
        items=items,
        summary={"files": len(items), "findings": findings_total},
    )
    emit_result(result, fmt=output_format(args.format), color=args.color)
    return 0 if ok else 1


def cmd_test(args: argparse.Namespace) -> int:
    """Run scenario tests against a machine with a scripted LLM (no API keys)."""
    import yaml

    from .scripttest import match_expectation, run_scenario

    registry = {**base_registry(), **load_path_registry(args.machine, validate=False)}
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

    if args.user and args.dir != ".":
        return _input_error(args, "--dir cannot be combined with --user")
    if not args.user and Path(args.dir).exists() and not Path(args.dir).is_dir():
        return _input_error(args, f"project root is not a directory: {args.dir}")
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
    templates = [
        (bundled_config(), config_target),
        (bundled_env_example(), env_target),
        (bundled_sample_machine(), machines / "hello.mkl"),
        (bundled_sample_test(), machines / "hello.test.yaml"),
    ]
    # Both modes get the schema next to runtime.yaml so the example's
    # yaml-language-server header validates in either location.
    templates.append((bundled_config_schema(), config_target.parent / "runtime.schema.json"))
    created_files: list[Path] = []
    created_dirs: list[Path] = []
    try:
        for directory in (config_target.parent, machines):
            if not directory.exists():
                directory.mkdir(parents=True, exist_ok=True)
                created_dirs.append(directory)
                created.append(str(directory))
        for source, target in templates:
            if target.exists():
                skipped.append(str(target))
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
            temporary = Path(temporary_name)
            try:
                with os.fdopen(fd, "wb") as handle, source.open("rb") as source_handle:
                    shutil.copyfileobj(source_handle, handle)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, target)
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
            created_files.append(target)
            created.append(str(target))
    except (OSError, shutil.Error) as exc:
        for path in reversed(created_files):
            path.unlink(missing_ok=True)
        for directory in sorted(created_dirs, key=lambda path: len(path.parts), reverse=True):
            with contextlib.suppress(OSError):
                directory.rmdir()
        return _input_error(args, f"initialization failed atomically: {exc}")
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
    """Resolve the console workspace, defaulting to the launch directory."""
    if workspace is not None:
        return workspace
    return str(Path.cwd().resolve())


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
    from .config import load_provider
    from .console.app import main as console_main

    workspace = _resolve_workspace(args.workspace)
    missing = host.missing_key_message(
        load_provider(args.config, args.provider, cwd=Path(workspace).resolve())
    )
    if missing:
        # Fail before the TUI launches; otherwise the brain dies on its first turn.
        print(missing, file=sys.stderr)
        return 2
    return console_main(
        args.config,
        args.provider,
        workspace,
        args.agent,
        continue_session=args.continue_session,
        session_id=args.session,
    )


def cmd_check(args: argparse.Namespace) -> int:
    ok = True
    items: list[dict] = []
    for path in args.machines:
        item = {"path": path, "status": "ok", "errors": [], "warnings": []}
        registry = {**base_registry(), **load_path_registry(path, validate=False)}
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
    ap = build_parser(
        {
            "run": cmd_run,
            "resume": cmd_resume,
            "console": cmd_console,
            "machines": cmd_machines,
            "init": cmd_init,
            "doctor": cmd_doctor,
            "check": cmd_check,
            "lint": cmd_lint,
            "test": cmd_test,
        }
    )
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
