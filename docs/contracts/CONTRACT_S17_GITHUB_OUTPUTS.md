# CONTRACT — S17: GitHub-versioned outputs + format-as-default + per-agent extraction

**Date:** 2026-07-05
**Status:** APPROVED → IMPLEMENTING
**Sprint:** S17 (single sprint, 3 parts)

## Scope

Three parts:
- **A**: Remove `--format` flag from CLI; defaults to always writing 3 files (debate.md, data.json, summary.md) + per-agent/
- **B**: Per-agent extraction always generated (no flag)
- **C**: GitHub-versioned outputs (remove `out/` from .gitignore, add GitHub Action for daily batch commits)

Also includes the 10-K URL fix from earlier (1-line + 3 regression tests).

### Decisões locked
- Outputs versioned: everything except raw 10-K HTMLs
- Commits: GitHub Action in batch (daily cron + manual dispatch)
- Per-agent: always generated, no flag
- `--format`: removed entirely
- `--output PATH`: kept (bypass, for scripting)

### Files
- `app/main.py` (modify)
- `app/cli_menu.py` (modify)
- `.gitignore` (modify)
- `.github/workflows/version-outputs.yml` (create)
- `tests/test_s17_defaults.py` (create)
- `app/filings/fetcher.py` (modify — 10-K URL fix)
- `tests/test_filings_fetcher.py` (create — 10-K URL regression)

### Output Criteria
1. argparse has NO `--format` flag
2. cli_menu has no Format menu; FORMATS constant removed
3. Every debate writes: `*_debate.md`, `*_data.json`, `*_summary.md`, `*_meta.json`, `per_agent/<persona>.md`
4. per_agent/<persona>.md has the persona's full debate content (theses + rebuttals)
5. .gitignore does NOT ignore `out/` (except raw HTMLs)
6. .github/workflows/version-outputs.yml exists with daily cron + manual dispatch
7. GitHub Action commits `out/` changes with informative message
8. Initial commit adds out/ (except raw HTMLs)
9. --output PATH bypasses the structure
10. 342+ tests pass; ruff clean
11. 10-K fetcher URL fix works (regression test included)

### Scope discipline
Touch ONLY the 7 files above. Do NOT touch `app/debate/*`, `app/models.py`, `app/agents.py`, `app/providers.py`, `app/runner.py`, `app/prompts/*`, `app/pipeline/*` (except the 10-K fetcher.py), `app/filings/*` (except the 10-K fetcher.py), `app/watch/*`, or any existing test file (only ADD new test files).