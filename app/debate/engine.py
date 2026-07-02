from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.agents import _HINTS, PROMPTS_DIR, _extract_content, _parse_json_or_default
from app.logging import get_logger
from app.models import (
    Consensus,
    DebateResult,
    Direction,
    Domain,
    Rebuttal,
    Thesis,
    Verdict,
)
from app.providers import LLMProvider, ProviderRegistry

log = get_logger(__name__)


def _read(path: str) -> str:
    p = Path(path)
    return p.read_text(encoding="utf-8") if p.exists() else ""


def persona_system_prompt(persona_id: str, target_kind: str) -> str:
    pdir = PROMPTS_DIR / persona_id
    refs_dir = pdir / "references"
    parts = [_read(pdir / "PERSONA.md")]
    if refs_dir.exists():
        for f in sorted(refs_dir.glob("*.md")):
            txt = _read(f)
            if txt:
                parts.append(txt)
    parts.append(_read(pdir / "indicators" / "_index.md"))
    return "\n\n---\n\n".join(p for p in parts if p)


def _hint_for(persona_id: str) -> str:
    h = _HINTS.get(persona_id)
    return f"Focus: {h.related}. {h.remember}" if h else ""


def build_thesis_messages(
    persona_id: str,
    target: str,
    domain: str,
    target_date: date,
    context_md: str,
) -> list[dict[str, str]]:
    system = persona_system_prompt(persona_id, target_kind=domain)
    system += f"\n\n===\nYou are assessing {target} as of {target_date.isoformat()}.\n{_hint_for(persona_id)}\n==="
    user = (
        f"# Data context for {target}\n\n"
        f"{context_md}\n\n"
        "# Your task\n"
        "Read the data above and produce an initial investment thesis for this target. "
        "You are NOT seeing any other persona's view yet — this is your independent first take.\n\n"
        "Submit a single structured thesis with:\n"
        "- verdict: BULLISH | BEARISH | NEUTRAL\n"
        "- conviction: float 0.0-1.0\n"
        "- key_drivers: 3-5 bullets (each citing a data point above)\n"
        "- reasoning: 1-2 paragraphs explaining your verdict from your persona's worldview\n"
        "- data_used: which data points from the context you leaned on\n"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_rebuttal_messages(
    persona_id: str,
    target: str,
    domain: str,
    target_date: date,
    context_md: str,
    prior_theses: list[Thesis],
) -> list[dict[str, str]]:
    system = persona_system_prompt(persona_id, target_kind=domain)
    system += f"\n\n===\nYou are assessing {target} as of {target_date.isoformat()}.\n{_hint_for(persona_id)}\n==="
    other = "\n\n".join(
        f"### {t.agent_id} (round {t.round}) — verdict {t.verdict.value} (conv {t.conviction:.2f})\n{t.reasoning}\nKey drivers: {'; '.join(t.key_drivers)}"
        for t in prior_theses
    )
    user = (
        f"# Data context for {target}\n\n{context_md}\n\n"
        f"# Other personas' theses (round {prior_theses[0].round})\n\n{other}\n\n"
        "# Your task\n"
        "Read the OTHER personas' theses carefully. Then produce a rebuttal:\n"
        "- targets: agent_ids of the personas you are responding to (your targets of agreement/disagreement)\n"
        "- concessions: 1-3 points where you concede to another persona\n"
        "- disagreements: 1-3 points where you push back, citing your persona's framework\n"
        "- revised_verdict: BULLISH | BEARISH | NEUTRAL (you may keep or change)\n"
        "- revised_conviction: float 0.0-1.0 (may go up or down)\n"
        "- reasoning: 1-2 paragraphs explaining your updated position\n\n"
        "Format rules: return targets/concessions/disagreements as FLAT JSON arrays "
        "of plain strings (e.g. [\"point 1\", \"point 2\"]). Do NOT nest arrays "
        "and do NOT wrap each item in XML tags such as <item>...</item>."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_verdict_messages(
    target: str,
    domain: str,
    target_date: date,
    context_md: str,
    theses: list[Thesis],
    rebuttals: list[Rebuttal],
) -> list[dict[str, str]]:
    counts = _tally(theses, rebuttals)
    system = (
        "You are the moderator of an investment debate. Your job is to read each persona's "
        "independent thesis AND their rebuttals to each other, then produce a single, fair, "
        "structured verdict that captures the agreement, the disagreement, and your best synthesis. "
        "Do NOT advocate for one persona's view. Be explicit about where consensus exists and where it doesn't."
    )
    theses_block = "\n\n".join(
        f"### {t.agent_id} (round {t.round}): {t.verdict.value} (conv {t.conviction:.2f})\n{t.reasoning}\nDrivers: {'; '.join(t.key_drivers)}"
        for t in theses
    )
    rebuttals_block = "\n\n".join(
        f"### {r.agent_id} (round {r.round}) → targets: {', '.join(r.targets) or '(none)'}\n"
        f"  concessions: {'; '.join(r.concessions) or '—'}\n"
        f"  disagreements: {'; '.join(r.disagreements) or '—'}\n"
        f"  revised verdict: {r.revised_verdict.value} (conv {r.revised_conviction:.2f})\n{r.reasoning}"
        for r in rebuttals
    ) or "_(no rebuttals — single-round debate)_"
    tally_block = (
        "## Position tally (pre-computed)\n"
        f"- bull: {counts['bull']}\n"
        f"- bear: {counts['bear']}\n"
        f"- neutral: {counts['neutral']}\n"
        f"- avg_conviction: {counts['avg_conviction']:.2f}\n"
        f"- suggested_consensus: {counts['consensus'].value}\n\n"
        "Your task: read the data, the theses, and the rebuttals below, then produce\n"
        "a structured verdict. The TALLY ABOVE is the ground truth — do not recount.\n"
        "Focus on the qualitative synthesis: points_of_agreement, points_of_disagreement,\n"
        "final_call, summary, confidence.\n\n"
    )
    user = (
        tally_block
        + f"# Debate summary\n"
        f"- Target: {target}\n"
        f"- Domain: {domain}\n"
        f"- Target date: {target_date.isoformat()}\n\n"
        f"# Data context\n{context_md}\n\n"
        f"# Round 0 theses\n{theses_block}\n\n"
        f"# Rebuttals\n{rebuttals_block}\n\n"
        "Produce a single structured verdict capturing the debate's net conclusion. "
        "Points of agreement must be claims shared by 2+ personas."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


_SCHEMA_DEFAULTS: dict[str, dict[str, Any]] = {
    "Thesis": {
        "agent_id": "[unavailable]",
        "target": "[unavailable]",
        "domain": "company",
        "round": 0,
        "verdict": "NEUTRAL",
        "conviction": 0.5,
        "reasoning": "[unavailable]",
        "key_drivers": [],
        "data_used": [],
    },
    "Rebuttal": {
        "agent_id": "[unavailable]",
        "target": "[unavailable]",
        "domain": "company",
        "round": 1,
        "revised_verdict": "NEUTRAL",
        "revised_conviction": 0.5,
        "reasoning": "[unavailable]",
        "targets": [],
        "concessions": [],
        "disagreements": [],
    },
    "Verdict": {},
}


def _invoke_structured(
    provider: LLMProvider,
    schema: type[BaseModel],
    messages: list[dict[str, str]],
    cfg: dict[str, Any] | None = None,
    callback: Any | None = None,
) -> BaseModel:
    model = provider.get_model()
    structured = model.with_structured_output(schema)
    if callback is not None:
        cfg = dict(cfg or {})
        cfg.setdefault("callbacks", []).append(callback)
    if cfg is not None:
        return structured.invoke(messages, config=cfg)
    return structured.invoke(messages)


def _invoke_with_fallback(
    provider: LLMProvider,
    schema: type[BaseModel],
    messages: list[dict[str, str]],
    callback: Any | None = None,
    counts: dict[str, Any] | None = None,
    target: str = "",
    domain: str = "",
) -> BaseModel | None:
    schema_name = schema.__name__
    defaults = _SCHEMA_DEFAULTS.get(schema_name, {})

    cfg: dict[str, Any] = {}
    if callback is not None:
        cfg["callbacks"] = [callback]

    model = provider.get_model()

    try:
        s = model.with_structured_output(schema, include_raw=True)
        res = s.invoke(messages, config=cfg or None)
        if isinstance(res, dict):
            parsed = res.get("parsed")
            if parsed is not None:
                log.debug("debate.invoke.fallback_used", level=1, schema=schema_name)
                return parsed
            err = res.get("parsing_error")
            if err is not None:
                log.warning("debate.invoke.l1_parsing_error", schema=schema_name, error=str(err)[:200])
        elif isinstance(res, BaseModel):
            log.debug("debate.invoke.fallback_used", level=1, schema=schema_name)
            return res
    except TypeError:
        try:
            s = model.with_structured_output(schema)
            res = s.invoke(messages, config=cfg or None)
            if isinstance(res, BaseModel):
                log.debug("debate.invoke.fallback_used", level=1, schema=schema_name)
                return res
            if isinstance(res, dict) and isinstance(res.get("parsed"), BaseModel):
                return res["parsed"]
        except Exception as e:
            log.warning("debate.invoke.l1_failed", schema=schema_name, error=str(e)[:200])
    except Exception as e:
        log.warning("debate.invoke.l1_failed", schema=schema_name, error=str(e)[:200])

    try:
        response = model.invoke(messages, config=cfg or None)
        content = _extract_content(response)
        d = _parse_json_or_default(content)
        for k, v in defaults.items():
            d.setdefault(k, v)
        if schema_name == "Verdict":
            d.setdefault("target", target)
            d.setdefault("domain", domain)
            if counts is not None:
                d.setdefault("consensus", counts.get("consensus", "NEUTRAL"))
                d.setdefault("bull_count", counts.get("bull", 0))
                d.setdefault("bear_count", counts.get("bear", 0))
                d.setdefault("neutral_count", counts.get("neutral", 0))
                d.setdefault("avg_conviction", counts.get("avg_conviction", 0.5))
            else:
                d.setdefault("consensus", "NEUTRAL")
                d.setdefault("bull_count", 0)
                d.setdefault("bear_count", 0)
                d.setdefault("neutral_count", 0)
                d.setdefault("avg_conviction", 0.5)
            d.setdefault("final_call", "[unavailable]")
            d.setdefault("confidence", 0.5)
            d.setdefault("summary", "[unavailable]")
            d.setdefault("points_of_agreement", [])
            d.setdefault("points_of_disagreement", [])
        instance = schema(**d)
        log.warning("debate.invoke.fallback_used", level=2, schema=schema_name)
        return instance
    except Exception as e:
        log.warning("debate.invoke.l2_failed", schema=schema_name, error=str(e)[:200])

    if schema_name == "Verdict" and counts is not None:
        log.warning("debate.invoke.fallback_used", level=3, schema="Verdict")
        return _heuristic_verdict(target, domain, [], [])

    try:
        instance = schema(**defaults)
        log.warning("debate.invoke.fallback_used", level=3, schema=schema_name)
        return instance
    except Exception as e:
        log.error("debate.invoke.l3_failed", schema=schema_name, error=str(e)[:200])
        return None


def run_debate(
    *,
    analysts: list[str],
    target: str,
    domain: str,
    target_date: date,
    context_md: str,
    rounds: int = 2,
    provider_name: str = "mock",
    include_synthesis: bool = True,
    callback: Any | None = None,
) -> DebateResult:
    log.info("debate.start", target=target, domain=domain, analysts=analysts, rounds=rounds, provider=provider_name)
    provider = ProviderRegistry.get(provider_name)

    theses = _run_round_theses(
        analysts=analysts,
        target=target,
        domain=domain,
        target_date=target_date,
        context_md=context_md,
        provider=provider,
        callback=callback,
    )
    log.info("debate.round_complete", round=0, n=len(theses))

    rebuttals: list[Rebuttal] = []
    prior = theses
    for r in range(1, rounds):
        prior_round = _run_round_rebuttals(
            analysts=analysts,
            target=target,
            domain=domain,
            target_date=target_date,
            context_md=context_md,
            prior_theses=prior,
            round_idx=r,
            provider=provider,
            callback=callback,
        )
        rebuttals.extend(prior_round)
        log.info("debate.round_complete", round=r, n=len(prior_round))
        prior = [
            Thesis(
                agent_id=rb.agent_id,
                target=rb.target,
                domain=rb.domain,
                round=rb.round,
                verdict=rb.revised_verdict,
                conviction=rb.revised_conviction,
                key_drivers=[],
                reasoning=rb.reasoning,
                data_used=[],
            )
            for rb in prior_round
        ]

    verdict = None
    if include_synthesis:
        verdict = _run_synthesis(
            target=target,
            domain=domain,
            target_date=target_date,
            context_md=context_md,
            theses=theses,
            rebuttals=rebuttals,
            provider=provider,
            callback=callback,
        )
        log.info("debate.synthesis_complete", consensus=verdict.consensus.value)

    from datetime import datetime
    result = DebateResult(
        run_id=f"debate_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
        domain=Domain(domain),
        target=target,
        target_date=target_date,
        provider=provider.provider_name(),
        analysts=list(analysts),
        context={"rendered_markdown": context_md},
        theses=theses,
        rebuttals=rebuttals,
        verdict=verdict,
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    log.info("debate.complete", target=target, n_theses=len(theses), n_rebuttals=len(rebuttals))
    return result


def _run_round_theses(
    *,
    analysts: list[str],
    target: str,
    domain: str,
    target_date: date,
    context_md: str,
    provider: LLMProvider,
    callback: Any | None = None,
) -> list[Thesis]:
    out: list[Thesis] = []
    with ThreadPoolExecutor(max_workers=max(1, len(analysts))) as ex:
        futures = {
            ex.submit(
                _invoke_with_fallback,
                provider,
                Thesis,
                build_thesis_messages(a, target, domain, target_date, context_md),
                callback,
            ): a
            for a in analysts
        }
        for fut, agent_id in futures.items():
            try:
                t = fut.result()
            except Exception as e:
                log.error("debate.thesis_dropped_unexpected", agent=agent_id, error=str(e))
                continue
            if isinstance(t, Thesis):
                t.agent_id = agent_id
                t.target = target
                t.domain = Domain(domain)
                t.round = 0
                out.append(t)
    return out


def _run_round_rebuttals(
    *,
    analysts: list[str],
    target: str,
    domain: str,
    target_date: date,
    context_md: str,
    prior_theses: list[Thesis],
    round_idx: int,
    provider: LLMProvider,
    callback: Any | None = None,
) -> list[Rebuttal]:
    out: list[Rebuttal] = []
    with ThreadPoolExecutor(max_workers=max(1, len(analysts))) as ex:
        futures = {
            ex.submit(
                _invoke_with_fallback,
                provider,
                Rebuttal,
                build_rebuttal_messages(
                    a, target, domain, target_date, context_md, prior_theses,
                ),
                callback,
            ): a
            for a in analysts
        }
        for fut, agent_id in futures.items():
            try:
                r = fut.result()
            except Exception as e:
                log.error("debate.rebuttal_dropped_unexpected", agent=agent_id, error=str(e))
                continue
            if isinstance(r, Rebuttal):
                r.agent_id = agent_id
                r.target = target
                r.domain = Domain(domain)
                r.round = round_idx
                out.append(r)
    return out


def _run_synthesis(
    *,
    target: str,
    domain: str,
    target_date: date,
    context_md: str,
    theses: list[Thesis],
    rebuttals: list[Rebuttal],
    provider: LLMProvider,
    callback: Any | None = None,
) -> Verdict:
    msgs = build_verdict_messages(target, domain, target_date, context_md, theses, rebuttals)
    counts = _tally(theses, rebuttals)
    v = _invoke_with_fallback(
        provider, Verdict, msgs, callback,
        counts=counts, target=target, domain=domain,
    )
    if v is not None:
        v.consensus = counts["consensus"]
        v.bull_count = counts["bull"]
        v.bear_count = counts["bear"]
        v.neutral_count = counts["neutral"]
        v.avg_conviction = counts["avg_conviction"]
        v.target = target
        v.domain = Domain(domain)
        return v
    log.warning("debate.synthesis_falling_back_heuristic", error="all fallback levels returned None")
    return _heuristic_verdict(target, domain, theses, rebuttals)


def _tally(theses: list[Thesis], rebuttals: list[Rebuttal]) -> dict[str, Any]:
    last_rebuttals: dict[str, Rebuttal] = {}
    for r in rebuttals:
        prev = last_rebuttals.get(r.agent_id)
        if prev is None or r.round > prev.round:
            last_rebuttals[r.agent_id] = r
    finals: list[tuple[Direction, float]] = []
    for t in theses:
        rb = last_rebuttals.get(t.agent_id)
        if rb is not None:
            finals.append((rb.revised_verdict, rb.revised_conviction))
        else:
            finals.append((t.verdict, t.conviction))
    counts = Counter(d for d, _ in finals)
    bull = counts.get(Direction.BULLISH, 0)
    bear = counts.get(Direction.BEARISH, 0)
    neu = counts.get(Direction.NEUTRAL, 0)
    total = max(1, len(finals))
    avg = sum(c for _, c in finals) / total
    if bull >= 0.75 * total:
        cons = Consensus.BULLISH
    elif bear >= 0.75 * total:
        cons = Consensus.BEARISH
    elif bull > bear and bull > neu:
        cons = Consensus.SPLIT_BULL
    elif bear > bull and bear > neu:
        cons = Consensus.SPLIT_BEAR
    else:
        cons = Consensus.NEUTRAL
    return {
        "bull": bull,
        "bear": bear,
        "neutral": neu,
        "avg_conviction": avg,
        "consensus": cons,
    }


def _heuristic_verdict(
    target: str, domain: str, theses: list[Thesis], rebuttals: list[Rebuttal]
) -> Verdict:
    finals = [t for t in theses]
    finals.extend(
        Thesis(
            agent_id=r.agent_id,
            target=r.target,
            domain=r.domain,
            round=r.round,
            verdict=r.revised_verdict,
            conviction=r.revised_conviction,
            reasoning=r.reasoning,
            key_drivers=[],
            data_used=[],
        )
        for r in rebuttals
    )
    counts = Counter(t.verdict for t in finals)
    bull = counts.get(Direction.BULLISH, 0)
    bear = counts.get(Direction.BEARISH, 0)
    neu = counts.get(Direction.NEUTRAL, 0)
    total = max(1, len(finals))
    avg = sum(t.conviction for t in finals) / total
    if bull >= 0.75 * total:
        cons = Consensus.BULLISH
    elif bear >= 0.75 * total:
        cons = Consensus.BEARISH
    elif bull > bear and bull > neu:
        cons = Consensus.SPLIT_BULL
    elif bear > bull and bear > neu:
        cons = Consensus.SPLIT_BEAR
    else:
        cons = Consensus.NEUTRAL
    return Verdict(
        target=target,
        domain=Domain(domain),
        consensus=cons,
        bull_count=bull,
        bear_count=bear,
        neutral_count=neu,
        avg_conviction=avg,
        points_of_agreement=[],
        points_of_disagreement=[],
        final_call=f"{cons.value} consensus among {len(finals)} positions",
        confidence=min(1.0, max(0.0, avg)),
        summary="Heuristic fallback — structured synthesis unavailable.",
    )
