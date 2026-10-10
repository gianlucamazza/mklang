"""Keyless, offline mklang playground for a static Gradio-Lite Space.

Same host surfaces as ``spaces/playground/app.py``, running in the browser
via Pyodide. mklang is installed from the committed wheel with
``deps=False`` — parse / check / lint / format / scripted runs never
load the openai, textual, or rich packages. No API keys, no model calls,
no Path B.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import yaml

from mklang.checkpoint import encode_checkpoint
from mklang.engine import RunResult
from mklang.host import build_output, check_machine
from mklang.loader import load_machine, validate_dict
from mklang.model import Gate, parse_machine
from mklang.registry import base_registry
from mklang.scripttest import build_registry, match_expectation, run_scenario

# No telemetry from this process. Gradio / hub clients honour these flags.
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("DO_NOT_TRACK", "1")

HERE = Path(__file__).resolve().parent
EXAMPLES = HERE / "examples"
CONFORMANCE = HERE / "conformance"
REPO_URL = "https://github.com/gianlucamazza/mklang"
ISSUE_123 = f"{REPO_URL}/issues/123"

HONESTY = f"""
# mklang playground lite (keyless / offline / static)

Deterministic host tools, running **in this browser** via Gradio-Lite +
Pyodide. **No LLM key, no network model call, no Path B.**

