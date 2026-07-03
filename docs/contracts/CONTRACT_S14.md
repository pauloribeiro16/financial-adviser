# CONTRACT — S14: Vigilância Progressiva (Surveillance)

**Contract ID:** SC-2026-14
**Date:** 2026-07-03
**Planner:** opencode
**Spec File:** (none — contract carries spec; 3 sequential sprints)
**Status:** DRAFT → APPROVED → IMPLEMENTING → VALIDATED
**Branch:** `sprint/s14-surveillance`
**Base:** `origin/master` (current `575d65d` + S13 merged)

---

## Context

The pipeline currently has two phases:
1. **Phase 1 — Analysis (debate)**: produce a per-ticker debate Markdown under `out/company/<sector>/<ticker>/<TS>_*_debate.md`
2. **Phase 2 — Surveillance (S14)**: aggregate per-sector intelligence from those debates into a watch-table

This contract implements Phase 2. It is a **separate, isolated workflow** (sub-command `watch`) that runs in parallel to debate. It must:

- Read the latest debate per ticker (no LLM debate in surveillance path itself)
- Call an LLM aggregator per ticker to produce a 5-bullet summary
- Compute sector-specific indicator values + ratings (heuristic Python)
- Compute a buy-price target (heuristic Python)
- Render per-ticker Markdown + sector rollup index
- Emit one Langfuse trace per sector with session_id `surveillance-<ts>` (separate from debate session_ids)

## Goals (locked, from user Q&A)

| Dimension | Decision |
|-----------|----------|
| Workflow entry | Sub-command CLI: `python3 -m app.main watch ...` |
| Trigger | Manual only (no auto, no cron) |
| Read scope per ticker | Last debate `.md` + `_meta.json` |
| Output | `out/surveillance/<sector>/<ticker>/current.md` + sector `_index.md` |
| Aggregator granularity | Per company (1 LLM call per company); concurrent |
| Aggregator model | `with_structured_output(WatchSummarySchema)` for the 5 bullets; deterministic Python for ratings + buy_price |
| Provider | Same provider as the most recent debate |
| LLM scope | End-to-end: reads the debate, emits 5 bullets |
| Indicator schema | YAML/JSON per sector in `app/sectors/` (NOT hardcoded in Python) |
| Schema of 5 bullets | Moat + Cycle phase + Financial Health + Valuation + Risks (mirrors 6 pillars) |
| Indicator count per sector | 6-8 |
| Buy-price heuristic | `fair_value = current_price * (sector_target_fcf_yield / company_fcf_yield)`, `margin = 0.85 + 0.03 * (moat_strength - 3)`, `buy_price = fair_value * margin` |
| Trail of debates | Visible at end of `current.md` (date + provider + analysts + conviction + path) |
| Drift handling | Append history.json; current.md shows latest curated summary |
| Langfuse | session_id `surveillance-<sector>-<ts>`; tags `phase:surveillance`, `sector:<name>`; one trace per sector (not per ticker) |
| Interactive menu | Add as option 2 in top-level menu (option 1 = Analyze) |
| Currency | USD |
| Source of indicator values | Heuristic from `data/cache/` (already populated); for sector-level (WTI, etc.) read from `pipeline/macro.py` if present, else `None` |

## Out of Scope

- Auto-refresh on debate completion (manual only)
- Cron / scheduled runs
- Sector-level indicators from live FRED (only cache)
- Multi-currency
- Pruning `history.json` (no auto-cleanup)
- Sub-second parallelism tuning (default 4 workers)

---

## Output Criteria

### Sprint S14-P1 — Structure (sectors YAML + reference reader + price target + CLI scaffold)

