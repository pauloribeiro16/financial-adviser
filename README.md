# financial-adviser

Multi-persona macroeconomic assessment pipeline built on **LangChain + Langfuse**.
Fifteen LLM analyst personas (Buffett, Lynch, Dalio, Burry, Greenspan, Bernanke,
Volcker, Dimon, Eisman, Grantham, Simons, Taleb, Wood, Gundlach, Thaler) interpret
8 US FRED indicators and produce quarterly assessments through their investment frameworks.

**No DB, no UI, no tool-calling.** Prompts in, JSON out.

## Quickstart

```bash
# 1. install
pip install -e .

# 2. (optional) copy .env from the source project, or set API key
cp /path/to/macro-forecasting-league/.env .env   # or:
cp .env.example .env && $EDITOR .env             # MINIMAX_API_KEY=sk-...

# 3. run a single persona against one indicator
python -m app.main --analysts buffett --indicators US.UST10Y --provider mock

# 4. run all 15 personas × all 8 indicators (real LLM)
python -m app.main --provider minimax --format json > run.json
```

The CLI auto-loads `./.env` via python-dotenv (when installed). To skip .env
loading (e.g. in tests), set `FA_SKIP_DOTENV=1` in the environment.
```

`--provider mock` runs offline with placeholder output — perfect for tests and CI.
`--provider minimax` calls the real Anthropic-compatible API.

### Output formats

`--format {md,json}` controls the output shape. Default is `md`.

| Format | Default path | With `--output PATH` |
|--------|--------------|----------------------|
| `md`   | `./out/run_<YYYYMMDD_HHMMSS>.md` | writes to `PATH` |
| `json` | stdout                          | writes to `PATH` |

```bash
# Markdown to default location (./out/run_<timestamp>.md)
python -m app.main --analysts buffett --indicators US.FFR --provider mock --format md

# Markdown to a specific path
python -m app.main --analysts buffett --indicators US.FFR --provider mock \
  --format md --output /tmp/buffett-ffr.md

# JSON to stdout (existing behaviour)
python -m app.main --analysts buffett --indicators US.FFR --provider mock --format json
```

### Running tests

```bash
pip install -e ".[dev]"
pytest tests/
```

The suite covers the catalog, persona registry, schema round-trip, mock-provider
end-to-end, runner fan-out, markdown formatter, and the CLI (`--format md`).

## What you get

```json
{
  "run": {
    "analysts": ["buffett", "burry"],
    "indicators": ["US.FFR", "US.UST10Y"],
    "provider": "minimax",
    "target_date": "2025-03-31"
  },
  "assessments": [
    {
      "agent_id": "buffett",
      "indicator_id": "US.FFR",
      "diagnosis": "...",
      "outlook": "...",
      "key_drivers": ["..."],
      "news_interpretation": "...",
      "reasoning_trace": "...",
      "signal_direction": "BULLISH",
      "signal_strength": 0.42,
      "provider": "minimax:MiniMax-M3",
      "target_date": "2025-03-31"
    }
  ]
}
```

## Project layout

```
financial-adviser/
├── app/
│   ├── agents.py        # BaseAgent + 15 personas + ALL_AGENTS + T0/T1/T2 loader
│   ├── runner.py        # parallel (analyst × indicator) runner
│   ├── main.py          # CLI entry
│   ├── catalog.py       # 8 US indicators
│   ├── models.py        # Pydantic schemas
│   ├── providers.py     # MiniMax + Mock + ProviderRegistry
│   ├── logging.py       # structlog wrapper
│   └── prompts/<15 dirs>/   # .md content for each persona
├── docs/contracts/      # sprint contracts + quality log
├── data/                # placeholder (no DB writes)
├── pyproject.toml
├── README.md            # ← this file
├── AGENTS.md            # conventions for contributors
├── .env.example
└── .gitignore
```

## Status

The MVP is feature-complete for the simplified scope: 15 personas × 8 indicators,
in-memory, parallel, Langfuse-traced when configured. See `docs/contracts/` for the
sprint history.

## License

TBD.
