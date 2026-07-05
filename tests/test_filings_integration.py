"""Integration tests for S16: --with-filings flag flows through context pipeline."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from app.filings.summarizer import get_or_build_summary
from app.models import FilingSummary
from app.pipeline.context import build_company_context, render_context_markdown


def test_main_help_includes_with_filings() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "app.main", "--help"],
        capture_output=True, text=True, timeout=15,
    )
    assert "with-filings" in result.stdout


def test_render_company_includes_filing_section() -> None:
    ctx = {
        "ticker": "XOM",
        "edgar": {},
        "quote": {},
        "fundamentals": {},
        "filing_summary": FilingSummary(
            ticker="XOM",
            filing_date="2025-12-31",
            form="10-K",
            business_and_market_risk="Cost advantage in Permian",
            risk_factors="Oil price volatility",
            md_and_a="Capital return phase",
        ),
    }
    md = render_context_markdown(ctx, kind="company")
    assert "10-K Narrative Summary" in md
    assert "Cost advantage in Permian" in md


def test_render_company_omits_filing_section_when_absent() -> None:
    ctx = {"ticker": "XOM", "edgar": {}, "quote": {}, "fundamentals": {}}
    md = render_context_markdown(ctx, kind="company")
    assert "10-K Narrative Summary" not in md


def test_build_company_context_default_no_filings(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail(*_args, **_kwargs):
        raise AssertionError("get_or_build_summary must not be called when with_filings=False")

    monkeypatch.setattr(
        "app.filings.summarizer.get_or_build_summary", _fail, raising=False,
    )
    import app.pipeline.context as ctx_mod
    monkeypatch.setattr(ctx_mod, "get_or_build_summary", None, raising=False)
    ctx = build_company_context("XOM")
    assert "filing_summary" not in ctx


def test_get_or_build_summary_uses_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cache_dir = tmp_path / "XOM"
    cache_dir.mkdir(parents=True)
    summary = FilingSummary(
        ticker="XOM",
        filing_date="2025-12-31",
        form="10-K",
        business_and_market_risk="Permian cost advantage",
        risk_factors="Oil price volatility",
        md_and_a="Revenue down due to refining margins",
    )
    (cache_dir / "2025-12-31_10k_summary.json").write_text(summary.model_dump_json())
    monkeypatch.setattr("app.filings.cache.CACHE_ROOT", tmp_path)
    result = get_or_build_summary("XOM", provider_name="mock")
    assert result is not None
    assert result.ticker == "XOM"
    assert result.form == "10-K"
