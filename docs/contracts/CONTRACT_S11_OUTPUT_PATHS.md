# CONTRACT — S11: Organized output directories

**Date:** 2026-07-03
**Status:** APPROVED → IMPLEMENTING
**Sprint:** S11 (single sprint)

## Scope

Replace the current flat `out/debate_<TS>/` and `out/run_<TS>/` layout with a hierarchical, navigable, self-describing structure:

```
out/
├── company/
│   └── <sector-slug>/
│       └── <TICKER>/
│           ├── <TS>_<provider>_meta.json
│           ├── <TS>_<provider>_debate.md
│           ├── <TS>_<provider>_summary.md
│           ├── <TS>_<provider>_rich.txt
│           ├── <TS>_<provider>_assessment.md
│           ├── <TS>_<provider>_data.json
│           └── per_agent/
│               ├── <persona>.md
│               └── ...
├── macro/
│   └── <INDICATOR>/
│       └── (same files as above)
```

### Decisões locked
- Slugs: kebab-case lowercase (e.g. `financial-services`, `consumer-cyclical`, `us-ffr`)
- No migration of old outputs
- Multi-target = one run per ticker
- `--output PATH` bypasses new structure
- All run files share prefix `<ISO-timestamp>_<provider>`

### Slug helper
```python
def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
```

### Path helpers (app/formatter.py)
- `output_path(domain, group, target, run_ts, provider, ext) -> Path`
- `run_dir(domain, group, target) -> Path` (shared by all runs of this target)
- `per_agent_dir(domain, group, target) -> Path`
- Keep `default_output_path()` and `default_run_dir()` returning old paths (back-compat)

### Filename convention
- Timestamp: `datetime.now().strftime("%Y-%m-%dT%H-%M-%S_%f")[:-3]` (ISO, file-safe)
- Example: `2026-07-03T14-23-45_123_minimax_debate.md`

### Output Criteria
| # | Criterion | Weight |
|---|-----------|--------|
| 1 | `output_path()` produces correct paths | MUST |
| 2 | `--company JPM` → `out/company/financial-services/JPM/<TS>_minimax_debate.md` | MUST |
| 3 | `--indicators US.FFR` → `out/macro/us-ffr/<TS>_<provider>_debate.md` | MUST |
| 4 | Multi-target = separate per-ticker dirs | MUST |
| 5 | `--output PATH` bypasses new structure | MUST |
| 6 | `per-agent` → `per_agent/<persona>.md` | MUST |
| 7 | `json` → `<TS>_<provider>_data.json` | MUST |
| 8 | `rich` → `<TS>_<provider>_rich.txt` | MUST |
| 9 | Sector from yfinance, fallback `unknown-sector` | MUST |
| 10 | Old outputs untouched | MUST |
| 11 | meta.json includes run_id, analysts, provider, target, target_date, domain, sector/indicator, rounds | MUST |

### Outcome
- 158 prior + ≥10 new tests green
- ruff clean
- 4 CLI scenarios write to expected paths

### Files
- `app/formatter.py` (modify)
- `app/main.py` (modify)
- `tests/test_output_paths.py` (create)

### Scope discipline
- Touch ONLY: `app/formatter.py`, `app/main.py`, `tests/test_output_paths.py`
- Do NOT touch: `app/debate/*`, `app/models.py`, `app/agents.py`, `app/providers.py`, `app/cli_menu.py`, `app/runner.py`, `app/prompts/*`, `app/pipeline/*`, existing tests
- Do NOT delete/modify `out/debate_<TS>/` or `out/run_<TS>/`

### Conventions
- `from __future__ import annotations`, structlog, no comments, snake_case
- `mkdir(parents=True, exist_ok=True)` on every directory creation
- `meta.json` with `indent=2, default=str`
- All paths via the new helpers