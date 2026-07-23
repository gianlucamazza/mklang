#!/usr/bin/env python3
"""Measure the console authoring loop's blind_spot (validation B1/B2, issue #59).

Corpus: docs/experiments/authoring-corpus.yaml (hand-written acceptance first).

For each item / repeat:
  1. Author a .mkl from `request` only (live LLM, or --fixture for offline demos).
  2. Static check via host.check_machine → check_pass.
  3. If check_pass, run every acceptance scenario via scripttest → behaviour_pass
     only when *all* scenarios match.
  4. On static failure, re-author once with the check errors (B2 repair rider);
     count author attempts until check passes or the repair budget is spent.

Metrics (issue thresholds):
  blind_spot = mean(check_pass) − mean(behaviour_pass)   over authoring trials
  < 0.10  → static gate substantially sufficient
  0.10–0.25 → opt-in test_machine
  > 0.25  → test_machine as a required step; 1.1.0 headline

Usage:
  # live (needs a provider key; DeepSeek default)
  uv run python scripts/authoring_blind_spot.py --provider deepseek --repeats 3

  # offline self-check of corpus + harness (fixture gold machines)
  uv run python scripts/authoring_blind_spot.py --fixture-pass

  # write a results markdown section
  uv run python scripts/authoring_blind_spot.py --provider deepseek --repeats 1 \\
    --summary-md docs/experiments/authoring-blind-spot.md
"""

from __future__ import annotations

import argparse
import json
import re
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from mklang.config import load_env_files, load_provider
from mklang.errors import ProviderError, RefusalError
from mklang.host import PrepareError, check_machine
from mklang.llm.base import LLM
from mklang.model import parse_machine
from mklang.providers import build_llm
from mklang.scripttest import match_expectation, run_scenario

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = ROOT / "docs" / "experiments" / "authoring-corpus.yaml"

AuthorFn = Callable[[dict, list[str] | None], str]

AUTHOR_SYSTEM = """\
You author mklang 0.3 machines. Emit ONLY a complete valid .mkl YAML document —
no markdown fences, no commentary before or after. Rules:
- Top-level: mklang: "0.3", machine (snake_case), entry, budget, optional
  default_tier / result / context / tools, then states.
- Never name a provider or model (tier only).
- Generative states: structure, prompt, output, gates. Optional: tier, reason,
  accumulate, sample, over, parse: list.
- Tool states: tool, input, output, gates.
- Call states: call, input, output, gates.
- Every multi-gate state ends with `- when: otherwise` last. No `when: always`.
- Gate policies: then: ok | repair: N | escalate: true | fail: true; fail has no to.
- Honor the requested machine name, state names, context keys, and gate targets
  exactly when the request pins them — acceptance tests pin those names.
"""


@dataclass
class Trial:
    item_id: str
    shape: str
    repeat: int
    check_pass: bool
    behaviour_pass: bool
    author_attempts: int
    check_errors: list[str] = field(default_factory=list)
    behaviour_mismatches: list[str] = field(default_factory=list)
    source: str = ""
    error: str = ""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:ya?ml|mkl)?\s*\n", "", text)
        text = re.sub(r"\n```\s*$", "", text)
    return text.strip()


def _load_corpus(path: Path) -> list[dict]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    items = (doc or {}).get("items") or []
    if not items:
        raise SystemExit(f"{path}: no items:")
    return items


def _author_live(llm: LLM, model: str, request: str, prior_errors: list[str] | None = None) -> str:
    user = f"Author the machine described here:\n\n{request.strip()}\n"
    if prior_errors:
        user += (
            "\nPrevious attempt failed validation. Fix these errors:\n- "
            + "\n- ".join(prior_errors)
            + "\n"
        )
    produced = llm.produce(model, AUTHOR_SYSTEM, user, reason=True)
    return _strip_fences(produced.text)


def _fixture_source(item: dict, *, pass_check: bool) -> str:
    """A minimal gold (or intentionally broken) machine matching the contract."""
    if not pass_check:
        return "machine: broken\nnot: valid\n"
    gold_path = ROOT / "docs" / "experiments" / "authoring-fixtures" / f"{item['id']}.mkl"
    if gold_path.is_file():
        return gold_path.read_text(encoding="utf-8")
    if item["id"] not in GOLD:
        raise SystemExit(f"no gold fixture for {item['id']}; add it to GOLD or run live")
    return GOLD[item["id"]]


