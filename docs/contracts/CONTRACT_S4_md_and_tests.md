# CONTRACT S4 — Markdown Output + Smoke Tests

**Date:** 2026-07-01
**Planner:** opencode
**Status:** DRAFT → APPROVED → IMPLEMENTING → VALIDATED
**Phase:** 4 of 4 (final sprint of MVP)
**Depends On:** MVP sprint (agents + runner + main)
**Parent Goal:** Extend `financial-adviser` with `.md` output and a pytest smoke suite.

---

## Trials

`trials: 3` — each criterion run 3 times.

---

## Scope

Two deliverables:

1. **Markdown formatter**: `app/formatter.py` (~80 LOC) converts a `list[Assessment]` into a well-formatted `.md` document. CLI default output.
2. **Pytest smoke suite**: `tests/` (~150 LOC) with 8 tests covering the MVP.

### Files to create

| File | Action | Lines (est.) | Why |
|------|--------|--------------|-----|
| `app/formatter.py` | create | ~80 | `render(assessments: list[Assessment], run_meta: dict) -> str` |
| `tests/__init__.py` | create | 0 | Package marker |
| `tests/conftest.py` | create | ~20 | `autouse` fixture for `ProviderRegistry.initialize_defaults()` |
| `tests/test_smoke.py` | create | ~120 | 8 tests |
| `docs/contracts/CONTRACT_S4_md_and_tests.md` | create | self | This file |

### Files to modify

| File | Action | Lines (Δ) | Why |
|------|--------|-----------|-----|
| `app/main.py` | modify | +25 | Add `--format {md,json}` (default `md`); auto-save to `./out/run_<TS>.md` when no `--output` |
| `pyproject.toml` | modify | +5 | Add `[tool.pytest.ini_options]` |
| `.gitignore` | modify | +1 | Add `out/` |
| `README.md` | modify | +15 | Document `--format` flag + `pytest` |
| `docs/contracts/QUALITY_LOG.md` | modify | +1 | Add S4 row |

---

## Output Criteria

### Markdown formatter
| # | Criterion | Weight | Tier |
|---|-----------|--------|------|
| 1 | `app/formatter.py` exposes `render(assessments: list[Assessment], meta: dict) -> str` | MUST | T2 |
| 2 | Rendered markdown contains the run metadata block (date, provider, target_date, counts) at top | MUST | T3 |
| 3 | Rendered markdown contains a "## Summary" H2 with a table of (analyst, indicator, signal, strength) rows | MUST | T3 |
| 4 | Rendered markdown contains one H2 section per assessment | MUST | T3 |
| 5 | Each assessment section has H3 subsections for Diagnosis, Outlook, Key drivers, News interpretation, Reasoning trace | MUST | T3 |
| 6 | Key drivers list rendered as `-` markdown bullets | MUST | T3 |
| 7 | No raw `repr()` or `"None"` placeholders — empty fields render as `_empty_` placeholder | SHOULD | T3 |

### CLI integration
| # | Criterion | Weight | Tier |
|---|-----------|--------|------|
| 8 | `app/main.py` accepts `--format {md,json}` flag, default `md` | MUST | T2 |
| 9 | When `--format md` and no `--output`, file is auto-created at `./out/run_<YYYYMMDD_HHMMSS>.md` | MUST | T3 |
| 10 | When `--output PATH` is given, output goes there regardless of format | SHOULD | T3 |
| 11 | When `--format json` (no `--output`), JSON prints to stdout (existing behavior preserved) | SHOULD | T3 |

### Tests
| # | Criterion | Weight | Tier |
|---|-----------|--------|------|
| 12 | `tests/test_smoke.py` defines 8 `test_*` functions | MUST | T2 |
| 13 | `tests/conftest.py` registers providers via autouse fixture | MUST | T2 |
| 14 | `pytest tests/` exits 0 with all 8 tests passing | MUST | T3 |
| 15 | Test 8 (`test_cli_end_to_end_with_mock`) uses `subprocess.run([sys.executable, "-m", "app.main", ...])` and asserts exit 0 + output file exists | MUST | T3 |
| 16 | Tests cover: catalog length, ALL_AGENTS length, unique IDs, Pydantic round-trip, mock LLM end-to-end, runner count, formatter sections, CLI end-to-end | MUST | T2 |
| 17 | Test runner uses tmp_path (pytest fixture) for output file; cleans up automatically | SHOULD | T3 |
| 18 | `ruff check app/ tests/` exits 0 | MUST | T3 |

---

## Outcome Criteria

| # | Criterion | Weight | Result |
|---|-----------|--------|--------|
| 1 | A second operator can run `python -m app.main --provider mock --analysts buffett --output /tmp/test.md && head -20 /tmp/test.md` and see markdown content with the persona's name | SHOULD | T3 |
| 2 | `pytest tests/ -v` runs all 8 tests in <2 seconds total | SHOULD | T3 |

