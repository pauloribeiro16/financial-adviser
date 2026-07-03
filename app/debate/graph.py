from __future__ import annotations

import operator
from datetime import date
from typing import Annotated, Any, Optional, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Send

from app.debate import engine
from app.logging import get_logger
from app.models import Domain, Rebuttal, Thesis, Verdict
from app.providers import ProviderRegistry

log = get_logger(__name__)


class DebateState(TypedDict, total=False):
    analysts: list[str]
    target: str
    domain: str
    target_date: date
    context_md: str
    context_raw: dict[str, Any]
    sector: str | None
    theses: Annotated[list[Thesis], operator.add]
    rebuttals: Annotated[list[Rebuttal], operator.add]
    verdict: Verdict | None
    round: int
    rounds: int
    provider_name: str
    include_synthesis: bool
    run_id: str
    _analyst: str
    _round_idx: int


def _extract_callbacks(config: Optional[RunnableConfig]) -> list[Any]:  # noqa: UP045
    if not config:
        return []
    mgr = config.get("callbacks") if isinstance(config, dict) else None
    if mgr is None:
        return []
    handlers = getattr(mgr, "handlers", None)
    if handlers:
        return list(handlers)
    if isinstance(mgr, (list, tuple)):
        return list(mgr)
    return []


def _first_callback(config: Optional[RunnableConfig]) -> Any | None:  # noqa: UP045
    cbs = _extract_callbacks(config)
    return cbs[0] if cbs else None


def _domain_enum(domain: str) -> Domain:
    return Domain(domain)


def _provider_for(state: DebateState) -> Any:
    name = state.get("provider_name") or "mock"
    return ProviderRegistry.get(name)


def _invoke_llm(
    provider: Any,
    schema: type[Any],
    messages: list[dict[str, str]],
    callbacks: list[Any],
) -> Any:
    """Delegate LLM invocation to ``engine._invoke_with_fallback`` (the master's
    3-level safety net) while propagating LangGraph callbacks.
    """
    callback = callbacks[0] if callbacks else None
    return engine._invoke_with_fallback(
        provider, schema, messages, callback=callback,
    )


def _prior_for_rebuttal(state: DebateState) -> list[Thesis]:
    rebuttals = list(state.get("rebuttals") or [])
    theses = list(state.get("theses") or [])
    cur_round = int(state.get("round") or 0)
    if cur_round <= 0:
        return theses
    last = [r for r in rebuttals if int(r.round) == cur_round]
    return [
        Thesis(
            agent_id=r.agent_id,
            target=r.target,
            domain=r.domain,
            round=r.round,
            verdict=r.revised_verdict,
            conviction=r.revised_conviction,
            key_drivers=[],
            reasoning=r.reasoning,
            data_used=[],
        )
        for r in last
    ]


def ingest_node(state: DebateState) -> dict:
    log.info(
        "debate.graph.ingest",
        target=state.get("target"),
        domain=state.get("domain"),
        analysts=state.get("analysts"),
    )
    return {}


def theses_dispatch_node(state: DebateState) -> dict:
    return {}


def theses_router(state: DebateState) -> list[Send]:
    return [
        Send("thesis_one", {**state, "_analyst": a})
        for a in (state.get("analysts") or [])
    ]


def thesis_one_node(state: DebateState, config: Optional[RunnableConfig] = None) -> dict:  # noqa: UP045
    persona_id = state["_analyst"]
    target = state["target"]
    domain = state["domain"]
    target_date = state["target_date"]
    context_md = state["context_md"]
    sector = state.get("sector")
    provider = _provider_for(state)
    callbacks = _extract_callbacks(config)
    msgs = engine.build_thesis_messages(
        persona_id, target, domain, target_date, context_md, sector=sector,
    )
    out = _invoke_llm(provider, Thesis, msgs, callbacks)
    if isinstance(out, Thesis):
        out.agent_id = persona_id
        out.target = target
        out.domain = _domain_enum(domain)
        out.round = 0
        log.info("debate.graph.thesis_done", agent=persona_id, round=0)
        return {"theses": [out]}
    log.warning(
        "debate.graph.thesis_dropped",
        agent=persona_id,
        type=type(out).__name__ if out is not None else "None",
    )
    return {"theses": []}


def rebuttals_dispatch_node(state: DebateState) -> dict:
    return {}


