"""MCP stdio server (ADR 0011, 0013): commission machines and get provenance back.

Tools: `run` / `resume` (commissioning), `list_machines` / `describe_machine`
(discovery of what may be commissioned), `check` (validation as structured
output). Transport only — everything sits above `engine.run` and reuses the
host seam (`host.prepare_*` / `host.build_output` / `host.check_machine`), so
parity with the CLI is by construction. Domain failures return a structured
`{"status": "error", ...}` payload; MCP tool errors are reserved for genuine
bugs. Nothing here may print to stdout — the stdio transport owns it. Provider
API keys resolve server-side from the environment.

Suspended runs live in an in-memory session store behind opaque single-use
handles; passing `checkpoint_path` additionally writes the CLI's file envelope
(0600) so a run can be resumed across processes — `resume` accepts either kind.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    # Real Context enables FastMCP's ctx injection; the annotation must resolve
    # from module globals because `from __future__ import annotations` stringifies
    # it. The fallback keeps `import mklang.mcp.server` working without the extra
    # (main() then shows the friendly install hint).
    from mcp.server.fastmcp import Context
except ImportError:  # pragma: no cover - exercised by the no-extra install

    class Context:  # placeholder type so annotations resolve; never instantiated
        pass


from .. import host
from ..checkpoint import load_checkpoint, save_checkpoint, verify_hash
from ..engine import run as run_machine
from ..registry import base_registry, load_stdlib_registry
from .sessions import Session, SessionStore

# None means the full ADR 0021 chain (project > user > /etc > bundled) via
# resolve_config — the same auto-discovery the CLI uses, so a server spawned
# outside a checkout still finds the user host config.
DEFAULT_CONFIG: str | None = None


def _build_llm(prov):
    from ..providers import build_llm

    return build_llm(prov)


def _error(slug: str, errors: list[str], warnings: list[str] | None = None) -> dict:
    return {"status": "error", "error": slug, "errors": errors, "warnings": warnings or []}


def _event_forwarder(ctx):
    """Bridge engine events to MCP logging notifications (ADR 0015 live seam).

    The forwarder is created on the server's event loop (FastMCP invokes sync
    tools there), but engine events may fire from fan-out worker threads too —
    so the captured loop plus `run_coroutine_threadsafe` is the one scheduling
    path safe from any thread, without blocking the emitter. Forwarding is
    isolated like the engine's own observer: a transport hiccup never touches
    the run. Returns None (no callback) when the request carries no context."""
    if ctx is None:
        return None
    import asyncio
    import json as _json

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None

    def forward(event: dict) -> None:
        try:
            coro = ctx.log(
                "info",
                _json.dumps(event, ensure_ascii=False, default=str),
                logger_name="mklang.event",
            )
            asyncio.run_coroutine_threadsafe(coro, loop)
        except Exception:
            pass

    return forward


def _finish(
    store: SessionStore,
    res,
    warnings: list[str],
    session: Session,
    checkpoint_path: str | None = None,
) -> dict:
    out = host.build_output(res)
    out["warnings"] = warnings
    if res.status == "suspended":
        session.frames = res.frames
        session.reason = res.error
        out["checkpoint"] = store.put(session)
        if checkpoint_path:
            save_checkpoint(
                checkpoint_path,
                session.machine.name,
                session.origin_path or "<inline>",
                res.error,
                res.frames,
                session.cost_budget,
                session.hitl,
                machine_source=session.origin_source,
            )
            out["checkpoint_file"] = str(checkpoint_path)
    return out


def _session_from(
    p: host.Prepared,
    cost_budget,
    hitl,
    origin_path,
    origin_source,
    on_truncate: str = "report",
) -> Session:
    return Session(
        machine=p.machine,
        registry=p.registry,
        llm=p.llm,
        prov=p.prov,
        tools=p.tools,
        hooks=p.hooks,
        frames=[],
        cost_budget=cost_budget,
        hitl=hitl,
        reason=None,
        origin_path=origin_path,
        origin_source=origin_source,
        on_truncate=on_truncate,
    )


def run_tool(
    store: SessionStore,
    defaults: dict,
    source: str | None = None,
    path: str | None = None,
    inputs: dict | None = None,
    cost_budget: int | None = None,
    config: str | None = None,
    provider: str | None = None,
    hitl: bool = False,
    strict: bool = False,
    checkpoint_path: str | None = None,
    on_event=None,
    on_truncate: str = "report",
) -> dict:
    if (source is None) == (path is None):
        return _error("invalid-request", ["provide exactly one of `source` or `path`"])
    if on_truncate not in ("report", "halt"):
        return _error(
            "invalid-request",
            [f"on_truncate must be 'report' or 'halt', got {on_truncate!r}"],
        )
    cfg = config or defaults["config"]
    prov_name = provider or defaults["provider"]
    try:
        if source is not None:
            p = host.prepare_source(cfg, prov_name, source, strict=strict, build_llm=_build_llm)
        else:
            p = host.prepare_path(cfg, prov_name, path, strict=strict, build_llm=_build_llm)
    except host.PrepareError as e:
        return _error("prepare-failed", e.errors, e.warnings)
    ctx = dict(p.machine.context)
    for k, v in (inputs or {}).items():
        host.set_path(ctx, k, v)
    host.inject_host_defaults(ctx)  # fill declared empty context.today, etc.
    res = run_machine(
        p.machine,
        ctx,
        p.registry,
        p.llm,
        p.prov.tiers,
        p.prov.judge_override(),
        tier_params=p.prov.params,
        cost_budget=cost_budget,
        tools=p.tools,
        hooks=p.hooks,
        suspendable=True,
        escalate_suspend=hitl,
        on_event=on_event,
        on_truncate=on_truncate,
    )
    session = _session_from(p, cost_budget, hitl, path, source, on_truncate=on_truncate)
    return _finish(store, res, p.warnings, session, checkpoint_path)


def _rerun(session: Session, frames: list[dict], budget, on_event=None, on_truncate=None) -> object:
    return run_machine(
        session.machine,
        dict(session.machine.context),
        session.registry,
        session.llm,
        session.prov.tiers,
        session.prov.judge_override(),
        tier_params=session.prov.params,
        cost_budget=budget,
        tools=session.tools,
        hooks=session.hooks,
        suspendable=True,
        escalate_suspend=session.hitl,
        resume=frames,
        on_event=on_event,
        on_truncate=on_truncate if on_truncate is not None else session.on_truncate,
    )


def _budget_warning(reason, old, new) -> list[str]:
    if reason == "cost-exhausted" and new is not None and old is not None and new <= old:
        return [
            f"cost budget {new} is not above the exhausted {old} — "
            f"the run will suspend again immediately"
        ]
    return []


def _resume_from_file(
    store: SessionStore,
    defaults: dict,
    ck_path: str,
    inputs: dict | None,
    cost_budget: int | None,
    checkpoint_path: str | None,
    force: bool,
    on_event=None,
    on_truncate: str = "report",
) -> dict:
    try:
        ck = load_checkpoint(ck_path)
    except (OSError, ValueError) as e:
        return _error("bad-checkpoint", [str(e)])
    source = ck.get("machine_source")
    machine_path = ck["machine_path"]
    try:
        if source is not None:
            p = host.prepare_source(
                defaults["config"], defaults["provider"], source, build_llm=_build_llm
            )
        else:
            if not verify_hash(ck, machine_path) and not force:
                return _error(
                    "machine-changed",
                    [f"{machine_path} changed since checkpoint (sha256 mismatch); pass force=true"],
                )
            p = host.prepare_path(
                defaults["config"], defaults["provider"], machine_path, build_llm=_build_llm
            )
    except OSError as e:
        return _error("bad-checkpoint", [str(e)])
    except host.PrepareError as e:
        return _error("prepare-failed", e.errors, e.warnings)
    budget = cost_budget if cost_budget is not None else ck.get("cost_budget")
    warnings = _budget_warning(ck.get("reason"), ck.get("cost_budget"), budget)
    for k, v in (inputs or {}).items():
        host.set_path(ck["frames"][-1]["ctx"], k, v)
    session = _session_from(
        p,
        budget,
        ck.get("hitl", False),
        None if source else machine_path,
        source,
        on_truncate=on_truncate,
    )
    res = _rerun(session, ck["frames"], budget, on_event, on_truncate)
    # Re-suspension persists to the file it came from unless redirected.
    return _finish(store, res, warnings, session, checkpoint_path or ck_path)


def resume_tool(
    store: SessionStore,
    checkpoint: str,
    inputs: dict | None = None,
    cost_budget: int | None = None,
    *,
    defaults: dict | None = None,
    checkpoint_path: str | None = None,
    force: bool = False,
    on_event=None,
    on_truncate: str | None = None,
) -> dict:
    defaults = defaults or {"config": DEFAULT_CONFIG, "provider": None}
    s = store.get(checkpoint)
    if s is None:
        if Path(checkpoint).is_file():
            return _resume_from_file(
                store,
                defaults,
                checkpoint,
                inputs,
                cost_budget,
                checkpoint_path,
                force,
                on_event,
                on_truncate=on_truncate or "report",
            )
        return _error(
            "unknown-checkpoint",
            [
                f"no suspended session for handle '{checkpoint}' (handles are single-use) "
                f"and no such checkpoint file"
            ],
        )
    budget = cost_budget if cost_budget is not None else s.cost_budget
    warnings = _budget_warning(s.reason, s.cost_budget, budget)
    # A human reply lands in the innermost frame's context (the suspended run).
    for k, v in (inputs or {}).items():
        host.set_path(s.frames[-1]["ctx"], k, v)
    if on_truncate is not None:
        if on_truncate not in ("report", "halt"):
            return _error(
                "invalid-request",
                [f"on_truncate must be 'report' or 'halt', got {on_truncate!r}"],
            )
        s.on_truncate = on_truncate
    res = _rerun(s, s.frames, budget, on_event, s.on_truncate)
    store.delete(checkpoint)
    s.cost_budget = budget
    return _finish(store, res, warnings, s, checkpoint_path)


def list_machines_tool() -> dict:
    stdlib = load_stdlib_registry()
    reg = base_registry()
    return {
        "machines": [
            {
                "name": name,
                "source": "stdlib" if name in stdlib else "plugin",
                "result": reg[name].result,
                "budget": reg[name].budget,
                "context_keys": sorted(reg[name].context),
            }
            for name in sorted(reg)
        ]
    }


def describe_machine_tool(name: str) -> dict:
    stdlib = load_stdlib_registry()
    reg = base_registry()
    if name not in reg:
        return _error("unknown-machine", [f"no bundled machine '{name}' (see list_machines)"])
    return host.describe_machine(reg[name], "stdlib" if name in stdlib else "plugin")


def check_tool(source: str | None = None, path: str | None = None, strict: bool = False) -> dict:
    if (source is None) == (path is None):
        return _error("invalid-request", ["provide exactly one of `source` or `path`"])
    return host.check_machine(source, path, strict=strict)


def create_server(config: str | None = DEFAULT_CONFIG, provider: str | None = None):
    """Build the FastMCP server. Requires the `mcp` package (`pip install mklang[mcp]`)."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("mklang")
    store = SessionStore()
    defaults = {"config": config, "provider": provider}

    @server.tool()
    def run(
        source: str | None = None,
        path: str | None = None,
        inputs: dict | None = None,
        cost_budget: int | None = None,
        config: str | None = None,
        provider: str | None = None,
        hitl: bool = False,
        strict: bool = False,
        checkpoint_path: str | None = None,
        on_truncate: str = "report",
        ctx: Context = None,
    ) -> dict:
        """Commission an mklang machine and return its result with full provenance
        (trace + usage). Pass the machine as inline `.mk` YAML via `source`, OR via
        `path`: a filesystem path (sibling `.mk` files become callable machines) or
        the bare name of a bundled machine (see list_machines) — exactly one of the
        two. Inline sources may `call:` bundled machines. `inputs` merges values
        into the machine's context by dotted key (e.g. {"ticket.body": "..."});
        list values are allowed. `cost_budget` caps total tokens. `on_truncate` is
        `report` (default: annotate truncated produce) or `halt` (ADR 0018). With
        `hitl: true`, a fired escalate gate suspends the run: the reply has
        `status: "suspended"` and an opaque single-use `checkpoint` handle for
        `resume`; pass `checkpoint_path` to ALSO persist the suspension to a file
        resumable across processes. While the run executes, live engine events
        stream as logging notifications (logger "mklang.event", JSON payloads).
        A `status: "error"` reply carries validation `errors` (nothing was
        run)."""
        return run_tool(
            store,
            defaults,
            source=source,
            path=path,
            inputs=inputs,
            cost_budget=cost_budget,
            config=config,
            provider=provider,
            hitl=hitl,
            strict=strict,
            checkpoint_path=checkpoint_path,
            on_event=_event_forwarder(ctx),
            on_truncate=on_truncate,
        )

    @server.tool()
    def resume(
        checkpoint: str,
        inputs: dict | None = None,
        cost_budget: int | None = None,
        checkpoint_path: str | None = None,
        force: bool = False,
        on_truncate: str | None = None,
        ctx: Context = None,
    ) -> dict:
        """Resume a suspended run. `checkpoint` is either the opaque single-use
        handle from this server's `run`, or the path of a checkpoint FILE written
        via `checkpoint_path` (cross-process durable; a file from `mklang run
        --checkpoint` works too). `inputs` injects values into the suspended
        context — e.g. the human reply as {"human.reply": "approve"}.
        `cost_budget` sets a new total token budget (must exceed the exhausted one
        to make progress). `on_truncate` overrides the session policy if set.
        If the run suspends again, the reply carries a NEW handle, and a file
        checkpoint is rewritten in place (or to `checkpoint_path`). `force: true`
        resumes even if the machine file changed since the checkpoint."""
        return resume_tool(
            store,
            checkpoint,
            inputs=inputs,
            cost_budget=cost_budget,
            defaults=defaults,
            checkpoint_path=checkpoint_path,
            force=force,
            on_event=_event_forwarder(ctx),
            on_truncate=on_truncate,
        )

    @server.tool()
    def list_machines() -> dict:
        """List the machines this server can commission by name: the bundled
        `std_*` architecture stdlib plus any `mklang.machines` plugins. Each entry
        has the context keys to set and the result key that comes back. Use
        describe_machine for the full contract."""
        return list_machines_tool()

    @server.tool()
    def describe_machine(name: str) -> dict:
        """The full commissionable contract of a bundled machine: entry state,
        budget, tiers, result key, context defaults (what `inputs` may override),
        and a state-by-state summary."""
        return describe_machine_tool(name)

    @server.tool()
    def check(source: str | None = None, path: str | None = None, strict: bool = False) -> dict:
        """Validate a machine WITHOUT running it — schema + semantic checks + lint
        smells as structured output: {ok, errors, warnings, lint}. Same validators
        as `mklang check`/`mklang lint`. Exactly one of `source` (inline `.mk`
        YAML) or `path`. Use it as the authoring loop before commissioning `run`."""
        return check_tool(source=source, path=path, strict=strict)

    return server


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="mklang-mcp",
        description="mklang MCP stdio server: commission machines via run/resume (ADR 0011).",
    )
    ap.add_argument(
        "--config", default=DEFAULT_CONFIG, help="runtime config (auto-discovered when omitted)"
    )
    ap.add_argument("--provider", default=None, help="override the config's `active` provider")
    args = ap.parse_args(argv)
    try:
        server = create_server(args.config, args.provider)
    except ImportError:
        print(
            "the MCP surface needs the `mcp` package — install with: pip install 'mklang[mcp]'",
            file=sys.stderr,
        )
        return 2
    server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