---

## Validation Commands

### Tier 2 — Imports

```bash
python3 -c "from app.formatter import render"
python3 -c "from app.main import main"
```

### Tier 3 — Behavioral

```bash
# Formatter
python3 <<'PY'
from datetime import date
from app.models import Assessment
from app.formatter import render
a = Assessment(
    agent_id="buffett", indicator_id="US.FFR", target_date=date(2025, 3, 31),
    provider="minimax", diagnosis="Test diagnosis.", outlook="Test outlook.",
    key_drivers=["a", "b", "c"], news_interpretation="Test news.",
    reasoning_trace="Test reasoning.", signal_direction="BULLISH", signal_strength=0.42,
)
md = render([a], meta={"analysts": ["buffett"], "indicators": ["US.FFR"], "provider": "minimax", "target_date": "2025-03-31", "completed_at": "2026-07-01"})
assert "# Macro Assessment Run" in md
assert "## Summary" in md
assert "| Analyst | Indicator | Signal | Strength |" in md
assert "### Diagnosis" in md
assert "### Outlook" in md
assert "### Key drivers" in md
assert "### News interpretation" in md
assert "### Reasoning trace" in md
assert "- a" in md and "- b" in md and "- c" in md
print("formatter OK; md length:", len(md))
PY

# CLI: --format md auto-save
cd /Users/pauloribeiro/Desktop/Projetos/financial-adviser/ && \
  rm -rf out/ && \
  MFL_ENV=development python3 -m app.main --analysts buffett --indicators US.FFR --provider mock --format md >/tmp/stdout.txt 2>/tmp/stderr.txt && \
  ls out/ && \
  test -f out/run_*.md && echo "file exists" || echo "MISSING"

# CLI: --format json stdout
cd /Users/pauloribeiro/Desktop/Projetos/financial-adviser/ && \
  MFL_ENV=development python3 -m app.main --analysts buffett --indicators US.FFR --provider mock --format json 2>/dev/null | python3 -c "import json, sys; d=json.loads(sys.stdin.read()); assert len(d['assessments'])==1; print('json OK')"

# CLI: --output custom path
cd /Users/pauloribeiro/Desktop/Projetos/financial-adviser/ && \
  rm -f /tmp/custom.md && \
  python3 -m app.main --analysts buffett --indicators US.FFR --provider mock --format md --output /tmp/custom.md 2>/dev/null && \
  test -f /tmp/custom.md && echo "custom path OK"

# Pytest
cd /Users/pauloribeiro/Desktop/Projetos/financial-adviser/ && pytest tests/ -v --tb=short

# Ruff
cd /Users/pauloribeiro/Desktop/Projetos/financial-adviser/ && ruff check app/ tests/
```

---

## Files to Change

| File | Action | LOC est. | Why |
|------|--------|----------|-----|
| `app/formatter.py` | create | 80 | Render assessment list as MD |
| `app/main.py` | modify | +25 | `--format` flag, auto-save logic |
| `tests/__init__.py` | create | 0 | Package marker |
| `tests/conftest.py` | create | 20 | `initialize_defaults` autouse |
| `tests/test_smoke.py` | create | 120 | 8 tests |
| `pyproject.toml` | modify | +5 | `[tool.pytest.ini_options]` |
| `.gitignore` | modify | +1 | `out/` |
| `README.md` | modify | +15 | Document `--format`, `pytest` |
| `docs/contracts/CONTRACT_S4_md_and_tests.md` | create | self | This file |
| `docs/contracts/QUALITY_LOG.md` | modify | +1 | S4 row |

Total ~265 LOC. No changes outside this contract.

---

## Risks

| Risk | Mitigation |
|---|---|
| `out/` cache conflicts across runs | Timestamp-based filename: `run_<YYYYMMDD_HHMMSS>.md` |
| `subprocess.run([sys.executable, "-m", "app.main", ...])` requires Python path on test runner | Use `sys.executable` (not `python3`) to guarantee same interpreter |
| Formatter test brittleness | Tests verify **sections present**, not exact text |
| `--format md` by default might break existing JSON-only consumers | Document in README as a behaviour change since S1 |
| `pytest` not yet installed | S1 contract declared it under `[project.optional-dependencies].dev = ["pytest>=8.0.0", ...]`. Use `pip install -e ".[dev]"` before S4 execution |

Rollback: `git revert <S4 commit>`.

---

## Correction Loop

- Max 3 cycles per failing criterion
- After 3 failures: STOP and ask user

---

## Sign-off

- [ ] User approved
- [ ] Executor implemented
- [ ] Validator verified
- [ ] Quality Log updated
- [ ] Committed
