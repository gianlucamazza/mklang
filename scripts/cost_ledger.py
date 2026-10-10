"""USD cost ledger and hard cap for the Evidence Release live runner.

Owner decision D1: the whole evidence release (every provider, every named
experiment) has a hard cap of $10. Before a run starts, the runner estimates
its cost from a pinned price table and the documented token figures below. If
``ledger total + estimate > $10``, the run is refused. After a call, the
actual provider token counts are written to ``costs.jsonl``.

Token figures used for the *pre-run* estimate are cited, not invented:

- Gate-divergence and first-true (same small synthetic corpus): GitHub issue
  `#60` prices one four-machine x 3-repeat Anthropic pass as
  ``~12 small synthetic runs ≈ ~30k tokens``. The per-run figure is
  ``30000 / 12``. There is no published input/output split, so the estimate
  charges the whole count at ``max(input, output)`` list price.
- Repair-convergence has no published token row. The pre-run estimate uses
  the harness ``cost_budget`` of 40_000 tokens as a ceiling (the engine
  stops charging at that cap). That is an upper bound, not a forecast.

USD after a run is ``tokens * pinned list price``. Adapters today record
token usage only; they do not surface a provider invoice field. If a later
adapter exposes one, prefer it and set ``usd_source`` to ``provider``.
"""

from __future__ import annotations

import json
from argparse import ArgumentParser, Namespace
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

USD_CAP = 10.0
LEDGER_NAME = "costs.jsonl"
PRICE_RETRIEVED = "2026-10-10"

# Issue #60: "~12 small synthetic runs ≈ ~30k tokens".
GATE_DIVERGENCE_ISSUE_60_TOKENS = 30_000
GATE_DIVERGENCE_ISSUE_60_RUNS = 12
TOKENS_PER_SMALL_SYNTHETIC_RUN = GATE_DIVERGENCE_ISSUE_60_TOKENS // GATE_DIVERGENCE_ISSUE_60_RUNS

# scripts/repair_convergence.py passes cost_budget=40_000 to engine.run.
REPAIR_COST_BUDGET_TOKENS = 40_000

# scripts/gate_divergence.py passes cost_budget=20_000. Used only as a
# published ceiling in the estimate table, not as the pre-run guard figure
# (the #60 per-run number is the cited estimate for that corpus).
GATE_DIVERGENCE_COST_BUDGET_TOKENS = 20_000


class CapExceededError(RuntimeError):
    """Starting this run would put ledger total + estimate over the hard cap."""


class UnknownPriceError(KeyError):
    """No pinned list price for this provider/model pair."""


@dataclass(frozen=True)
class Price:
    """USD per 1M tokens, with the page and date the number was read from."""

    input_usd_per_mtok: float
    output_usd_per_mtok: float
    source: str
    retrieved: str
    notes: str = ""


# Conservative list prices: DeepSeek uses the official *peak cache-miss* /
# *peak output* column so an estimate never assumes off-peak or a cache hit.
PRICES: dict[tuple[str, str], Price] = {
    ("deepseek", "deepseek-v4-flash"): Price(
        input_usd_per_mtok=0.30,
        output_usd_per_mtok=1.20,
        source="https://api-docs.deepseek.com/quick_start/pricing",
        retrieved=PRICE_RETRIEVED,
        notes=(
            "Peak cache-miss input $0.30 / peak output $1.20 per 1M. Official "
            "page bills legacy `deepseek-v4-flash` as `deepseek-flash` "
            "(DeepSeek-V4.1-Flash). Off-peak is half; cache-hit input is lower."
        ),
    ),
    ("deepseek", "deepseek-flash"): Price(
        input_usd_per_mtok=0.30,
        output_usd_per_mtok=1.20,
        source="https://api-docs.deepseek.com/quick_start/pricing",
        retrieved=PRICE_RETRIEVED,
        notes="Same card as deepseek-v4-flash (retired alias served by V4.1-Flash).",
    ),
    ("openai", "gpt-5.6-luna"): Price(
        input_usd_per_mtok=0.20,
        output_usd_per_mtok=1.20,
        source="https://developers.openai.com/api/docs/models/gpt-5.6-luna",
        retrieved=PRICE_RETRIEVED,
        notes="Also listed on https://developers.openai.com/api/docs/pricing (standard context).",
    ),
    ("openai", "gpt-5.6-terra"): Price(
        input_usd_per_mtok=2.00,
        output_usd_per_mtok=12.00,
        source="https://developers.openai.com/api/docs/pricing",
        retrieved=PRICE_RETRIEVED,
        notes="Standard-context column. Evidence-release config pins openai to luna.",
    ),
    ("openrouter", "anthropic/claude-sonnet-5"): Price(
        input_usd_per_mtok=2.00,
        output_usd_per_mtok=10.00,
        source="https://openrouter.ai/anthropic/claude-sonnet-5",
        retrieved=PRICE_RETRIEVED,
        notes="OpenRouter list price for the model id already in runtime.example.yaml.",
    ),
}


