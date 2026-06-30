# AGENTS.md — financial-adviser

Multi-persona macroeconomic assessment pipeline built on LangChain + Langfuse.
**No DB, no UI, no orchestration framework.** Just prompts → LLM → JSON.

## What's in this repo

```
financial-adviser/
├── app/
│   ├── agents.py        # BaseAgent + 15 persona classes + ALL_AGENTS + T0/T1/T2 loader
│   ├── runner.py        # parallel (analyst × indicator) runner, returns list[Assessment]
│   ├── main.py          # CLI entry: python -m app.main --analysts ... --provider ...
│   ├── catalog.py       # 8 US indicators (slim)
│   ├── models.py        # Pydantic schemas (Indicator, Assessment, AgentProfile)
│   ├── providers.py     # LLMProvider + MiniMaxProvider + MockProvider + ProviderRegistry
│   ├── logging.py       # structlog wrapper (setup_logging, get_logger)
│   └── prompts/         # 15 persona dirs of .md content (PERSONA.md, references/, indicators/)
├── pyproject.toml
├── README.md
├── AGENTS.md            # ← this file
├── .env.example
├── .gitignore
├── data/.gitkeep        # placeholder (no DB writes)
└── docs/
```

## Hard Rules

1. **No DB.** Assessments are returned in memory. Do not introduce DuckDB/SQLite/JSON file persistence. If you need to share results between calls, pass the list around.
2. **No UI.** Do not add FastAPI/Jinja2/templates. The CLI (`app/main.py`) is the only entry point.
3. **No tool-calling.** Do not add `app/tools/` or LangChain `bind_tools`. Agents use `with_structured_output(Assessment)` directly.
4. **No comments in code** unless explicitly asked.
5. **All assessments follow `Assessment` schema** in `app/models.py`. Pydantic enforces `0.0 ≤ signal_strength ≤ 1.0`; the parser validates via `with_structured_output` (with JSON fallback).
6. **All indicators go through `app/catalog.py`** — no hardcoded FRED series in agent prompts.
7. **All logging** via `app.logging.get_logger`. Event names dot-namespaced (`runner.start`, `agent.initialized`, etc.).
8. **Langfuse tracing is optional.** If `LANGFUSE_PUBLIC_KEY` is set in env, the agent attaches a `CallbackHandler`. Without it, the runner runs fine without tracing.
9. **Ruff** for lint. Line length 100. Run `ruff check app/` before committing.

## Code Style

- Python 3.11+, type hints on public APIs
- `from app.X import Y` for internal imports
- Snake_case modules, PascalCase classes
- Pydantic v2 for all schemas
- LangChain messages use the `[{"role": ..., "content": ...}]` dict format (not `SystemMessage`/`HumanMessage` objects) — simpler and Just Works for both Anthropic and mock.

## Persona Contract

Every persona MUST:

1. Behave consistently with its worldview on every call.
2. Submit a complete `Assessment` (see `app/models.py`).
3. Be discoverable in `ALL_AGENTS` (built automatically by the factory in `app/agents.py`).
4. Ship the full directory structure under `app/prompts/<persona_id>/`:
   - `PERSONA.md` (T0 — always loaded)
   - `references/{framework,playbook,assessment,guardrails,voice,history}.md` (T1 — always loaded)
   - `indicators/_index.md` (T1 — engagement matrix)
   - `indicators/<indicator_id>.md` (T2 — loaded into user prompt for `primary` indicators)

## Adding a New Persona

1. Create `app/prompts/<persona_id>/{PERSONA.md, references/*.md, indicators/_index.md, indicators/*.md}`. Mirror the depth of an existing persona.
2. Add a hint to the `_HINTS` dict in `app/agents.py` (3 fields: `related`, `remember`).
3. Add an entry to `_PERSONA_DEFS` in `app/agents.py` (4 fields: `id`, `name`, `school`, `description`).
4. `ruff check app/` should pass.
5. `python -m app.main --analysts <id> --provider mock` should print a valid JSON with one or more assessments.

## Adding a New Indicator

1. Add to `CATALOG_US` in `app/catalog.py` with required fields.
2. Optionally add a T2 deep note per persona in `app/prompts/<persona>/indicators/<indicator_id>.md`.
3. No DB migration needed (no DB).

## Switching Providers

```bash
export MINIMAX_API_KEY=sk-...
export ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic  # default
python -m app.main --analysts buffett,burry --provider minimax
```

Or for tests / offline:

```bash
python -m app.main --analysts buffett --provider mock
```

The `MockProvider` returns a `MockModel` whose `invoke()` returns a `SimpleNamespace` with placeholder fields — useful for unit tests and CI without network.

## Running

```bash
# install
pip install -e .

# minimal smoke (no API key)
python -m app.main --analysts buffett --indicators US.FFR --provider mock

# real run
export MINIMAX_API_KEY=sk-...
python -m app.main --analysts buffett,burry,dimon --provider minimax

# all 15 personas × all 8 indicators (parallel)
python -m app.main --analysts $(python -c "print(','.join(__import__('app.agents', fromlist=['ALL_AGENTS']).ALL_AGENTS.keys()))") --provider mock
```

## Logging

```python
from app.logging import get_logger
log = get_logger(__name__)
log.info("event.name", key=value)
```

Event names:
- `runner.start`, `runner.assessment_done`, `runner.complete`
- `agent.initialized`, `agent.structured_failed_falling_back`
- `provider.registered`
- `agent.langfuse_unavailable`
