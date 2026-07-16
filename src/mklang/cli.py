"""`mklang` command-line interface: run and check machines."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_provider
from .engine import run
from .loader import check_tiers, load_machine, semantic_check
from .registry import load_registry


def _build_llm(prov):
    if prov.name == "anthropic":
        from .llm.anthropic import AnthropicLLM

        return AnthropicLLM(prov.api_key, prov.base_url)
    from .llm.openai_compat import OpenAICompatLLM

    return OpenAICompatLLM(prov.api_key, prov.base_url)


def _coerce(value: str):
    """JSON-parse a --set value (so lists/objects/numbers work); fall back to str."""
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return value


def _apply_sets(ctx: dict, sets: list[str]) -> dict:
    for kv in sets or []:
        key, value = kv.split("=", 1)
        cur = ctx
        parts = key.split(".")
        for p in parts[:-1]:
            nxt = cur.get(p)
            if not isinstance(nxt, dict):
                nxt = {}
                cur[p] = nxt
            cur = nxt
        cur[parts[-1]] = _coerce(value)
    return ctx


def cmd_run(args) -> int:
    prov = load_provider(args.config, args.provider)
    if not prov.api_key and prov.name != "local":
        print(f"# warning: no API key for provider '{prov.name}' — set it in .env", file=sys.stderr)
    llm = _build_llm(prov)
    directory = Path(args.machine).parent
    registry = load_registry(directory, validate=False)
    try:
        machine = load_machine(args.machine)
    except Exception as e:  # noqa: BLE001 — surface load/validation failure cleanly
        print(f"{args.machine}: ERROR: {getattr(e, 'message', str(e))}", file=sys.stderr)
        return 2
    registry[machine.name] = machine
    errors, warnings = semantic_check(machine, registry)
    errors.extend(check_tiers(machine, prov.tiers))
    for w in warnings:
        print(f"# warning: {w}", file=sys.stderr)
    if errors:
        for e in errors:
            print(f"{args.machine}: error: {e}", file=sys.stderr)
        return 2
    from .tools import BUILTINS

    for sid, s in machine.states.items():
        if s.kind == "tool" and s.tool not in BUILTINS:
            print(
                f"# warning: state '{sid}' uses tool '{s.tool}' not in the built-in "
                f"registry {sorted(BUILTINS)} — the run halts if it is reached",
                file=sys.stderr,
            )
    ctx = _apply_sets(dict(machine.context), args.set)
    print(f"# {machine.name} · provider={prov.name} · tiers={prov.tiers}", file=sys.stderr)
    res = run(
        machine,
        ctx,
        registry,
        llm,
        prov.tiers,
        prov.judge_model(),
        tier_params=prov.params,
        cost_budget=args.max_tokens,
        tools=BUILTINS,
    )
    out = {
        "status": res.status,
        "error": res.error,
        "result": res.result,
        "usage": res.usage,
        "trace": res.trace,
    }
    if res.at is not None:
        out["at"] = res.at
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if res.status == "done" else 1


def cmd_check(args) -> int:
    ok = True
    for path in args.machines:
        registry = load_registry(Path(path).parent, validate=False)
        try:
            machine = load_machine(path)
        except Exception as e:  # noqa: BLE001 — surface any load/validation failure
            msg = getattr(e, "message", str(e))
            print(f"{path}: SCHEMA ERROR: {msg}")
            ok = False
            continue
        errors, warnings = semantic_check(machine, registry)
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
    r.set_defaults(fn=cmd_run)

    c = sub.add_parser("check", help="validate machines (schema + semantics)")
    c.add_argument("machines", nargs="+")
    c.set_defaults(fn=cmd_check)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
