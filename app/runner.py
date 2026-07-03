"""Parallel runner: call (persona × indicator) assessments and return list[Assessment].

Phase 3 — also exposes ``run_debate_only`` for the new debate pipeline.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Any

from app.agents import ALL_AGENTS, BaseAgent
from app.catalog import get_target_indicators
from app.debate.tracing import DebateTrace
from app.logging import get_logger
from app.models import Assessment, DebateResult
from app.providers import ProviderRegistry

log = get_logger(__name__)


def _resolve_analysts(analysts: list[str]) -> list[type[BaseAgent]]:
    unknown = [a for a in analysts if a not in ALL_AGENTS]
    if unknown:
        raise ValueError(
            f"Unknown analyst IDs: {unknown}. Available: {sorted(ALL_AGENTS)}"
        )
    return [ALL_AGENTS[a] for a in analysts]


def _resolve_indicators(indicators: list[str] | None) -> list[str]:
    if indicators:
        return list(indicators)
    return list(get_target_indicators())


def run(
    analysts: list[str],
    indicators: list[str] | None = None,
    target_date: date | None = None,
    provider_name: str = "minimax",
    langfuse_handler: Any | None = None,
    max_workers: int = 0,
) -> list[Assessment]:
    """Run all (analyst × indicator) assessments in parallel.

    Args:
        analysts: list of persona IDs (e.g. ["buffett", "burry"]).
        indicators: list of indicator IDs; defaults to all 8 in the catalog.
        target_date: forecast date; defaults to today.
        provider_name: LLM provider ("minimax" or "mock").
        langfuse_handler: optional pre-built Langfuse callback.
        max_workers: thread pool size (0 = len(analysts) × len(indicators)).

    Returns:
        list of Assessment objects (one per (analyst, indicator) pair).
    """
    ProviderRegistry.initialize_defaults()
    target_date = target_date or date.today()
    agent_classes = _resolve_analysts(analysts)
    indicators = _resolve_indicators(indicators)

    try:
        agents = {cls.agent_id: cls(provider_name=provider_name, langfuse_handler=langfuse_handler) for cls in agent_classes}
    except (RuntimeError, ValueError) as e:
        msg = str(e)
        log.error("runner.aborted_due_to_init_error", error=msg)
        raise RuntimeError(msg) from e
    work = [(aid, ind) for aid in analysts for ind in indicators]
    pool_size = max_workers if max_workers > 0 else len(work)
    log.info(
        "runner.start",
        n_analysts=len(analysts),
        n_indicators=len(indicators),
        n_calls=len(work),
        provider=provider_name,
    )

    results: list[Assessment] = []
    init_error: str | None = None
    with ThreadPoolExecutor(max_workers=pool_size) as executor:
        futures = {
            executor.submit(agents[aid].generate_assessment, ind, target_date): (aid, ind)
            for aid, ind in work
        }
        for fut in as_completed(futures):
            aid, ind = futures[fut]
            try:
                results.append(fut.result())
                log.info("runner.assessment_done", agent=aid, indicator=ind)
            except RuntimeError as e:
                msg = str(e)
                log.error("runner.assessment_failed", agent=aid, indicator=ind, error=msg)
                if init_error is None:
                    init_error = msg
                    for f in futures:
                        f.cancel()
            except Exception as e:
                log.error("runner.assessment_failed", agent=aid, indicator=ind, error=str(e))

    if init_error is not None:
        log.error("runner.aborted_due_to_init_error", error=init_error)
        raise RuntimeError(init_error)

    log.info("runner.complete", n_results=len(results))
    return results


def run_debate_only(
    *,
    analysts: list[str],
    target: str,
    domain: str,
    target_date: date | None = None,
    rounds: int = 2,
    provider_name: str = "mock",
    include_synthesis: bool = True,
    session_id: str | None = None,
    ctx: dict[str, Any] | None = None,
    trace: DebateTrace | None = None,
) -> DebateResult:
    """Debate-only entry point used by the CLI.

    Delegates to ``app.debate.orchestrator.orchestrate_debate`` and supplies
    ``date.today()`` as a default for ``target_date``. Kept here (instead of
    in ``app.debate.orchestrator``) so the CLI import surface stays narrow.
    """
    from app.debate.orchestrator import orchestrate_debate

    td = target_date or date.today()
    return orchestrate_debate(
        analysts=list(analysts),
        target=target,
        domain=domain,
        target_date=td,
        rounds=rounds,
        provider_name=provider_name,
        include_synthesis=include_synthesis,
        session_id=session_id,
        ctx=ctx,
        trace=trace,
    )
