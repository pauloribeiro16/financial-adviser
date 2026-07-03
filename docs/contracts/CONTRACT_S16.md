# CONTRACT — S16: Pré-resumo do 10-K (opcional, scope limitado)

**Contract ID:** SC-2026-16
**Date:** 2026-07-03
**Planner:** opencode
**Spec File:** (none — contract carries spec; single sprint, 3 sequential sub-phases)
**Status:** DRAFT → APPROVED → IMPLEMENTING → VALIDATED
**Branch:** `sprint/s16-filings` (a partir de `origin/master` com S14+S15 merged)
**Base:** master com S14+S15 merged

---

## Context

Antes de correr um debate, opcionalmente, baixar e resumir a última 10-K filing (Item 1 Business, Item 1A Risk Factors, Item 7 MD&A, Item 7A Market Risk) para fornecer **narrativa** ao debate (o pipeline actual só extrai XBRL facts numéricos).

**Decisões locked:**
- Só 10-K (anual). Sem 10-Q, sem 8-K.
- Opcional via flag `--with-filings` no debate. Default: não usar (comportamento actual inalterado).
- 3 chamadas LLM por empresa (Item 1+7A agrupados, Item 1A, Item 7).
- Map-reduce se secção >8K palavras (chunks de 4K com overlap 200).
- Cache permanente em JSON (`data/cache/filings/<ticker>/<filing_date>_10k_summary.json`), TTL infinito.
- Integração mínima no debate — o `FilingSummary` aparece como nova secção no `render_context_markdown()`. Nenhuma mudança no engine, graph, orchestrator, watch.

## Goals

1. Executor pode APENAS tocar nos ficheiros listados em "FICH-LOCKED".
2. Tudo o resto do sistema (debate engine, watch, prompts, sectors, providers, debate graph, orchestrator) **não muda**.
3. O comportamento default do CLI é idêntico ao actual (sem `--with-filings`).
4. Ruff clean, todos os testes passam, 0 regressões.

---

## FICH-LOCKED (scope exacto)

### Ficheiros que o Executor PODE criar (lista exaustiva)

| Ficheiro | LOC máx | Propósito |
|----------|---------|-----------|
| `app/filings/__init__.py` | 5 | Package marker |
| `app/filings/fetcher.py` | 80 | Download HTML do SEC |
| `app/filings/section_parser.py` | 120 | Extrair Item 1, 1A, 7, 7A |
| `app/filings/summarizer.py` | 200 | 3 chamadas LLM + map-reduce |
| `app/filings/cache.py` | 60 | Cache JSON permanente |
| `app/filings/prompts.py` | 100 | Prompts por secção |
| `tests/test_section_parser.py` | 150 | Tests parser |
| `tests/test_summarizer.py` | 150 | Tests summarizer |
| `tests/test_filings_cache.py` | 80 | Tests cache |

### Ficheiros que o Executor PODE modificar (diffs mínimos)

| Ficheiro | Δ máx | O que muda |
|----------|-------|-----------|
| `app/models.py` | +15 | Adicionar `FilingSummary` schema (4 campos) |
| `app/pipeline/context.py` | +20 | `build_company_context(ticker, *, with_filings=False)` aceita novo kwarg |
| `app/pipeline/context.py::_render_company()` | +15 | Nova secção `## 10-K Narrative Summary` se `filing_summary` presente |
| `app/main.py` | +5 | Flag `--with-filings` (action store_true, default False) |
| `app/cli_menu.py` | +10 | Toggle "Include 10-K narrative?" (default No) |

---

## PROIBIÇÕES ABSOLUTAS

O Executor **NÃO PODE**:

1. Modificar `app/debate/engine.py` — debate não muda
2. Modificar `app/debate/graph.py` — grafo não muda
3. Modificar `app/debate/orchestrator.py` — orchestrator não muda
4. Modificar `app/watch/` — vigilância não muda nesta fase
5. Modificar `app/prompts/` — prompts de persona não mudam
6. Modificar `app/providers.py` — providers não mudam
7. Modificar `app/sectors/` — YAMLs não mudam
8. Modificar `pyproject.toml` — sem novas dependências
9. Criar comandos CLI novos — só `--with-filings` flag no debate existente
10. Refactorizar código não listado
11. Adicionar comentários ao código
12. Adicionar docstrings além de 1 linha por função pública
13. Mudar comportamento default do CLI (sem `--with-filings` = actual)
14. Criar schemas Pydantic além de `FilingSummary`
15. Implementar 10-Q ou 8-K parsing (só 10-K)
16. Usar BeautifulSoup, lxml, ou libs de parsing HTML além de stdlib (regex + str)
17. Usar async (só httpx síncrono)
18. Criar DB ou persistência (só JSON files)