# Gold machines aligned with authoring-corpus.yaml contracts (offline harness only).
GOLD: dict[str, str] = {
    "linear_summarize": """\
mklang: "0.3"
machine: bs_summarize
entry: summarize
budget: 4
result: summary
context: { note: "" }
states:
  summarize:
    structure: a one-sentence summary of the note
    prompt: "Summarize: {{note}}"
    output: summary
    gates:
      - { when: "the output is a non-empty summary", then: ok, to: END }
      - { when: otherwise, then: ok, to: END }
""",
    "linear_echo": """\
mklang: "0.3"
machine: bs_echo
entry: speak
budget: 3
result: answer
context: { task: "" }
states:
  speak:
    structure: a short direct answer
    prompt: "Task: {{task}}"
    output: answer
    gates:
      - { when: "the answer addresses the task", then: ok, to: END }
      - { when: otherwise, then: ok, to: END }
""",
    "route_spam": """\
mklang: "0.3"
machine: bs_spam
entry: label
budget: 4
result: verdict
context: { text: "" }
states:
  label:
    structure: 'exactly one of the words "spam", "ham", or "unknown"'
    prompt: "Classify: {{text}}"
    output: tag
    gates:
      - { when: 'the output is the word "spam"', then: ok, to: spam_path }
      - { when: 'the output is the word "ham"', then: ok, to: ham_path }
      - { when: otherwise, then: ok, to: unknown_path }
  spam_path:
    structure: the single word spam
    prompt: confirm spam
    output: verdict
    gates: [{ when: otherwise, then: ok, to: END }]
  ham_path:
    structure: the single word ham
    prompt: confirm ham
    output: verdict
    gates: [{ when: otherwise, then: ok, to: END }]
  unknown_path:
    structure: the single word unknown
    prompt: confirm unknown
    output: verdict
    gates: [{ when: otherwise, then: ok, to: END }]
""",
    "route_sentiment": """\
mklang: "0.3"
machine: bs_sentiment
entry: assess
budget: 4
result: label
context: { review: "" }
states:
  assess:
    structure: 'exactly one of "positive", "negative", "mixed"'
    prompt: "Sentiment of: {{review}}"
    output: label
    gates:
      - { when: 'the output is "positive"', then: ok, to: END }
      - { when: 'the output is "negative"', then: ok, to: END }
      - { when: otherwise, then: ok, to: END }
""",
    "repair_grounding": """\
mklang: "0.3"
machine: bs_ground
entry: answer
budget: 6
result: reply
context: { fact: "", question: "" }
states:
  answer:
    structure: a short answer grounded only in the given fact
    prompt: |
      Fact: {{fact}}
      Question: {{question}}
    output: reply
    gates:
      - { when: "the answer is grounded in the given fact", then: ok, to: END }
      - { when: "the answer invents facts not in the given fact", repair: 1, to: answer }
      - { when: otherwise, then: ok, to: END }
""",
    "escalate_severity": """\
mklang: "0.3"
machine: bs_severity
entry: triage
budget: 5
result: note
context: { incident: "" }
states:
  triage:
    structure: 'exactly one of "page" or "log"'
    prompt: "Incident: {{incident}} — page a human or only log?"
    output: decision
    gates:
      - { when: "the decision is to page a human", escalate: true, to: human }
      - { when: otherwise, then: ok, to: logged }
  human:
    structure: a handoff note
    prompt: "Handoff: {{incident}}"
    output: note
    gates: [{ when: otherwise, then: ok, to: END }]
  logged:
    structure: a short log line
    prompt: "Log: {{incident}}"
    output: note
    gates: [{ when: otherwise, then: ok, to: END }]
""",
    "tool_calc": """\
mklang: "0.3"
machine: bs_calc
entry: compute
budget: 4
result: out
tools:
  - { name: calc, description: "Evaluate arithmetic, input expression" }
context: { expr: "" }
states:
  compute:
    tool: calc
    input: { expression: "{{expr}}" }
    output: out
    gates: [{ when: otherwise, then: ok, to: END }]
""",
    "tool_then_reply": """\
mklang: "0.3"
machine: bs_tool_reply
entry: lookup
budget: 6
result: answer
tools:
  - { name: search_kb, description: "KB search, input query" }
context: { topic: "" }
states:
  lookup:
    tool: search_kb
    input: { query: "{{topic}}" }
    output: facts
    gates: [{ when: otherwise, then: ok, to: draft }]
  draft:
    structure: a short answer using the facts
    prompt: "Topic {{topic}} facts {{facts}}"
    output: answer
    gates: [{ when: otherwise, then: ok, to: END }]
""",
    "accumulate_notes": """\
mklang: "0.3"
machine: bs_accum
entry: collect
budget: 8
result: notes
tools:
  - { name: calc, description: "arithmetic" }
context: { expr: "", notes: [] }
states:
  collect:
    tool: calc
    input: { expression: "{{expr}}" }
    output: notes
    accumulate: true
    gates: [{ when: otherwise, then: ok, to: done }]
  done:
    structure: the word done
    prompt: finish
    output: flag
    gates: [{ when: otherwise, then: ok, to: END }]
""",
    "sample_fanout": """\
mklang: "0.3"
machine: bs_sample
entry: ideas
budget: 6
result: pick
context: { topic: "" }
states:
  ideas:
    structure: one short idea as a single line
    prompt: "Idea for {{topic}}"
    output: candidates
    sample: 3
    gates: [{ when: otherwise, then: ok, to: pick }]
  pick:
    structure: the best idea copied verbatim from the candidates
    prompt: "Pick best of: {{candidates}}"
    output: pick
    gates: [{ when: otherwise, then: ok, to: END }]
""",
    "call_child": """\
mklang: "0.3"
machine: bs_parent
entry: run_child
budget: 5
result: out
context: { msg: "" }
states:
  run_child:
    call: bs_child_echo
    input: { text: "{{msg}}" }
    output: out
    gates: [{ when: otherwise, then: ok, to: END }]
""",
    "parse_list": """\
mklang: "0.3"
machine: bs_list
entry: list_items
budget: 4
result: items
context: { topic: "" }
states:
  list_items:
    structure: a JSON array of 2 short strings
    parse: list
    prompt: "Two items about {{topic}} as a JSON array"
    output: items
    gates: [{ when: otherwise, then: ok, to: END }]
""",
    "two_step_plan": """\
mklang: "0.3"
machine: bs_plan
entry: plan
budget: 6
result: report
context: { goal: "" }
states:
  plan:
    structure: a one-line plan
    prompt: "Plan for: {{goal}}"
    output: steps
    gates: [{ when: otherwise, then: ok, to: report }]
  report:
    structure: a one-line report that mentions the plan
    prompt: "Goal {{goal}} plan {{steps}}"
    output: report
    gates: [{ when: otherwise, then: ok, to: END }]
""",
    "fail_gate": """\
mklang: "0.3"
machine: bs_fail
entry: guard
budget: 3
result: ok_text
context: { code: "" }
states:
  guard:
    structure: 'exactly "ok" or "bad"'
    prompt: "Code: {{code}}"
    output: ok_text
    gates:
      - { when: 'the output is "ok"', then: ok, to: END }
      - { when: 'the output is "bad"', fail: true }
      - { when: otherwise, then: ok, to: END }
""",
    "reason_flag": """\
mklang: "0.3"
machine: bs_reason
entry: think
budget: 4
result: answer
context: { q: "" }
states:
  think:
    structure: a short answer
    reason: true
    prompt: "Q: {{q}}"
    output: answer
    gates: [{ when: otherwise, then: ok, to: END }]
""",
    "default_tier_fast": """\
mklang: "0.3"
machine: bs_fast
entry: go
budget: 3
result: out
default_tier: fast
context: { x: "" }
states:
  go:
    structure: echo of x
    prompt: "{{x}}"
    output: out
    gates: [{ when: otherwise, then: ok, to: END }]
""",
    "budget_tight": """\
mklang: "0.3"
machine: bs_tight
entry: one
budget: 2
result: out
context: { n: "" }
states:
  one:
    structure: the number as a word
    prompt: "Number {{n}}"
    output: out
    gates: [{ when: otherwise, then: ok, to: END }]
""",
    "multi_gate_otherwise_last": """\
mklang: "0.3"
machine: bs_multi
entry: pick
budget: 4
result: choice
context: { s: "" }
states:
  pick:
    structure: 'exactly "a" or "b" or "c"'
    prompt: "Pick for {{s}}"
    output: choice
    gates:
      - { when: 'the output is "a"', then: ok, to: END }
      - { when: 'the output is "b"', then: ok, to: END }
      - { when: otherwise, then: ok, to: END }
""",
    "hitl_review": """\
mklang: "0.3"
machine: bs_hitl
entry: draft
budget: 6
result: final
context: { request: "" }
states:
  draft:
    structure: a decision that grants or denies the request
    prompt: "grant: {{request}}"
    output: draft
    gates:
      - { when: "the decision grants something", escalate: true, to: review }
      - { when: otherwise, then: ok, to: END }
  review:
    structure: the human decision applied
    prompt: "human said {{human.reply}} draft was {{draft}}"
    output: final
    gates: [{ when: otherwise, then: ok, to: END }]
""",
    "tool_search_stub": """\
mklang: "0.3"
machine: bs_search
entry: find
budget: 4
result: hits
tools:
  - { name: search, description: "web search, input query" }
context: { query: "" }
states:
  find:
    tool: search
    input: { query: "{{query}}" }
    output: hits
    gates: [{ when: otherwise, then: ok, to: END }]
""",
}


