"""`mklang` command-line interface: run and check machines."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import host
from .checkpoint import load_checkpoint, save_checkpoint, verify_hash
from .engine import run
from .loader import load_machine, semantic_check
from .registry import base_registry, load_registry


def _build_llm(prov):
    from .providers import build_llm

    return build_llm(prov)


def _coerce(value: str):
    """JSON-parse a --set value (so lists/objects/numbers work); fall back to str."""
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return value


def _apply_sets(ctx: dict, sets: list[str]) -> dict:
    for kv in sets or []:
        key, value = kv.split("=", 1)
        host.set_path(ctx, key, _coerce(value))
    return ctx


def _prepare(args, machine_path: str):
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
        for w in err.warnings:
            print(f"# warning: {w}", file=sys.stderr)
        label = "ERROR" if err.kind == "load" else "error"
        for e in err.errors:
            print(f"{machine_path}: {label}: {e}", file=sys.stderr)
        return 2
    for w in p.warnings:
        print(f"# warning: {w}", file=sys.stderr)
    return p.prov, p.llm, p.registry, p.machine, p.tools, p.hooks


def _emit(res, checkpoint_path, machine, machine_path, cost_budget, hitl=False) -> int:
    """Print the result JSON; write a checkpoint on suspension. Exit: 0 done, 3 suspended, 1 halt."""
    out = host.build_output(res)
    if res.status == "suspended":
        save_checkpoint(
            checkpoint_path, machine.name, machine_path, res.error, res.frames, cost_budget, hitl
        )
        out["checkpoint"] = str(checkpoint_path)
        print(
            f"# suspended ({res.error}) — checkpoint written to {checkpoint_path}", file=sys.stderr
        )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if res.status == "done":
        return 0
    return 3 if res.status == "suspended" else 1


def cmd_run(args) -> int:
    if args.hitl and not args.checkpoint:
        print("--hitl requires --checkpoint (the suspension must land somewhere)", file=sys.stderr)
        return 2
    prep = _prepare(args, args.machine)
    if isinstance(prep, int):
        return prep
    prov, llm, registry, machine, tools, hooks = prep
    ctx = _apply_sets(dict(machine.context), args.set)
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
    )
    return _emit(res, args.checkpoint, machine, args.machine, args.max_tokens, hitl=args.hitl)


def cmd_resume(args) -> int:
    try:
        ck = load_checkpoint(args.checkpoint)
    except (OSError, ValueError) as e:
        print(f"{args.checkpoint}: ERROR: {e}", file=sys.stderr)
        return 2
    machine_path = args.machine or ck["machine_path"]
    try:
        hash_ok = verify_hash(ck, machine_path)
    except OSError as e:
        print(f"{machine_path}: ERROR: {e}", file=sys.stderr)
        return 2
    if not hash_ok:
        if not args.force:
            print(
                f"{machine_path}: ERROR: machine changed since checkpoint "
                f"(sha256 mismatch); use --force to resume anyway",
                file=sys.stderr,
            )
            return 2
        print(
            f"# warning: {machine_path} changed since checkpoint — resuming anyway", file=sys.stderr
        )
    prep = _prepare(args, machine_path)
    if isinstance(prep, int):
        return prep
    prov, llm, registry, machine, tools, hooks = prep
    cost_budget = args.max_tokens if args.max_tokens is not None else ck.get("cost_budget")
    if ck.get("reason") == "cost-exhausted" and cost_budget is not None:
        old = ck.get("cost_budget")
        if old is not None and cost_budget <= old:
            print(
                f"# warning: cost budget {cost_budget} is not above the exhausted "
                f"{old} — the run will suspend again immediately",
                file=sys.stderr,
            )
    out_path = args.checkpoint_out or args.checkpoint
    hitl = ck.get("hitl", False) or args.hitl
    # A human reply lands in the innermost frame's context (the suspended run).
    _apply_sets(ck["frames"][-1]["ctx"], args.set)
    print(f"# {machine.name} · resume · provider={prov.name} · tiers={prov.tiers}", file=sys.stderr)
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
    )
    return _emit(res, out_path, machine, machine_path, cost_budget, hitl=hitl)


def cmd_lint(args) -> int:
    from .lint import lint_machine

    llm = prov = None
    if args.llm:
        from .config import load_provider

        prov = load_provider(args.config, args.provider)
        llm = _build_llm(prov)
        print(
            f"# --llm probe: provider={prov.name} · advisory only, non-deterministic "
            f"(ADR 0010) — never a --strict error source",
            file=sys.stderr,
        )
    ok = True
    findings_total = 0
    for path in args.machines:
        registry = {**base_registry(), **load_registry(Path(path).parent, validate=False)}
        try:
            machine = load_machine(path)
        except Exception as e:  # surface any load/validation failure
            print(f"{path}: SCHEMA ERROR: {getattr(e, 'message', str(e))}")
            ok = False
            continue
        errors, warnings = semantic_check(machine, registry, strict=args.strict)
        findings = lint_machine(machine)
        findings_total += len(findings)
        for w in warnings:
            print(f"{path}: warning: {w}")
        for e in errors:
            print(f"{path}: error: {e}")
        for f in findings:
            print(f"{path}: lint: {f}")
        if llm is not None and not errors:
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
                print(f"{path}: llm: {f}")  # advisory: exempt from --strict on purpose
        if errors:
            ok = False
        elif not findings:
            print(f"{path}: ok")
    if not ok:
        return 1
    return 1 if (args.strict and findings_total) else 0


def cmd_test(args) -> int:
    """Run scenario tests against a machine with a scripted LLM (no API keys)."""
    import yaml

    from .scripttest import match_expectation, run_scenario

    registry = {**base_registry(), **load_registry(Path(args.machine).parent, validate=False)}
    try:
        machine = load_machine(args.machine)
    except Exception as e:  # surface any load/validation failure
        print(f"{args.machine}: SCHEMA ERROR: {getattr(e, 'message', str(e))}", file=sys.stderr)
        return 2
    registry[machine.name] = machine

    try:
        doc = yaml.safe_load(Path(args.script).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        print(f"{args.script}: ERROR: {e}", file=sys.stderr)
        return 2
    scenarios = (doc or {}).get("scenarios")
    if not scenarios:
        print(f"{args.script}: ERROR: no `scenarios:` list", file=sys.stderr)
        return 2

    all_pass = True
    for i, sc in enumerate(scenarios):
        name = sc.get("name", f"scenario[{i}]")
        expect = sc.get("expect")
        if expect is None:
            print(f"FAIL {name}: scenario has no `expect:` block")
            all_pass = False
            continue
        try:
            result = run_scenario(machine, registry, sc)
        except Exception as e:  # a scenario error is a failure, not a crash
            print(f"FAIL {name}: scenario raised {type(e).__name__}: {e}")
            all_pass = False
            continue
        mismatches = match_expectation(result, expect)
        if not mismatches:
            print(f"PASS {name}")
            continue
        all_pass = False
        first = mismatches[0]
        print(f"FAIL {name}")
        print(f"       {first.key}: expected {first.expected!r}, got {first.actual!r}")
        if len(mismatches) > 1:
            print(f"       (+{len(mismatches) - 1} more mismatch(es))")
    return 0 if all_pass else 1


def cmd_machines(args) -> int:
    """List commissionable machines as JSON: bundled stdlib, plugins, and the
    .mk files of a project directory (which shadow same-named bundled ones)."""
    from .registry import load_stdlib_registry

    stdlib = load_stdlib_registry()
    reg = base_registry()
    sources = {name: ("stdlib" if name in stdlib else "plugin") for name in reg}
    if args.dir:
        for name, m in load_registry(args.dir, validate=False).items():
            reg[name] = m
            sources[name] = "local"
    out = [host.describe_machine(reg[name], sources[name]) for name in sorted(reg)]
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_console(args) -> int:
    """Launch the agent-first console TUI (ADR 0015; needs the [console] extra)."""
    try:
        from .console.app import main as console_main
    except ImportError:
        print(
            "the console needs the `textual` package — install with: pip install 'mklang[console]'",
            file=sys.stderr,
        )
        return 2
    return console_main(args.config, args.provider, args.workspace, args.agent)


def cmd_check(args) -> int:
    ok = True
    for path in args.machines:
        registry = {**base_registry(), **load_registry(Path(path).parent, validate=False)}
        try:
            machine = load_machine(path)
        except Exception as e:  # surface any load/validation failure
            msg = getattr(e, "message", str(e))
            print(f"{path}: SCHEMA ERROR: {msg}")
            ok = False
            continue
        errors, warnings = semantic_check(machine, registry, strict=args.strict)
        for w in warnings:
            print(f"{path}: warning: {w}")
        for e in errors:
            print(f"{path}: error: {e}")
        if errors:
            ok = False
        else:
            print(f"{path}: ok")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mklang", description="Run and check mklang machines.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="execute a machine against a provider")
    r.add_argument("machine")
    r.add_argument("--config", default="config/runtime.example.yaml")
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
        help="a fired escalate gate suspends for human review (requires --checkpoint); "
        "reply via `mklang resume --set`",
    )
    r.add_argument(
        "--strict",
        action="store_true",
        help="refuse to run a document whose mklang: version is unsupported "
        "(version-unsupported); default is a warning",
    )
    r.set_defaults(fn=cmd_run)

    s = sub.add_parser("resume", help="resume a suspended run from a checkpoint")
    s.add_argument("checkpoint")
    s.add_argument("--config", default="config/runtime.example.yaml")
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
    s.add_argument("--machine", default=None, help="machine path override (if the .mk moved)")
    s.add_argument(
        "--checkpoint",
        dest="checkpoint_out",
        default=None,
        metavar="PATH",
        help="where to write the checkpoint on re-suspension (default: overwrite the input)",
    )
    s.add_argument("--force", action="store_true", help="resume even if the machine file changed")
    s.set_defaults(fn=cmd_resume)

    co = sub.add_parser("console", help="agent-first console TUI (needs the [console] extra)")
    co.add_argument("--config", default="config/runtime.example.yaml")
    co.add_argument("--provider", default=None, help="override the config's `active` provider")
    co.add_argument(
        "--workspace",
        default="./machines",
        metavar="DIR",
        help="where authored machines live; writes are confined here (default ./machines)",
    )
    co.add_argument(
        "--agent",
        default=None,
        metavar="FILE.mk",
        help="swap the console's brain with your own machine (same tool contract)",
    )
    co.set_defaults(fn=cmd_console)

    m = sub.add_parser("machines", help="list commissionable machines (stdlib, plugins) as JSON")
    m.add_argument(
        "--dir",
        default=None,
        metavar="DIR",
        help="also list the .mk machines of a project directory",
    )
    m.set_defaults(fn=cmd_machines)

    c = sub.add_parser("check", help="validate machines (schema + semantics)")
    c.add_argument("machines", nargs="+")
    c.add_argument(
        "--strict",
        action="store_true",
        help="treat an unsupported mklang: version as an error (version-unsupported)",
    )
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
    li.add_argument("--config", default="config/runtime.example.yaml")
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
    t.set_defaults(fn=cmd_test)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
