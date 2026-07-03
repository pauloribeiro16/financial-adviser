from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.prompts import registry as reg
from app.prompts.registry import (
    _DEFAULT_TASK_TEMPLATES,
    clear_cache,
    get_system_prompt,
    get_task_template,
)
from app.prompts.sync import _PERSONA_IDS, _TASK_NAMES, build_parser

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _reset_cache() -> Any:
    clear_cache()
    yield
    clear_cache()


@pytest.fixture
def no_langfuse_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)


def test_get_system_prompt_falls_back_to_disk_without_langfuse(no_langfuse_env) -> None:
    s = get_system_prompt("buffett")
    assert isinstance(s, str)
    assert len(s) > 1000, s
    assert "Buffett" in s
    assert "Moat" in s or "moat" in s.lower()


def test_get_system_prompt_works_for_every_persona(no_langfuse_env) -> None:
    for pid in _PERSONA_IDS:
        s = get_system_prompt(pid)
        assert len(s) > 200, f"{pid} system prompt too short: {len(s)}"


def test_get_task_template_thesis_compiles(no_langfuse_env) -> None:
    t = get_task_template(
        "thesis",
        target="AAPL",
        target_date="2026-07-02",
        context_md="ctx",
        hint="h",
    )
    assert "AAPL" in t
    assert "ctx" in t
    assert "2026-07-02" in t
    assert "h" in t
    assert "thesis" in t.lower()


def test_get_task_template_rebuttal_compiles(no_langfuse_env) -> None:
    t = get_task_template(
        "rebuttal",
        target="US.FFR",
        target_date="2026-07-02",
        context_md="ctx",
        prior_theses_block="buffett says BULLISH",
        round=1,
        hint="h",
    )
    assert "US.FFR" in t
    assert "buffett says BULLISH" in t
    assert "round 1" in t


def test_get_task_template_verdict_compiles(no_langfuse_env) -> None:
    t = get_task_template(
        "verdict",
        target="AAPL",
        domain="company",
        target_date="2026-07-02",
        context_md="ctx",
        theses_block="t1\nt2",
        rebuttals_block="r1",
        tally_block="bull=1",
    )
    assert "AAPL" in t
    assert "company" in t
    assert "t1" in t and "r1" in t
    assert "bull=1" in t


def test_get_task_template_unknown_task_returns_empty(no_langfuse_env) -> None:
    t = get_task_template("nonexistent", foo="bar")
    assert t == ""


def test_get_task_template_missing_var_left_as_empty(no_langfuse_env) -> None:
    t = get_task_template("thesis", target="AAPL")
    assert "AAPL" in t
    assert "{{target_date}}" not in t


def test_clear_cache_resets_internal_state(no_langfuse_env) -> None:
    get_system_prompt("buffett")
    assert reg._CACHE
    clear_cache()
    assert reg._CACHE == {}


def test_cache_avoids_re_fetch(no_langfuse_env) -> None:
    client_mock = MagicMock()
    reg._CACHE["persona-buffett-system"] = "from-cache"
    reg._CACHE["task:thesis"] = "task-from-cache"
    assert get_system_prompt("buffett") == "from-cache"
    client_mock.get_prompt.assert_not_called()


def test_langfuse_path_compiles_and_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    prompt_obj = MagicMock()
    prompt_obj.prompt = "compiled-text"
    client = MagicMock()
    client.get_prompt = MagicMock(return_value=prompt_obj)
    reg._client = client
    try:
        result = get_system_prompt("buffett")
        assert result == "compiled-text"
        client.get_prompt.assert_called_once_with(
            "persona-buffett-system", label="latest"
        )
        assert reg._CACHE["persona-buffett-system"] == "compiled-text"
        get_system_prompt("buffett")
        client.get_prompt.assert_called_once()
    finally:
        reg._client = None
        reg._CACHE.pop("persona-buffett-system", None)


def test_langfuse_failure_falls_back_to_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    client = MagicMock()
    client.get_prompt = MagicMock(side_effect=RuntimeError("boom"))
    reg._client = client
    try:
        s = get_system_prompt("buffett")
        assert "Buffett" in s
        assert len(s) > 1000
    finally:
        reg._client = None
        reg._CACHE.pop("persona-buffett-system", None)


def test_langfuse_failure_on_task_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    client = MagicMock()
    client.get_prompt = MagicMock(side_effect=RuntimeError("boom"))
    reg._client = client
    try:
        t = get_task_template(
            "thesis", target="AAPL", context_md="x", hint="h", target_date="d"
        )
        assert "AAPL" in t
    finally:
        reg._client = None
        reg._CACHE.pop("task-thesis", None)