def _parse_authored(source: str):
    """Parse authored YAML into a Machine, or return an error string."""
    try:
        doc = yaml.safe_load(source)
    except yaml.YAMLError as e:
        return None, f"yaml: {e}"
    if not isinstance(doc, dict):
        return None, "source is not a YAML mapping"
    try:
        return parse_machine(doc), None
    except (TypeError, ValueError, KeyError, PrepareError) as e:
        return None, f"parse: {e}"


def _run_behaviour(source: str, item: dict) -> tuple[bool, list[str]]:
    """Run all acceptance scenarios; return (all_pass, mismatch strings)."""
    machine, err = _parse_authored(source)
    if machine is None:
        return False, [err or "parse failed"]

    registry = {machine.name: machine}
    for name, md in (item.get("registry") or {}).items():
        try:
            registry[name] = parse_machine(md)
        except (TypeError, ValueError, KeyError, PrepareError) as e:
            return False, [f"registry {name!r}: {e}"]

    mismatches: list[str] = []
    scenarios = (item.get("acceptance") or {}).get("scenarios") or []
    if not scenarios:
        return False, ["no acceptance scenarios"]
    for sc in scenarios:
        name = sc.get("name", "?")
        expect = sc.get("expect")
        if expect is None:
            mismatches.append(f"{name}: no expect")
            continue
        try:
            result = run_scenario(machine, registry, sc)
        except Exception as e:  # a scenario error is a failure, not a crash
            mismatches.append(f"{name}: raised {type(e).__name__}: {e}")
            continue
        ms = match_expectation(result, expect)
        if ms:
            mismatches.extend(f"{name}: {m}" for m in ms)
    return (not mismatches), mismatches