def rebuttals_router(state: DebateState) -> list[Send] | str:
    rounds = int(state.get("rounds") or 1)
    cur_round = int(state.get("round") or 0)
    if rounds <= 1 or cur_round >= rounds - 1:
        return "synthesis"
    round_idx = cur_round + 1
    return [
        Send(
            "rebuttal_one",
            {**state, "_analyst": a, "_round_idx": round_idx},
        )
        for a in (state.get("analysts") or [])
    ]


def rebuttal_one_node(state: DebateState, config: Optional[RunnableConfig] = None) -> dict:  # noqa: UP045
    persona_id = state["_analyst"]
    target = state["target"]
    domain = state["domain"]
    target_date = state["target_date"]
    context_md = state["context_md"]
    sector = state.get("sector")
    round_idx = int(state["_round_idx"])
    provider = _provider_for(state)
    callbacks = _extract_callbacks(config)
    prior_theses = _prior_for_rebuttal(state)
    msgs = engine.build_rebuttal_messages(
        persona_id, target, domain, target_date, context_md, prior_theses, sector=sector,
    )
    out = _invoke_llm(provider, Rebuttal, msgs, callbacks)
    if isinstance(out, Rebuttal):
        out.agent_id = persona_id
        out.target = target
        out.domain = _domain_enum(domain)
        out.round = round_idx
        log.info(
            "debate.graph.rebuttal_done", agent=persona_id, round=round_idx,
        )
        return {"rebuttals": [out]}
    log.warning(
        "debate.graph.rebuttal_dropped",
        agent=persona_id,
        round=round_idx,
        type=type(out).__name__ if out is not None else "None",
    )
    return {"rebuttals": []}


def advance_round_node(state: DebateState) -> dict:
    return {"round": int(state.get("round") or 0) + 1}


def synthesis_node(state: DebateState, config: Optional[RunnableConfig] = None) -> dict:  # noqa: UP045
    if not bool(state.get("include_synthesis", True)):
        return {}
    provider = _provider_for(state)
    callback = _first_callback(config)
    theses = list(state.get("theses") or [])
    rebuttals = list(state.get("rebuttals") or [])
    try:
        verdict = engine._run_synthesis(
            target=state["target"],
            domain=state["domain"],
            target_date=state["target_date"],
            context_md=state["context_md"],
            theses=theses,
            rebuttals=rebuttals,
            provider=provider,
            callback=callback,
        )
    except Exception as e:
        log.error("debate.graph.synthesis_failed", error=str(e))
        return {}
    log.info("debate.graph.synthesis_done", consensus=verdict.consensus.value)
    return {"verdict": verdict}


def build_debate_graph() -> Any:
    g = StateGraph(DebateState)
    g.add_node("ingest", ingest_node)
    g.add_node("theses", theses_dispatch_node)
    g.add_node("thesis_one", thesis_one_node)
    g.add_node("rebuttals", rebuttals_dispatch_node)
    g.add_node("rebuttal_one", rebuttal_one_node)
    g.add_node("advance_round", advance_round_node)
    g.add_node("synthesis", synthesis_node)
    g.set_entry_point("ingest")
    g.add_edge("ingest", "theses")
    g.add_conditional_edges("theses", theses_router)
    g.add_edge("thesis_one", "rebuttals")
    g.add_conditional_edges("rebuttals", rebuttals_router)
    g.add_edge("rebuttal_one", "advance_round")
    g.add_edge("advance_round", "rebuttals")
    g.add_edge("synthesis", END)
    return g.compile(checkpointer=MemorySaver())


def run_debate_graph(
    initial_state: dict[str, Any],
    thread_id: str | None = None,
    callbacks: list[Any] | None = None,
) -> dict[str, Any]:
    graph = build_debate_graph()
    cfg: dict[str, Any] = {
        "configurable": {"thread_id": thread_id or "debate-default"},
    }
    if callbacks:
        cfg["callbacks"] = list(callbacks)
    return graph.invoke(initial_state, config=cfg)


__all__ = [
    "DebateState",
    "build_debate_graph",
    "run_debate_graph",
    "ingest_node",
    "theses_dispatch_node",
    "theses_router",
    "thesis_one_node",
    "rebuttals_dispatch_node",
    "rebuttals_router",
    "rebuttal_one_node",
    "advance_round_node",
    "synthesis_node",
]