---

## Schema EXACTO

```python
class FilingSummary(BaseModel):
    ticker: str
    filing_date: str       # "YYYY-MM-DD"
    form: str              # "10-K"
    business_and_market_risk: str = Field(..., max_length=500)
    risk_factors: str = Field(..., max_length=500)
    md_and_a: str = Field(..., max_length=500)
```

## Assinaturas EXACTAS

```python
# fetcher.py
def download_10k_html(cik: str, accession: str, primary_document: str) -> str:
    """Returns HTML text or raises httpx.HTTPError after 3 retries."""

# section_parser.py
def extract_sections(html_text: str) -> dict[str, str]:
    """Returns {'business': str, 'risk_factors': str, 'md_and_a': str, 'market_risk': str}.
    Missing sections return empty string."""

# summarizer.py
def summarize_sections(sections: dict[str, str], ticker: str, provider_name: str) -> FilingSummary:
    """3 LLM calls (map-reduce per section if >8K words). Returns FilingSummary."""

def get_or_build_summary(ticker: str, provider_name: str) -> FilingSummary | None:
    """Cache-first. If cache miss → download + parse + summarize + cache.
    Returns None if 10-K unavailable."""

# cache.py
def get(ticker: str, filing_date: str) -> FilingSummary | None: ...
def put(summary: FilingSummary) -> None: ...
def latest_filing_date(ticker: str) -> str | None: ...

# prompts.py
SECTION_PROMPT_BUSINESS_RISK: str   # Item 1 + 7A
SECTION_PROMPT_RISK_FACTORS: str    # Item 1A
SECTION_PROMPT_MD_A: str            # Item 7
CONSOLIDATION_PROMPT: str           # map-reduce consolidation
```

---

## Map-reduce EXACTO

```python
_MAX_WORDS_DIRECT = 8000
_CHUNK_WORDS = 4000
_CHUNK_OVERLAP = 200

def _summarize_section(text: str, prompt: str, provider, schema) -> str:
    if len(text.split()) <= _MAX_WORDS_DIRECT:
        return _single_call(text, prompt, provider, schema)
    chunks = _chunk(text, _CHUNK_WORDS, _CHUNK_OVERLAP)
    partials = [_single_call(c, prompt, provider, schema) for c in chunks]
    return _consolidate(partials, CONSOLIDATION_PROMPT, provider, schema)
```

Usa `engine._invoke_with_fallback` (master 3-level safety net), NÃO `with_structured_output` directo.

---

## Integration points EXACTOS

### `app/pipeline/context.py::build_company_context()`

```python
def build_company_context(ticker: str, *, with_filings: bool = False) -> dict[str, Any]:
    # ... existing code unchanged ...
    ctx = {
        "ticker": ticker,
        "edgar": edgar,
        "quote": quote,
        "fundamentals": fundamentals,
    }
    if with_filings:
        from app.filings.summarizer import get_or_build_summary
        filing = get_or_build_summary(ticker, provider_name="minimax")
        if filing is not None:
            ctx["filing_summary"] = filing
    return ctx
```

### `app/pipeline/context.py::_render_company()`

```python
filing = ctx.get("filing_summary")
if filing is not None:
    sections.append("\n## 10-K Narrative Summary")
    sections.append(f"_Source: {filing.form} filed {filing.filing_date}_\n")
    sections.append(f"**Business & Market Risk:** {filing.business_and_market_risk}\n")
    sections.append(f"**Risk Factors:** {filing.risk_factors}\n")
    sections.append(f"**MD&A Highlights:** {filing.md_and_a}\n")
```

### `app/main.py`

```python
p.add_argument("--with-filings", action="store_true", default=False,
               help="Download and summarize latest 10-K before debate (adds ~30s).")
```

E a chamada passa o kwarg:
```python
ctx = build_company_context(target, with_filings=args.with_filings)
```

