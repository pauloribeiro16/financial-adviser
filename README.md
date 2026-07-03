# financial-adviser

Multi-persona macroeconomic assessment pipeline. Fifteen LLM analyst personas
(Buffett, Lynch, Dalio, Burry, Greenspan, Bernanke, Volcker, Dimon, Eisman,
Grantham, Simons, Taleb, Wood, Gundlach, Thaler) debate an investment thesis
through structured rounds and end with an optional moderator synthesis.

Two domains share one engine:

- **company** — a ticker (SEC EDGAR + yfinance fundamentals)
- **macro** — one or more FRED indicators

`--provider mock` runs offline with placeholder output — perfect for tests and CI.
`--provider minimax` calls the real Anthropic-compatible API and requires
`MINIMAX_API_KEY` in env.

See [AGENTS.md](./AGENTS.md) for the full contributor conventions.

## Quickstart

```bash
# 1. install
pip install -e .

# 2. (optional) copy .env from the source project, or set API key
cp .env.example .env && $EDITOR .env             # MINIMAX_API_KEY=sk-...

# 3. interactive menu (domain · analysts · rounds · format)
python -m app.main --interactive

# 4. company mode (debate over AAPL with 2 personas, 2 rounds, mock)
python -m app.main --company AAPL \
                   --analysts buffett,taleb \
                   --provider mock --rounds 2

# 5. rich output to a TTY (no --output required)
python -m app.main --company AAPL --analysts buffett,taleb \
                   --provider mock --rounds 1 --rich

# 6. legacy macro (one analyst, one indicator, MD)
python -m app.main --analysts buffett --indicators US.FFR \
                   --provider mock --format md
```

The CLI auto-loads `./.env` via python-dotenv (when installed). To skip .env
loading (e.g. in tests), set `FA_SKIP_DOTENV=1` in the environment.

## Domains & debate flow

The pipeline always starts with a data context (`pipeline.context`) — for a
ticker it pulls the latest 10-K + XBRL facts from EDGAR and a quote + multiples
from yfinance; for an indicator it pulls the last observations from FRED. That
context is rendered to Markdown and given to every persona as the common
factual baseline. Round 0 is independent theses (one `Thesis` per persona, in
parallel). Round 1..N are rebuttals: each persona sees every prior thesis and
returns a `Rebuttal` with explicit concessions and disagreements plus a
revised verdict. The optional final step is a moderator `Verdict` that counts
the bull / bear / neutral tally, surfaces points of agreement and disagreement,
and writes a free-form summary. Output is Markdown by default; with `--rich`
and a TTY, the result is pretty-printed to stdout via a `rich` table.

The macro path remains available as a "legacy" single-indicator run
(`--format md` with one analyst, no `--rounds`/`--no-synthesis`) for backward
compatibility — it skips the debate engine and produces a single `Assessment`
per (analyst, indicator).

## Default personas per domain

| Domain   | CLI flag              | Default personas (4)                       | Target example |
|----------|-----------------------|--------------------------------------------|----------------|
| company  | `--company AAPL`      | buffett, lynch, burry, taleb               | `AAPL`         |
| macro    | `--indicators US.FFR` | dalio, gundlach, volcker, greenspan        | `US.FFR`       |

Any of the 15 personas can be picked for either domain via the interactive
menu or `--analysts` flag.

### Output formats

`--format {md,json,per-agent,debate}` controls the output shape. Default is
`debate`. The legacy formats (`md`, `json`, `per-agent`) trigger the legacy
runner only when the legacy conditions match (single analyst, single indicator,
no synthesis, no rounds>1).

| Format        | Default path                                | With `--output PATH`     |
|---------------|---------------------------------------------|--------------------------|
| `debate`      | `./out/debate_<TS>/` (per-target MD + _summary.md) | writes to `PATH` (md/json/dir) |
| `per-agent`   | `./out/run_<TS>/` (tree, legacy)            | writes tree to `PATH`    |
| `md`          | `./out/run_<TS>.md` (legacy)                | writes to `PATH`         |
| `json`        | stdout                                      | writes to `PATH`         |

