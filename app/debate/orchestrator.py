"""High-level debate orchestrator: build context → run engine → record trace.

This module is the single entry point used by the CLI (``app/runner.py`` and
``app/main.py``). It glues together:

  1. ``app.pipeline.context`` — produces a data packet (company ticker or
     macro indicators) and renders it to Markdown for the LLM.
  2. ``app.debate.engine.run_debate`` — runs the actual structured debate.
  3. ``app.debate.tracing.DebateTrace`` — optional Langfuse v4 wiring
     (``@observe`` decorator + ``CallbackHandler`` passed to every invoke +
     ``propagate_attributes`` for ``session_id`` / ``tags`` / ``metadata``).
     Becomes a no-op when Langfuse env vars are absent.

Mock-provider shim
------------------

``app.providers.MockModel`` only knows the ``Assessment`` schema, so
``run_debate`` would crash on the Verdict thesis when invoked with
``--provider mock`` from the CLI. To keep the CLI smoke test working
without modifying ``app.providers``, we install a schema-aware mock
provider (covering ``Assessment``, ``Thesis``, ``Rebuttal``, ``Verdict``)
into ``ProviderRegistry`` whenever the caller asks for ``"mock"``.
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from typing import Any

from langfuse import observe

from app.debate import engine
from app.debate.tracing import DebateTrace
from app.logging import get_logger
from app.models import (
    Assessment,
    Consensus,
    DebateResult,
    Direction,
    Domain,
    Rebuttal,
    Thesis,
    Verdict,
)
from app.pipeline import context as pipeline_context
from app.providers import LLMProvider, MockProvider, ProviderRegistry

log = get_logger(__name__)


class _SchemaAwareMockModel:
    """Returns a valid Pydantic instance for whichever schema was requested.

    Covers all four schemas used by the runtime (Assessment, Thesis,
    Rebuttal, Verdict) so the same mock provider works for both the legacy
    assessment path and the new debate path.
    """

    def __init__(self, schema: Any = None) -> None:
        self._schema = schema

    def with_structured_output(self, schema: Any) -> _SchemaAwareMockModel:
        return _SchemaAwareMockModel(schema)

    def bind_tools(self, tools: Any) -> _SchemaAwareMockModel:
        return self

    def invoke(self, messages: list[dict[str, str]], config: Any = None) -> Any:
        s = self._schema
        if s is Assessment:
            user_content = messages[-1]["content"] if messages else ""
            preview = user_content[:60].replace("\n", " ")
            return SimpleNamespace(
                diagnosis=f"[MOCK diagnosis based on: {preview}...]",
                outlook="[MOCK] Outlook: NEUTRAL, awaiting data.",
                key_drivers=["mock driver 1", "mock driver 2", "mock driver 3"],
                news_interpretation="[MOCK] No material news in scope.",
                reasoning_trace="[MOCK] Reasoning trace: placeholder for testing.",
                signal_direction="NEUTRAL",
                signal_strength=0.5,
            )
        if s is Thesis:
            return Thesis(
                agent_id="mock",
                target="MOCK",
                domain=Domain.MACRO,
                round=0,
                verdict=Direction.NEUTRAL,
                conviction=0.5,
                key_drivers=["mock driver a", "mock driver b"],
                reasoning="[MOCK thesis] placeholder reasoning.",
                data_used=["mock data point"],
            )
        if s is Rebuttal:
            return Rebuttal(
                agent_id="mock",
                target="MOCK",
                domain=Domain.MACRO,
                round=1,
                targets=["other"],
                concessions=["mock concession"],
                disagreements=["mock disagreement"],
                revised_verdict=Direction.NEUTRAL,
                revised_conviction=0.5,
                reasoning="[MOCK rebuttal] placeholder reasoning.",
            )
        if s is Verdict:
            return Verdict(
                target="MOCK",
                domain=Domain.MACRO,
                consensus=Consensus.NEUTRAL,
                bull_count=0,
                bear_count=0,
                neutral_count=2,
                avg_conviction=0.5,
                points_of_agreement=["mock agreement"],
                points_of_disagreement=[],
                final_call="[MOCK] Neutral consensus",
                confidence=0.5,
                summary="[MOCK] Summary of debate.",
            )
        return SimpleNamespace(text="[MOCK] unknown schema")


class _SchemaAwareMockProvider(LLMProvider):
    def provider_name(self) -> str:
        return "mock"

    def get_model(self) -> _SchemaAwareMockModel:
        return _SchemaAwareMockModel()


def _ensure_mock_provider_is_schema_aware(provider_name: str) -> None:
    """If ``provider_name`` is ``"mock"``, replace the registry entry with a
    schema-aware mock so debate-engine Verdict calls don't crash.

    Idempotent: leaves the registry untouched if the current provider already
    handles Verdict, or if the caller asked for a real provider.
    """
    if provider_name != "mock":
        return
    try:
        existing = ProviderRegistry.get("mock")
    except Exception:
        existing = None
    if existing is not None and not isinstance(existing, MockProvider):
        return
    ProviderRegistry.register("mock", _SchemaAwareMockProvider())


def _build_context(domain: str, target: str, target_date: date) -> dict[str, Any]:
    if domain == "company":
        return pipeline_context.build_company_context(target)
    as_of = target_date.isoformat() if target_date else None
    return pipeline_context.build_macro_context([target], as_of)


def _should_use_graph(fmt: str | None, rounds: int) -> bool:
    """Decide if a debate call should go through the LangGraph graph.py.

    LangGraph path is used for debate mode (rounds > 1 or ``fmt == "debate"``).
    Legacy path keeps ``engine.run_debate()`` for ``fmt in {"md", "json", "per-agent"}``.
    """
    if fmt in ("md", "json", "per-agent"):
        return False
    if rounds and rounds > 1:
        return True
    if fmt == "debate":
        return True
    return False


def _state_to_debate_result(
    state: dict[str, Any],
    target: str,
    domain: str,
    target_date: date,
    provider_name: str,
    analysts: list[str],
    context_md: str,
    include_synthesis: bool,
) -> DebateResult:
    """Convert the final graph state dict into a ``DebateResult``.

    Mirrors the ``DebateResult`` constructor in ``engine.run_debate`` so
    downstream consumers (formatter, CLI writer, Langfuse scoring) see an
    identical shape regardless of whether the engine or the graph was used.
    """
    theses = list(state.get("theses") or [])
    rebuttals = list(state.get("rebuttals") or [])
    verdict = state.get("verdict") if include_synthesis else None
    return DebateResult(
        run_id=f"debate_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
        domain=Domain(domain),
        target=target,
        target_date=target_date,
        provider=provider_name,
        analysts=list(analysts),
        context={"rendered_markdown": context_md},
        theses=theses,
        rebuttals=rebuttals,
        verdict=verdict,
        created_at=datetime.now().isoformat(timespec="seconds"),
    )


@observe(name="debate.orchestrator", as_type="span")
def orchestrate_debate(
    *,
    analysts: list[str],
    target: str,
    domain: str,
    target_date: date,
    rounds: int,
    provider_name: str,
    include_synthesis: bool,
    session_id: str | None = None,
    ctx: dict[str, Any] | None = None,
    trace: DebateTrace | None = None,
    output_format: str | None = None,
    use_graph: bool | None = None,
) -> DebateResult:
    """Run a full debate (data ingest → theses → rebuttals → synthesis) and
    return the structured ``DebateResult``.

    Args:
        analysts: persona IDs (e.g. ``["buffett", "taleb"]``).
        target: ticker (company) or indicator_id (macro).
        domain: ``"company"`` or ``"macro"``.
        target_date: forecast/as-of date.
        rounds: number of debate rounds (1 = thesis + synthesis, 2 = + rebuttal, …).
        provider_name: ``"mock"`` or ``"minimax"`` (see ``ProviderRegistry``).
        include_synthesis: if False, skip the moderator verdict.
        session_id: optional Langfuse session grouping.
        ctx: pre-built context dict (skips ``pipeline.context`` when given).
        trace: pre-built ``DebateTrace`` (caller owns lifecycle). When
            ``None``, this function builds a local one and uses its
            ``attributes(...)`` context manager to apply trace-level
            attributes (session_id, tags, metadata, trace_name) via
            ``langfuse.propagate_attributes`` — no-op when Langfuse env
            vars are missing.
        output_format: optional CLI ``--format`` value (``"md"``, ``"json"``,
            ``"per-agent"``, ``"debate"``). When provided, used together with
            ``rounds`` to decide whether to route through the LangGraph graph
            (``app/debate/graph.py``) or fall back to ``engine.run_debate``.
        use_graph: explicit override for the graph/legacy routing decision.
            When ``None``, the decision is derived from
            ``_should_use_graph(output_format, rounds)``.

    Returns:
        Fully populated ``DebateResult``.
    """
    log.info(
        "debate.orchestrator.start",
        target=target,
        domain=domain,
        analysts=analysts,
        rounds=rounds,
        provider=provider_name,
    )

    _ensure_mock_provider_is_schema_aware(provider_name)

    if ctx is None:
        ctx = _build_context(domain, target, target_date)
    context_md = pipeline_context.render_context_markdown(ctx, kind=domain)

    if trace is None:
        trace = DebateTrace()

    sector: str | None = None
    if domain == "company":
        sector = (ctx.get("quote") or {}).get("sector")

    if use_graph is None:
        use_graph = _should_use_graph(output_format, rounds)

    with trace.attributes(
        session_id=session_id,
        tags=[f"domain:{domain}", f"target:{target}"] + [f"analyst:{a}" for a in analysts],
        metadata={
            "analysts": list(analysts),
            "rounds": rounds,
            "include_synthesis": include_synthesis,
            "provider": provider_name,
            "sector": sector,
            "execution_path": "graph" if use_graph else "engine",
        },
        name=f"debate.{domain}.{target}",
    ):
        if use_graph:
            from app.debate.graph import run_debate_graph

            log.info(
                "debate.orchestrator.route",
                target=target,
                path="graph",
                output_format=output_format,
                rounds=rounds,
            )
            initial_state: dict[str, Any] = {
                "analysts": list(analysts),
                "target": target,
                "domain": domain,
                "target_date": target_date,
                "context_md": context_md,
                "context_raw": dict(ctx),
                "sector": sector,
                "theses": [],
                "rebuttals": [],
                "verdict": None,
                "round": 0,
                "rounds": rounds,
                "provider_name": provider_name,
                "include_synthesis": include_synthesis,
                "run_id": f"debate_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
            }
            thread_id = session_id or f"debate-{domain}-{target}"
            graph_callbacks: list[Any] | None = None
            if getattr(trace, "enabled", False) and trace.callback is not None:
                graph_callbacks = [trace.callback]
            final_state = run_debate_graph(
                initial_state,
                thread_id=thread_id,
                callbacks=graph_callbacks,
            )
            result = _state_to_debate_result(
                final_state,
                target=target,
                domain=domain,
                target_date=target_date,
                provider_name=provider_name,
                analysts=list(analysts),
                context_md=context_md,
                include_synthesis=include_synthesis,
            )
        else:
            log.info(
                "debate.orchestrator.route",
                target=target,
                path="engine",
                output_format=output_format,
                rounds=rounds,
            )
            result = engine.run_debate(
                analysts=list(analysts),
                target=target,
                domain=domain,
                target_date=target_date,
                context_md=context_md,
                rounds=rounds,
                provider_name=provider_name,
                include_synthesis=include_synthesis,
                callback=trace.callback,
                sector=sector,
            )

    log.info(
        "debate.orchestrator.complete",
        target=target,
        n_theses=len(result.theses),
        n_rebuttals=len(result.rebuttals),
        has_verdict=result.verdict is not None,
    )
    return result
