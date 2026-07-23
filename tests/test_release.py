"""Release provenance and live-matrix gate tests (offline)."""

from pathlib import Path
import importlib.util
import re
import subprocess
import tomllib

import pytest

import mklang


ROOT = Path(__file__).resolve().parents[1]


def _gate_divergence_module():
    path = ROOT / "scripts" / "gate_divergence.py"
    spec = importlib.util.spec_from_file_location("gate_divergence", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_argcomplete_marker_is_in_the_entrypoint_head():
    # argcomplete only scans the first 1024 bytes of the console-script module.
    cli_path = ROOT / "src" / "mklang" / "cli.py"
    assert b"PYTHON_ARGCOMPLETE_OK" in cli_path.read_bytes()[:1024]


def test_package_versions_are_synchronized():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["version"] == mklang.__version__


def test_pkgbuild_version_is_synchronized():
    # Nothing else pins the Arch recipe to the package version; sha256sums is
    # excluded because it can only follow the published PyPI sdist digest
    # (packaging/arch/README.md release checklist).
    pkgbuild = (ROOT / "packaging" / "arch" / "PKGBUILD").read_text(encoding="utf-8")
    assert f"pkgver={mklang.__version__}\n" in pkgbuild


def test_current_version_docs_are_synchronized():
    version = mklang.__version__
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")

    assert f"`pyproject.toml` (currently `{version}`)" in changelog
    assert f"## [{version}]" in changelog
    assert f"package {version}**" in readme
    assert f"package **{version}**" in roadmap


# The tag/CHANGELOG invariant: distribution began at 0.5.3 (the first PyPI
# release was 0.5.4; 0.5.3 was the last pre-publish tag). Every CHANGELOG entry
# from 0.5.3 up MUST carry a matching `v<version>` git tag; entries at or below
# 0.5.2 are pre-distribution history and are exempt. See the 2026-07-23
# validation report (docs/experiments/) for the measured three-way divergence.
_DISTRIBUTION_CUTOFF = (0, 5, 3)


def _version_tuple(version: str) -> tuple[int, ...]:
    """Parse a dotted version into a padded 3-tuple for ordering (`0.5` -> (0, 5, 0))."""
    parts = [int(p) for p in version.split(".")]
    return tuple(parts + [0] * (3 - len(parts)))


def _changelog_versions() -> list[str]:
    """Every version heading (`## [X.Y.Z]`) declared in CHANGELOG.md."""
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    return re.findall(r"^## \[([0-9][^\]]*)\]", changelog, re.MULTILINE)


def _git_tags() -> set[str] | None:
    """Return the repo's tags, or None when git/tags are unavailable (an sdist
    install or a shallow checkout without tags — the invariant simply can't be
    checked there, so the test skips rather than fails)."""
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "tag"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    tags = set(result.stdout.split())
    return tags or None


def test_changelog_entries_from_distribution_cutoff_are_tagged():
    """Every CHANGELOG entry from the distribution cutoff up must carry a git tag."""
    tags = _git_tags()
    if tags is None:
        pytest.skip("no git tags available (sdist or shallow checkout)")
    missing = [
        version
        for version in _changelog_versions()
        if _version_tuple(version) >= _DISTRIBUTION_CUTOFF and f"v{version}" not in tags
    ]
    assert not missing, (
        f"CHANGELOG entries at/above {'.'.join(map(str, _DISTRIBUTION_CUTOFF))} without a "
        f"matching git tag: {missing}. Tag them (`v<version>`) or, if they were never "
        f"released, drop them from the CHANGELOG."
    )


def test_console_docs_link_to_host_path_ssot():
    best_practices = (ROOT / "docs/guides/best-practices.md").read_text(encoding="utf-8")
    console = (ROOT / "docs/guides/console.md").read_text(encoding="utf-8")
    anchor = "#current-host-layout-documentation-ssot"
    session_path = "$XDG_STATE_HOME/mklang/console/sessions/<id>/"

    assert "### Current host layout (documentation SSOT)" in best_practices
    assert session_path in best_practices
    assert session_path in console
    assert f"best-practices.md{anchor}" in console


def test_release_gate_requires_every_core_repeat():
    _ci_errors = _gate_divergence_module()._ci_errors

    rows = [
        {
            "provider": provider,
            "repeat": repeat,
            "skipped": False,
            "status": "done",
            "signature": "same",
            "output_hash": "same",
        }
        for provider in ("deepseek", "openai")
        for repeat in range(3)
    ]
    assert _ci_errors(rows, ["deepseek", "openai"], 3, 1.0) == []


def test_release_gate_ignores_skipped_optional_providers_when_counting_machines():
    # Regression: skipped providers carry no `machine` field (see `_run_once`), so
    # the distinct-machine count once included `None` and inflated
    # `repeats * n_machines`. With the release matrix always skipping the
    # no-key optional providers, that made the gate demand 2x the runs and fail
    # the 0.16.0 live-matrix despite perfect agreement.
    _ci_errors = _gate_divergence_module()._ci_errors

    rows = [
        {
            "provider": provider,
            "machine": "gate_divergence",
            "repeat": repeat,
            "skipped": False,
            "status": "done",
            "signature": "same",
            "output_hash": "same",
        }
        for provider in ("deepseek", "openai")
        for repeat in range(3)
    ]
    # Optional providers without keys: skipped rows have NO `machine` field.
    rows += [
        {"provider": provider, "repeat": repeat, "skipped": True, "reason": "no API key"}
        for provider in ("anthropic", "google", "openrouter", "xai", "mistral")
        for repeat in range(3)
    ]
    assert _ci_errors(rows, ["deepseek", "openai"], 3, 1.0) == []


def test_release_gate_distinguishes_skips_failures_and_divergence():
    module = _gate_divergence_module()
    _ci_errors, _summary = module._ci_errors, module._summary

    rows = [
        {
            "provider": "deepseek",
            "repeat": 0,
            "skipped": False,
            "status": "done",
            "signature": "a",
            "output_hash": "a",
        },
        {"provider": "deepseek", "repeat": 1, "skipped": False, "status": "error", "error": "boom"},
        {"provider": "openai", "repeat": 0, "skipped": True, "reason": "no API key"},
        {
            "provider": "openai",
            "repeat": 1,
            "skipped": False,
            "status": "done",
            "signature": "b",
            "output_hash": "b",
        },
    ]
    summary = _summary(rows, ["deepseek", "openai"])
    errors = _ci_errors(rows, ["deepseek", "openai"], 2, 1.0)

    assert summary["runs_skipped"] == 1
    assert summary["runs_failed"] == 1
    assert any("deepseek" in error and "failed" in error for error in errors)
    assert any("openai" in error and "skipped" in error for error in errors)
    assert any("agreement" in error for error in errors)


def test_optional_provider_divergence_does_not_block_core_gate():
    _ci_errors = _gate_divergence_module()._ci_errors

    rows = [
        {
            "provider": "deepseek",
            "repeat": 0,
            "skipped": False,
            "status": "done",
            "signature": "same",
            "output_hash": "same",
        },
        {
            "provider": "openai",
            "repeat": 0,
            "skipped": False,
            "status": "done",
            "signature": "same",
            "output_hash": "same",
        },
        {
            "provider": "mistral",
            "repeat": 0,
            "skipped": False,
            "status": "done",
            "signature": "different",
            "output_hash": "different",
        },
    ]
    assert _ci_errors(rows, ["deepseek", "openai"], 1, 1.0) == []


def test_release_gate_per_machine_agreement_override():
    """Control-flow machines can use a lower floor than the default 1.0."""
    _ci_errors = _gate_divergence_module()._ci_errors

    # Two machines, two providers, one repeat each — perfect agreement on easy,
    # split signatures on escalate (rate 0.0 for the only cross-provider pair).
    rows = []
    for machine, sig in (("gate_divergence", "easy"), ("severity_escalate", "a")):
        rows.append(
            {
                "provider": "deepseek",
                "machine": machine,
                "repeat": 0,
                "skipped": False,
                "status": "done",
                "signature": sig,
                "output_hash": sig,
            }
        )
    rows.append(
        {
            "provider": "openai",
            "machine": "gate_divergence",
            "repeat": 0,
            "skipped": False,
            "status": "done",
            "signature": "easy",
            "output_hash": "easy",
        }
    )
    rows.append(
        {
            "provider": "openai",
            "machine": "severity_escalate",
            "repeat": 0,
            "skipped": False,
            "status": "done",
            "signature": "b",  # disagrees with deepseek
            "output_hash": "b",
        }
    )
    # Default floor 1.0 fails escalate
    errs = _ci_errors(rows, ["deepseek", "openai"], 1, 1.0)
    assert any("severity_escalate" in e for e in errs)
    # Override floor 0.0 accepts total disagreement on escalate; easy still 1.0
    assert (
        _ci_errors(
            rows,
            ["deepseek", "openai"],
            1,
            1.0,
            min_agreement_by_machine={"severity_escalate": 0.0},
        )
        == []
    )