@dataclass(frozen=True)
class TokenEstimate:
    """Cited pre-run token figure. ``kind`` says how to turn it into USD."""

    tokens: int
    kind: str  # "issue-60-unsplit" | "cost-budget-ceiling"
    source: str
    notes: str


TOKEN_ESTIMATES: dict[str, TokenEstimate] = {
    "gate-divergence": TokenEstimate(
        tokens=TOKENS_PER_SMALL_SYNTHETIC_RUN,
        kind="issue-60-unsplit",
        source="https://github.com/gianlucamazza/mklang/issues/60",
        notes=(
            f"{GATE_DIVERGENCE_ISSUE_60_TOKENS} tokens / "
            f"{GATE_DIVERGENCE_ISSUE_60_RUNS} runs from the issue body. "
            "No input/output split was published; the estimate charges the "
            "whole count at max(input, output) list price."
        ),
    ),
    "first-true-fidelity": TokenEstimate(
        tokens=TOKENS_PER_SMALL_SYNTHETIC_RUN,
        kind="issue-60-unsplit",
        source="https://github.com/gianlucamazza/mklang/issues/60",
        notes=(
            "No live first-true token row exists. The pre-run figure is the "
            "same #60 per-run count used for gate-divergence (the pinned "
            "corpus is that suite). Live first-true is judge-only and should "
            "be smaller; this is an upper bound borrowed from that estimate, "
            "not a measurement."
        ),
    ),
    "repair-convergence": TokenEstimate(
        tokens=REPAIR_COST_BUDGET_TOKENS,
        kind="cost-budget-ceiling",
        source="scripts/repair_convergence.py cost_budget=40_000",
        notes=(
            "No published repair-convergence token row. The engine "
            "cost_budget is the hard token ceiling for one run."
        ),
    ),
}


def lookup_price(provider: str, model: str) -> Price:
    try:
        return PRICES[(provider, model)]
    except KeyError as exc:
        known = ", ".join(f"{p}/{m}" for p, m in sorted(PRICES))
        raise UnknownPriceError(
            f"no pinned list price for {provider}/{model} (have: {known})"
        ) from exc


def usd_from_tokens(price: Price, input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens * price.input_usd_per_mtok + output_tokens * price.output_usd_per_mtok
    ) / 1_000_000


def estimate_run_usd(provider: str, model: str, experiment: str) -> tuple[float, dict[str, Any]]:
    """Conservative USD for one not-yet-started run. Does not invent a token split."""
    if experiment not in TOKEN_ESTIMATES:
        raise KeyError(f"no token estimate for experiment {experiment!r}")
    spec = TOKEN_ESTIMATES[experiment]
    price = lookup_price(provider, model)
    if spec.kind in {"issue-60-unsplit", "cost-budget-ceiling"}:
        # Charge the whole cited count at the more expensive side. That is a
        # bound, not a claim about the input/output mix.
        rate = max(price.input_usd_per_mtok, price.output_usd_per_mtok)
        usd = spec.tokens * rate / 1_000_000
        input_tokens, output_tokens = 0, spec.tokens
    else:
        raise ValueError(f"unknown token-estimate kind {spec.kind!r}")
    return usd, {
        "provider": provider,
        "model": model,
        "experiment": experiment,
        "tokens": spec.tokens,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "usd": usd,
        "kind": spec.kind,
        "token_source": spec.source,
        "token_notes": spec.notes,
        "price_source": price.source,
        "price_retrieved": price.retrieved,
        "price_notes": price.notes,
        "input_usd_per_mtok": price.input_usd_per_mtok,
        "output_usd_per_mtok": price.output_usd_per_mtok,
    }


def parse_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSON ({exc.msg})") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_no}: ledger row must be an object")
        rows.append(row)
    return rows


def ledger_total_usd(path: Path) -> float:
    return sum(float(row.get("usd") or 0) for row in parse_ledger(path))


