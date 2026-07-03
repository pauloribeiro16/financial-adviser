from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.debate.orchestrator import orchestrate_debate
from app.debate.tracing import DebateTrace
from app.main import _auto_session_id
from app.providers import ProviderRegistry
from tests._mock_provider import SchemaAwareMockProvider

_AUTO_SID_RE = re.compile(r"^debate-[a-z]+-[A-Za-z0-9._]+-\d{8}_\d{6}$")


REPO_ROOT = Path("/home/epmq-cyber/Área de Trabalho/projects/financial-adviser")


@pytest.fixture
def schema_aware_mock() -> Any:
    ProviderRegistry.register("mock", SchemaAwareMockProvider())
    yield
    ProviderRegistry._providers.pop("mock", None)


@pytest.fixture
def company_ctx() -> dict[str, Any]:
    return {
        "ticker": "AAPL",
        "edgar": {"submissions": {}, "latest_10k": None, "facts": {}},
        "quote": {},
        "fundamentals": {},
    }


def test_auto_session_id_matches_format_pattern() -> None:
    sid = _auto_session_id("company", "AAPL")
    assert _AUTO_SID_RE.match(sid), f"unexpected format: {sid!r}"
    assert sid.startswith("debate-company-AAPL-")


def test_auto_session_id_macro_target() -> None:
    sid = _auto_session_id("macro", "US.FFR")
    assert _AUTO_SID_RE.match(sid), f"unexpected format: {sid!r}"
    assert sid.startswith("debate-macro-US.FFR-")


def test_auto_session_id_two_calls_differ() -> None:
    sid_a = _auto_session_id("company", "AAPL")
    time.sleep(1.05)
    sid_b = _auto_session_id("company", "AAPL")
    assert sid_a != sid_b, "calls 1.05s apart should differ"


def _spy_on_trace_attributes(monkeypatch: pytest.MonkeyPatch, captured: list[dict[str, Any]]) -> None:
    original_attributes = DebateTrace.attributes

    def spy_attributes(self: Any, **kwargs: Any) -> Any:
        captured.append(dict(kwargs))
        return original_attributes(self, **kwargs)

    monkeypatch.setattr(DebateTrace, "attributes", spy_attributes)


def test_explicit_session_id_preserved_in_orchestrator(
    schema_aware_mock: Any,
    company_ctx: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict[str, Any]] = []
    _spy_on_trace_attributes(monkeypatch, captured)

    result = orchestrate_debate(
        analysts=["buffett"],
        target="AAPL",
        domain="company",
        target_date=date(2025, 3, 31),
        rounds=1,
        provider_name="mock",
        include_synthesis=True,
        session_id="explicit-s12-p3",
        ctx=company_ctx,
    )

    assert result is not None
    assert captured, "trace.attributes was never called"
    matching = [
        c for c in captured
        if c.get("session_id") == "explicit-s12-p3"
        and any(t == "domain:company" for t in (c.get("tags") or []))
    ]
    assert matching, (
        f"explicit session_id not propagated to trace.attributes; calls={captured!r}"
    )


def test_orchestrator_auto_generates_session_id_when_none(
    schema_aware_mock: Any,
    company_ctx: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict[str, Any]] = []
    _spy_on_trace_attributes(monkeypatch, captured)

    result = orchestrate_debate(
        analysts=["buffett"],
        target="AAPL",
        domain="company",
        target_date=date(2025, 3, 31),
        rounds=1,
        provider_name="mock",
        include_synthesis=True,
        session_id=None,
        ctx=company_ctx,
    )

    assert result is not None
    assert captured, "trace.attributes was never called"
    auto_sids = [
        c.get("session_id") for c in captured
        if isinstance(c.get("session_id"), str)
        and c.get("session_id").startswith("debate-company-AAPL-")
    ]
    assert auto_sids, (
        f"no auto session_id reached trace.attributes; calls={captured!r}"
    )
    for sid in auto_sids:
        assert re.match(
            r"^debate-company-AAPL-\d{8}_\d{6}$", sid
        ), f"unexpected auto session_id shape: {sid!r}"


def _run_cli(*args: str, env_override: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in {"LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"}}
    env["FA_SKIP_DOTENV"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    if env_override:
        env.update(env_override)
    return subprocess.run(
        [sys.executable, "-m", "app.main", *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
    )


def test_cli_auto_session_id_printed_to_stderr(tmp_path: Path) -> None:
    output = tmp_path / "auto_id.json"
    result = _run_cli(
        "--company", "AAPL",
        "--analysts", "buffett",
        "--provider", "mock",
        "--rounds", "1",
        "--output", str(output),
        "--env", "development",
    )
    assert result.returncode == 0, (
        f"exit {result.returncode}; stderr={result.stderr!r}; "
        f"stdout={result.stdout!r}"
    )
    matching = [
        line for line in result.stderr.splitlines()
        if line.startswith("session_id: debate-company-AAPL-")
    ]
    assert matching, f"no auto session_id line printed. stderr={result.stderr!r}"
    assert re.match(
        r"^session_id: debate-company-AAPL-\d{8}_\d{6}$", matching[0]
    ), f"unexpected line: {matching[0]!r}"


def test_cli_explicit_session_id_preserved_no_auto_line(tmp_path: Path) -> None:
    output = tmp_path / "explicit.json"
    result = _run_cli(
        "--company", "AAPL",
        "--analysts", "buffett",
        "--provider", "mock",
        "--rounds", "1",
        "--session-id", "user-supplied-session-xyz",
        "--output", str(output),
        "--env", "development",
    )
    assert result.returncode == 0, (
        f"exit {result.returncode}; stderr={result.stderr!r}; "
        f"stdout={result.stdout!r}"
    )
    auto_lines = [
        line for line in result.stderr.splitlines()
        if line.startswith("session_id: debate-")
    ]
    assert not auto_lines, (
        f"auto session_id line printed even though --session-id was explicit. "
        f"stderr={result.stderr!r}"
    )
    assert output.exists()
