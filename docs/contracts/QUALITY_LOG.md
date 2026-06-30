# Quality Log — financial-adviser

Format: `Sprint | Date | Criteria Pass | Avg @k | Verdict | Notes`

| Sprint | Date       | Output (P/F/T) | Outcome (P/F/T) | pass@k avg | Verdict | Notes |
|--------|------------|----------------|-----------------|------------|---------|-------|
| S1     | 2026-07-01 | 13/13          | 2/2 (1 skipped) | 3/3        | PASS    | Bootstrap. 6 files + git init. Validator flagged `data/` parent-exclude quirk; fixed in-place. |
| S2     | 2026-07-01 | 16/16          | 2/2             | 3/3        | PASS    | Core layer. ~370 LOC. Contract typo `Category.RATES`→`MONETARY` fixed. Ruff clean. |
| S3a    | 2026-07-01 | (rollback)     | —               | —          | VOID    | Lifted DuckDBStore (486 LOC) + LangfuseHandler (71 LOC) verbatim. **Rolled back** on user pivot: no DuckDB, "remodelação, menos código". Files deleted from repo. |
| MVP    | 2026-07-01 | —              | —               | —          | PASS    | **MVP simplification**: 7 Python files, 781 LOC total. agent.py = 319 LOC (single file: BaseAgent + 15 personas + T0/T1/T2 loader + JSON fallback). runner.py = 85 LOC (ThreadPoolExecutor). main.py = 76 LOC (CLI). Flattened dir (no `core/`, `models/`, `services/`). Persona .md content lifted (259 files, 6886 LOC). `with_structured_output(Assessment)` + Langfuse-optional. End-to-end CLI smoke passed with `--provider mock`. |
| S4     | 2026-07-01 | 18/18          | 2/2             | 3/3        | PASS    | Markdown formatter (`app/formatter.py`, ~145 LOC) + CLI `--format {md,json}` (default `md` → `./out/run_<TS>.md`) + pytest smoke suite (8 tests). Total new/modified ~265 LOC. Ruff clean. |
| S5     | 2026-07-01 | 18/18          | 2/2             | 3/3        | PASS    | Per-agent `.md` layout (`render_per_agent` + `render_summary` + `default_run_dir`) + `--format per-agent` default + `--indicators` default = `US.UST10Y` + empty-indicators guard (exit 1) + 2 new tests (13 total). Ruff clean. run_id aligns with default_run_dir() for link consistency. |

## Pivots / Architecture Changes

### 2026-07-01 — MVP Simplification Pivot

User requested:
- No DuckDB
- Not a replica — remodeling
- Simpler, less code, better organized

**Decision**: drop S3a and S3b. Reset to a minimal architecture focused on the
core demo loop: 1 LLM call per (persona, indicator), in-memory only, no
persistence, no orchestration complexity.

### Final MVP Architecture (after pivot)

```
app/
├── __init__.py
├── core/
│   ├── __init__.py
│   └── logging.py                # structlog (24 LOC, kept from S2)
├── models/
│   ├── __init__.py
│   └── schemas.py                # Pydantic schemas (113 LOC, kept from S2)
├── services/
│   ├── __init__.py
│   ├── catalog.py                # 8 US indicators (126 LOC, kept from S2)
│   └── providers.py              # MiniMax + Mock + Registry (87 LOC, kept from S2)
└── agents/                       # TBD: 1 file or multi-file?
```

`data/` gitignored with `.gitkeep` for path preservation.

### Open Architectural Decisions (post-pivot, MVP sprint)

To be decided before next contract:
- Single `app/agents.py` (one file, ~500 LOC) vs `app/agents/{base,prompts,loader}.py`
  (multi-file). User leaning toward fewer files ("less code").
- Whether to flatten `app/{core,models,services}` into `app/{logging,models,catalog,providers}.py`
  (truly flat) or keep current nesting.
- Whether to lift 15 personas' `.md` content as-is or trim/regenerate.

---

## MVP Sprint (2026-07-01) — Simplification Pivot

### Final architecture (decided and implemented)

