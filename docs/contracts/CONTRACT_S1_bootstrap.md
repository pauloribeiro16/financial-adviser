# CONTRACT S1 — Bootstrap

**Date:** 2026-07-01
**Planner:** opencode
**Status:** DRAFT → APPROVED → IMPLEMENTING → VALIDATED
**Phase:** 1 of 6
**Parent Goal:** Extract the LangChain + Langfuse agent pipeline from
`/Users/pauloribeiro/Desktop/Projetos/macro-forecasting-league` into a new
standalone repo `financial-adviser` at
`/Users/pauloribeiro/Desktop/Projetos/financial-adviser`.

---

## Trials

`trials: 3` — each criterion is run 3 times. PASS = ≥2/3 green.

---

## Scope

Create the project skeleton: directory layout, tooling config,
environment template, gitignore, AGENTS.md (conventions), README skeleton.
No application code yet — that's S2.

This sprint is fully self-contained and produces a "compilable empty repo"
that can be opened by any tool and passes `ruff check`.

---

## Output Criteria (what was produced)

| # | Criterion | Weight | Tier |
|---|-----------|--------|------|
| 1 | Directory `/Users/pauloribeiro/Desktop/Projetos/financial-adviser/` exists and is writable | MUST | T3 |
| 2 | `pyproject.toml` is a valid TOML file with project name `financial-adviser`, Python `>=3.11`, and the trimmed agent-only deps (langchain, langchain-anthropic, langfuse, pydantic, structlog, numpy, pandas, duckdb, httpx, pyyaml, python-dotenv) — and NO infra deps (no fastapi, no uvicorn, no jinja2, no apscheduler, no typer, no fredapi, no yfinance) | MUST | T3 |
| 3 | `pyproject.toml` declares the three project scripts `seed-demo` and `run-assessment` as entry points (placeholder implementations acceptable in S1; real impl in S5) | SHOULD | T2 |
| 4 | `.env.example` contains exactly the required env vars documented in the plan: `MINIMAX_API_KEY`, `MINIMAX_MODEL`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`, `MI_DB_PATH`, `MFL_ENV` — each with a comment line above | MUST | T3 |
| 5 | `.gitignore` blocks at least: `.env`, `data/`, `__pycache__/`, `*.duckdb`, `*.pyc`, `.venv/`, `venv/`, `.ruff_cache/`, `.mypy_cache/`, `dist/`, `build/`, `*.egg-info/` | MUST | T3 |
| 6 | `README.md` exists at repo root with sections: Title, Description (≤200 chars), Quickstart (install + verify), Project layout tree, Status (links to contracts S1-S6), License placeholder | MUST | T3 |
| 7 | `AGENTS.md` exists at repo root with at minimum: Hard Rules (1: US-first scope), Logging convention (structlog via `app.core.logging.get_logger`), Code style (no comments unless asked, ruff), Catalog rule (all indicators via `app.services.catalog`), Schema rule (all assessments follow `AssessmentSchema` in `app/agents/base_agent.py`), 3-role contract reference | MUST | T3 |
| 8 | `data/.gitkeep` exists (the directory is gitignored but the path is preserved) | MUST | T2 |
| 9 | `git init` was run in the repo; `git status` reports `On branch master` (or default) with no errors | MUST | T3 |
| 10 | `ruff check .` exits 0 when run inside the repo | SHOULD | T3 |
| 11 | `python -c "import tomllib; tomllib.load(open('pyproject.toml','rb'))"` exits 0 | MUST | T3 |
| 12 | Repo contains zero application code yet — only the bootstrap files listed above (no `app/` directory content, no test files) | MUST | T2 |
| 13 | `docs/contracts/CONTRACT_S1_bootstrap.md` is committed as the first doc (proves the workflow is operating) | SHOULD | T2 |

---

## Outcome Criteria (system state after)

| # | Criterion | Weight | Result |
|---|-----------|--------|--------|
| 1 | A second operator can `cd financial-adviser && python -m venv .venv && source .venv/bin/activate && pip install -e .` without import errors from the package skeleton itself | SHOULD | T3 |
| 2 | `git log` shows one or zero commits (per user instruction: no automatic first commit) | MUST | T3 |
| 3 | The repo can be opened in any editor without "missing README" warnings (README + AGENTS.md present) | MUST | T3 |

---

## Validation Commands

### Tier 1 — Syntax (NICE only)

| What | Command | Expected |
|------|---------|----------|
| TOML parses | `python3 -c "import tomllib; tomllib.load(open('pyproject.toml','rb'))"` | exit 0 |

### Tier 2 — Import & Runtime

| What | Command | Expected |
|------|---------|----------|
| Repo layout present | `ls -la /Users/pauloribeiro/Desktop/Projetos/financial-adviser/` shows `docs/`, `data/`, `.env.example`, `.gitignore`, `pyproject.toml`, `README.md`, `AGENTS.md`, `.git/` | exit 0 |
| git initialized | `git -C /Users/pauloribeiro/Desktop/Projetos/financial-adviser/ status` exits 0 and prints branch name (not "not a git repository") | exit 0 |
| Ruff config (when present) lints empty repo | `cd /Users/pauloribeiro/Desktop/Projetos/financial-adviser/ && ruff check .` | exit 0 |
| data/.gitkeep present | `test -f /Users/pauloribeiro/Desktop/Projetos/financial-adviser/data/.gitkeep` | exit 0 |

### Tier 3 — Behavioral (MUST criteria)

| # | Criterion | Command | Expected |
|---|-----------|---------|----------|
| 1 | pyproject deps correct + no infra | `python3 -c "import tomllib; d=tomllib.load(open('pyproject.toml','rb')); deps=' '.join(d['project']['dependencies']); required=['langchain','langchain-anthropic','langfuse','pydantic','structlog','duckdb']; forbidden=['fastapi','uvicorn','jinja2','apscheduler','typer','fredapi','yfinance']; [print('MISSING',x) for x in required if x not in deps]; [print('FORBIDDEN',x) for x in forbidden if x in deps]; assert all(x in deps for x in required) and not any(x in deps for x in forbidden)"` | exit 0 |
| 2 | .env.example complete | `cd /Users/pauloribeiro/Desktop/Projetos/financial-adviser/ && for v in MINIMAX_API_KEY MINIMAX_MODEL LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY LANGFUSE_HOST MI_DB_PATH MFL_ENV; do grep -q "^$v=" .env.example || (echo "MISSING $v"; exit 1); done` | exit 0 |
| 3 | .gitignore blocks the right paths | `cd /Users/pauloribeiro/Desktop/Projetos/financial-adviser/ && for p in '^.env$' '^data/' '^__pycache__/' '\.duckdb$' '\.pyc$' '^\.venv/'; do grep -E "$p" .gitignore >/dev/null || (echo "MISSING $p"; exit 1); done` | exit 0 |
| 4 | README has required sections | `cd /Users/pauloribeiro/Desktop/Projetos/financial-adviser/ && for h in '# financial-adviser' '## Quickstart' '## Project layout' '## Status'; do grep -q "$h" README.md || (echo "MISSING $h"; exit 1); done` | exit 0 |
| 5 | AGENTS.md has hard rules | `cd /Users/pauloribeiro/Desktop/Projetos/financial-adviser/ && for h in '## Hard Rules' 'US-first' 'structlog' 'no comments' 'AssessmentSchema'; do grep -q "$h" AGENTS.md || (echo "MISSING $h"; exit 1); done` | exit 0 |
| 6 | git init worked | `git -C /Users/pauloribeiro/Desktop/Projetos/financial-adviser/ rev-parse --is-inside-work-tree` prints `true` | exit 0 |
| 7 | README+AGENTS present | `test -f /Users/pauloribeiro/Desktop/Projetos/financial-adviser/README.md && test -f /Users/pauloribeiro/Desktop/Projetos/financial-adviser/AGENTS.md` | exit 0 |

---

## Files to Change

| File | Action | Lines (est.) | Why |
|------|--------|-------------|-----|
| `/Users/pauloribeiro/Desktop/Projetos/financial-adviser/pyproject.toml` | create | ~40 | Project metadata + trimmed deps + scripts |
| `/Users/pauloribeiro/Desktop/Projetos/financial-adviser/.env.example` | create | ~15 | Template env file with all required vars |
| `/Users/pauloribeiro/Desktop/Projetos/financial-adviser/.gitignore` | create | ~30 | Block data/, .env, __pycache__, *.duckdb, etc. |
| `/Users/pauloribeiro/Desktop/Projetos/financial-adviser/README.md` | create | ~80 | Quickstart + layout + status |
| `/Users/pauloribeiro/Desktop/Projetos/financial-adviser/AGENTS.md` | create | ~120 | Conventions, hard rules |
| `/Users/pauloribeiro/Desktop/Projetos/financial-adviser/data/.gitkeep` | create | 0 | Placeholder so path exists in git |
| `/Users/pauloribeiro/Desktop/Projetos/financial-adviser/.git/` | via `git init` | n/a | Local git history |

**No application code in this sprint.** No `app/__init__.py`, no tests, no
ruff config file (the default ruff rules in 0.6+ are sufficient; if needed,
S2 will add `[tool.ruff]`).

---

## Risks

| Risk | Probability | Mitigation |
|------|-------------|------------|
| `python-dotenv` not needed in deps (no code uses it yet in S1) | low | Keep in deps; S2 will use it for `.env` loading |
| User disagrees with default ruff rules | low | S2 can add explicit `[tool.ruff]` config; not blocking for S1 |
| `git init` creates files outside the intended dir | very low | The bash command explicitly uses absolute path; verified with `ls` |
| Pyproject uses Python 3.11+; user's system Python may be older | low | Document Python 3.11+ requirement in README; user can use pyenv |

**Rollback:** `rm -rf /Users/pauloribeiro/Desktop/Projetos/financial-adviser/` (no commits yet).

---

## Correction Loop

- Max 3 cycles per failing criterion
- After 3 failures: STOP and ask user

---

## Sign-off

- [ ] User approved this contract
- [ ] Executor implemented
- [ ] Validator verified
- [ ] Quality Log updated

---

## Git Workflow

Per user instruction: **no automatic first commit in S1**. Git is initialized
but no `git add` / `git commit` runs. The user will decide when to commit.
Subsequent sprints (S2+) will commit per the standard contract pattern.

---

## Out of Scope (deferred to later sprints)

- Any `app/` directory contents → S2 (Core) + S3 (Services) + S4 (Agents)
- `scripts/` → S5
- `tests/` → S6
- Documentation beyond README + AGENTS → later (S3+ for ADR-derived docs)