def refuse_if_over_cap(
    ledger: Path,
    *,
    provider: str,
    model: str,
    experiment: str,
    cap: float = USD_CAP,
    pending_usd: float = 0.0,
) -> float:
    """Return the USD estimate, or raise CapExceededError without spending."""
    estimate, meta = estimate_run_usd(provider, model, experiment)
    spent = ledger_total_usd(ledger)
    projected = spent + pending_usd + estimate
    if projected > cap:
        raise CapExceededError(
            f"refusing {experiment} {provider}/{model}: ledger ${spent:.6f} + "
            f"pending ${pending_usd:.6f} + estimate ${estimate:.6f} = "
            f"${projected:.6f} exceeds cap ${cap:.2f} "
            f"(token source: {meta['token_source']})"
        )
    return estimate


def append_cost_row(
    ledger: Path,
    *,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    run_id: str,
    experiment: str,
    timestamp: str | None = None,
    usd: float | None = None,
    usd_source: str = "price-table",
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    price = lookup_price(provider, model)
    if usd is None:
        usd = usd_from_tokens(price, input_tokens, output_tokens)
        usd_source = "price-table"
    row: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "usd": usd,
        "usd_source": usd_source,
        "price_source": price.source,
        "price_retrieved": price.retrieved,
        "run_id": run_id,
        "timestamp": timestamp
        or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "experiment": experiment,
    }
    if extra:
        row.update(extra)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return row


def usage_from_row(row: Mapping[str, Any]) -> tuple[int, int]:
    usage = row.get("usage") or {}
    if not isinstance(usage, Mapping):
        return 0, 0
    return int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0)


def run_id_for(row: Mapping[str, Any], experiment: str) -> str:
    machine = row.get("machine") or row.get("item") or "unknown"
    provider = row.get("provider") or "unknown"
    repeat = row.get("repeat", 0)
    started = row.get("started_at") or ""
    arm = row.get("arm")
    parts = [experiment, str(provider), str(machine), str(repeat)]
    if arm:
        parts.append(str(arm))
    if started:
        parts.append(str(started))
    return "/".join(parts)


def add_cost_arguments(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--cost-ledger",
        type=Path,
        default=None,
        help="append one costs.jsonl line per run; refuse to start past --usd-cap",
    )
    parser.add_argument(
        "--usd-cap",
        type=float,
        default=USD_CAP,
        help=f"hard USD cap over the whole ledger (default {USD_CAP:.0f})",
    )
    parser.add_argument(
        "--cost-experiment",
        default=None,
        help="experiment name for the ledger/guard (default: the script's experiment)",
    )


def maybe_guard(
    args: Namespace,
    *,
    provider: str,
    model: str,
    experiment: str,
    pending_usd: float = 0.0,
) -> float:
    ledger = getattr(args, "cost_ledger", None)
    if ledger is None:
        return 0.0
    cap = float(getattr(args, "usd_cap", USD_CAP))
    named = getattr(args, "cost_experiment", None) or experiment
    return refuse_if_over_cap(
        Path(ledger),
        provider=provider,
        model=model,
        experiment=named,
        cap=cap,
        pending_usd=pending_usd,
    )


def maybe_record(args: Namespace, row: Mapping[str, Any], *, experiment: str) -> None:
    ledger = getattr(args, "cost_ledger", None)
    if ledger is None:
        return
    named = getattr(args, "cost_experiment", None) or experiment
    provider = str(row.get("provider") or "unknown")
    model = str(row.get("model") or "unknown")
    if row.get("skipped") or not row.get("usage"):
        extra = {"status": row.get("status"), "skipped": bool(row.get("skipped"))}
        if row.get("reason"):
            extra["reason"] = row.get("reason")
        try:
            lookup_price(provider, model)
        except UnknownPriceError:
            return
        append_cost_row(
            Path(ledger),
            provider=provider,
            model=model,
            input_tokens=0,
            output_tokens=0,
            run_id=run_id_for(row, named),
            experiment=named,
            timestamp=str(row["started_at"]) if row.get("started_at") else None,
            usd=0.0,
            usd_source="no-call",
            extra=extra,
        )
        return
    input_tokens, output_tokens = usage_from_row(row)
    append_cost_row(
        Path(ledger),
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        run_id=run_id_for(row, named),
        experiment=named,
        timestamp=str(row["started_at"]) if row.get("started_at") else None,
    )