| # | Criterion | Weight |
|---|-----------|--------|
| OC1 | `app/sectors/energy.yaml` exists with 6-8 indicator specs (id, name, extract path, healthier_is, thresholds) | MUST |
| OC2 | `app/sectors/technology.yaml`, `app/sectors/healthcare.yaml`, `app/sectors/financial-services.yaml` exist (≥6 indicators each) | MUST |
| OC3 | `app/sectors/__init__.py` loads YAML, validates schema, exposes `SECTOR_INDICATORS: dict[str, list[IndicatorSpec]]` | MUST |
| OC4 | `app/watch/reference_reader.py` has `load_latest_debate(sector, ticker) -> DebateRef | None` returning path to latest `*_debate.md` + parsed `*_meta.json` | MUST |
| OC5 | `app/watch/price_target.py` implements `compute_buy_price(current_price, sector_target_fcf_yield, company_fcf_yield, moat_strength) -> float` per the locked heuristic | MUST |
| OC6 | `app/watch/cli.py` has `cmd_watch(args) -> int` function that handles `--sector`, `--ticker`, `--all`, `--provider`, `--output` flags | MUST |
| OC7 | `tests/test_sectors.py` loads all 4 sector YAMLs and asserts non-empty + schema valid | MUST |
| OC8 | `tests/test_price_target.py` covers: positive signal (FCF > sector), negative signal, moat scaling, edge case FCF=0 | MUST |
| OC9 | `tests/test_reference_reader.py` covers: empty sector → None, single debate returns it, multiple debates picks latest by TS | MUST |
| OC10 | `ruff check app/watch/ app/sectors/ tests/test_sectors.py tests/test_price_target.py tests/test_reference_reader.py` clean | MUST |
| OC11 | `pytest tests/test_sectors.py tests/test_price_target.py tests/test_reference_reader.py -v` — all pass | MUST |

### Sprint S14-P2 — Aggregator + Renderer + Langfuse

| # | Criterion | Weight |
|---|-----------|--------|
| OC12 | `app/watch/aggregator.py` defines `WatchSummary` Pydantic schema with 5 fields: `moat`, `cycle_phase`, `financial_health`, `valuation`, `risks` (each `str` with character cap) | MUST |
| OC13 | `aggregate_one(provider, debate_text, ticker, sector) -> WatchSummary` — calls LLM with structured output, retries once on validation error | MUST |
| OC14 | `app/watch/markdown_renderer.py` renders `current.md` per the agreed template (5 bullets + indicators table + buy target + trail) | MUST |
| OC15 | `app/watch/sector_file.py` writes `out/surveillance/<sector>/_index.md` rollup with all tickers in sector | MUST |
| OC16 | `app/watch/sector_runner.py` iterates tickers in sector, calls aggregator + rating helpers + renderer concurrently (up to 4 workers) | MUST |
| OC17 | `app/watch/langfuse_tracing.py` provides `surveillance_trace(sector) -> DebateTrace`-like context manager with `session_id="surveillance-<sector>-<ts>"` and tags | MUST |
| OC18 | Aggregator reads real `data/cache/` to fill indicator values; missing values render as "n/a" | MUST |
| OC19 | `tests/test_aggregator.py` covers: schema validation, retry path, indicator extraction from cache | MUST |
| OC20 | `tests/test_renderer.py` covers: full render, missing-debate case, malformed rating values, end-to-end with mock provider | MUST |
| OC21 | `ruff check app/watch/` clean | MUST |
| OC22 | `pytest tests/test_aggregator.py tests/test_renderer.py -v` all pass | MUST |

### Sprint S14-P3 — CLI Integration + Menu + Tests

| # | Criterion | Weight |
|---|-----------|--------|
| OC23 | `app/main.py` adds `watch` subparser with `--sector`, `--ticker`, `--all`, `--provider`, `--output` flags and `add_subparsers(..., required=True)` | MUST |
| OC24 | `python3 -m app.main watch --sector Energy --provider mock --output /tmp/s14-test` — exit 0, writes `out/surveillance/Energy/` files | MUST |
| OC25 | `python3 -m app.main watch` without args shows help + exits 0 (no error, just helpful usage) | MUST |
| OC26 | `python3 -m app.main watch --sector NonExistent` exits 1 with clear error | MUST |
| OC27 | `app/cli_menu.py` top-level menu has new option "Watch (refresh surveillance table)" selecting between debate + watch | MUST |
| OC28 | Interactive menu flow: top picks mode (analyze/watch) → if watch, picks sector → runs watch | MUST |
| OC29 | `tests/test_cli_watch.py` covers: subcommand present, valid + invalid args, missing output | MUST |
| OC30 | `pytest tests/ --tb=no -q` — ≥0 regressions (current baseline: 215 pass, 10 fail pre-existing path tests) | MUST |
| OC31 | `ruff check app/ tests/` clean | MUST |

## Outcome Criteria

| # | Criterion | Weight |
|---|-----------|--------|
| ON1 | `python3 -m app.main --help` shows `watch` subcommand | MUST |
| ON2 | Run a debate on XOM (mock), then `watch --sector Energy --provider mock`, produces `out/surveillance/Energy/XOM/current.md` + `out/surveillance/Energy/_index.md` | MUST |
| ON3 | `out/surveillance/Energy/XOM/current.md` contains: 5 bullets (Moat/Cycle/Financial/Valuation/Risks) + 6+ indicator rows with rating + buy_price + trail | MUST |
| ON4 | Langfuse receives a trace per sector run with session_id matching `surveillance-energy-<ts>` | SHOULD |
| ON5 | `tests/test_orchestrator.py`, `tests/test_debate_graph.py`, `tests/test_session_id.py` — all pass (no regressions to debate path) | MUST |

