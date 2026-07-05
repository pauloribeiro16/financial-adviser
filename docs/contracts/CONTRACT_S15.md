# CONTRACT — S15: Aggregator Prompt Hardening

**Contract ID:** SC-2026-15
**Date:** 2026-07-03
**Planner:** opencode
**Spec File:** (none — contract carries spec; single sprint)
**Status:** DRAFT → APPROVED → IMPLEMENTING → VALIDATED
**Branch:** `sprint/s15-prompt-hardening` (just created)
**Base:** `origin/master` (`575d65d`)

---

## Context

After S14, the surveillance aggregator (`app/watch/aggregator.py`) produces a 5-bullet `WatchSummary` per ticker. Live smoke + user review found 5 problems with the prompt and the schema:

1. The LLM sees only the debate in text form; it does **not** see the structured fundamentals (FCF yield, EBITDA, current price) that the Python heuristic already extracts from `data/cache/`. This causes inconsistency between the bullets (LLM guesses) and the indicators table (Python extracts).
2. `cycle_phase` is `str` (free-text). MiniMax-M3 produces inconsistent labels ("Mature cyclical commodity producer" instead of "Capital Return"), breaking sector rollup.
3. The system prompt says "use traffic-light emojis when natural" but does not enforce. `price_target.compute_buy_price()` calls `moat_strength_from_text()` which depends on 🟢/🟡/🔴 in the moat bullet. If the emoji is missing, the heuristic silently falls back to the lowest tier.
4. The system prompt has **no few-shot exemplar** — output style varies across tickers (concise vs essay).
5. The system prompt has **no "DO NOT" block** — MiniMax-M3 exhibits specific failure patterns: hedge phrases, platitudes, invented numbers, embedded numbered lists, metacomm about the debate, recommendation tone, disclaimers, ticker repetition per bullet, connector spam (Moreover/Furthermore), negation hedges, synonym stacking.

## Goals

Harden the aggregator prompt + schema to:

1. Pass `fundamentals` dict (already extracted by `sector_runner.py` / `markdown_renderer.py`) into the user message as a structured snapshot.
2. Constrain `cycle_phase` to a `StrEnum` of 4 phases (literal enforcement).
3. **Force** moat to start with 🟢/🟡/🔴 — both in prompt AND via `field_validator`.
4. Add a 1-shot exemplar (based on real XOM debate) to lock style.
5. Add a 14-item "DO NOT" block listing the specific MiniMax-M3 failure patterns observed in debate logs.
6. Tests for each new behavior so regressions are caught.

User decision (locked from Q&A):
- Few-shot exemplar: **based on real XOM debate**
- Cycle phase: **enum** (Literal["Hyper-Growth", "Operating Leverage", "Capital Return", "Decline"])
- Emoji: **mandatory in moat** (validator + prompt)

## Out of Scope

- Few-shot with N > 1 examples (single example only)
- Changing indicator definitions in YAML
- Changing `price_target.py` logic (depends on emoji; we keep the contract that moat starts with one)
- Surfacing "stale debate" warnings (would require tracking debate age)
- Validation errors that soft-warn instead of hard-reject (validator hard-rejects)

---

## Output Criteria

| # | Criterion | Weight |
|---|-----------|--------|
| OC1 | `app/watch/aggregator.py` defines `CyclePhase` (`StrEnum`) with 4 values: `HYPER_GROWTH="Hyper-Growth"`, `OPERATING_LEVERAGE="Operating Leverage"`, `CAPITAL_RETURN="Capital Return"`, `DECLINE="Decline"` | MUST |
| OC2 | `WatchSummary.cycle_phase` field type changed from `str` to `CyclePhase` | MUST |
| OC3 | `WatchSummary` has a `field_validator` on `moat` that **hard-rejects** if the stripped value does not start with one of 🟢 / 🟡 / 🔴 | MUST |
| OC4 | `aggregate_one()` accepts a new parameter `fundamentals: dict[str, float | None] | None = None` and embeds it in the user message under a `# Fundamentals snapshot` block (or omits the block when None) | MUST |
| OC5 | The `# Fundamentals snapshot` block formats each value with its unit (e.g. "FCF yield: 6.4%"). Missing values render as "n/a". | MUST |
| OC6 | `_build_messages()` system message includes a 14-item "DO NOT" block covering: hedge phrases, invented numbers, platitudes, embedded numbered lists, metacomm, recommendations, disclaimers, ticker repetition per bullet, same point in different words, negation hedges, synonym stacking, emoji outside moat, connector spam, padding generic language | MUST |
| OC7 | `_build_messages()` system message includes a single 1-shot `<example>` block based on the real XOM debate under `out/company/energy/XOM/` (or last available), with all 5 fields populated correctly | MUST |
| OC8 | `MockModel` (in `app/providers.py`) returns a `WatchSummary` with `cycle_phase` as a valid `CyclePhase` value (e.g. `"Capital Return"`) so mock runs work | MUST |
| OC9 | `_placeholder_summary()` (the double-fallback placeholder) is updated so each field uses a placeholder string containing a valid emoji for moat (e.g. `🟡 Data unavailable` so the buy_price heuristic still returns a sensible value) | MUST |
| OC10 | `sector_runner.py` is updated to pass the indicators dict it already extracts into `aggregate_one()` as the `fundamentals` argument | MUST |
| OC11 | `tests/test_aggregator.py` adds: `test_cycle_phase_enum_validation`, `test_moat_validator_rejects_no_emoji`, `test_moat_validator_accepts_three_emojis`, `test_fundamentals_block_in_user_message`, `test_placeholder_summary_starts_with_emoji`, `test_do_not_block_present_in_system_message`, `test_example_block_present_in_system_message` (≥7 new tests) | MUST |
| OC12 | `ruff check app/watch/` clean | MUST |
| OC13 | All **existing** tests still pass (no regressions): `test_aggregator.py`, `test_renderer.py`, `test_cli_watch.py`, `test_orchestrator.py`, `test_debate_graph.py`, `test_session_id.py`, etc. | MUST |
| OC14 | `pytest tests/ --tb=no -q` — 0 new failures beyond the pre-existing 10 path-test failures | MUST |

