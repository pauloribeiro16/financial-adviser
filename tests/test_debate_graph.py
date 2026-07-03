from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from langchain_core.callbacks.base import BaseCallbackHandler
from langgraph.checkpoint.memory import MemorySaver

from app.debate.graph import (
    DebateState,
    advance_round_node,
    build_debate_graph,
    ingest_node,
    rebuttals_dispatch_node,
    rebuttals_router,
    run_debate_graph,
    synthesis_node,
    theses_dispatch_node,
    theses_router,
    thesis_one_node,
)
from app.models import Rebuttal, Thesis, Verdict
from app.providers import ProviderRegistry
from tests._mock_provider import SchemaAwareMockProvider

GRAPH_NODE_NAMES = (
    "ingest",
    "theses",
    "thesis_one",
    "rebuttals",
    "rebuttal_one",
    "advance_round",
    "synthesis",
)


class _RecordingCallbackHandler(BaseCallbackHandler):
    """Minimal callback handler that records every dispatch it receives.

    Inherits from ``BaseCallbackHandler`` so the LangChain callback manager
    recognises it as a real handler (sets ``raise_error`` / ``ignore_chain``
    / etc. defaults), and overrides the ``on_*`` methods to record events.
    """

    def __init__(self) -> None:
        super().__init__()
        self.events: list[tuple[str, str]] = []

    def on_chain_start(self, serialized: dict[str, Any], inputs: dict[str, Any], **kw: Any) -> None:
        name = (serialized or {}).get("name") or (serialized or {}).get("id") or "<chain>"
        self.events.append(("chain_start", str(name)))

    def on_chain_end(self, outputs: dict[str, Any], **kw: Any) -> None:
        self.events.append(("chain_end", ""))

    def on_chain_error(self, error: BaseException, **kw: Any) -> None:
        self.events.append(("chain_error", str(error)))

    def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], **kw: Any) -> None:
        self.events.append(("llm_start", ""))

    def on_llm_end(self, response: Any, **kw: Any) -> None:
        self.events.append(("llm_end", ""))

    def on_llm_error(self, error: BaseException, **kw: Any) -> None:
        self.events.append(("llm_error", str(error)))

    def on_tool_start(self, serialized: dict[str, Any], input_str: str, **kw: Any) -> None:
        self.events.append(("tool_start", ""))

    def on_tool_end(self, output: Any, **kw: Any) -> None:
        self.events.append(("tool_end", ""))

    def on_tool_error(self, error: BaseException, **kw: Any) -> None:
        self.events.append(("tool_error", str(error)))


def _initial_state(
    *,
    analysts: list[str],
    rounds: int = 1,
    target: str = "US.FFR",
    sector: str | None = None,
    run_id: str = "test-run",
) -> dict[str, Any]:
    return {
        "analysts": list(analysts),
        "target": target,
        "domain": "macro",
        "target_date": date(2026, 7, 2),
        "context_md": "# Context\nFed funds rate is 5.25%.",
        "context_raw": {},
        "sector": sector,
        "theses": [],
        "rebuttals": [],
        "verdict": None,
        "round": 0,
        "rounds": rounds,
        "provider_name": "mock",
        "include_synthesis": True,
        "run_id": run_id,
    }


@pytest.fixture
def mock_provider() -> Any:
    ProviderRegistry.register("mock", SchemaAwareMockProvider())
    yield
    ProviderRegistry._providers.pop("mock", None)


def test_build_debate_graph_returns_compiled_graph_with_memory_saver() -> None:
    g = build_debate_graph()
    assert g is not None
    checkpointer = g.checkpointer
    assert isinstance(checkpointer, MemorySaver)


def test_build_debate_graph_has_all_seven_nodes() -> None:
    g = build_debate_graph()
    node_names = set(g.nodes.keys())
    for name in GRAPH_NODE_NAMES:
        assert name in node_names, f"missing node: {name}"


def test_invoke_rounds_1_produces_verdict_with_empty_rebuttals(mock_provider: Any) -> None:
    g = build_debate_graph()
    state = _initial_state(analysts=["buffett"], rounds=1)
    result = g.invoke(state, config={"configurable": {"thread_id": "t-r1"}})
    assert len(result["theses"]) == 1
    assert result["rebuttals"] == []
    assert result["verdict"] is not None
    assert isinstance(result["verdict"], Verdict)
    assert result["round"] == 0


def test_invoke_rounds_2_produces_theses_and_rebuttals(mock_provider: Any) -> None:
    g = build_debate_graph()
    state = _initial_state(analysts=["buffett", "taleb"], rounds=2, run_id="r2")
    result = g.invoke(state, config={"configurable": {"thread_id": "t-r2"}})
    assert len(result["theses"]) == 2
    assert len(result["rebuttals"]) == 2
    assert {t.agent_id for t in result["theses"]} == {"buffett", "taleb"}
    assert all(isinstance(r, Rebuttal) for r in result["rebuttals"])
    assert all(r.round == 1 for r in result["rebuttals"])
    assert result["verdict"] is not None


def test_theses_router_fans_out_one_send_per_analyst() -> None:
    from langgraph.types import Send

    state = _initial_state(analysts=["buffett", "taleb", "lynch"])
    sends = theses_router(state)
    assert len(sends) == 3
    assert all(isinstance(s, Send) for s in sends)
    assert {s.arg["_analyst"] for s in sends} == {"buffett", "taleb", "lynch"}
    assert all(s.node == "thesis_one" for s in sends)


