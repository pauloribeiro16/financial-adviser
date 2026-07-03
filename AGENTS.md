# AGENTS.md — financial-adviser

Multi-persona macroeconomic assessment pipeline.
**Two domains, one adversarial debate.** Just prompts → LLM → structured Pydantic.

The product evaluates a target through a panel of personas who each submit an
investment thesis, rebut each other for N rounds, and end with an optional
moderator synthesis. Domain `company` evaluates a ticker (SEC EDGAR + yfinance);
domain `macro` evaluates FRED indicators. Either way, the same debate engine runs
and the same Markdown / rich-table output is produced.

## What's in this repo

```
financial-adviser/
├── app/
│   ├── agents.py        # BaseAgent + 15 persona classes + ALL_AGENTS + T0/T1/T2 loader
│   ├── runner.py        # parallel (analyst × indicator) runner (legacy) + run_debate_only
│   ├── orchestrator/    # → app/debate/orchestrator.py (data ingest + engine + trace)
│   ├── main.py          # CLI entry: python -m app.main --company AAPL --analysts ...
│   ├── cli_menu.py      # questionary interactive picker (company | macro | analysts | rounds | format)
│   ├── catalog.py       # 8 US FRED indicators (slim)
│   ├── models.py        # Pydantic schemas (Assessment, DebateResult, Thesis, Rebuttal, Verdict, Domain)
│   ├── providers.py     # LLMProvider + MiniMaxProvider + MockProvider + ProviderRegistry
│   ├── logging.py       # structlog wrapper (setup_logging, get_logger)
│   ├── formatter.py     # render (MD), render_summary, render_per_agent, render_debate_rich
│   ├── debate/          # engine.py + orchestrator.py + tracing.py (Langfuse optional)
│   ├── pipeline/        # cache.py + context.py + edgar.py + market.py + macro.py
│   └── prompts/         # 15 persona dirs of .md content (PERSONA.md, references/, indicators/)
├── tests/               # smoke + debate + formatter + cli_debate + orchestrator (+ _mock_provider)
├── pyproject.toml
├── README.md            # ← user-facing quickstart
├── AGENTS.md            # ← this file
├── .env.example
├── .gitignore
├── data/cache/          # JSON file cache (no engine, TTL-configurable)
└── docs/
```

## Hard Rules

1. **DB-less — fetched data cached as JSON files under `data/cache/`** (TTL-configurable, no engine). Assessments / debate results are returned in memory. Do not introduce DuckDB/SQLite. To share results between calls, pass the list around.
2. **No UI.** Do not add FastAPI/Jinja2/templates. The CLI (`app/main.py`) is the only entry point; rich tables go to stdout (auto-detected by `sys.stdout.isatty()`).
3. **No LangChain tool-calling.** Data fetching happens via `app/pipeline/*` modules BEFORE the LLM call (orchestration, not agent tools). Agents still use `with_structured_output(Schema)` for typed answers.
4. **No comments in code** unless explicitly asked.
5. **All structured answers follow the schemas in `app/models.py`.** `Assessment` for legacy runs, `Thesis` + `Rebuttal` + `Verdict` for debate runs. Pydantic enforces `0.0 ≤ conviction ≤ 1.0`; parsers use `with_structured_output` (with JSON fallback).
6. **All indicators go through `app/catalog.py`** — no hardcoded FRED series in agent prompts. Company data goes through `app/pipeline/edgar.py` + `app/pipeline/market.py`.
7. **All logging** via `app.logging.get_logger`. Event names dot-namespaced (`runner.start`, `agent.initialized`, `debate.round_complete`, …).
8. **Langfuse tracing is optional for legacy agents.** When `LANGFUSE_PUBLIC_KEY` is set in env, an agent attaches a `CallbackHandler`.
9. **Debate traces** — `run_debate` (via `app/debate/orchestrator.py`) emits one root Langfuse trace per debate with `session_id` + nested spans per round (`data-ingest`, `round-N-theses`, `synthesis`). Without Langfuse env vars the trace becomes a no-op and the runner still works offline.
10. **Ruff** for lint. Line length 100. Run `ruff check app/ tests/` before committing.

## Code Style

- Python 3.11+, type hints on public APIs
- `from app.X import Y` for internal imports
- Snake_case modules, PascalCase classes
- Pydantic v2 for all schemas
- LangChain messages use the `[{"role": ..., "content": ...}]` dict format (not `SystemMessage`/`HumanMessage` objects) — simpler and Just Works for both Anthropic and mock.
- `rich.console.Console` for pretty-printer output (`render_debate_rich`); never mix rich markup with Markdown renderers.

## Domains & Default Personas

Two top-level domains share the same debate engine; the only thing that changes is how the data context is built:

