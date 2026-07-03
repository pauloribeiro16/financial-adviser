from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from app.debate.graph import (
    advance_round_node,
    build_debate_graph,
    ingest_node,
    rebuttals_dispatch_node,
    synthesis_node,
    theses_dispatch_node,
    thesis_one_node,
)
from app.providers import ProviderRegistry
from tests._mock_provider import SchemaAwareMockProvider

NODE_FUNCS = (
    ("ingest", ingest_node),
    ("theses", theses_dispatch_node),
    ("thesis_one", thesis_one_node),
    ("rebuttals", rebuttals_dispatch_node),
    ("advance_round", advance_round_node),
    ("synthesis", synthesis_node),
)


@pytest.fixture
def mock_provider() -> Any:
    ProviderRegistry.register("mock", SchemaAwareMockProvider())
    yield
    ProviderRegistry._providers.pop("mock", None)


@pytest.mark.parametrize(
    "name,fn",
    [(n, f) for n, f in NODE_FUNCS],
    ids=[n for n, _ in NODE_FUNCS],
)
def test_node_is_wrapped_by_observe(name: str, fn: Any) -> None:
    """Each graph node must be wrapped by ``@observe`` from langfuse.

    ``@observe`` (``langfuse>=4.x``) decorates the function with
    ``functools.wraps`` semantics, leaving ``__wrapped__`` set to the
    original underlying callable — the simplest reliable marker.
    """
    wrapped = getattr(fn, "__wrapped__", None)
    assert wrapped is not None, (
        f"node {name!r} is missing the @observe decorator "
        f"(expected __wrapped__ attribute)"
    )
    assert callable(wrapped), f"node {name!r} __wrapped__ is not callable"
    assert wrapped is not fn, f"node {name!r} __wrapped__ points to itself"


def test_compiled_graph_binds_all_observed_nodes(mock_provider: Any) -> None:
    """``build_debate_graph`` must successfully bind all decorated node
    functions and produce a runnable compiled graph."""
    from langgraph.checkpoint.memory import MemorySaver

    g = build_debate_graph()
    assert isinstance(g.checkpointer, MemorySaver)
    for name in ("ingest", "theses", "thesis_one", "rebuttals", "advance_round", "synthesis"):
        assert name in g.nodes, f"compiled graph missing node: {name}"

    state = {
        "analysts": ["buffett"],
        "target": "AAPL",
        "domain": "company",
        "target_date": date(2025, 3, 31),
        "context_md": "# ctx",
        "context_raw": {},
        "sector": None,
        "theses": [],
        "rebuttals": [],
        "verdict": None,
        "round": 0,
        "rounds": 1,
        "provider_name": "mock",
        "include_synthesis": True,
        "run_id": "decorator-bind-test",
    }
    result = g.invoke(state, config={"configurable": {"thread_id": "decorator-bind"}})
    assert "theses" in result and len(result["theses"]) == 1
    assert result["verdict"] is not None


def test_observe_decorator_callable_directly() -> None:
    """Sanity: each node function still works when called directly without
    the LangGraph runtime — the decorator must not break direct invocations."""
    from datetime import date

    state: dict[str, Any] = {
        "analysts": ["buffett"],
        "target": "US.FFR",
        "domain": "macro",
        "target_date": date(2026, 7, 2),
        "context_md": "# x",
        "theses": [],
        "rebuttals": [],
        "round": 0,
        "rounds": 1,
    }
    assert ingest_node(state) == {}
    assert theses_dispatch_node(state) == {}
    assert advance_round_node(state) == {"round": 1}