This Space parses, validates, lints, and formats `.mkl` documents, then runs
bundled [scripted scenarios]({REPO_URL}/blob/main/docs/reference/cli.md#test)
and [conformance cases]({REPO_URL}/blob/main/conformance/README.md) with the
scripted LLM. Produce texts and judge picks come from the fixture, not a model.

mklang is loaded from a committed wheel with `micropip.install(..., deps=False)`.
`openai`, `textual`, and `rich` are CLI / TUI / live-provider extras — they
are not imported on this path.

**It does not** run `mklang run` against a provider, accept an API key, call
Jev / Noul / any `judge: jev-*` adapter (Path B, [issue #123]({ISSUE_123}),
`production_ready: false`), or send telemetry.

Source: [{REPO_URL}]({REPO_URL})
"""


def _dumps(payload: object) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n"


def _error(*messages: str, **extra: object) -> str:
    payload: dict[str, object] = {"ok": False, "errors": list(messages)}
    payload.update(extra)
    return _dumps(payload)


def bundled_example_names() -> list[str]:
    return sorted(path.stem for path in EXAMPLES.glob("*.mkl"))


def bundled_conformance_names() -> list[str]:
    return sorted(path.stem for path in CONFORMANCE.glob("*.yaml"))


def bundled_scenario_names(example: str) -> list[str]:
    script = EXAMPLES / f"{example}.test.yaml"
    if not script.is_file():
        return []
    doc = yaml.safe_load(script.read_text(encoding="utf-8")) or {}
    return [str(row["name"]) for row in doc.get("scenarios") or [] if row.get("name")]


def load_example_source(example: str) -> str:
    path = EXAMPLES / f"{example}.mkl"
    if not path.is_file():
        return f"# unknown bundled example: {example}\n"
    return path.read_text(encoding="utf-8")


def _gate_summary(gate: Gate) -> dict[str, object]:
    summary: dict[str, object] = {"when": gate.when, "then": gate.kind, "to": gate.to}
    if gate.repair is not None:
        summary["repair"] = gate.repair
    if gate.hook:
        summary["hook"] = gate.hook
    if gate.ask:
        summary["ask"] = gate.ask
    if gate.reply_to:
        summary["reply_to"] = gate.reply_to
    return summary


def parse_source(source: str) -> str:
    """YAML → schema → `parse_machine`. No provider, no Path B."""
    if not source or not str(source).strip():
        return _error("source is empty")
    try:
        data = yaml.safe_load(source)
    except yaml.YAMLError as exc:
        return _error(f"invalid YAML: {exc}")
    if not isinstance(data, dict):
        return _error("source is not a mapping (a .mkl document is a YAML mapping)")
    try:
        validate_dict(data)
        machine = parse_machine(data)
    except Exception as exc:  # schema or parse failure — surface the message
        return _error(getattr(exc, "message", str(exc)))
    return _dumps(
        {
            "ok": True,
            "machine": machine.name,
            "version": machine.version,
            "entry": machine.entry,
            "budget": machine.budget,
            "default_tier": machine.default_tier,
            "result": machine.result,
            "states": [
                {
                    "id": sid,
                    "kind": state.kind,
                    "output": state.output,
                    "tier": state.tier,
                    "parse": state.parse,
                    "tool": state.tool,
                    "call": state.call,
                    "gates": [_gate_summary(gate) for gate in state.gates],
                }
                for sid, state in machine.states.items()
            ],
        }
    )


def check_source(source: str, strict: bool = False) -> str:
    """`mklang check` + lint on inline source. No provider, no `--llm`."""
    if not source or not str(source).strip():
        return _error("source is empty")
    return _dumps(check_machine(source=source, strict=bool(strict)))


def format_source(source: str) -> str:
    """Parse YAML and dump it again. Comments are not preserved."""
    if not source or not str(source).strip():
        return "# empty document\n"
    try:
        data = yaml.safe_load(source)
    except yaml.YAMLError as exc:
        return f"# format failed: invalid YAML\n# {exc}\n"
    if data is None:
        return "# empty document\n"
    if not isinstance(data, dict):
        return "# format failed: a .mkl document must be a YAML mapping\n"
    return yaml.safe_dump(
        data,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        indent=2,
        width=88,
    )


def _checkpoint_envelope(
    result: RunResult, *, machine_name: str, machine_path: str, source: str | None
) -> dict[str, object] | None:
    if result.status != "suspended" or not result.frames:
        return None
    raw = encode_checkpoint(
        machine_name,
        machine_path,
        result.error or "suspended",
        result.frames,
        cost_budget=None,
        machine_source=source,
    )
    envelope = json.loads(raw.decode("utf-8"))
    if not isinstance(envelope, dict):
        return None
    return envelope


def _scenario_payload(
    result: RunResult,
    expect: dict | None,
    *,
    machine_name: str,
    machine_path: str,
    source: str | None = None,
) -> dict[str, object]:
    mismatches = match_expectation(result, expect) if expect else []
    payload: dict[str, object] = {
        "ok": not mismatches if expect is not None else result.status != "halt",
        "passed": not mismatches if expect is not None else None,
        "mismatches": [str(item) for item in mismatches],
        "result": build_output(result),
        "context": result.context,
    }
    if expect is not None:
        payload["expect"] = expect
    checkpoint = _checkpoint_envelope(
        result, machine_name=machine_name, machine_path=machine_path, source=source
    )
    if checkpoint is not None:
        payload["checkpoint"] = checkpoint
    return payload


def run_example(example: str, scenario: str) -> str:
    """Run one bundled `*.test.yaml` scenario with the scripted LLM."""
    machine_path = EXAMPLES / f"{example}.mkl"
    script_path = EXAMPLES / f"{example}.test.yaml"
    if not machine_path.is_file() or not script_path.is_file():
        return _error(
            f"unknown bundled example {example!r}",
            available=bundled_example_names(),
        )
    try:
        machine = load_machine(machine_path)
    except Exception as exc:
        return _error(f"{machine_path.name}: {getattr(exc, 'message', exc)}")
    doc = yaml.safe_load(script_path.read_text(encoding="utf-8")) or {}
    scenarios = doc.get("scenarios") or []
    chosen = next((row for row in scenarios if row.get("name") == scenario), None)
    if chosen is None:
        return _error(
            f"unknown scenario {scenario!r} for example {example!r}",
            available=bundled_scenario_names(example),
        )
    result = run_scenario(machine, {**base_registry(), machine.name: machine}, chosen)
    return _dumps(
        {
            "example": example,
            "scenario": scenario,
            **_scenario_payload(
                result,
                chosen.get("expect"),
                machine_name=machine.name,
                machine_path=str(machine_path),
                source=machine_path.read_text(encoding="utf-8"),
            ),
        }
    )


def run_conformance(case: str) -> str:
    """Run one bundled conformance case (scripted LLM, same matcher as CI)."""
    path = CONFORMANCE / f"{case}.yaml"
    if not path.is_file():
        return _error(
            f"unknown bundled conformance case {case!r}",
            available=bundled_conformance_names(),
        )
    case_doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(case_doc, dict) or "machine" not in case_doc:
        return _error(f"{path.name}: not a conformance case")
    machine, registry = build_registry(case_doc)
    result = run_scenario(machine, registry, case_doc)
    return _dumps(
        {
            "case": case_doc.get("case", case),
            "description": case_doc.get("description"),
            **_scenario_payload(
                result,
                case_doc.get("expect"),
                machine_name=machine.name,
                machine_path=str(path),
                source=yaml.safe_dump(case_doc.get("machine"), sort_keys=False),
            ),
        }
    )


def build_demo():
    """Build the Gradio UI. Importing callbacks does not require this."""
    import gradio as gr

    example_names = bundled_example_names()
    default_example = "hello" if "hello" in example_names else example_names[0]
    default_scenarios = bundled_scenario_names(default_example)
    default_scenario = default_scenarios[0] if default_scenarios else None
    case_names = bundled_conformance_names()
    default_case = "linear" if "linear" in case_names else (case_names[0] if case_names else None)

    with gr.Blocks(title="mklang playground") as demo:
        gr.Markdown(HONESTY)

        with gr.Tab("Inspect"):
            gr.Markdown(
                "Paste a `.mkl` document or load a bundled example. "
                "**Parse** is YAML + schema + the host dataclass. "
                "**Check** is `mklang check` plus lint (no `--llm`). "
                "**Format** re-dumps YAML (comments are dropped)."
            )
            inspect_example = gr.Dropdown(
                label="Bundled example",
                choices=example_names,
                value=default_example,
            )
            source = gr.Code(
                label=".mkl source",
                language="yaml",
                value=load_example_source(default_example),
                lines=22,
            )
            with gr.Row():
                parse_btn = gr.Button("Parse", variant="primary")
                check_btn = gr.Button("Check + lint")
                format_btn = gr.Button("Format")
            inspect_out = gr.Code(label="Output", language="json", lines=18)

            inspect_example.change(fn=load_example_source, inputs=inspect_example, outputs=source)
            parse_btn.click(fn=parse_source, inputs=source, outputs=inspect_out)
            check_btn.click(fn=check_source, inputs=source, outputs=inspect_out)
            format_btn.click(fn=format_source, inputs=source, outputs=inspect_out)

        with gr.Tab("Run example"):
            gr.Markdown(
                "Scripted `mklang test` on a bundled machine. The LLM, tools, "
                "and judges are fixtures — the same path CI uses. No keys."
            )
            run_example_dd = gr.Dropdown(
                label="Example",
                choices=example_names,
                value=default_example,
            )
            run_scenario_dd = gr.Dropdown(
                label="Scenario",
                choices=default_scenarios,
                value=default_scenario,
            )
            run_btn = gr.Button("Run scripted scenario", variant="primary")
            run_out = gr.Code(label="Run result / checkpoint", language="json", lines=22)

            def _sync_scenarios(example: str):
                names = bundled_scenario_names(example)
                return gr.update(choices=names, value=names[0] if names else None)

            run_example_dd.change(
                fn=_sync_scenarios, inputs=run_example_dd, outputs=run_scenario_dd
            )
            run_btn.click(fn=run_example, inputs=[run_example_dd, run_scenario_dd], outputs=run_out)

        with gr.Tab("Conformance"):
            gr.Markdown(
                "Bundled interpreter cases from `conformance/cases/`. "
                "`escalate-ask` suspends and shows the checkpoint envelope "
                "(in memory only — nothing is written to disk)."
            )
            case_dd = gr.Dropdown(
                label="Case",
                choices=case_names,
                value=default_case,
            )
            case_btn = gr.Button("Run conformance case", variant="primary")
            case_out = gr.Code(label="Conformance output", language="json", lines=22)
            case_btn.click(fn=run_conformance, inputs=case_dd, outputs=case_out)

        gr.Markdown(
            f"Not Path B. See [issue #123]({ISSUE_123}) — Noul-only host judge "
            "is opt-in, not default, and `production_ready` is false. "
            f"License: Apache-2.0. Repo: {REPO_URL}"
        )

    return demo


# Built when Gradio is installed so `gradio app.py` / Spaces can find `demo`.
# Importing this module for the smoke test must not launch a server.
try:
    demo = build_demo()
except (ImportError, AttributeError):
    demo = None


if __name__ == "__main__":
    if demo is None:
        raise SystemExit("gradio is required to launch the playground UI")
    # Gradio-Lite 5.x has no ssr_mode; Gradio 6 accepts it. Stay compatible.
    try:
        demo.launch(ssr_mode=False)
    except TypeError:
        demo.launch()