## Outcome Criteria

| # | Criterion | Weight |
|---|-----------|--------|
| ON1 | Live smoke: run a mock debate for XOM (or any ticker in `out/company/`), then `python3 -m app.main watch --sector Energy --provider mock`. The generated `current.md` has all 5 bullets, `cycle_phase` is exactly one of the 4 enum values, `moat` starts with 🟢/🟡/🔴. | MUST |
| ON2 | `python3 -c "from app.watch.aggregator import aggregate_one, WatchSummary, CyclePhase; print(CyclePhase.CAPITAL_RETURN)"` exits 0 | MUST |

---

## File Changes Summary

| File | Action | Notes |
|------|--------|-------|
| `app/watch/aggregator.py` | modify | `CyclePhase` enum, `field_validator` on moat, `fundamentals` arg, DO NOT block, example block |
| `app/watch/sector_runner.py` | modify | Pass indicators dict to `aggregate_one()` |
| `app/providers.py` | modify | `MockModel` returns valid `WatchSummary` with valid `CyclePhase` |
| `tests/test_aggregator.py` | modify | Add 7+ new tests (OC11) |

## Risks

| Risk | Mitigation |
|------|------------|
| `CyclePhase` enum rejects MiniMax-M3's "Mature cyclical commodity producer" style output | Repair path already exists in `_invoke_with_fallback`; enum error becomes a validation error → repair retry |
| `field_validator` on moat is too strict (rejects legitimate variations like "🟢. " (emoji + period)) | Validator accepts if the **first character** is one of the 3 emojis; period/space/dash after is fine |
| Few-shot exemplar drifts if XOM debate is deleted/changed | Use a static string baked into the code; not a live file read |
| Fundamentals dict has non-numeric values | Render with `f"{v}"` (default string representation); for None, render "n/a" |
| `MockProvider` already has `_SchemaAwareMockModel` — verify it still works with new schema | Test: `python -m app.main watch --sector Energy --provider mock` must succeed |

## Commit Strategy

Single atomic commit:
```
feat(watch): S15 — aggregator prompt hardening (enum, validator, fundamentals, exemplar, DO NOT)
```

## Validation Commands

```bash
cd /home/epmq-cyber/Área de Trabalho/projects/financial-adviser
source .venv/bin/activate

# CyclePhase enum works
python3 -c "from app.watch.aggregator import CyclePhase; print(CyclePhase.CAPITAL_RETURN.value)"

# Moat validator rejects no emoji
python3 -c "
from app.watch.aggregator import WatchSummary
try:
    WatchSummary(moat='Strong moat, widening', cycle_phase='Capital Return',
                 financial_health='Net debt 0.4x', valuation='Fair', risks='Risk 1')
    print('FAIL: should have rejected')
except Exception as e:
    print('OK: rejected no-emoji moat')
"

# Moat validator accepts emoji
python3 -c "
from app.watch.aggregator import WatchSummary
s = WatchSummary(moat='🟢 Cost advantage', cycle_phase='Capital Return',
                financial_health='Net debt 0.4x', valuation='Fair', risks='Risk 1')
print('OK:', s.moat)
"

# System message contains the new blocks
python3 -c "
from app.watch.aggregator import _build_messages
msgs = _build_messages('XOM', 'Energy', '# debate text', repair=False, fundamentals={'FCF yield': 0.064, 'Net Debt/EBITDA': 0.39})
sys_msg = msgs[0]['content']
assert 'DO NOT' in sys_msg
assert 'moat MUST start with' in sys_msg
assert '<example>' in sys_msg
assert 'cycle_phase' in sys_msg
print('OK: all blocks present')
"

# User message contains fundamentals
python3 -c "
from app.watch.aggregator import _build_messages
msgs = _build_messages('XOM', 'Energy', '# debate text', repair=False, fundamentals={'FCF yield': 0.064, 'EV/EBITDA': None})
user_msg = msgs[1]['content']
assert 'Fundamentals snapshot' in user_msg
assert '6.4%' in user_msg  # 0.064 → 6.4%
assert 'n/a' in user_msg
print('OK: fundamentals block formatted')
"

# End-to-end watch smoke
python3 -m app.main watch --sector Energy --provider mock --output /tmp/s15-test
cat /tmp/s15-test/Energy/XOM/current.md | head -20

# Lint
ruff check app/watch/

# Tests
pytest tests/test_aggregator.py tests/test_renderer.py tests/test_cli_watch.py -v

# Master regression
pytest tests/test_orchestrator.py tests/test_debate_graph.py tests/test_session_id.py tests/test_prompts_registry.py --tb=no -q

# Full
pytest tests/ --tb=no -q
```

## What to return

1. Files modified with line-count diffs
2. ruff output (clean)
3. New tests passing (≥7)
4. Master regression test count (no new failures)
5. `pytest tests/ --tb=no -q` total summary (expect 0 new failures)
6. Live smoke output (the watch mock run)
7. Any deviations from the contract
