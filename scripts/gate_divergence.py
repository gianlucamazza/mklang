#!/usr/bin/env python3
"""Measure cross-provider gate agreement on a fixed machine + inputs.

Syntactic portability ("same .mkl, any provider") does not imply semantic
agreement on which prose gate fires. This script runs a small routing machine
once per provider (with API key) and reports pairwise agreement on the
gate-trace signature.

Agreement alone is a weak measure — it cannot fail on an easy task, it scores a
shared wrong answer as perfect, and pooling same-provider repeats with
cross-provider pairs inflates it. So the summary also reports the cross/intra
decomposition, `accuracy` against a declared gold route, `gate_blind_spot`
(agreement minus accuracy) and, under `--paraphrase`, invariance to how the author
worded the condition. See docs/experiments/gate-divergence.md.

Usage:
  uv run python scripts/gate_divergence.py
  uv run python scripts/gate_divergence.py --providers deepseek,openai --repeats 3
  uv run python scripts/gate_divergence.py --jsonl results.jsonl
  uv run python scripts/gate_divergence.py --repeats 3 \
    --require-providers deepseek,openai --min-agreement 1.0 \
    --summary-json summary.json
  uv run python scripts/gate_divergence.py --machines all --paraphrase \
    --repeats 3 --min-cross-agreement 0.8 --min-accuracy 0.8

Requires keys in .env (same as `mklang run`). Skips providers without a key.
See docs/experiments/gate-divergence.md.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections.abc import Callable
from itertools import combinations
from pathlib import Path

from mklang.cli import _build_llm
from mklang.config import ProviderConfig, load_provider
from mklang.engine import run
from mklang.llm.base import LLM
from mklang.model import parse_machine

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = str(ROOT / "config" / "runtime.example.yaml")

# A suite of small synthetic machines, each stressing a DIFFERENT gate shape so
# the experiment measures more than one kind of judge decision. Every machine is
# fast-tier throughout and terminates in a few steps. Agreement is always
# computed WITHIN a machine (cross-machine signatures differ by construction).
#
# `gate_divergence` is kept verbatim and stays the default single machine so the
# release gate (release.yml) and its pinned history remain comparable.
MACHINES: dict[str, dict] = {
    # 1) Multi-way `ok` routing on a categorical label.
    "gate_divergence": {
        "machine": "gate_divergence",
        "entry": "label",
        "budget": 5,
        "default_tier": "fast",
        "states": {
            "label": {
                "structure": 'Exactly one word: "spam", "ham", or "unknown".',
                "prompt": (
                    "Classify this message as spam, ham, or unknown. "
                    "Reply with exactly one of those three words.\n"
                    "Message: Congratulations! You won a free prize. Click here now."
                ),
                "output": "tag",
                "gates": [
                    {"when": 'the output is the word "spam"', "then": "ok", "to": "spam_path"},
                    {"when": 'the output is the word "ham"', "then": "ok", "to": "ham_path"},
                    {"when": "otherwise", "then": "ok", "to": "other_path"},
                ],
            },
            "spam_path": {
                "structure": 'The single word "SPAM_OK".',
                "prompt": "Reply with exactly SPAM_OK",
                "output": "done_msg",
                "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
            },
            "ham_path": {
                "structure": 'The single word "HAM_OK".',
                "prompt": "Reply with exactly HAM_OK",
                "output": "done_msg",
                "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
            },
            "other_path": {
                "structure": 'The single word "OTHER_OK".',
                "prompt": "Reply with exactly OTHER_OK",
                "output": "done_msg",
                "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
            },
        },
    },
    # 2) Borderline judgement: a deliberately mixed-signal review, so the
    # positive/negative/mixed gates are genuinely contestable across judges.
    "sentiment_borderline": {
        "machine": "sentiment_borderline",
        "entry": "assess",
        "budget": 4,
        "default_tier": "fast",
        "states": {
            "assess": {
                "structure": "One or two sentences describing the reviewer's sentiment.",
                "prompt": (
                    "Summarize the sentiment of this product review in one line.\n"
                    "Review: The build quality is excellent and it feels premium, but it "
                    "died after three days and support never replied."
                ),
                "output": "reading",
                "gates": [
                    {
                        "when": "the sentiment is clearly positive overall",
                        "then": "ok",
                        "to": "pos",
                    },
                    {
                        "when": "the sentiment is clearly negative overall",
                        "then": "ok",
                        "to": "neg",
                    },
                    {"when": "otherwise", "then": "ok", "to": "mixed"},
                ],
            },
            "pos": {
                "structure": 'The word "POSITIVE".',
                "prompt": "Reply with exactly POSITIVE",
                "output": "verdict",
                "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
            },
            "neg": {
                "structure": 'The word "NEGATIVE".',
                "prompt": "Reply with exactly NEGATIVE",
                "output": "verdict",
                "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
            },
            "mixed": {
                "structure": 'The word "MIXED".',
                "prompt": "Reply with exactly MIXED",
                "output": "verdict",
                "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
            },
        },
    },
    # 3) Control-flow-critical gate: an `escalate` on "severe" decides whether a
    # human is looped in. Divergence here is the costly kind (SPEC §11).
    "severity_escalate": {
        "machine": "severity_escalate",
        "entry": "triage",
        "budget": 4,
        "default_tier": "fast",
        "result": "outcome",
        "states": {
            "triage": {
                "structure": 'The single label "NON_SEVERE".',
                "prompt": (
                    "This fixed release-gate fixture is NON_SEVERE: there is no data loss, "
                    "no security incident, and no ongoing outage. Reply with exactly NON_SEVERE.\n"
                    "Incident: intermittent 500s on the refund endpoint, ~2% of calls, "
                    "no data loss observed, a retry usually succeeds."
                ),
                "output": "assessment",
                "gates": [
                    {
                        "when": 'the output starts with the label "SEVERE"',
                        "escalate": True,
                        "to": "human",
                    },
                    {"when": "otherwise", "then": "ok", "to": "auto"},
                ],
            },
            "auto": {
                "structure": 'The word "AUTO_HANDLED".',
                "prompt": "Reply with exactly AUTO_HANDLED",
                "output": "outcome",
                "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
            },
            "human": {
                "structure": 'The word "ESCALATED".',
                "prompt": "Reply with exactly ESCALATED",
                "output": "outcome",
                "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
            },
        },
    },
    # 4) Self-correction gate: a `repair` loop on "grounded in the given fact"
    # stresses whether judges agree an answer is adequately grounded.
    "grounding_repair": {
        "machine": "grounding_repair",
        "entry": "answer",
        "budget": 6,
        "default_tier": "fast",
        "result": "final",
        "context": {"fact": "The store's return window is 30 days from delivery."},
        "states": {
            "answer": {
                "structure": "A one-sentence customer reply.",
                "prompt": (
                    "Answer the customer using ONLY this fact: {{fact}}\n"
                    "Customer: How long do I have to return an item?"
                ),
                "output": "final",
                "gates": [
                    {
                        "when": "the reply is grounded in the given fact and states 30 days",
                        "then": "ok",
                        "to": "END",
                    },
                    {
                        "when": "the reply is vague or not grounded in the fact",
                        "repair": 1,
                        "to": "answer",
                    },
                    {"when": "otherwise", "then": "ok", "to": "END"},
                ],
            },
        },
    },
}

# --- Boundary corpus -------------------------------------------------------
# Machines 1-4 above measure agreement on tasks where a competent judge has an
# easy time. Agreement 1.0 on those has no discriminating power: a measure that
# cannot fail is not evidence. The machines below are built at the decision
# boundary — the answer is defensible but not obvious — and each carries a GOLD
# route, so agreement can be compared against *correctness* instead of standing
# in for it.
MACHINES.update(
    {
        # 5) Marginal condition: the amount sits EXACTLY on the limit and the gate
        # says "strictly greater". The produced text is pinned, so the only thing
        # under measurement is the judge's handling of the boundary.
        "threshold_edge": {
            "machine": "threshold_edge",
            "entry": "assess",
            "budget": 4,
            "default_tier": "fast",
            "result": "outcome",
            "states": {
                "assess": {
                    "structure": 'The single line "AMOUNT 500.00 EUR / LIMIT 500.00 EUR".',
                    "prompt": ("Reply with exactly: AMOUNT 500.00 EUR / LIMIT 500.00 EUR"),
                    "output": "reading",
                    "gates": [
                        {
                            "when": "the amount is strictly greater than the limit",
                            "then": "ok",
                            "to": "over",
                        },
                        {"when": "otherwise", "then": "ok", "to": "within"},
                    ],
                },
                "over": {
                    "structure": 'The word "OVER".',
                    "prompt": "Reply with exactly OVER",
                    "output": "outcome",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                },
                "within": {
                    "structure": 'The word "WITHIN".',
                    "prompt": "Reply with exactly WITHIN",
                    "output": "outcome",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                },
            },
        },
        # 6) Near-overlapping gates: both conditions are true of the same output
        # and the narrower one is second. SPEC §5 says the FIRST true gate fires,
        # so the language — not taste — fixes the gold route. This measures
        # whether judges honour priority order rather than "best match".
        "priority_shadow": {
            "machine": "priority_shadow",
            "entry": "draft",
            "budget": 4,
            "default_tier": "fast",
            "result": "outcome",
            "states": {
                "draft": {
                    "structure": 'The single line "REFUND 2000 EUR APPROVED FOR ORDER 71".',
                    "prompt": "Reply with exactly: REFUND 2000 EUR APPROVED FOR ORDER 71",
                    "output": "reply",
                    "gates": [
                        {"when": "the reply mentions a refund", "then": "ok", "to": "broad"},
                        {
                            "when": "the reply mentions a refund above 1000 EUR",
                            "then": "ok",
                            "to": "narrow",
                        },
                        {"when": "otherwise", "then": "ok", "to": "neither"},
                    ],
                },
                "broad": {
                    "structure": 'The word "BROAD".',
                    "prompt": "Reply with exactly BROAD",
                    "output": "outcome",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                },
                "narrow": {
                    "structure": 'The word "NARROW".',
                    "prompt": "Reply with exactly NARROW",
                    "output": "outcome",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                },
                "neither": {
                    "structure": 'The word "NEITHER".',
                    "prompt": "Reply with exactly NEITHER",
                    "output": "outcome",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                },
            },
        },
        # 7) No condition holds. The catch-all is the correct route, which the
        # judge can only reach by declining every listed condition (SPEC §5
        # "none of the above"). Before that option existed this machine could not
        # route correctly at all — it measures exactly what totality bought.
        "none_holds": {
            "machine": "none_holds",
            "entry": "classify",
            "budget": 4,
            "default_tier": "fast",
            "result": "outcome",
            "states": {
                "classify": {
                    "structure": 'The single line "MAINTENANCE WINDOW SCHEDULED FOR SUNDAY".',
                    "prompt": "Reply with exactly: MAINTENANCE WINDOW SCHEDULED FOR SUNDAY",
                    "output": "ticket",
                    "gates": [
                        {
                            "when": "the output reports a failed payment",
                            "then": "ok",
                            "to": "payment",
                        },
                        {
                            "when": "the output reports a login problem",
                            "then": "ok",
                            "to": "login",
                        },
                        {"when": "otherwise", "then": "ok", "to": "other"},
                    ],
                },
                "payment": {
                    "structure": 'The word "PAYMENT".',
                    "prompt": "Reply with exactly PAYMENT",
                    "output": "outcome",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                },
                "login": {
                    "structure": 'The word "LOGIN".',
                    "prompt": "Reply with exactly LOGIN",
                    "output": "outcome",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                },
                "other": {
                    "structure": 'The word "OTHER".',
                    "prompt": "Reply with exactly OTHER",
                    "output": "outcome",
                    "gates": [{"when": "otherwise", "then": "ok", "to": "END"}],
                },
            },
        },
    }
)

# Author intent per machine, as a ROUTE signature (`state>to`, see
# `_route_signature`). Only machines with a defensible right answer appear here:
# `sentiment_borderline` deliberately has none, and listing a gold route for it
# would smuggle taste in as ground truth.
GOLD: dict[str, str] = {
    "gate_divergence": "label>spam_path || spam_path>END",
    "severity_escalate": "triage>auto || auto>END",
    "grounding_repair": "answer>END",
    "threshold_edge": "assess>within || within>END",
    "priority_shadow": "draft>broad || broad>END",
    "none_holds": "classify>other || other>END",
}

# Paraphrase variants: the SAME machine with reworded `when` conditions. States,
# targets, and prompts are untouched, so the route space is identical and any
# routing difference is the judge reacting to wording rather than to evidence.
# Shape: machine -> [{"label": …, "gates": {state_id: {gate_index: new_when}}}].
PARAPHRASES: dict[str, list[dict]] = {
    "gate_divergence": [
        {
            "label": "p1",
            "gates": {
                "label": {
                    0: "the classification given is spam",
                    1: "the classification given is ham",
                }
            },
        },
    ],
    "threshold_edge": [
        {
            "label": "p1",
            "gates": {"assess": {0: "the amount exceeds the limit"}},
        },
        {
            "label": "p2",
            "gates": {"assess": {0: "the amount is above the limit, not merely equal to it"}},
        },
    ],
    "priority_shadow": [
        {
            "label": "p1",
            "gates": {
                "draft": {
                    0: "a refund is mentioned in the reply",
                    1: "a refund larger than 1000 EUR is mentioned in the reply",
                }
            },
        },
    ],
    "none_holds": [
        {
            "label": "p1",
            "gates": {
                "classify": {
                    0: "the output is about a payment that did not go through",
                    1: "the output is about being unable to sign in",
                }
            },
        },
    ],
}

# Back-compat alias for anything importing the original single machine.
MACHINE = MACHINES["gate_divergence"]

BASE_VARIANT = "base"


def paraphrase_doc(machine: str, variant: dict) -> dict:
    """Apply a paraphrase variant's `when` rewrites to a copy of the machine doc."""
    doc = copy.deepcopy(MACHINES[machine])
    for sid, changes in variant["gates"].items():
        gates = doc["states"][sid]["gates"]
        for index, text in changes.items():
            if gates[index]["when"].strip().lower() == "otherwise":
                raise ValueError(f"{machine}/{variant['label']}: refusing to reword `otherwise`")
            gates[index]["when"] = text
    return doc