```
app/
├── __init__.py
├── logging.py        # structlog (24 LOC, lifted from S2)
├── models.py         # Pydantic schemas (66 LOC, slim — dropped Observation/AssessmentOutput/RunRequest/EventItem/GlobalContext)
├── catalog.py        # 8 US indicators (110 LOC, dropped lag_days/is_target)
├── providers.py      # MiniMaxProvider + MockProvider + MockModel + ProviderRegistry (101 LOC)
├── agents.py         # BaseAgent + 15 personas + T0/T1/T2 loader + JSON fallback (319 LOC)
├── runner.py         # Parallel runner (85 LOC)
└── main.py           # CLI entry (76 LOC)

app/prompts/<15 dirs>/   # PERSONA.md + references/*.md + indicators/*.md (lifted from source, 259 files, 6886 LOC)
```

Total Python: **781 LOC**. Compare to original source's `app/agents/base_agent.py` alone = 744 LOC.

### Decisions
1. **Flatten**: `app/{core,models,services}` → `app/{logging,models,catalog,providers}.py`. Single-level directory structure.
2. **Single agent file**: `app/agents.py` holds BaseAgent + 15 persona classes + loader + hint table.
3. **Lift .md content verbatim**: 259 persona .md files moved from source to `app/prompts/`.
4. **MockProvider is real**: replaced source's MagicMock-based mock with a `MockModel` class that returns a `SimpleNamespace` matching Assessment's fields. Pydantic accepts it.
5. **Langfuse via env**: if `LANGFUSE_PUBLIC_KEY` is set, attach `CallbackHandler`. Otherwise no-op (graceful).
6. **JSON fallback**: `with_structured_output(Assessment)` is the primary path. If it raises, `BaseAgent.generate_assessment` falls back to plain `model.invoke()` + JSON-parse (regex extract if needed).

### Validation
- `ruff check app/` → clean
- `python -m app.main --analysts buffett,burry,dimon --indicators US.FFR,US.UST10Y,US.VIX --provider mock` → 9 valid Assessment objects in JSON output
- All 15 persona classes constructed cleanly via factory
- T0/T1 prompt assembly works (system prompts 19K-26K chars per persona)
- T2 deep notes load from disk when present (Bernanke's US.FFR note → 2.3K chars user prompt)

### What was deleted (vs S3a direction)
- `app/services/store.py` (486 LOC, DuckDBStore — deleted)
- `app/services/langfuse_tracer.py` (71 LOC, singleton — folded into `providers.py`)
- `app/services/context_builder.py`, `derived_signals.py`, `indicator_brief.py`, `news_agent.py` (lifted but never validated; deleted before MVP)
- `tests/architecture/`, `tests/integrity/` (drift gate for original architecture — irrelevant to MVP)
- Sprint contracts `S3a_*` and `S3b_*` (deleted; the work they described was rolled back)

---

## Sprint S1 Details

### Executor
- Subagent: `general`
- Created: `pyproject.toml` (48 lines), `.env.example` (13), `.gitignore` (30), `README.md` (70), `AGENTS.md` (110), `data/.gitkeep`
- `git init` local, no first commit (per user instruction)
- One self-reported off-by-case fix in `AGENTS.md` ("**No comments**" → "**no comments**") to match contract T3.5 grep

### Validator
- 13/13 Output Criteria PASS; O1 skipped (pip install destructive)
- Flagged `.gitignore` parent-directory exclude quirk → fix applied (`data/` → `data/*`, `!data/` re-include)

---

## Sprint S2 Details

### Executor
- 8 files (~370 LOC): logging (24, lifted verbatim), schemas (113, lifted + 2 enum additions), providers (87, lifted + MockProvider), catalog (126, slim 8 IDs)
- Catalog typo on C6 (`Category.RATES` → `Category.MONETARY`) self-resolved by using authoritative spec value

### Validator
- 18/18 criteria verified independently
- Lifted files byte-identical via `diff`
- Catalog IDs match exactly: 8 IDs in expected order
- ProviderRegistry initializes both `minimax` and `mock`
- Ruff clean

---

## Sprint S3a Details — ROLLED BACK

### What happened
- Executor correctly lifted 2 files verbatim (557 LOC combined, byte-identical to source via `diff`)
- Correctly refused to add methods that weren't in source
- Validator confirmed byte-identity and real-API behavior

### Why rolled back
- User pivoted: no DuckDB, simpler architecture, less code
- `store.py` + `langfuse_tracer.py` deleted from repo
- S3a/S3b contracts deleted
- Score voided — does NOT count toward validation pipeline

### Lessons
- Spec-via-source API in future contracts. Never assume method names without grep.
- Faster path: prototype the minimal MVP first (a single 100-LOC BaseAgent that runs), THEN expand.