def _check(source: str, item: dict) -> tuple[bool, list[str]]:
    """Static check via host.check_machine.

    When the item declares a `registry:` of sibling machines (for `call:`),
    write them next to the authored file so discovery matches `mklang check`
    on a project directory — the same contract authors get outside this harness.
    """
    reg = item.get("registry") or {}
    if not reg:
        verdict = check_machine(source=source)
        return bool(verdict.get("ok")), list(verdict.get("errors") or [])

    try:
        doc = yaml.safe_load(source)
    except yaml.YAMLError as e:
        return False, [f"source is not valid YAML: {e}"]
    if not isinstance(doc, dict):
        return False, ["source is not a YAML mapping"]
    name = str(doc.get("machine") or "authored")

    with tempfile.TemporaryDirectory(prefix="mklang-bs-") as tmp:
        tdir = Path(tmp)
        (tdir / f"{name}.mkl").write_text(source, encoding="utf-8")
        for rname, md in reg.items():
            (tdir / f"{rname}.mkl").write_text(
                yaml.safe_dump(md, sort_keys=False), encoding="utf-8"
            )
        verdict = check_machine(path=str(tdir / f"{name}.mkl"))
    return bool(verdict.get("ok")), list(verdict.get("errors") or [])


def run_trial(
    item: dict,
    repeat: int,
    *,
    author_fn: AuthorFn,
    max_repairs: int = 1,
) -> Trial:
    """Author (with optional static-repair loop), then check + behaviour."""
    attempts = 0
    prior_errors: list[str] = []
    source = ""
    check_ok = False
    check_errors: list[str] = []
    for _ in range(1 + max_repairs):
        attempts += 1
        try:
            source = author_fn(item, prior_errors or None)
        except (ProviderError, RefusalError, OSError, RuntimeError, ValueError) as e:
            return Trial(
                item_id=item["id"],
                shape=item.get("shape", ""),
                repeat=repeat,
                check_pass=False,
                behaviour_pass=False,
                author_attempts=attempts,
                error=f"author: {e}",
            )
        check_ok, check_errors = _check(source, item)
        if check_ok:
            break
        prior_errors = check_errors
    if not check_ok:
        return Trial(
            item_id=item["id"],
            shape=item.get("shape", ""),
            repeat=repeat,
            check_pass=False,
            behaviour_pass=False,
            author_attempts=attempts,
            check_errors=check_errors,
            source=source,
        )
    beh_ok, beh_ms = _run_behaviour(source, item)
    return Trial(
        item_id=item["id"],
        shape=item.get("shape", ""),
        repeat=repeat,
        check_pass=True,
        behaviour_pass=beh_ok,
        author_attempts=attempts,
        check_errors=[],
        behaviour_mismatches=beh_ms,
        source=source,
    )


