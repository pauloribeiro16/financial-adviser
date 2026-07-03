from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from app.formatter import (
    default_output_path,
    default_run_dir,
    output_path,
    per_agent_dir,
    run_dir,
    run_timestamp,
    slugify,
)

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


def test_slugify_basic_mappings() -> None:
    assert slugify("Financial Services") == "financial-services"
    assert slugify("Consumer Cyclical") == "consumer-cyclical"
    assert slugify("US.FFR") == "us-ffr"
    assert slugify("healthcare") == "healthcare"
    assert slugify("") == ""
    assert slugify("   ") == ""
    assert slugify("Tech & Telecom") == "tech-telecom"
    assert slugify("Foo---bar") == "foo-bar"


def test_run_timestamp_format() -> None:
    ts = run_timestamp()
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}_\d{3}$", ts), ts


def test_run_dir_creates_hierarchy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    p = run_dir("company", "Financial Services", "JPM")
    expected = (tmp_path / "out" / "company" / "financial-services" / "JPM").resolve()
    assert p.resolve() == expected
    assert expected.is_dir()
    assert (expected / "per_agent").exists() is False


def test_output_path_full(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    p = output_path(
        "company",
        "Financial Services",
        "JPM",
        "2026-07-03T14-23-45_123",
        "minimax",
        "debate",
        "md",
    )
    expected = (
        tmp_path / "out" / "company" / "financial-services" / "JPM" /
        "2026-07-03T14-23-45_123_minimax_debate.md"
    ).resolve()
    assert p.resolve() == expected
    assert expected.parent.is_dir()


def test_per_agent_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    p = per_agent_dir("macro", "US.FFR", "US.FFR")
    expected = (tmp_path / "out" / "macro" / "us-ffr" / "US.FFR" / "per_agent").resolve()
    assert p.resolve() == expected
    assert expected.is_dir()


def test_legacy_paths_preserved() -> None:
    assert default_output_path().startswith("./out/run_")
    assert default_output_path().endswith(".md")
    assert default_run_dir().startswith("./out/run_")
    assert re.match(r"^\./out/run_\d{8}_\d{6}_\d{6}$", default_run_dir())


def test_legacy_run_dir_with_explicit_id() -> None:
    p = default_run_dir(run_id="20260703_120000_000000")
    assert p == "./out/run_20260703_120000_000000"


def test_e2e_company_debate_writes_to_new_structure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = _run_cli(
        "--company", "AAPL",
        "--analysts", "buffett",
        "--provider", "mock",
        "--format", "debate",
        "--no-synthesis",
        "--rounds", "1",
        "--env", "development",
        cwd=tmp_path,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    base = tmp_path / "out" / "company" / "technology" / "AAPL"
    assert base.is_dir(), f"missing dir; tree: {list((tmp_path / 'out').rglob('*'))}"
    md_files = sorted(base.glob("*_mock_debate.md"))
    assert len(md_files) == 1
    assert "Round 0" in md_files[0].read_text(encoding="utf-8")
    meta_files = sorted(base.glob("*_mock_meta.json"))
    assert len(meta_files) == 1
    meta = json.loads(meta_files[0].read_text(encoding="utf-8"))
    for k in ("run_id", "analysts", "provider", "target", "target_date",
              "domain", "rounds", "formats"):
        assert k in meta, f"missing key {k} in meta.json"
    assert meta["sector"] == "Technology"
    assert meta["domain"] == "company"
    assert meta["target"] == "AAPL"


def test_e2e_macro_debate_writes_to_new_structure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = _run_cli(
        "--indicators", "US.FFR",
        "--analysts", "dalio",
        "--provider", "mock",
        "--format", "debate",
        "--no-synthesis",
        "--rounds", "1",
        "--env", "development",
        cwd=tmp_path,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    matches = list((tmp_path / "out" / "macro").rglob("*_mock_debate.md"))
    assert len(matches) == 1, f"files: {matches}"
    assert "us-ffr" in str(matches[0])
    meta = json.loads(matches[0].parent.glob("*_mock_meta.json").__next__().read_text(encoding="utf-8"))
    assert meta["indicator"] == "US.FFR"
    assert meta["domain"] == "macro"


def test_e2e_multi_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = _run_cli(
        "--company", "JPM,BAC",
        "--analysts", "buffett",
        "--provider", "mock",
        "--format", "debate",
        "--no-synthesis",
        "--rounds", "1",
        "--env", "development",
        cwd=tmp_path,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    base = tmp_path / "out" / "company" / "financial-services"
    jpm_dir = base / "JPM"
    bac_dir = base / "BAC"
    assert jpm_dir.is_dir(), f"missing JPM dir; tree: {sorted(base.rglob('*'))}"
    assert bac_dir.is_dir(), f"missing BAC dir; tree: {sorted(base.rglob('*'))}"
    assert list(jpm_dir.glob("*_mock_debate.md"))
    assert list(bac_dir.glob("*_mock_debate.md"))


def test_explicit_output_bypasses_new_structure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    out_file = tmp_path / "s11_explicit.md"
    result = _run_cli(
        "--company", "AAPL",
        "--analysts", "buffett",
        "--provider", "mock",
        "--format", "debate",
        "--no-synthesis",
        "--rounds", "1",
        "--output", str(out_file),
        "--env", "development",
        cwd=tmp_path,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    assert out_file.exists()
    assert (tmp_path / "out").exists() is False, \
        f"new structure should not be created; found: {list((tmp_path / 'out').rglob('*'))}"


def test_meta_json_complete_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = _run_cli(
        "--company", "AAPL",
        "--analysts", "buffett,taleb",
        "--provider", "mock",
        "--format", "debate",
        "--no-synthesis",
        "--rounds", "1",
        "--env", "development",
        cwd=tmp_path,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    base = tmp_path / "out" / "company" / "technology" / "AAPL"
    meta_files = sorted(base.glob("*_mock_meta.json"))
    assert meta_files, f"missing meta.json; tree: {sorted(base.rglob('*'))}"
    meta = json.loads(meta_files[0].read_text(encoding="utf-8"))
    required = {
        "run_id", "analysts", "provider", "target", "target_date",
        "domain", "rounds", "formats", "completed_at",
    }
    missing = required - meta.keys()
    assert not missing, f"missing keys: {missing}"
    assert "sector" in meta
    assert meta["sector"] == "Technology"
    assert set(meta["analysts"]) == {"buffett", "taleb"}


def test_old_outputs_untouched() -> None:
    """Snapshot the existing out/debate_* and out/run_* dirs before/after."""
    out_dir = REPO_ROOT / "out"
    if not out_dir.exists():
        pytest.skip("no out/ directory to snapshot")
    old_dirs: list[Path] = []
    for prefix in ("debate_", "run_"):
        old_dirs.extend(p for p in out_dir.iterdir() if p.is_dir() and p.name.startswith(prefix))
    assert old_dirs, "no legacy run/debate directories to snapshot"
    snapshots: dict[Path, tuple[int, str]] = {}
    for d in old_dirs:
        files = sorted(d.rglob("*"))
        sample = ""
        if files:
            sample_path = next((f for f in files if f.is_file()), None)
            if sample_path is not None:
                sample = sample_path.read_text(encoding="utf-8", errors="replace")[:200]
        snapshots[d] = (len([f for f in files if f.is_file()]), sample)
    for d, (count, sample) in snapshots.items():
        assert d.exists(), f"legacy dir disappeared: {d}"
        files = sorted(d.rglob("*"))
        new_count = len([f for f in files if f.is_file()])
        assert new_count == count, \
            f"file count changed in {d}: {count} -> {new_count}"
        sample_path = next((f for f in files if f.is_file()), None)
        if sample_path is not None:
            new_sample = sample_path.read_text(encoding="utf-8", errors="replace")[:200]
            assert new_sample == sample, f"sample changed in {d}"


def test_per_agent_writes_subdirectory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = _run_cli(
        "--company", "AAPL",
        "--analysts", "buffett,taleb",
        "--provider", "mock",
        "--format", "per-agent",
        "--no-synthesis",
        "--rounds", "1",
        "--env", "development",
        cwd=tmp_path,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    base = tmp_path / "out" / "company" / "technology" / "AAPL"
    pa_dir = base / "per_agent"
    assert pa_dir.is_dir(), f"missing per_agent dir; tree: {sorted(base.rglob('*'))}"
    persona_files = sorted(pa_dir.glob("*.md"))
    assert persona_files, f"no per-persona files in {pa_dir}"
    assert any("buffett" in p.name for p in persona_files)
    assert any("taleb" in p.name for p in persona_files)
    md_files = list(base.glob("*_mock_debate.md"))
    assert md_files


def test_provider_slug_in_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = _run_cli(
        "--indicators", "US.FFR",
        "--analysts", "dalio",
        "--provider", "mock",
        "--format", "json",
        "--no-synthesis",
        "--rounds", "1",
        "--env", "development",
        cwd=tmp_path,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    matches = list((tmp_path / "out" / "macro").rglob("*_mock_data.json"))
    assert matches, f"no data.json written; tree: {sorted((tmp_path / 'out').rglob('*'))}"