def test_sync_push_without_env_exits_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    parser = build_parser()
    args = parser.parse_args(["push"])
    with pytest.raises(SystemExit) as exc_info:
        args.func(args)
    assert exc_info.value.code == 2


def test_sync_push_with_persona_only_pushes_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    client = MagicMock()
    client.create_prompt = MagicMock(return_value=MagicMock())
    client.get_prompt = MagicMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr("app.prompts.registry._langfuse_client", lambda: client)
    parser = build_parser()
    args = parser.parse_args(["push", "--persona", "buffett"])
    rc = args.func(args)
    assert rc == 0
    names = [c.kwargs["name"] for c in client.create_prompt.call_args_list]
    assert "persona-buffett-system" in names
    for pid in _PERSONA_IDS:
        if pid != "buffett":
            assert f"persona-{pid}-system" not in names


def test_sync_push_full_pushes_all_15_personas_plus_3_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    client = MagicMock()
    client.create_prompt = MagicMock(return_value=MagicMock())
    monkeypatch.setattr("app.prompts.registry._langfuse_client", lambda: client)
    parser = build_parser()
    args = parser.parse_args(["push"])
    rc = args.func(args)
    assert rc == 0
    expected = len(_PERSONA_IDS) + len(_TASK_NAMES)
    assert client.create_prompt.call_count == expected
    names = [c.kwargs["name"] for c in client.create_prompt.call_args_list]
    for pid in _PERSONA_IDS:
        assert f"persona-{pid}-system" in names
    for tn in _TASK_NAMES:
        assert f"task-{tn}" in names


def test_sync_push_task_labels_match_task_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    client = MagicMock()
    client.create_prompt = MagicMock(return_value=MagicMock())
    monkeypatch.setattr("app.prompts.registry._langfuse_client", lambda: client)
    parser = build_parser()
    args = parser.parse_args(["push"])
    args.func(args)
    for call in client.create_prompt.call_args_list:
        name = call.kwargs["name"]
        if name.startswith("task-"):
            task_name = name.removeprefix("task-")
            assert call.kwargs["labels"] == ["task", task_name]


def test_sync_push_persona_labels_match_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    client = MagicMock()
    client.create_prompt = MagicMock(return_value=MagicMock())
    monkeypatch.setattr("app.prompts.registry._langfuse_client", lambda: client)
    parser = build_parser()
    args = parser.parse_args(["push"])
    args.func(args)
    persona_calls = [
        c for c in client.create_prompt.call_args_list
        if c.kwargs["name"].startswith("persona-")
    ]
    assert len(persona_calls) == len(_PERSONA_IDS)
    for call in persona_calls:
        assert call.kwargs["labels"] == ["persona", "system"]


def test_default_task_templates_have_expected_placeholders() -> None:
    assert "{{target}}" in _DEFAULT_TASK_TEMPLATES["thesis"]
    assert "{{context_md}}" in _DEFAULT_TASK_TEMPLATES["thesis"]
    assert "{{target_date}}" in _DEFAULT_TASK_TEMPLATES["thesis"]
    assert "{{hint}}" in _DEFAULT_TASK_TEMPLATES["thesis"]
    assert "{{prior_theses_block}}" in _DEFAULT_TASK_TEMPLATES["rebuttal"]
    assert "{{round}}" in _DEFAULT_TASK_TEMPLATES["rebuttal"]
    assert "{{theses_block}}" in _DEFAULT_TASK_TEMPLATES["verdict"]
    assert "{{rebuttals_block}}" in _DEFAULT_TASK_TEMPLATES["verdict"]
    assert "{{tally_block}}" in _DEFAULT_TASK_TEMPLATES["verdict"]


def test_engine_build_thesis_uses_registry(no_langfuse_env) -> None:
    from datetime import date

    from app.debate.engine import build_thesis_messages

    msgs = build_thesis_messages(
        persona_id="buffett",
        target="AAPL",
        domain="company",
        target_date=date(2026, 7, 2),
        context_md="P/E 22, FCF $80B.",
    )
    assert msgs[0]["role"] == "system"
    assert "Buffett" in msgs[0]["content"]
    assert "AAPL" in msgs[0]["content"]


def test_sync_cli_exits_nonzero_without_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    result = subprocess.run(
        [sys.executable, "-m", "app.prompts.sync", "push"],
        capture_output=True,
        text=True,
        env={k: v for k, v in os.environ.items()
             if k not in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST")},
    )
    assert result.returncode == 2
    assert "Langfuse credentials missing" in result.stderr