def _summarize(trials: list[Trial]) -> dict:
    n = len(trials) or 1
    check_rate = sum(t.check_pass for t in trials) / n
    beh_rate = sum(t.behaviour_pass for t in trials) / n
    blind = check_rate - beh_rate
    multi_repair = sum(1 for t in trials if t.author_attempts >= 2)
    exhausted = sum(1 for t in trials if not t.check_pass and t.author_attempts >= 2)
    if blind < 0.10:
        verdict = "static gate substantially sufficient — do not build test_machine"
    elif blind <= 0.25:
        verdict = "real but bounded — test_machine as an opt-in tool"
    else:
        verdict = "structurally incomplete — test_machine required between save and run (1.1.0)"
    return {
        "n_trials": len(trials),
        "check_pass_rate": round(check_rate, 4),
        "behaviour_pass_rate": round(beh_rate, 4),
        "blind_spot": round(blind, 4),
        "fraction_needing_repair": round(multi_repair / n, 4),
        "fraction_exhausted_repair": round(exhausted / n, 4),
        "verdict": verdict,
        "per_item": _per_item(trials),
    }


def _per_item(trials: list[Trial]) -> dict:
    by: dict[str, list[Trial]] = {}
    for t in trials:
        by.setdefault(t.item_id, []).append(t)
    out: dict[str, dict] = {}
    for iid, group in sorted(by.items()):
        n = len(group)
        out[iid] = {
            "shape": group[0].shape,
            "n": n,
            "check_pass": sum(t.check_pass for t in group),
            "behaviour_pass": sum(t.behaviour_pass for t in group),
            "mean_author_attempts": round(sum(t.author_attempts for t in group) / n, 2),
        }
    return out