| Domain   | Data pipeline module                          | CLI flag              | Default analysts (4)                | Target example |
|----------|-----------------------------------------------|-----------------------|-------------------------------------|----------------|
| `company`| `app/pipeline/context.build_company_context` | `--company AAPL`      | `buffett, lynch, burry, taleb`      | `AAPL`         |
| `macro`  | `app/pipeline/context.build_macro_context`    | `--indicators US.FFR` | `dalio, gundlach, volcker, greenspan`| `US.FFR`       |

All 15 personas in `ALL_AGENTS` are valid for either domain — the defaults are just sensible starting points.

## Persona Contract

Every persona MUST:

1. Behave consistently with its worldview on every call.
2. Submit a complete `Assessment` (legacy) or participate in the thesis/rebuttal/verdict loop (debate).
3. Be discoverable in `ALL_AGENTS` (built automatically by the factory in `app/agents.py`).
4. Ship the full directory structure under `app/prompts/<persona_id>/`:
   - `PERSONA.md` (T0 — always loaded)
   - `references/{framework,playbook,assessment,guardrails,voice,history}.md` (T1 — always loaded)
   - `indicators/_index.md` (T1 — engagement matrix)
   - `indicators/<indicator_id>.md` (T2 — loaded into user prompt for `primary` indicators)

## Debate Flow

1. `app.debate.orchestrator.orchestrate_debate` builds the data context (`pipeline.context`).
2. The orchestrator opens one root `DebateTrace` (`app/debate/tracing.py`) — no-op without `LANGFUSE_PUBLIC_KEY`.
3. Round 0 — every analyst submits a `Thesis` (parallel via `ThreadPoolExecutor`).
4. Round 1..N — every analyst submits a `Rebuttal` referencing the prior theses.
5. Optional — `engine._run_synthesis` produces a `Verdict` via a moderator call (or heuristic fallback if structured synthesis fails).
6. `_record_rounds` + `_record_synthesis` emit one Langfuse generation per persona per round + a top-level synthesis generation + 5 scores (bull/bear/neutral/consensus/confidence).
7. Output is rendered as Markdown (`formatter._render_debate_md`) or as a rich table (TTY only, via `formatter.render_debate_rich`).

## Adding a New Persona

1. Create `app/prompts/<persona_id>/{PERSONA.md, references/*.md, indicators/_index.md, indicators/*.md}`. Mirror the depth of an existing persona.
2. Add a hint to the `_HINTS` dict in `app/agents.py` (2 fields: `related`, `remember`).
3. Add an entry to `_PERSONA_DEFS` in `app/agents.py` (4 fields: `id`, `name`, `school`, `description`).
4. `ruff check app/ tests/` should pass.
5. `python -m app.main --analysts <id> --provider mock` should print a valid assessment (legacy) or `python -m app.main --company AAPL --analysts <id> --provider mock` should print a debate result.

## Adding a New Indicator

1. Add to `CATALOG_US` in `app/catalog.py` with required fields.
2. Optionally add a T2 deep note per persona in `app/prompts/<persona>/indicators/<indicator_id>.md`.
3. No migration needed (no DB).

## Switching Providers

```bash
export MINIMAX_API_KEY=sk-...
export ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic  # default
python -m app.main --company AAPL --analysts buffett,taleb --provider minimax
```

Or for tests / offline:

```bash
python -m app.main --company AAPL --analysts buffett --provider mock --rounds 1
python -m app.main --analysts buffett --provider mock          # legacy macro
```

The `MockProvider` returns a `MockModel` whose `invoke()` returns a `SimpleNamespace` with placeholder fields — useful for unit tests and CI without network. Debate runs use a `_SchemaAwareMockProvider` from `tests/_mock_provider.py` (installed automatically by the orchestrator) that knows about `Thesis`, `Rebuttal` and `Verdict` as well.

## Running

```bash
# install
pip install -e .

# interactive (questionary menus for domain / personas / rounds / format)
python -m app.main --interactive

# minimal smoke (no API key)
python -m app.main --analysts buffett --indicators US.FFR --provider mock

# company + 2 analysts, real debate
python -m app.main --company AAPL --analysts buffett,taleb --provider minimax --rounds 2

# rich output (auto-activates when stdout is a TTY and no --output is set)
python -m app.main --company AAPL --analysts buffett --provider mock --rich

# all 15 personas × all 8 indicators (parallel, legacy mode)
python -m app.main --analysts $(python -c "print(','.join(__import__('app.agents', fromlist=['ALL_AGENTS']).ALL_AGENTS.keys()))") --provider mock
```

## Logging

```python
from app.logging import get_logger
log = get_logger(__name__)
log.info("event.name", key=value)
```

Key event names:
- `runner.start`, `runner.assessment_done`, `runner.complete`
- `agent.initialized`, `agent.structured_failed_falling_back`, `agent.langfuse_unavailable`
- `provider.registered`
- `debate.start`, `debate.round_complete`, `debate.synthesis_complete`, `debate.complete`
- `pipeline.context.build_company`, `pipeline.context.build_macro`
- `pipeline.edgar.fetch_packet`, `pipeline.market.quote`, `pipeline.macro.fetch_observation`