---

## Sub-phases

| Phase | Scope | Depende de |
|-------|-------|-----------|
| **S16-P1** | `fetcher.py` + `section_parser.py` + `cache.py` + `FilingsSummary` schema + tests | — |
| **S16-P2** | `summarizer.py` + `prompts.py` + tests | P1 |
| **S16-P3** | `context.py` integration + `main.py` flag + `cli_menu.py` toggle | P2 |

---

## Critérios de validação (MUST)

| # | Critério | Comando |
|---|----------|---------|
| OC1 | `from app.filings.fetcher import download_10k_html` | exit 0 |
| OC2 | `from app.filings.section_parser import extract_sections` | exit 0 |
| OC3 | `from app.filings.summarizer import summarize_sections, get_or_build_summary` | exit 0 |
| OC4 | `from app.models import FilingSummary` | exit 0 |
| OC5 | `extract_sections("")` returns all-empty dict (não crasha) | assert |
| OC6 | `python3 -m app.main --help` mostra `--with-filings` | grep |
| OC7 | `python3 -m app.main --company AAPL --provider mock --rounds 1` (SEM --with-filings) → exit 0, mesmo comportamento | exit 0 |
| OC8 | `pytest tests/test_section_parser.py tests/test_summarizer.py tests/test_filings_cache.py -v` | all pass |
| OC9 | `pytest tests/ --tb=no -q` | 0 novas falhas (expect 300+10 pre-exist) |
| OC10 | `ruff check app/filings/ app/models.py app/pipeline/context.py` | clean |

## Critérios de NÃO-regressão

| # | Critério |
|---|----------|
| ON1 | `pytest tests/test_orchestrator.py tests/test_debate_graph.py tests/test_debate_smoke.py tests/test_session_id.py tests/test_prompts_registry.py` — all pass |
| ON2 | `python3 -m app.main --company AAPL --analysts buffett --provider mock --rounds 1` — exit 0 |
| ON3 | `python3 -m app.main watch --sector Energy --provider mock` — exit 0 |

## Smoke SHOULD (requer rede + minimax)

```bash
python3 -m app.main --company XOM --analysts buffett --with-filings --provider minimax --rounds 1
# Verificar que o debate Markdown inclui "## 10-K Narrative Summary"
```

---

## Validation Commands

```bash
cd /home/epmq-cyber/Área de Trabalho/projects/financial-adviser
source .venv/bin/activate

# Imports
python3 -c "from app.filings.fetcher import download_10k_html"
python3 -c "from app.filings.section_parser import extract_sections; r = extract_sections(''); assert r == {'business': '', 'risk_factors': '', 'md_and_a': '', 'market_risk': ''}; print('OK')"
python3 -c "from app.filings.summarizer import summarize_sections, get_or_build_summary"
python3 -c "from app.filings.cache import get, put, latest_filing_date"
python3 -c "from app.models import FilingSummary"

# CLI flag present
python3 -m app.main --help 2>&1 | grep "with-filings"

# Backward compat
python3 -m app.main --company AAPL --analysts buffett --provider mock --rounds 1

# Lint
ruff check app/filings/ app/models.py app/pipeline/context.py
ruff check app/

# Tests
pytest tests/test_section_parser.py tests/test_summarizer.py tests/test_filings_cache.py -v
pytest tests/test_orchestrator.py tests/test_debate_graph.py tests/test_session_id.py tests/test_prompts_registry.py --tb=no -q
pytest tests/ --tb=no -q
```

## Commit Strategy

3 atomic commits:
- `feat(filings): S16-P1 — fetcher + section_parser + cache + FilingSummary schema`
- `feat(filings): S16-P2 — summarizer (3 calls + map-reduce) + prompts`
- `feat(filings): S16-P3 — CLI flag + context integration + menu toggle`

Plus final: `docs(contracts): record S16 in QUALITY_LOG`.

## What to return (per sub-phase)

1. Files modified/created with line-count diffs
2. ruff output (clean)
3. New tests passing
4. Master regression test count
5. Full pytest summary
6. Confirmed: FICH-LOCKED respected (nothing outside the list touched)
7. Confirmed: PROIBIÇÕES respected (nothing in the prohibition list touched)
8. Any deviations from the contract
