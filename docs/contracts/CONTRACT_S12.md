# CONTRACT — S12: Port LangGraph + Langfuse Prompts + Coherent Tracing to Master

**Contract ID:** SC-2026-12
**Date:** 2026-07-02
**Planner:** opencode
**Spec File:** (none — carried by contract; single contract with 3 sprints)
**Status:** DRAFT → APPROVED → IMPLEMENTING → VALIDATED
**Branch:** `sprint/s12-port-prompts-langgraph`
**Base:** `origin/master` (commit `7a88010`)

---

## Context

The remote `origin/master` (commit `7a88010`) diverged from our local `sprint/s7-prompts-langgraph` (commit `79ce015`). The two tracks share the ancestor `0f19c4e` but evolved independently for 18 vs 6 commits.

**Master evolved to** (from `0f19c4e` to `7a88010`):
- S7 depth/news: deep analysis prompts, derived metrics, news pipeline, 3-level fallback safety net
- S8 schema-fix: schema separation (`ThesisInput`/`RebuttalInput`), enum coercion (`_coerce_direction`)
- S9 sector-lenses: sector-aware analysis
- S10 personas-news: sector-specific analysts, persona domain filtering, 8-Ks
- S11 output-paths: organized output directory tree

**Our branch added** (from `0f19c4e` to `79ce015`):
- S7-P1: Langfuse prompts registry + sync CLI
- S7-P2: LangGraph StateGraph debate engine
- S7-P3: Coherent tracing + auto session_id
- S8: LLM output robustness (coercion + retry)

Both tracks independently solved the coercion bug (`d9eddd8` on master, `51d2efc` on our branch). Master's solution is more advanced (3-level fallback with slim schemas, enum coercion).

## Goal

Port our 3 unique contributions to master, adapted to master's API:
1. **Langfuse prompts registry** (`app/prompts/{__init__,registry,sync}.py`) — NEW files, no conflict
2. **LangGraph StateGraph** (`app/debate/graph.py`) — adapted to master's engine (slim schemas, 3-level fallback, sector support)
3. **Coherent tracing** (auto `session_id` + `@observe` decorators) — adapted to master's main.py and orchestrator

**Decisions locked** (user-approved):
- LangGraph **replaces** `engine.run_debate` for debate mode (orchestrator routes to graph)
- LangGraph uses master's **3-level fallback** (not our retry-with-repair)
- Legacy mode (`--format {md,json,per-agent}`) continues to use `engine.run_debate` directly

## Out of Scope

