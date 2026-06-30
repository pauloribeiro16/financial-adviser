# CONTRACT S5 — Per-agent MD layout + indicators default single

**Date:** 2026-07-01
**Planner:** opencode
**Status:** DRAFT → APPROVED → IMPLEMENTING → VALIDATED
**Phase:** 5 of N
**Depends On:** S4 (MD formatter + CLI flag + tests)
**Parent Goal:** Output `.md` files split per (persona, indicator) into separate directories.

---

## Trials

`trials: 3` — each criterion run 3 times.

---

## Scope

Three deliverables:

1. **Per-agent `.md` layout**: each run produces `out/run_<TS>/<persona>/<indicator>.md` instead of one big file.
2. **Default `--indicators` = 1**: when omitted, default to `["US.UST10Y"]` instead of all 8.
3. **`--format per-agent`**: new CLI format (default).

A `_summary.md` is also written at the run root.

---

## Files to modify

| File | Action | Δ LOC | Why |
|------|--------|-------|-----|
| `app/formatter.py` | modify | +80 | `render_per_agent(...)`, `render_summary(...)`, `default_run_dir()` |
| `app/main.py` | modify | +35 | Default `--indicators=["US.UST10Y"]`; `--format {md,json,per-agent}` default `per-agent`; write tree layout |
| `tests/test_smoke.py` | modify | +60 | +2 tests: per-agent layout, default-single-indicator |
| `.gitignore` | (unchanged) | 0 | `out/` already ignored |

---

## Output Criteria

### Per-agent formatter
| # | Criterion | Weight | Tier |
|---|-----------|--------|------|
| 1 | `app/formatter.py` exposes `render_per_agent(assessments, meta) -> dict[str, list[tuple[str, str]]]` returning `{persona_id: [(indicator_id, md_content), ...]}` | MUST | T3 |
| 2 | `render_per_agent` produces one `.md` string per (persona, indicator) pair, NOT concatenated per persona | MUST | T3 |
| 3 | Each per-(persona, indicator) markdown contains: header `# <Persona Name> on <Indicator>`, metadata blockquote (timestamp, run id, target date, provider, signal direction + strength, persona id), H3 sections (Diagnosis, Outlook, Key drivers, News interpretation, Reasoning trace) | MUST | T3 |
| 4 | Empty fields render as `_empty_`, drivers as `-` bullets (consistent with S4) | SHOULD | T3 |
| 5 | `render_summary(assessments, meta) -> str` returns markdown with: H1 title, metadata block, summary table (persona × indicator), file index with relative links | MUST | T3 |
| 6 | `default_run_dir() -> str` returns `./out/run_<YYYYMMDD_HHMMSS>` | MUST | T3 |

### CLI
| # | Criterion | Weight | Tier |
|---|-----------|--------|------|
| 7 | `app/main.py` `--format` accepts `{md,json,per-agent}`, default `per-agent` | MUST | T2 |
| 8 | `app/main.py` `--indicators` default becomes `["US.UST10Y"]` (was: all 8 from catalog) | MUST | T3 |
| 9 | When `--format per-agent` and no `--output`, output goes to `./out/run_<YYYYMMDD_HHMMSS>/` with `_summary.md` and `<persona>/<indicator>.md` files | MUST | T3 |
| 10 | When `--format per-agent --output DIR`, output goes to `DIR` (DIR replaces the timestamp dir) | MUST | T3 |
| 11 | When `--format md` (legacy), old single-file behavior is preserved | MUST | T3 |
| 12 | When `--format json`, JSON goes to stdout (or `--output` file) — unchanged | SHOULD | T3 |
| 13 | When `--indicators ""` (empty), CLI prints error and exits 1 (no empty-list silent fallback) | MUST | T3 |

### Tests
| # | Criterion | Weight | Tier |
|---|-----------|--------|------|
| 14 | `tests/test_smoke.py` adds 2 new test functions: `test_per_agent_layout` and `test_default_single_indicator` | MUST | T2 |
| 15 | `pytest tests/` exits 0; total = 13 tests passing | MUST | T3 |
| 16 | New test `test_per_agent_layout` invokes `runner.run(...)`, calls `formatter.render_per_agent(...)` + `render_summary(...)`, writes them, asserts the directory tree exists | MUST | T3 |
| 17 | New test `test_default_single_indicator` invokes `python -m app.main` without `--indicators` and verifies output contains exactly 1 assessment | MUST | T3 |
| 18 | `ruff check app/ tests/` exits 0 | MUST | T3 |

---

## Outcome Criteria

| # | Criterion | Weight | Result |
|---|-----------|--------|--------|
| 1 | A second operator runs `python -m app.main --analysts buffett,burry --indicators US.FFR,US.UST10Y --provider mock` and gets `out/run_<TS>/_summary.md` + `out/run_<TS>/buffett/US.FFR.md` + 3 more files | SHOULD | T3 |
| 2 | Operator runs `python -m app.main --analysts buffett --provider mock` (no indicators) and gets just `out/run_<TS>/_summary.md` + `out/run_<TS>/buffett/US.UST10Y.md` | SHOULD | T3 |

---

## Validation Commands

### Tier 2 — Imports
```bash
python3 -c "from app.formatter import render_per_agent, render_summary, default_run_dir; print('formatter OK')"
```

### Tier 3 — Behavioral