def _write_md(path: Path, summary: dict, trials: list[Trial], meta: dict) -> None:
    lines = [
        "# Authoring-loop blind_spot results",
        "",
        f"**Date:** {meta.get('date', '')}",
        f"**Provider / model:** {meta.get('provider', 'fixture')} / {meta.get('model', '-')}",
        f"**Repeats:** {meta.get('repeats', 1)} · **Items:** {meta.get('n_items', '?')}",
        f"**Corpus:** `{meta.get('corpus', DEFAULT_CORPUS)}`",
        "",
        "## Headline",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| check_pass_rate | **{summary['check_pass_rate']}** |",
        f"| behaviour_pass_rate | **{summary['behaviour_pass_rate']}** |",
        f"| **blind_spot** | **{summary['blind_spot']}** |",
        f"| fraction needing ≥1 repair | {summary['fraction_needing_repair']} |",
        f"| fraction exhausted repair without check_pass | {summary['fraction_exhausted_repair']} |",
        "",
        f"**Verdict:** {summary['verdict']}",
        "",
        "Thresholds (fixed in advance, issue #59): `<0.10` close B1 / "
        "`0.10–0.25` opt-in `test_machine` / `>0.25` required step + 1.1.0 headline.",
        "",
        "## Per-item",
        "",
        "| id | shape | check_pass | behaviour_pass | mean author attempts |",
        "| --- | --- | --- | --- | --- |",
    ]
    for iid, row in summary["per_item"].items():
        lines.append(
            f"| `{iid}` | {row['shape']} | {row['check_pass']}/{row['n']} | "
            f"{row['behaviour_pass']}/{row['n']} | {row['mean_author_attempts']} |"
        )
    fails = [t for t in trials if t.check_pass and not t.behaviour_pass]
    if fails:
        lines += ["", "## Blind-spot trials (check ok, behaviour fail)", ""]
        for t in fails:
            lines.append(f"- `{t.item_id}` r{t.repeat}: " + "; ".join(t.behaviour_mismatches[:3]))
    lines += ["", "## Related", "", "- Issue #59 · validation report 2026-07-23 (B1/B2)", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _make_live_author(config: str | None, provider: str | None) -> tuple[AuthorFn, str, str]:
    """Build a live AuthorFn and return (fn, provider_name, model)."""
    load_env_files()
    prov = load_provider(config, provider)
    if not prov.api_key and prov.name != "local":
        raise SystemExit(f"no API key for provider {prov.name!r} (set {prov.api_key_env})")
    llm = build_llm(prov)
    model = (
        prov.tiers.get("reasoning") or prov.tiers.get("balanced") or next(iter(prov.tiers.values()))
    )

    def author(item: dict, prior_errors: list[str] | None) -> str:
        return _author_live(llm, model, item["request"], prior_errors)

    return author, prov.name, model


def _make_fixture_author(*, pass_check: bool) -> AuthorFn:
    def author(item: dict, prior_errors: list[str] | None) -> str:
        del prior_errors  # fixtures do not re-author on static failure
        return _fixture_source(item, pass_check=pass_check)

    return author


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    ap.add_argument("--config", default=None, help="runtime.yaml (default: resolved host config)")
    ap.add_argument("--provider", default=None, help="provider name (live mode)")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--ids", default="", help="comma-separated item ids (default: all)")
    ap.add_argument(
        "--max-repairs",
        type=int,
        default=1,
        help="static-repair re-authors after check fail",
    )
    ap.add_argument(
        "--fixture-pass",
        action="store_true",
        help="offline: use GOLD machines (no API). Validates corpus acceptance + harness.",
    )
    ap.add_argument(
        "--fixture-fail",
        action="store_true",
        help="offline: emit broken sources (sanity for check_pass=0 path).",
    )
    ap.add_argument("--summary-json", type=Path, default=None)
    ap.add_argument("--summary-md", type=Path, default=None)
    ap.add_argument("--keep-sources-dir", type=Path, default=None)
    args = ap.parse_args(argv)

    items = _load_corpus(args.corpus)
    if args.ids:
        want = {x.strip() for x in args.ids.split(",") if x.strip()}
        items = [i for i in items if i["id"] in want]
        missing = want - {i["id"] for i in items}
        if missing:
            raise SystemExit(f"unknown ids: {sorted(missing)}")

    live = not (args.fixture_pass or args.fixture_fail)
    if live:
        author_fn, provider_name, model = _make_live_author(args.config, args.provider)
    else:
        author_fn = _make_fixture_author(pass_check=args.fixture_pass)
        provider_name, model = "fixture", "-"

    trials: list[Trial] = []
    t0 = time.time()
    for item in items:
        for r in range(args.repeats):
            print(f"→ {item['id']} r{r} …", flush=True)
            trial = run_trial(item, r, author_fn=author_fn, max_repairs=args.max_repairs)
            if trial.behaviour_pass:
                mark = "OK"
            elif not trial.check_pass:
                mark = "CHECK"
            else:
                mark = "BEH"
            print(
                f"  [{mark}] check={trial.check_pass} beh={trial.behaviour_pass} "
                f"attempts={trial.author_attempts}"
                + (f" err={trial.error}" if trial.error else ""),
                flush=True,
            )
            if args.keep_sources_dir and trial.source:
                args.keep_sources_dir.mkdir(parents=True, exist_ok=True)
                (args.keep_sources_dir / f"{item['id']}-r{r}.mkl").write_text(
                    trial.source, encoding="utf-8"
                )
            trials.append(trial)
    summary = _summarize(trials)
    meta = {
        "date": time.strftime("%Y-%m-%d"),
        "provider": provider_name,
        "model": model,
        "repeats": args.repeats,
        "n_items": len(items),
        "corpus": str(args.corpus),
        "elapsed_s": round(time.time() - t0, 1),
        "live": live,
    }
    print(json.dumps({"summary": summary, "meta": meta}, indent=2))
    if args.summary_json:
        args.summary_json.write_text(
            json.dumps(
                {"summary": summary, "meta": meta, "trials": [asdict(t) for t in trials]},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    if args.summary_md:
        _write_md(args.summary_md, summary, trials, meta)
    # Offline gold path must be fully green (harness + corpus integrity).
    if args.fixture_pass and summary["behaviour_pass_rate"] < 1.0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
