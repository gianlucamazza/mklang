#!/usr/bin/env python3
"""Named Evidence Release experiments: estimate (no API) or live under the $10 cap.

  uv run python scripts/run_evidence_release.py --estimate
  uv run python scripts/run_evidence_release.py --estimate --experiment gate-divergence
  uv run python scripts/run_evidence_release.py --live --experiment first-true-live

`--estimate` never calls a provider. `--live` is for GitHub Actions
(`evidence-live.yml`) after Lab review — do not run it from a prep VM.

mklang can reach Anthropic models through the builtin `openrouter` OpenAI-
compatible adapter and a `vendor/model` id. The named #60 experiment uses
`config/evidence-release.yaml` with every OpenRouter tier set to
`anthropic/claude-sonnet-5`. The native `anthropic` adapter is not used
(no `ANTHROPIC_API_KEY` in Actions).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.cost_ledger import (  # noqa: E402
    EVIDENCE_LIVE_WORKFLOW,
    LEDGER_NAME,
    PRICES,
    TOKEN_ESTIMATES,
    USD_CAP,
    UnmergedLedgerError,
    append_dispatch_marker,
    estimate_run_usd,
    ledger_total_usd,
    require_prior_live_runs_in_ledger,
)

RELEASE_DIR = ROOT / "evidence" / "2026-10-evidence-release"
DEFAULT_CONFIG = ROOT / "config" / "evidence-release.yaml"

# The 2026-08-09 seven-machine suite (four shapes + boundary corpus).
# `--machines all` also includes later hostile_* fixtures; those are not this
# named experiment.
SEVEN_MACHINES = (
    "gate_divergence",
    "sentiment_borderline",
    "severity_escalate",
    "grounding_repair",
    "threshold_edge",
    "priority_shadow",
    "none_holds",
)


@dataclass(frozen=True)
class PlannedRun:
    experiment: str
    provider: str
    model: str
    label: str


@dataclass(frozen=True)
class NamedExperiment:
    name: str
    experiment: str
    description: str
    providers: tuple[str, ...]
    models: dict[str, str]
    run_count: int
    argv: tuple[str, ...]
    notes: str


def _tip_sha() -> str | None:
    if not (ROOT / ".git").exists():
        return None
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def named_experiments() -> dict[str, NamedExperiment]:
    seven = ",".join(SEVEN_MACHINES)
    config = str(DEFAULT_CONFIG)
    deepseek_model = "deepseek-v4-flash"
    openai_model = "gpt-5.6-luna"
    claude_model = "anthropic/claude-sonnet-5"
    return {
        "gate-divergence": NamedExperiment(
            name="gate-divergence",
            experiment="gate-divergence",
            description="Seven-machine suite on DeepSeek + OpenAI.",
            providers=("deepseek", "openai"),
            models={"deepseek": deepseek_model, "openai": openai_model},
            run_count=len(SEVEN_MACHINES) * 2 * 3,
            argv=(
                "scripts/gate_divergence.py",
                "--config",
                config,
                "--machines",
                seven,
                "--providers",
                "deepseek,openai",
                "--repeats",
                "3",
            ),
            notes=(
                "7 machines x 2 providers x 3 repeats = 42 runs. Hostile "
                "fixtures omitted. No --paraphrase."
            ),
        ),
        "gate-divergence-anthropic-openrouter": NamedExperiment(
            name="gate-divergence-anthropic-openrouter",
            experiment="gate-divergence",
            description="#60 third provider: Claude via OpenRouter (no Anthropic key).",
            providers=("openrouter",),
            models={"openrouter": claude_model},
            run_count=len(SEVEN_MACHINES) * 3,
            argv=(
                "scripts/gate_divergence.py",
                "--config",
                config,
                "--machines",
                seven,
                "--providers",
                "openrouter",
                "--repeats",
                "3",
            ),
            notes=(
                "7 machines x 3 repeats on openrouter/`anthropic/claude-sonnet-5`. "
                "#60 priced 4 machines x 3 as ~30k tokens; this is the current "
                "seven-machine suite. Provider field is `openrouter`; model id "
                "is the Anthropic one."
            ),
        ),
        "repair-convergence": NamedExperiment(
            name="repair-convergence",
            experiment="repair-convergence",
            description="ADR 0031 §3 second provider (OpenAI) with the three comparison arms.",
            providers=("openai",),
            models={"openai": openai_model},
            run_count=6 * 3 * 3,
            argv=(
                "scripts/repair_convergence.py",
                "--config",
                config,
                "--provider",
                "openai",
                "--repeats",
                "3",
                "--arms",
                "first_attempt,plain_resample,feedback_repair",
            ),
            notes=(
                "6 corpus items x 3 arms x 3 repeats = 54 runs. DeepSeek already "
                "has the 2026-08-20 row; this is the second provider."
            ),
        ),
        "first-true-live": NamedExperiment(
            name="first-true-live",
            experiment="first-true-fidelity",
            description="One --live first-true trial on priority_shadow (two arm rows).",
            providers=("deepseek",),
            models={"deepseek": deepseek_model},
            run_count=2,
            argv=(
                "scripts/first_true_eval.py",
                "--config",
                config,
                "--live",
                "--provider",
                "deepseek",
                "--machines",
                "priority_shadow",
                "--repeats",
                "1",
            ),
            notes=(
                "The harness emits one first_true row and one prompt_spaghetti "
                "row per trial. That is the first live measurement, not a mock."
            ),
        ),
    }


def planned_runs(spec: NamedExperiment) -> list[PlannedRun]:
    """Expand a named experiment into one PlannedRun per billed call.

    Counts are structural (machines x providers x repeats x arms). They are
    not measured token counts.
    """
    runs: list[PlannedRun] = []
    if spec.name == "gate-divergence":
        for machine in SEVEN_MACHINES:
            for provider, model in spec.models.items():
                for repeat in range(3):
                    runs.append(
                        PlannedRun(
                            spec.experiment,
                            provider,
                            model,
                            f"{machine}/{provider}[{repeat}]",
                        )
                    )
    elif spec.name == "gate-divergence-anthropic-openrouter":
        provider, model = "openrouter", spec.models["openrouter"]
        for machine in SEVEN_MACHINES:
            for repeat in range(3):
                runs.append(
                    PlannedRun(
                        spec.experiment,
                        provider,
                        model,
                        f"{machine}/{provider}[{repeat}]",
                    )
                )
    elif spec.name == "repair-convergence":
        from scripts.repair_convergence import CORPUS

        provider, model = "openai", spec.models["openai"]
        arms = ("first_attempt", "plain_resample", "feedback_repair")
        for item in CORPUS:
            for arm in arms:
                for repeat in range(3):
                    runs.append(
                        PlannedRun(
                            spec.experiment,
                            provider,
                            model,
                            f"{item['id']}/{arm}[{repeat}]",
                        )
                    )
    elif spec.name == "first-true-live":
        for arm in ("first_true", "prompt_spaghetti"):
            runs.append(
                PlannedRun(
                    spec.experiment,
                    "deepseek",
                    spec.models["deepseek"],
                    f"priority_shadow/{arm}[0]",
                )
            )
    else:
        raise KeyError(spec.name)
    if len(runs) != spec.run_count:
        raise RuntimeError(f"{spec.name}: planned {len(runs)} runs, declared {spec.run_count}")
    return runs


def estimate_experiment(spec: NamedExperiment) -> dict[str, Any]:
    rows = []
    total = 0.0
    tokens = 0
    for run in planned_runs(spec):
        usd, meta = estimate_run_usd(run.provider, run.model, run.experiment)
        total += usd
        tokens += int(meta["tokens"])
        rows.append({"label": run.label, **meta})
    token_spec = TOKEN_ESTIMATES[spec.experiment]
    return {
        "name": spec.name,
        "experiment": spec.experiment,
        "description": spec.description,
        "providers": list(spec.providers),
        "models": spec.models,
        "runs": spec.run_count,
        "tokens_est": tokens,
        "usd_est": total,
        "token_source": token_spec.source,
        "token_kind": token_spec.kind,
        "token_notes": token_spec.notes,
        "notes": spec.notes,
        "runs_detail": rows,
    }


def render_estimate_table(summaries: Sequence[dict[str, Any]], *, ledger: Path) -> str:
    spent = ledger_total_usd(ledger)
    lines = [
        f"Hard cap: ${USD_CAP:.2f}. Ledger so far: ${spent:.6f} ({ledger}).",
        "USD estimates charge cited tokens at max(input, output) list price "
        "(no invented in/out split). Sources are in scripts/cost_ledger.py.",
        "",
        "| experiment | providers / models | runs | tokens (est.) | USD (est.) | token source |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    grand_usd = 0.0
    grand_tokens = 0
    grand_runs = 0
    for summary in summaries:
        models = ", ".join(f"{p}={m}" for p, m in summary["models"].items())
        lines.append(
            "| "
            + " | ".join(
                [
                    str(summary["name"]),
                    models,
                    str(summary["runs"]),
                    str(summary["tokens_est"]),
                    f"{summary['usd_est']:.6f}",
                    str(summary["token_source"]),
                ]
            )
            + " |"
        )
        grand_usd += float(summary["usd_est"])
        grand_tokens += int(summary["tokens_est"])
        grand_runs += int(summary["runs"])
    lines.append(
        f"| **all named** |  | **{grand_runs}** | **{grand_tokens}** | **{grand_usd:.6f}** |  |"
    )
    lines.append("")
    lines.append("Pinned list prices (retrieved 2026-10-10):")
    for (provider, model), price in sorted(PRICES.items()):
        lines.append(
            f"- `{provider}/{model}`: ${price.input_usd_per_mtok}/M in, "
            f"${price.output_usd_per_mtok}/M out — {price.source}"
        )
    for summary in summaries:
        lines.append("")
        lines.append(f"### {summary['name']}")
        lines.append(summary["description"])
        lines.append(summary["notes"])
        lines.append(summary["token_notes"])
        projected = spent + float(summary["usd_est"])
        if projected > USD_CAP:
            lines.append(
                f"Would refuse: ledger ${spent:.6f} + estimate "
                f"${summary['usd_est']:.6f} > ${USD_CAP:.2f}."
            )
        else:
            lines.append(
                f"Fits the cap: ledger ${spent:.6f} + estimate "
                f"${summary['usd_est']:.6f} = ${projected:.6f} ≤ ${USD_CAP:.2f}."
            )
    return "\n".join(lines) + "\n"


def _write_environments(release: Path, spec: NamedExperiment) -> None:
    payload = {
        "status": "live-dispatch",
        "experiment": spec.name,
        "config": str(DEFAULT_CONFIG.relative_to(ROOT)),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "tip_sha": _tip_sha(),
        "started_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "usd_cap": USD_CAP,
        "anthropic": {
            "native_adapter": False,
            "reason": "no ANTHROPIC_API_KEY in Actions",
            "openrouter": {
                "feasible": True,
                "provider": "openrouter",
                "model": "anthropic/claude-sonnet-5",
                "adapter": "openai_compat",
            },
        },
    }
    (release / "environments.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _gh_ndjson(path: str, jq: str) -> list[dict[str, Any]]:
    """List-shaped GitHub API pages as objects. Fail closed if gh cannot run."""
    try:
        raw = subprocess.check_output(
            ["gh", "api", "--paginate", path, "--jq", jq],
            text=True,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise UnmergedLedgerError(
            "refusing --live: cannot list evidence-live runs via "
            f"`gh api {path}` ({detail.strip() or exc}). "
            "Need GITHUB_TOKEN with actions: read."
        ) from exc
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict):
            raise UnmergedLedgerError(
                f"refusing --live: unexpected gh api row from {path}: {item!r}"
            )
        rows.append(item)
    return rows


def fetch_evidence_live_listings(
    repo: str,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    runs = _gh_ndjson(
        f"/repos/{repo}/actions/workflows/{EVIDENCE_LIVE_WORKFLOW}/runs?per_page=100",
        ".workflow_runs[]",
    )
    jobs_by_id: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        rid = str(run.get("id", "") or "")
        if not rid:
            continue
        jobs_by_id[rid] = _gh_ndjson(
            f"/repos/{repo}/actions/runs/{rid}/jobs?per_page=100",
            ".jobs[]",
        )
    return runs, jobs_by_id


def check_prior_live_runs(ledger: Path, *, current_run_id: str, repo: str) -> list[str]:
    runs, jobs_by_id = fetch_evidence_live_listings(repo)
    return require_prior_live_runs_in_ledger(
        ledger,
        current_run_id=current_run_id,
        workflow_runs=runs,
        jobs_by_run_id=jobs_by_id,
    )


def _live_argv(spec: NamedExperiment, release: Path) -> list[str]:
    jsonl = release / f"{spec.name}.jsonl"
    summary = release / f"{spec.name}-summary.json"
    ledger = release / LEDGER_NAME
    extra = [
        "--jsonl",
        str(jsonl),
        "--summary-json",
        str(summary),
        "--cost-ledger",
        str(ledger),
        "--usd-cap",
        str(USD_CAP),
        "--cost-experiment",
        spec.experiment,
    ]
    github_run_id = os.environ.get("GITHUB_RUN_ID")
    if github_run_id:
        extra.extend(["--github-run-id", github_run_id])
    return [*spec.argv[1:], *extra]


def _run_script(spec: NamedExperiment, argv: list[str]) -> int:
    if spec.name.startswith("gate-divergence"):
        from scripts.gate_divergence import main as gd_main

        return gd_main(argv)
    if spec.name == "repair-convergence":
        from scripts.repair_convergence import main as rc_main

        return rc_main(argv)
    if spec.name == "first-true-live":
        from scripts.first_true_eval import main as ft_main

        return ft_main(argv)
    raise KeyError(spec.name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--experiment",
        default="all",
        help="named experiment, or 'all' (estimate only)",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--estimate",
        action="store_true",
        help="print projected cost; no provider calls",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="run one named experiment under the $10 ledger cap (Actions only)",
    )
    mode.add_argument(
        "--require-prior-live-runs",
        action="store_true",
        help="fail closed unless every prior evidence-live run that reached "
        "the live step is in the checked-out costs.jsonl (no API spend)",
    )
    parser.add_argument("--release", type=Path, default=RELEASE_DIR)
    args = parser.parse_args(argv)

    catalog = named_experiments()
    if args.experiment != "all" and args.experiment not in catalog:
        parser.error(f"unknown experiment {args.experiment!r} (have: {', '.join(catalog)} or all)")
    if args.live and args.experiment == "all":
        parser.error("--live needs one named experiment (not all)")

    release = args.release if args.release.is_absolute() else ROOT / args.release
    ledger = release / LEDGER_NAME
    if args.require_prior_live_runs:
        repo = os.environ.get("GITHUB_REPOSITORY")
        current = os.environ.get("GITHUB_RUN_ID")
        if not repo or not current:
            print(
                "# unmerged ledger: GITHUB_REPOSITORY and GITHUB_RUN_ID are required "
                "to compare prior evidence-live runs against costs.jsonl",
                file=sys.stderr,
            )
            return 3
        try:
            required = check_prior_live_runs(ledger, current_run_id=current, repo=repo)
        except UnmergedLedgerError as exc:
            print(f"# unmerged ledger: {exc}", file=sys.stderr)
            return 3
        print(f"prior live runs present in ledger: {', '.join(required) if required else '(none)'}")
        return 0

    selected = list(catalog.values()) if args.experiment == "all" else [catalog[args.experiment]]
    summaries = [estimate_experiment(spec) for spec in selected]
    table = render_estimate_table(summaries, ledger=ledger)
    print(table)
    if args.estimate:
        return 0

    spec = selected[0]
    summary = summaries[0]
    spent = ledger_total_usd(ledger)
    if spent + float(summary["usd_est"]) > USD_CAP:
        print(
            f"# refuse {spec.name}: ledger ${spent:.6f} + estimate "
            f"${summary['usd_est']:.6f} exceeds ${USD_CAP:.2f}",
            file=sys.stderr,
        )
        return 3

    release.mkdir(parents=True, exist_ok=True)
    github_run_id = os.environ.get("GITHUB_RUN_ID")
    if github_run_id:
        append_dispatch_marker(ledger, github_run_id=github_run_id, experiment=spec.experiment)
    _write_environments(release, spec)
    code = _run_script(spec, _live_argv(spec, release))
    (release / "summary.json").write_text(
        json.dumps(
            {
                "experiment": spec.name,
                "exit_code": code,
                "ledger_usd": ledger_total_usd(ledger),
                "usd_cap": USD_CAP,
                "estimate": {k: summary[k] for k in summary if k != "runs_detail"},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