def test_rebuttals_router_returns_synthesis_when_done() -> None:
    state = _initial_state(analysts=["buffett"], rounds=1)
    assert rebuttals_router(state) == "synthesis"


def test_rebuttals_router_returns_synthesis_when_max_rounds_reached() -> None:
    state = _initial_state(analysts=["buffett"], rounds=2)
    state["round"] = 1
    assert rebuttals_router(state) == "synthesis"


def test_rebuttals_router_returns_send_list_when_more_rounds_remain() -> None:
    from langgraph.types import Send

    state = _initial_state(analysts=["buffett", "taleb"], rounds=2)
    state["round"] = 0
    sends = rebuttals_router(state)
    assert isinstance(sends, list)
    assert len(sends) == 2
    assert all(isinstance(s, Send) for s in sends)
    assert all(s.node == "rebuttal_one" for s in sends)
    assert all(s.arg["_round_idx"] == 1 for s in sends)


def test_run_debate_graph_helper_returns_final_state(mock_provider: Any) -> None:
    state = _initial_state(analysts=["buffett"], rounds=1)
    result = run_debate_graph(state, thread_id="helper-test")
    assert "theses" in result
    assert "rebuttals" in result
    assert "verdict" in result
    assert len(result["theses"]) == 1
    assert result["rebuttals"] == []


def test_thesis_one_node_stamps_metadata(mock_provider: Any) -> None:
    state = _initial_state(analysts=["buffett"], rounds=1)
    state["_analyst"] = "buffett"
    out = thesis_one_node(state)
    assert "theses" in out
    assert len(out["theses"]) == 1
    thesis = out["theses"][0]
    assert isinstance(thesis, Thesis)
    assert thesis.agent_id == "buffett"
    assert thesis.target == "US.FFR"
    assert thesis.domain.value == "macro"
    assert thesis.round == 0


def test_synthesis_node_returns_verdict(mock_provider: Any) -> None:
    state = _initial_state(analysts=["buffett"], rounds=1)
    out = synthesis_node(state)
    assert "verdict" in out
    assert isinstance(out["verdict"], Verdict)


def test_advance_round_node_increments_round() -> None:
    state = _initial_state(analysts=["buffett"], rounds=2)
    state["round"] = 0
    out = advance_round_node(state)
    assert out["round"] == 1
    state["round"] = 1
    out = advance_round_node(state)
    assert out["round"] == 2


def test_ingest_node_returns_empty_dict() -> None:
    state = _initial_state(analysts=["buffett"], rounds=1)
    out = ingest_node(state)
    assert out == {}


def test_theses_and_rebuttals_dispatch_nodes_return_empty_dict() -> None:
    state = _initial_state(analysts=["buffett", "taleb"], rounds=2)
    assert theses_dispatch_node(state) == {}
    assert rebuttals_dispatch_node(state) == {}


def test_synthesis_node_skipped_when_include_synthesis_false(mock_provider: Any) -> None:
    state = _initial_state(analysts=["buffett"], rounds=1)
    state["include_synthesis"] = False
    out = synthesis_node(state)
    assert out == {}


def test_callbacks_propagate_through_graph_nodes(mock_provider: Any) -> None:
    handler = _RecordingCallbackHandler()
    state = _initial_state(analysts=["buffett"], rounds=1)
    run_debate_graph(
        state,
        thread_id="cb-test",
        callbacks=[handler],
    )
    assert len(handler.events) > 0, "callback handler should have received events"
    kinds = {e[0] for e in handler.events}
    assert "chain_start" in kinds or "tool_start" in kinds or "llm_start" in kinds
    assert "chain_end" in kinds or "tool_end" in kinds or "llm_end" in kinds


def test_sector_passed_through_to_engine_messages(mock_provider: Any) -> None:
    captured: list[list[dict[str, str]]] = []

    from app.debate import engine as engine_mod

    original = engine_mod.build_thesis_messages

    def spy(persona_id: str, target: str, domain: str, target_date: date, context_md: str, sector: str | None = None) -> list[dict[str, str]]:
        captured.append(original(persona_id, target, domain, target_date, context_md, sector=sector))
        return captured[-1]

    engine_mod.build_thesis_messages = spy  # type: ignore[assignment]
    try:
        state = _initial_state(analysts=["buffett"], rounds=1, sector="Technology")
        state["_analyst"] = "buffett"
        thesis_one_node(state)
    finally:
        engine_mod.build_thesis_messages = original  # type: ignore[assignment]

    assert captured, "build_thesis_messages should have been called"
    msgs = captured[0]
    sys_msg = msgs[0]["content"]
    assert "Technology" in sys_msg or "Sector" in sys_msg or "technology" in sys_msg.lower() or "Technology sector lens" in sys_msg or "Sector lens: Technology" in sys_msg


def test_state_schema_typed_dict_supports_sector() -> None:
    sample: DebateState = {
        "analysts": ["buffett"],
        "sector": "Technology",
        "theses": [],
        "rebuttals": [],
        "round": 0,
        "rounds": 1,
    }
    assert sample["sector"] == "Technology"
    assert "target" not in sample