When `--company` is set, the target is always the ticker. When `--indicators`
is omitted, the CLI defaults to a single indicator: `US.UST10Y`. Pass an
explicit `--indicators ""` (empty) to get a clear error and exit code 1.
`--company` and `--indicators` are mutually exclusive.

```bash
# Debate to default dir
python -m app.main --company AAPL --analysts buffett,taleb --provider mock

# Debate to a specific MD file
python -m app.main --company AAPL --analysts buffett,taleb \
                   --provider mock --rounds 1 --format debate \
                   --output /tmp/aapl.md

# Rich to TTY
python -m app.main --company AAPL --analysts buffett,taleb \
                   --provider mock --rounds 1 --rich

# Legacy: per-agent tree
python -m app.main --analysts buffett,burry --indicators US.FFR \
                   --provider mock --format per-agent --output /tmp/run1

# Legacy: Markdown
python -m app.main --analysts buffett --indicators US.FFR \
                   --provider mock --format md --output /tmp/buffett-ffr.md

# Legacy: JSON to stdout
python -m app.main --analysts buffett --indicators US.FFR \
                   --provider mock --format json
```

### Running tests

```bash
pip install -e ".[dev]"
pytest tests/
```

The suite covers the catalog, persona registry, schema round-trip, mock-provider
end-to-end, runner fan-out, markdown formatter, per-agent layout, default
single-indicator behaviour, the CLI (`--format {md,per-agent,debate}`), the
debate engine, the orchestrator (with and without Langfuse env vars), and
the rich-table formatter.

## What you get (debate example)

```markdown
# Debate — AAPL (company) — 2025-03-31

> Provider: `minimax:MiniMax-M3` · Analysts: buffett, taleb · Rounds: 2

## Round 0 — Initial theses
### buffett
- **Verdict:** BULLISH (conviction 0.78)
- **Key drivers:**
  - durable moat in services
  - FCF compounding
  - net cash balance sheet
...

## Round 1 — Rebuttals
### buffett → taleb
- **Revised verdict:** BULLISH (conviction 0.72)
- **Concessions:** tail risk is real
- **Disagreements:** moats still hold in the regime
...

## Synthesis
- **Consensus:** SPLIT_BULL
- **Final call:** Moats hold; size small for tail.
- **Confidence:** 0.61
- **Avg conviction:** 0.65
- **Tally:** bull=1 · bear=0 · neutral=1
...
```

## Project layout

```
financial-adviser/
├── app/
│   ├── agents.py        # BaseAgent + 15 personas + ALL_AGENTS + T0/T1/T2 loader
│   ├── runner.py        # legacy assessment runner + run_debate_only
│   ├── main.py          # CLI entry
│   ├── cli_menu.py      # questionary interactive picker
│   ├── catalog.py       # 8 US FRED indicators
│   ├── models.py        # Pydantic schemas (Assessment, Thesis, Rebuttal, Verdict, …)
│   ├── providers.py     # MiniMax + Mock + ProviderRegistry
│   ├── formatter.py     # render (MD), render_summary, render_per_agent, render_debate_rich
│   ├── logging.py       # structlog wrapper
│   ├── debate/          # engine.py + orchestrator.py + tracing.py (Langfuse optional)
│   ├── pipeline/        # cache.py + context.py + edgar.py + market.py + macro.py
│   └── prompts/<15 dirs>/   # .md content for each persona
├── tests/
├── docs/contracts/      # sprint contracts + quality log
├── data/cache/          # JSON file cache (no DB, TTL-configurable)
├── pyproject.toml
├── README.md            # ← this file
├── AGENTS.md            # conventions for contributors
├── .env.example
└── .gitignore
```

## Status

MVP for company evaluation pipeline with adversarial multi-turn debate; macro
domain kept as legacy mode. See `docs/contracts/` for the sprint history.

## License

Proprietary — internal Market Intelligence project.
