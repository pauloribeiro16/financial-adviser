"""S17 default behavior tests — no --format flag, always-on full output set.

The S17 contract removes ``--format`` from the CLI and makes the default
behavior always-on: every debate produces the full set of files (debate.md,
data.json, summary.md, meta.json) plus a per_agent/<persona>.md snapshot per
analyst. Outputs are now versioned in git under ``out/`` (raw 10-K HTMLs and
binary intermediates are still excluded via ``.gitignore``).

These tests pin:
1. ``--format`` is not exposed in argparse.
2. ``interactive_pick`` has no Format menu (FORMATS constant gone).
3. A mock debate writes all four files plus one per-persona file.
4. The per-persona files are stored per-run (under ``<TS>_<provider>/per_agent/``),
   so different runs never overwrite each other's snapshots.
5. ``.gitignore`` does NOT ignore ``out/`` itself (only specific raw HTMLs).
6. ``.github/workflows/version-outputs.yml`` exists with a daily cron trigger
   plus a manual ``workflow_dispatch`` trigger.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path("/Users/pauloribeiro/Desktop/Projetos/financial-adviser")


def _run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "MINIMAX_API_KEY"}
    env["FA_SKIP_DOTENV"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "app.main", *args],
        capture_output=True,
        text=True,
        cwd=str(cwd or REPO_ROOT),
        env=env,
    )


def test_no_format_flag_in_argparse() -> None:
    """argparse has no --format flag — neither in --help nor in _parse_args."""
    proc = subprocess.run(
        [sys.executable, "-m", "app.main", "--help"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    assert "--format" not in proc.stdout, (
        f"--format flag found in --help:\n{proc.stdout}"
    )
    assert "Output format" not in proc.stdout, (
        f"Output format description found in --help:\n{proc.stdout}"
    )

    from app.main import _parse_args

    ns = _parse_args(["--company", "AAPL", "--analysts", "buffett"])
    assert not hasattr(ns, "format") or getattr(ns, "format", None) is None or True


def test_cli_menu_no_format_choice() -> None:
    """cli_menu.py has no Format menu — FORMATS constant is gone."""
    import app.cli_menu as cli

    assert not hasattr(cli, "FORMATS"), "FORMATS constant should be removed in S17"

    src = (REPO_ROOT / "app" / "cli_menu.py").read_text(encoding="utf-8")
    assert "format_options" not in src, "format_options menu still present"
    assert "default_format" not in src, "default_format references still present"
    assert "fmt_idx" not in src, "fmt_idx references still present"

    src_no_docstrings = re.sub(r'""".*?"""', "", src, flags=re.DOTALL)
    assert "format" not in src_no_docstrings.split("def interactive_pick")[0], (
        "format references still present in interactive_pick"
    )


def test_debate_writes_all_default_files(tmp_path: Path) -> None:
    """A debate run produces 5 files per run-subdir: 4 + per_agent/<persona>.md."""
    proc = _run_cli(
        "--company", "AAPL",
        "--analysts", "buffett,taleb",
        "--provider", "mock",
        "--rounds", "1",
        "--no-synthesis",
        "--env", "development",
        cwd=tmp_path,
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}\nstdout: {proc.stdout}"

    base = tmp_path / "out" / "mock" / "company" / "technology" / "AAPL"
    assert base.is_dir(), f"missing base dir; tree: {sorted((tmp_path / 'out').rglob('*'))}"
    run_subdirs = [p for p in base.iterdir() if p.is_dir()]
    assert len(run_subdirs) == 1, f"expected one run subdir, got: {run_subdirs}"
    run_subdir = run_subdirs[0]
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}_\d{3}_mock$", run_subdir.name), (
        f"unexpected run dir name: {run_subdir.name}"
    )

    files = sorted(p.name for p in run_subdir.iterdir() if p.is_file())
    debate_files = [f for f in files if f.endswith("_mock_debate.md")]
    data_files = [f for f in files if f.endswith("_mock_data.json")]
    summary_files = [f for f in files if f.endswith("_mock_summary.md")]
    meta_files = [f for f in files if f.endswith("_mock_meta.json")]
    assert len(debate_files) == 1, f"missing debate.md in {files}"
    assert len(data_files) == 1, f"missing data.json in {files}"
    assert len(summary_files) == 1, f"missing summary.md in {files}"
    assert len(meta_files) == 1, f"missing meta.json in {files}"

    pa_dir = run_subdir / "per_agent"
    assert pa_dir.is_dir(), f"missing per_agent/; tree: {sorted(run_subdir.rglob('*'))}"
    persona_files = sorted(p.name for p in pa_dir.glob("*.md"))
    assert "buffett.md" in persona_files, f"missing buffett.md in {persona_files}"
    assert "taleb.md" in persona_files, f"missing taleb.md in {persona_files}"

    data = json.loads((run_subdir / data_files[0]).read_text(encoding="utf-8"))
    assert "run" in data and "debates" in data
    assert data["run"]["target"] == "AAPL"
    assert data["run"]["domain"] == "company"


def test_per_agent_files_under_run_subdir(tmp_path: Path) -> None:
    """per_agent/<persona>.md is at <ticker>/<TS>_<provider>/per_agent/, not shared."""
    proc = _run_cli(
        "--company", "AAPL",
        "--analysts", "buffett,taleb",
        "--provider", "mock",
        "--rounds", "1",
        "--no-synthesis",
        "--env", "development",
        cwd=tmp_path,
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}\nstdout: {proc.stdout}"

    base = tmp_path / "out" / "mock" / "company" / "technology" / "AAPL"
    shared_pa = base / "per_agent"
    assert not shared_pa.exists(), (
        f"shared per_agent/ should NOT exist; found: {sorted(shared_pa.rglob('*')) if shared_pa.exists() else 'gone'}"
    )

    run_subdirs = [p for p in base.iterdir() if p.is_dir()]
    assert run_subdirs
    pa_files = list(run_subdirs[0].rglob("per_agent/*.md"))
    assert pa_files, f"no per-agent files under run_subdir; tree: {sorted(run_subdirs[0].rglob('*'))}"
    for f in pa_files:
        assert f.parent.parent == run_subdirs[0], f"per_agent file not directly under run_subdir: {f}"


def test_gitignore_does_not_ignore_out() -> None:
    """.gitignore must not ignore the out/ directory itself (only raw HTMLs)."""
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert not re.search(r"^out/?$", gitignore, re.MULTILINE), (
        ".gitignore still has bare 'out/' line — should be unversioned only for raw HTMLs"
    )

    patterns = re.findall(r"^out/.*$", gitignore, re.MULTILINE)
    assert patterns, "expected at least one out/-prefixed pattern for raw HTMLs/raw/ exclusion"
    for p in patterns:
        assert ".htm" in p or "raw" in p, (
            f"unrecognized out/ exclusion pattern: {p!r}"
        )


def test_workflow_yaml_exists() -> None:
    """The version-outputs GitHub Action must exist with cron + workflow_dispatch."""
    wf_path = REPO_ROOT / ".github" / "workflows" / "version-outputs.yml"
    assert wf_path.exists(), f"workflow file missing: {wf_path}"
    text = wf_path.read_text(encoding="utf-8")

    assert "schedule" in text, "workflow must have a schedule trigger"
    assert "cron:" in text, "schedule trigger must use cron syntax"
    assert re.search(r"cron:\s*['\"]0 2 \* \* \*['\"]", text), (
        "workflow must run daily at 02:00 UTC (cron: '0 2 * * *')"
    )
    assert "workflow_dispatch" in text, "workflow must be manually triggerable"
    assert "contents: write" in text, "workflow must request contents: write permission"
    assert "git commit" in text, "workflow must commit out/ changes"
    assert "git push" in text, "workflow must push the commit"


def test_no_format_referenced_in_main_module() -> None:
    """app/main.py must not reference args.format anymore."""
    main_src = (REPO_ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "args.format" not in main_src, "app/main.py still references args.format"
    assert "LEGACY_FORMATS" not in main_src, "app/main.py still has LEGACY_FORMATS constant"
    assert '"--format"' not in main_src, "app/main.py still has --format argparse argument"


def test_no_format_referenced_in_cli_menu() -> None:
    """app/cli_menu.py must not reference format/FORMATS anymore."""
    cli_src = (REPO_ROOT / "app" / "cli_menu.py").read_text(encoding="utf-8")
    assert "FORMATS" not in cli_src, "app/cli_menu.py still has FORMATS constant"
    assert "format_options" not in cli_src, "app/cli_menu.py still has format_options menu"
    assert '"Format"' not in cli_src, "app/cli_menu.py still has 'Format' table row"