def _trace_signature(trace: list[dict]) -> str:
    """Compact, comparable signature of routing decisions (not full outputs)."""
    parts = []
    for step in trace:
        parts.append(
            f"{step.get('state')}|{step.get('gate')}|{step.get('gate_via')}|{step.get('to')}"
        )
    return " || ".join(parts)


def _route_signature(trace: list[dict]) -> str:
    """Signature of the PATH only — `state>to`, without the gate's `when` text.

    Two runs of paraphrase variants have different `_trace_signature`s by
    construction (the condition text is part of it), so route equality is the
    only meaningful comparison across wordings. It is also the form author intent
    is expressed in (`GOLD`)."""
    return " || ".join(f"{s.get('state')}>{s.get('to')}" for s in trace)


def _output_hash(trace: list[dict]) -> str:
    blob = json.dumps([s.get("output") for s in trace], ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def _run_once(
    provider_name: str,
    config: str,
    judge_tier: str | None = None,
    machine_doc: dict | None = None,
    build_llm: Callable[[ProviderConfig], LLM] = _build_llm,
    variant: str = BASE_VARIANT,
) -> dict:
    """Run one machine once for one provider. `build_llm` is injectable so the
    offline suite can drive the harness with a scripted LLM (no keys)."""
    prov = load_provider(config, provider_name)
    # The missing-key skip only applies to the real live path; an injected
    # build_llm means there is no live call to gate (offline tests).
    if build_llm is _build_llm and not prov.api_key and prov.name != "local":
        return {"provider": provider_name, "skipped": True, "reason": "no API key"}
    doc = machine_doc if machine_doc is not None else MACHINE
    m = parse_machine(doc)
    # Default: judging follows each state's tier (SPEC §2.1). `--judge-tier` forces a
    # single tier's model for all gates, so pre/post-F1 divergence runs are comparable.
    judge_override = prov.tiers[judge_tier] if judge_tier else prov.judge_override()
    r = run(
        m,
        dict(m.context),
        {m.name: m},
        build_llm(prov),
        prov.tiers,
        judge_override,
        tier_params=prov.params,
        cost_budget=20_000,
    )
    route = _route_signature(r.trace) if r.trace else ""
    gold = GOLD.get(m.name)
    return {
        "provider": provider_name,
        "machine": m.name,
        "variant": variant,
        "skipped": False,
        "status": r.status,
        "error": r.error,
        "judge_tier": judge_tier,
        "judge_override": judge_override,
        "signature": _trace_signature(r.trace) if r.trace else "",
        "route": route,
        # None when the machine has no defensible right answer (see GOLD).
        "correct": None if gold is None else route == gold,
        "output_hash": _output_hash(r.trace) if r.trace else "",
        "gates": [
            {
                "state": s.get("state"),
                "gate": s.get("gate"),
                "gate_via": s.get("gate_via"),
                "judge_model": s.get("judge_model"),
                "to": s.get("to"),
                "judge_fallback": s.get("judge_fallback"),
            }
            for s in (r.trace or [])
        ],
        "usage": r.usage,
    }


def _done(rows: list[dict]) -> list[dict]:
    return [r for r in rows if not r.get("skipped") and r.get("status") == "done"]


def _variant_of(row: dict) -> str:
    return row.get("variant") or BASE_VARIANT


def _rate(hits: int, total: int) -> float | None:
    return (hits / total) if total else None


def _pairwise_agreement(rows: list[dict]) -> list[dict]:
    """Pairwise signature agreement, computed WITHIN each machine AND paraphrase
    variant — cross-machine signatures differ by construction, and a reworded
    variant is a different input, so pooling either would be meaningless.

    Each pair records `same_provider`: a pair of repeats from one provider
    measures **self-consistency**, not cross-provider portability. Pooling the two
    inflates the headline number, since repeats of one model agree more often than
    two different models do."""
    ok = _done(rows)
    out = []
    groups = sorted(
        {(r.get("machine"), _variant_of(r)) for r in ok},
        key=lambda k: (k[0] is None, k[0], k[1]),
    )
    for machine, variant in groups:
        group = [r for r in ok if r.get("machine") == machine and _variant_of(r) == variant]
        for a, b in combinations(group, 2):
            pair = {
                "a": a["provider"],
                "b": b["provider"],
                "same_provider": a["provider"] == b["provider"],
                "same_signature": a["signature"] == b["signature"],
                "same_outputs": a["output_hash"] == b["output_hash"],
            }
            if machine is not None:
                pair["machine"] = machine
            if variant != BASE_VARIANT:
                pair["variant"] = variant
            out.append(pair)
    return out


def _agreement_block(rows: list[dict]) -> dict:
    """Agreement over one comparable group, decomposed by pair kind."""
    pairs = _pairwise_agreement(rows)
    cross = [p for p in pairs if not p["same_provider"]]
    intra = [p for p in pairs if p["same_provider"]]
    return {
        "pairs": len(pairs),
        # Pooled over every within-group pair (both kinds) — the historical
        # number the release gate is pinned to.
        "signature_agreement_rate": _rate(sum(1 for p in pairs if p["same_signature"]), len(pairs)),
        # Portability: do two DIFFERENT providers route the same way?
        "cross_provider_agreement_rate": _rate(
            sum(1 for p in cross if p["same_signature"]), len(cross)
        ),
        # Stability: does ONE provider route the same way on identical repeats?
        # None with --repeats 1 — the run simply cannot answer it.
        "intra_provider_agreement_rate": _rate(
            sum(1 for p in intra if p["same_signature"]), len(intra)
        ),
    }


def _accuracy_block(rows: list[dict]) -> dict:
    """Correctness against author intent (GOLD), for machines that have one.

    Agreement is a measure of *consensus*; it scores a shared wrong answer as
    perfect. Accuracy is the missing half, and their gap is what agreement
    overstates."""
    scored = [r for r in _done(rows) if r.get("correct") is not None]
    return {
        "scored_runs": len(scored),
        "accuracy": _rate(sum(1 for r in scored if r["correct"]), len(scored)),
    }


def _machine_rates(rows: list[dict]) -> dict[str, dict]:
    """Per-machine rates over the base (un-paraphrased) runs.

    Paraphrase variants are excluded here: they are a different input, so folding
    them into the headline would silently change what the release floor means.
    They get their own `paraphrase` block."""
    done = [r for r in _done(rows) if _variant_of(r) == BASE_VARIANT]
    per: dict[str, dict] = {}
    # Narrow to str: row dicts are untyped, so r.get("machine") is Any | None.
    machines = sorted({m for r in done if isinstance(m := r.get("machine"), str)})
    for machine in machines:
        group = [r for r in done if r.get("machine") == machine]
        per[machine] = {
            "runs_done": len(group),
            **_agreement_block(group),
            **_accuracy_block(group),
            "distinct_signatures": sorted({r["signature"] for r in group}),
        }
    # Rows without a machine name (legacy fixtures) land under "default".
    bare = [r for r in done if not isinstance(r.get("machine"), str)]
    if bare:
        per["default"] = {
            "runs_done": len(bare),
            **_agreement_block(bare),
            **_accuracy_block(bare),
            "distinct_signatures": sorted({r["signature"] for r in bare}),
        }
    return per


def _paraphrase_rates(rows: list[dict]) -> dict[str, dict]:
    """Paraphrase invariance: same evidence, reworded conditions — same route?

    Computed per (machine, provider) across variants, so it isolates wording
    sensitivity from cross-provider divergence. A judge that is invariant here is
    reading the evidence; one that is not is reading the phrasing."""
    done = _done(rows)
    per: dict[str, dict] = {}
    machines = sorted({m for r in done if isinstance(m := r.get("machine"), str)})
    for machine in machines:
        group = [r for r in done if r.get("machine") == machine]
        variants = sorted({_variant_of(r) for r in group})
        if len(variants) < 2:
            continue
        same = total = 0
        for provider in sorted({r["provider"] for r in group}):
            by_provider = [r for r in group if r["provider"] == provider]
            for a, b in combinations(by_provider, 2):
                if _variant_of(a) == _variant_of(b):
                    continue  # same wording: that is the agreement metric, not this one
                total += 1
                same += a["route"] == b["route"]
        per[machine] = {
            "variants": variants,
            "cross_variant_pairs": total,
            "invariant_pairs": same,
            "paraphrase_invariance_rate": _rate(same, total),
            "distinct_routes": sorted({r["route"] for r in group}),
        }
    return per


def _summary(rows: list[dict], names: list[str]) -> dict:
    pairs = _pairwise_agreement(rows)
    done = _done(rows)
    base = [r for r in done if _variant_of(r) == BASE_VARIANT]
    per_machine = _machine_rates(rows)
    paraphrase = _paraphrase_rates(rows)
    agreement = _agreement_block(base)
    accuracy = _accuracy_block(done)
    summary = {
        "providers_attempted": names,
        "machines": sorted({m for r in done if isinstance(m := r.get("machine"), str)}),
        "runs_done": len(done),
        "runs_skipped": sum(1 for r in rows if r.get("skipped")),
        "runs_failed": sum(1 for r in rows if not r.get("skipped") and r.get("status") != "done"),
        "pairwise": pairs,
        # Pooled over all within-machine base pairs; identical to the per-machine
        # rate for a single machine, so the release gate keeps one comparable
        # number. It is NOT the discriminating one — see the decomposition below.
        "signature_agreement_rate": agreement["signature_agreement_rate"],
        "cross_provider_agreement_rate": agreement["cross_provider_agreement_rate"],
        "intra_provider_agreement_rate": agreement["intra_provider_agreement_rate"],
        "accuracy": accuracy["accuracy"],
        "scored_runs": accuracy["scored_runs"],
        # How much agreement overstates correctness on the machines that have a
        # gold route — the gate-judging analogue of the authoring `blind_spot`
        # (docs/experiments/authoring-blind-spot.md). Positive means the judges
        # concur more often than they are right.
        "gate_blind_spot": (
            None
            if agreement["signature_agreement_rate"] is None or accuracy["accuracy"] is None
            else round(agreement["signature_agreement_rate"] - accuracy["accuracy"], 4)
        ),
        "per_machine": per_machine,
        "distinct_signatures": sorted({r["signature"] for r in done}),
    }
    if paraphrase:
        summary["paraphrase"] = paraphrase
    return summary


def _parse_agreement_overrides(raw: str) -> dict[str, float]:
    """Parse `machine=0.5,other=1.0` into a per-machine agreement floor map."""
    out: dict[str, float] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError(f"expected machine=rate, got {part!r}")
        name, rate_s = part.split("=", 1)
        name = name.strip()
        rate = float(rate_s.strip())
        if not 0 <= rate <= 1:
            raise ValueError(f"rate for {name!r} must be in [0, 1], got {rate}")
        out[name] = rate
    return out


def _ci_errors(
    rows: list[dict],
    required: list[str],
    repeats: int,
    min_agreement: float | None,
    min_agreement_by_machine: dict[str, float] | None = None,
    floors: dict[str, float] | None = None,
) -> list[str]:
    """Return release-gate failures without hiding unavailable or failed providers.

    With `repeats` runs per (provider, machine, variant), a required provider must
    have `repeats * n_groups` successful rows; the agreement floor is enforced
    per-machine so no single machine can hide behind a high pooled average.
    `min_agreement_by_machine` overrides the global floor for named machines
    (control-flow-critical shapes like ``severity_escalate``).

    `floors` carries the optional whole-suite floors for the decomposed metrics —
    `cross_provider_agreement_rate`, `intra_provider_agreement_rate`, `accuracy`,
    `paraphrase_invariance_rate` — none of which is enforced unless asked for, so
    the pinned release history stays comparable."""
    errors: list[str] = []
    overrides = min_agreement_by_machine or {}
    # Count only (machine, variant) groups that actually ran. Skipped-provider
    # rows carry no `machine` field (see `_run_once`), so a naive distinct-count
    # over all rows would include `None` and inflate the expectation — failing the
    # release gate even with perfect agreement whenever any optional provider
    # lacks a key (the normal release-matrix state).
    groups = {(r["machine"], _variant_of(r)) for r in rows if r.get("machine") is not None}
    expected = repeats * max(1, len(groups))
    for name in required:
        provider_rows = [r for r in rows if r.get("provider") == name]
        if len(provider_rows) != expected:
            errors.append(
                f"required provider {name!r}: expected {expected} runs, got {len(provider_rows)}"
            )
            continue
        skipped = [r for r in provider_rows if r.get("skipped")]
        failed = [r for r in provider_rows if not r.get("skipped") and r.get("status") != "done"]
        if skipped:
            errors.append(f"required provider {name!r}: {len(skipped)} run(s) skipped")
        if failed:
            errors.append(f"required provider {name!r}: {len(failed)} run(s) failed")

    agreement_rows = [r for r in rows if not required or r.get("provider") in required]
    if min_agreement is not None or overrides:
        for machine, stats in _machine_rates(agreement_rows).items():
            rate = stats["signature_agreement_rate"]
            floor = overrides.get(machine, min_agreement)
            if floor is None:
                continue
            if rate is None or rate < floor:
                label = "" if machine == "default" else f" [{machine}]"
                errors.append(f"signature agreement {rate!r}{label} is below required {floor:.3f}")
    errors.extend(_decomposed_floor_errors(agreement_rows, floors or {}))
    return errors


def _decomposed_floor_errors(rows: list[dict], floors: dict[str, float]) -> list[str]:
    """Enforce the opt-in floors on the metrics the pooled rate cannot express."""
    if not floors:
        return []
    summary = _summary(rows, [])
    measured: dict[str, float | None] = {
        "cross_provider_agreement_rate": summary["cross_provider_agreement_rate"],
        "intra_provider_agreement_rate": summary["intra_provider_agreement_rate"],
        "accuracy": summary["accuracy"],
    }
    paraphrase = summary.get("paraphrase") or {}
    if paraphrase:
        measured["paraphrase_invariance_rate"] = _rate(
            sum(stats["invariant_pairs"] for stats in paraphrase.values()),
            sum(stats["cross_variant_pairs"] for stats in paraphrase.values()),
        )
    errors: list[str] = []
    for metric, floor in floors.items():
        rate = measured.get(metric)
        if rate is None:
            errors.append(f"{metric} was not measured by this run (floor {floor:.3f} requested)")
        elif rate < floor:
            errors.append(f"{metric} {rate!r} is below required {floor:.3f}")
    return errors


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        help="runtime YAML (default: config/runtime.example.yaml)",
    )
    p.add_argument(
        "--providers",
        default="deepseek,openai,anthropic,google,xai,mistral,openrouter",
        help="comma-separated provider names to try",
    )
    p.add_argument("--repeats", type=int, default=1, help="runs per provider")
    p.add_argument("--jsonl", type=Path, default=None, help="append raw rows here")
    p.add_argument("--summary-json", type=Path, default=None, help="write the summary JSON here")
    p.add_argument(
        "--require-providers",
        default="",
        help="comma-separated providers whose every repeat must finish successfully",
    )
    p.add_argument(
        "--min-agreement",
        type=float,
        default=None,
        help="default minimum pairwise signature agreement in [0, 1] (release gate)",
    )
    p.add_argument(
        "--min-agreement-by-machine",
        default="",
        help="per-machine floors as name=rate pairs (override --min-agreement), e.g. "
        "severity_escalate=0.5 — control-flow-critical shapes need a floor, not silence",
    )
    p.add_argument(
        "--min-cross-agreement",
        type=float,
        default=None,
        help="minimum agreement over pairs of DIFFERENT providers — the portability "
        "claim. Not enforced unless given (the pooled --min-agreement also counts "
        "same-provider repeats, which agree more easily)",
    )
    p.add_argument(
        "--min-intra-agreement",
        type=float,
        default=None,
        help="minimum agreement over repeats of the SAME provider at identical "
        "inputs (self-consistency). Needs --repeats > 1 to be measurable",
    )
    p.add_argument(
        "--min-accuracy",
        type=float,
        default=None,
        help="minimum fraction of runs that take the GOLD route on machines that "
        "declare one — agreement scores a shared wrong answer as perfect",
    )
    p.add_argument(
        "--min-paraphrase-invariance",
        type=float,
        default=None,
        help="minimum fraction of same-provider cross-wording pairs that route "
        "identically (needs --paraphrase)",
    )
    p.add_argument(
        "--paraphrase",
        action="store_true",
        help="also run each selected machine's reworded variants (same states, same "
        "targets, different `when` text) and report paraphrase invariance",
    )
    p.add_argument(
        "--judge-tier",
        choices=("fast", "balanced", "reasoning"),
        default=None,
        help="force all gate judging onto this tier's model (default: follow each "
        "state's tier, SPEC §2.1). The demo machines are fast-tier throughout.",
    )
    p.add_argument(
        "--machines",
        default="gate_divergence",
        help="comma-separated machine names from the suite, or 'all'. Default is "
        f"the single 'gate_divergence' machine (release-gate compatible). "
        f"Available: {', '.join(MACHINES)}.",
    )
    args = p.parse_args(argv)

    if args.repeats < 1:
        p.error("--repeats must be at least 1")
    if args.min_agreement is not None and not 0 <= args.min_agreement <= 1:
        p.error("--min-agreement must be between 0 and 1")
    floors: dict[str, float] = {}
    for flag, metric in (
        ("min_cross_agreement", "cross_provider_agreement_rate"),
        ("min_intra_agreement", "intra_provider_agreement_rate"),
        ("min_accuracy", "accuracy"),
        ("min_paraphrase_invariance", "paraphrase_invariance_rate"),
    ):
        value = getattr(args, flag)
        if value is None:
            continue
        if not 0 <= value <= 1:
            p.error(f"--{flag.replace('_', '-')} must be between 0 and 1")
        floors[metric] = value
    if "intra_provider_agreement_rate" in floors and args.repeats < 2:
        p.error("--min-intra-agreement needs --repeats 2 or more to be measurable")
    if "paraphrase_invariance_rate" in floors and not args.paraphrase:
        p.error("--min-paraphrase-invariance needs --paraphrase")
    try:
        agreement_overrides = _parse_agreement_overrides(args.min_agreement_by_machine)
    except ValueError as e:
        p.error(f"--min-agreement-by-machine: {e}")

    if args.machines.strip() == "all":
        machine_names = list(MACHINES)
    else:
        machine_names = [x.strip() for x in args.machines.split(",") if x.strip()]
    unknown_machines = sorted(set(machine_names) - set(MACHINES))
    if unknown_machines:
        p.error(f"unknown machines: {', '.join(unknown_machines)} (have: {', '.join(MACHINES)})")
    if not machine_names:
        p.error("--machines selected nothing")

    names = [x.strip() for x in args.providers.split(",") if x.strip()]
    required = [x.strip() for x in args.require_providers.split(",") if x.strip()]
    unknown_required = sorted(set(required) - set(names))
    if unknown_required:
        p.error(f"required providers not present in --providers: {', '.join(unknown_required)}")
    rows: list[dict] = []
    for machine_name in machine_names:
        docs = [(BASE_VARIANT, MACHINES[machine_name])]
        if args.paraphrase:
            docs += [
                (v["label"], paraphrase_doc(machine_name, v))
                for v in PARAPHRASES.get(machine_name, [])
            ]
            if len(docs) == 1:
                print(f"# no paraphrase variants declared for {machine_name}", file=sys.stderr)
        for variant, doc in docs:
            for name in names:
                for i in range(args.repeats):
                    try:
                        row = _run_once(
                            name,
                            args.config,
                            judge_tier=args.judge_tier,
                            machine_doc=doc,
                            variant=variant,
                        )
                    except Exception as e:  # provider/network/runtime failures become error rows
                        row = {
                            "provider": name,
                            "machine": machine_name,
                            "variant": variant,
                            "skipped": False,
                            "status": "error",
                            "error": f"{type(e).__name__}: {e}",
                        }
                    row["repeat"] = i
                    rows.append(row)
                    suffix = "" if variant == BASE_VARIANT else f"~{variant}"
                    tag = f"{machine_name}{suffix}/{name}[{i}]"
                    if row.get("skipped"):
                        print(f"# skip {tag}: {row.get('reason')}", file=sys.stderr)
                    elif row.get("status") != "done":
                        print(f"# error {tag}: {row.get('error')}", file=sys.stderr)
                    else:
                        print(
                            f"{tag}: status={row['status']} sig={row['signature']!r}",
                            file=sys.stderr,
                        )
                    if args.jsonl:
                        with args.jsonl.open("a", encoding="utf-8") as f:
                            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = _summary(rows, names)
    errors = _ci_errors(
        rows,
        required,
        args.repeats,
        args.min_agreement,
        min_agreement_by_machine=agreement_overrides or None,
        floors=floors or None,
    )
    summary["gate_errors"] = errors
    rendered = json.dumps(summary, indent=2, ensure_ascii=False)
    print(rendered)
    if args.summary_json:
        args.summary_json.write_text(rendered + "\n", encoding="utf-8")
    for error in errors:
        print(f"# release gate: {error}", file=sys.stderr)
    if errors:
        return 1
    done = [r for r in rows if not r.get("skipped") and r.get("status") == "done"]
    if len(done) < 2:
        print(
            "# need at least two successful providers to measure agreement",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
