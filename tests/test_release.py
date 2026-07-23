"""Release provenance and live-matrix gate tests (offline)."""

from pathlib import Path
import importlib.util
import tomllib

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
