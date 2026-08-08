"""The taint-incidence harness (ADR 0031 §1) runs offline and reports the shape
the experiment doc records."""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_taint_incidence_reports_the_bundled_corpus():
    out = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "taint_incidence.py")],
        capture_output=True,
        text=True,
        check=True,
    )
    summary = json.loads(out.stdout)
    assert summary["machines"] >= 15
    assert summary["threshold_adr_0031"] == 0.25
    # The showcase's real send is the corpus's one effectful tool state; if this
    # grows, the experiment doc's row is stale and should gain a new one.
    assert summary["effectful_tool_states"] >= 1
    assert set(summary["per_machine"]) >= {"triage"}