- NOT bringing our `_coerce_str_list` (master's is more complete)
- NOT bringing our retry-with-repair (master's 3-level fallback covers this)
- NOT modifying master's `engine.py` API (only consuming it)
- NOT bringing our `app/debate/tracing.py` changes (master's is the right one)
- NOT modifying master's `models.py` (their coercion is better)

---

## Output Criteria

### Sprint S12-P1 — Langfuse Prompts Registry (port)

| # | Criterion | Weight |
|---|-----------|--------|
| OC1 | `app/prompts/__init__.py` exists (empty package marker) | MUST |
| OC2 | `app/prompts/registry.py` exists with `get_system_prompt(persona_id)`, `get_task_template(task_name, **vars)`, `clear_cache()`, `_langfuse_client()` | MUST |
| OC3 | Registry tries Langfuse first, falls back to disk (which uses master's `persona_system_prompt` from `app/debate/engine.py`) | MUST |
| OC4 | `_DEFAULT_TASK_TEMPLATES` in registry is **minimal** — only task instructions + variables; does NOT duplicate master's 6-pillar analysis structure (that comes from engine.py) | MUST |
| OC5 | `app/prompts/sync.py` CLI exists with `push`, `push --persona X`, `list`, `diff` subcommands | MUST |
| OC6 | `python -m app.prompts.sync push` creates 18 prompts (15 personas + 3 tasks) in Langfuse | MUST |
| OC7 | `sync push` without LANGFUSE env vars exits 2 with clear message | MUST |
| OC8 | `tests/test_prompts_registry.py` ports and passes (≥15 tests) | MUST |
| OC9 | `ruff check app/prompts/ tests/test_prompts_registry.py` — clean | MUST |

### Sprint S12-P2 — LangGraph Debate Engine (adapt to master)

| # | Criterion | Weight |
|---|-----------|--------|
| OC10 | `app/debate/graph.py` exists with `build_debate_graph() -> CompiledStateGraph` + 7 nodes | MUST |
| OC11 | Nodes call master's API: `engine.build_thesis_messages(... sector=state.get("sector"))`, `engine.build_rebuttal_messages(...)`, `engine._run_synthesis(...)` | MUST |
| OC12 | LLM calls use master's `_invoke_with_fallback` (3-level safety net) instead of plain `with_structured_output` | MUST |
| OC13 | Graph uses `LLM_INPUT_SCHEMA` from master's `engine.py` for tool-call payloads (slim schemas) | MUST |
| OC14 | Graph compiled with `MemorySaver` checkpointer | MUST |
| OC15 | Fan-out via `Send()` for parallel theses/rebuttals | MUST |
| OC16 | Conditional edge after rebuttals: `round < rounds` → rebuttals (loop), else → synthesis | MUST |
| OC17 | `app/debate/orchestrator.py` routes to `graph.invoke()` for debate mode (when `--company` or `--rounds > 1` or `--format debate`) | MUST |
| OC18 | `orchestrator.py` routes to `engine.run_debate()` for legacy mode (when `--format {md, json, per-agent}` with conditions met) | MUST |
| OC19 | `engine.run_debate` is **NOT removed** (legacy path still uses it) | MUST |
| OC20 | `tests/test_debate_graph.py` adapted and passes (≥5 tests, all using master's API) | MUST |
| OC21 | `pytest tests/test_orchestrator.py tests/test_debate_smoke.py tests/test_debate_synthesis.py tests/test_context_enrichment.py -v` — all pass (no regressions) | MUST |

### Sprint S12-P3 — Coherent Tracing + Auto session_id

| # | Criterion | Weight |
|---|-----------|--------|
| OC22 | `_auto_session_id(domain, target)` helper exists in `app/main.py` | MUST |
| OC23 | CLI auto-generates `session_id = "debate-{domain}-{target}-{YYYYMMDD_HHMMSS}"` when `--session-id` is None | MUST |
| OC24 | Auto-generated session_id is printed to stderr | MUST |
| OC25 | Explicit `--session-id` value is preserved as-is | MUST |
| OC26 | `orchestrator.py` auto-generates `session_id` when caller passes `None` (defensive, for direct API users) | MUST |
| OC27 | Each graph node has `@observe(name=..., as_type=...)` decorator | MUST |
| OC28 | `tests/test_session_id.py` passes (≥5 tests: format, propagation, uniqueness, explicit preserved, orchestrator auto-gen) | MUST |
| OC29 | `tests/test_graph_decorators.py` passes (≥2 tests) | MUST |
| OC30 | Live Langfuse check: 1 trace per debate with `session_id` + ≥8 observations correctly nested | SHOULD |

## Outcome Criteria

| # | Criterion | Weight |
|---|-----------|--------|
| ON1 | `ruff check app/ tests/` — clean | MUST |
| ON2 | `pytest tests/ --tb=no -q` — ≥100 pass (master has ~80, our additions ≥20) | MUST |
| ON3 | `python -m app.main --company AAPL --analysts buffett,taleb --provider mock --rounds 2` — valid DebateResult | MUST |
| ON4 | `python -m app.main --analysts buffett --provider mock --format per-agent` (legacy path) — exit 0 | MUST |
| ON5 | `python -m app.main --company AAPL --analysts buffett,taleb --provider minimax --rounds 2` — exit 0 + Langfuse receives 1 trace with session_id | MUST |
| ON6 | `python -m app.main --interactive` — menu works | MUST |
| ON7 | 3 atomic commits on `sprint/s12-port-prompts-langgraph` branch | MUST |

---

## File Changes Summary

| File | Action | Sprint | Notes |
|------|--------|--------|-------|
| `app/prompts/__init__.py` | create | P1 | empty |
| `app/prompts/registry.py` | create | P1 | minimal templates, master's pillars come from engine |
| `app/prompts/sync.py` | create | P1 | CLI push/list/diff |
| `tests/test_prompts_registry.py` | create | P1 | unit tests |
| `app/debate/graph.py` | create | P2 | adapted to master's engine API |
| `app/debate/orchestrator.py` | modify | P2 | route to graph (debate) or engine (legacy) |
| `tests/test_debate_graph.py` | create | P2 | unit tests using master's API |
| `app/main.py` | modify | P3 | `_auto_session_id` helper + CLI logic |
| `tests/test_session_id.py` | create | P3 | unit tests |
| `tests/test_graph_decorators.py` | create | P3 | unit tests |
| `docs/contracts/QUALITY_LOG.md` | modify | end | record S12 |

## Risks

- **Engine API drift**: master's `build_thesis_messages` signature includes `sector`. If we miss it, graphs fail for company targets. Mitigated by P2 tests with `sector="Technology"`.
- **Slim schema output**: master's `_invoke_with_fallback` returns `BaseModel | None`. Nodes must handle `None` gracefully (log + return empty list).
- **`engine.run_debate` removal**: if master removes `run_debate` in the future, our legacy path breaks. Not in scope now; document in code comment that legacy path depends on this.
- **Langfuse self-hosted env vars**: same as S7-P1 — `set -a && source .env && set +a` before `sync push`.

## Commit Strategy

3 atomic commits, one per sprint:
- `feat(debate): S12-P1 — Langfuse prompts registry (port to master)`
- `feat(debate): S12-P2 — LangGraph debate engine adapted to master engine`
- `feat(debate): S12-P3 — coherent tracing + auto session_id`

Plus a `docs(contracts): record S12 in QUALITY_LOG` commit at the end.

## Validation Commands

```bash
cd /home/epmq-cyber/Área de Trabalho/projects/financial-adviser
source .venv/bin/activate

# Per sprint (executor runs these)
# P1
ruff check app/prompts/ tests/test_prompts_registry.py
pytest tests/test_prompts_registry.py -v
set -a && source .env && set +a
python -m app.prompts.sync push

# P2
ruff check app/debate/graph.py app/debate/orchestrator.py tests/test_debate_graph.py
pytest tests/test_debate_graph.py tests/test_orchestrator.py tests/test_debate_smoke.py -v

# P3
ruff check app/main.py tests/test_session_id.py tests/test_graph_decorators.py
pytest tests/test_session_id.py tests/test_graph_decorators.py -v

# Final
ruff check app/ tests/
pytest tests/ --tb=no -q
python -m app.main --company AAPL --analysts buffett --provider mock --rounds 1
python -m app.main --analysts buffett --provider mock --format per-agent --output /tmp/s12-legacy
set -a && source .env && set +a && python -m app.main --company AAPL --analysts buffett,taleb --provider minimax --rounds 2
```