```bash
# render_per_agent output
python3 <<'PY'
from datetime import date
from app.models import Assessment
from app.formatter import render_per_agent, render_summary, default_run_dir
a1 = Assessment(agent_id="buffett", indicator_id="US.FFR", target_date=date(2025,3,31),
                provider="minimax", diagnosis="d1", outlook="o1",
                key_drivers=["x","y"], news_interpretation="n1", reasoning_trace="r1",
                signal_direction="BULLISH", signal_strength=0.42)
a2 = Assessment(agent_id="buffett", indicator_id="US.UST10Y", target_date=date(2025,3,31),
                provider="minimax", diagnosis="d2", outlook="o2",
                key_drivers=["x"], news_interpretation="", reasoning_trace="",
                signal_direction="BEARISH", signal_strength=0.7)
a3 = Assessment(agent_id="taleb", indicator_id="US.FFR", target_date=date(2025,3,31),
                provider="minimax", diagnosis="d3", outlook="o3",
                key_drivers=["a","b","c"], news_interpretation="n3", reasoning_trace="r3",
                signal_direction="NEUTRAL", signal_strength=0.55)
d = render_per_agent([a1,a2,a3], meta={"target_date":"2025-03-31","provider":"minimax","analysts":["buffett","taleb"],"indicators":["US.FFR","US.UST10Y"]})
assert set(d.keys()) == {"buffett", "taleb"}, d.keys()
assert len(d["buffett"]) == 2  # buffett has US.FFR + US.UST10Y
assert len(d["taleb"]) == 1    # taleb only has US.FFR
md = d["buffett"][0][1]  # (US.FFR, md)
assert "# Warren E. Buffett on US.FFR" in md, md[:200]
assert "### Diagnosis" in md
assert "### Outlook" in md
assert "### Key drivers" in md
assert "### News interpretation" in md
assert "### Reasoning trace" in md
assert "BULLISH" in md and "0.42" in md
summary = render_summary([a1,a2,a3], meta={"target_date":"2025-03-31","provider":"minimax","analysts":["buffett","taleb"],"indicators":["US.FFR","US.UST10Y"], "completed_at": "2026-07-01"})
assert "# Run summary" in summary
assert "| Persona |" in summary
assert "buffett/US.FFR.md" in summary  # index link
print("per-agent layout OK; default_run_dir():", default_run_dir())
PY

# CLI per-agent layout
cd /Users/pauloribeiro/Desktop/Projetos/financial-adviser/
rm -rf out/
python3 -m app.main --analysts buffett,burry --indicators US.FFR --provider mock --format per-agent >/tmp/stdout.txt 2>/tmp/stderr.txt
echo "exit=$?"
ls -la out/
find out -type f | sort

# CLI: empty --indicators
cd /Users/pauloribeiro/Desktop/Projetos/financial-adviser/
python3 -m app.main --analysts buffett --indicators "" --provider mock 2>&1 | tail -3
echo "exit=$?"

# CLI: --format md legacy still works
cd /Users/pauloribeiro/Desktop/Projetos/financial-adviser/
rm -f /tmp/legacy.md
python3 -m app.main --analysts buffett --indicators US.FFR --provider mock --format md --output /tmp/legacy.md >/dev/null 2>&1
echo "legacy md exit=$?"
test -f /tmp/legacy.md && head -3 /tmp/legacy.md

# CLI: default (no --indicators) → only US.UST10Y
cd /Users/pauloribeiro/Desktop/Projetos/financial-adviser/
rm -rf out/
python3 -m app.main --analysts buffett --provider mock >/tmp/dflt.txt 2>/tmp/dflt.err
echo "default exit=$?"
ls out/run_*/buffett/

# Pytest
cd /Users/pauloribeiro/Desktop/Projetos/financial-adviser/ && pytest tests/ -v --tb=short

# Ruff
cd /Users/pauloribeiro/Desktop/Projetos/financial-adviser/ && ruff check app/ tests/
```

---

## Files to Change

| File | Action | LOC est. | Why |
|------|--------|----------|-----|
| `app/formatter.py` | modify | +80 | render_per_agent, render_summary, default_run_dir |
| `app/main.py` | modify | +35 | indicators default US.UST10Y; format flag; tree layout writer |
| `tests/test_smoke.py` | modify | +60 | 2 new tests |
| `docs/contracts/CONTRACT_S5_per_agent_layout.md` | create | self | this file |
| `docs/contracts/QUALITY_LOG.md` | modify | +1 | S5 row |

Total ~175 LOC. No changes outside this contract.

---

## Risks

| Risk | Mitigation |
|---|---|
| Two runs in same second share directory name | Use microsecond precision in timestamp: `run_YYYYMMDD_HHMMSS_<µs>` |
| Existing tests rely on `out/run_*.md` being a file (S4) | S4 test passes `--output` explicitly so doesn't care about default dir |
| Persona IDs with non-ASCII or weird chars | Persona IDs are ASCII (`buffett`, `taleb`, etc.). Safe to use as path segments |
| Nested directory creation failure (e.g. readonly disk) | Use `Path.mkdir(parents=True, exist_ok=True)` and let exception bubble up with clear message |

---

## Correction Loop

- Max 3 cycles per failing criterion
- After 3 failures: STOP and ask user

---

## Sign-off

- [ ] User approved (done at contract-creation time)
- [ ] Executor implemented
- [ ] Validator verified
- [ ] Quality Log updated
- [ ] Committed