---

## File Changes Summary

| File | Action | Sprint | Notes |
|------|--------|--------|-------|
| `app/sectors/__init__.py` | create | P1 | YAML loader + IndicatorSpec validation |
| `app/sectors/energy.yaml` | create | P1 | 6-8 indicators |
| `app/sectors/technology.yaml` | create | P1 | 6+ indicators |
| `app/sectors/healthcare.yaml` | create | P1 | 6+ indicators |
| `app/sectors/financial-services.yaml` | create | P1 | 6+ indicators |
| `app/watch/__init__.py` | create | P1 | package marker |
| `app/watch/cli.py` | create | P1 | sub-command CLI scaffold |
| `app/watch/reference_reader.py` | create | P1 | load latest debate |
| `app/watch/price_target.py` | create | P1 | buy-price heuristic |
| `tests/test_sectors.py` | create | P1 | YAML loading + schema |
| `tests/test_price_target.py` | create | P1 | heuristic units |
| `tests/test_reference_reader.py` | create | P1 | latest-debate selection |
| `app/watch/aggregator.py` | create | P2 | WatchSummary + LLM |
| `app/watch/markdown_renderer.py` | create | P2 | markdown templates |
| `app/watch/sector_file.py` | create | P2 | sector index writer |
| `app/watch/sector_runner.py` | create | P2 | orchestration + concurrency |
| `app/watch/langfuse_tracing.py` | create | P2 | session_id prefix |
| `tests/test_aggregator.py` | create | P2 | aggregator units |
| `tests/test_renderer.py` | create | P2 | renderer units |
| `app/main.py` | modify | P3 | add `watch` subparser |
| `app/cli_menu.py` | modify | P3 | top-level menu mode picker |
| `tests/test_cli_watch.py` | create | P3 | CLI subcommand tests |
| `docs/contracts/QUALITY_LOG.md` | modify | end | record S14 |

## Risks

- **YAML schemas can drift** if sectors evolve. Mitigation: `SECTOR_INDICATORS` validated at load time (Pydantic `IndicatorSpec` with `model_validate`); missing required keys → clear error.
- **Aggregator prompts the LLM for free-form text** which may diverge frome schema. Mitigation: Pydantic `WatchSummary` schema enforced via `with_structured_output` + repair retry (mirrors S8).
- **Concurrency stresses Langfuse limits**. Mitigation: 4 workers max + Langfuse v4 OTEL handles concurrent enqueue.
- **`data/cache/` schema may differ across tickers**. Mitigation: `IndicatorSpec.extract` is a dotted-path string resolved with `functools.reduce(getitem, ...)`, returns None if missing.
- **Master evolves** (S15+). Mitigation: pinned to `origin/master` S13 baseline.

## Commit Strategy

3 atomic commits:
- `feat(watch): S14-P1 — sectors YAML + reference reader + price target + CLI scaffold`
- `feat(watch): S14-P2 — aggregator + markdown renderer + sector file + langfuse tracing`
- `feat(watch): S14-P3 — CLI integration (watch subcommand) + menu + tests`

Plus final: `docs(contracts): record S14 in QUALITY_LOG`.

## Validation Commands

```bash
cd /home/epmq-cyber/Área de Trabalho/projects/financial-adviser
source .venv/bin/activate

# Per sprint
ruff check app/watch/ app/sectors/ tests/test_*.py
pytest tests/test_sectors.py tests/test_price_target.py tests/test_reference_reader.py -v  # P1
pytest tests/test_aggregator.py tests/test_renderer.py -v                                 # P2
pytest tests/test_cli_watch.py -v                                                         # P3

# Final smoke (with mock)
python3 -m app.main --company XOM --analysts buffett,taleb --provider mock --rounds 1
python3 -m app.main watch --sector Energy --provider mock
ls out/surveillance/Energy/  # should have XOM/current.md + _index.md
cat out/surveillance/Energy/XOM/current.md  # verify structure

# Regression
pytest tests/test_orchestrator.py tests/test_debate_graph.py tests/test_session_id.py -v
pytest tests/ --tb=no -q
```

## What to return (per sprint)

1. Files created/modified with line counts
2. ruff output (clean)
3. New tests passing
4. Full pytest count
5. Smoke CLI outputs
6. Any deviations from the contract
