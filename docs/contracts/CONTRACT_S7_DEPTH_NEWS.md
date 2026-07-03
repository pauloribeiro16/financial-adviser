# CONTRACT — Profundidade de análise + Notícias + Fallback robusto

**Date:** 2026-07-02
**Status:** APPROVED → IMPLEMENTING
**Sprints:** 4 sequenciais (P1 → P2 → P3 → P4)

## Scope

Quatro itens encadeados que tornam a análise de empresa profunda (não superficial) e fiável contra o MiniMax-M3:

- **P1 (fundação)** — Rede de segurança de 3 níveis para Thesis/Rebuttal/Verdict. Um persona NUNCA é dropado do debate.
- **P2** — Pipeline de notícias: yfinance `.news` (recentes) + EDGAR 8-K (eventos materiais com impacto).
- **P3** — Métricas derivadas pré-calculadas (ROIC, net debt/EBITDA, FCF conversion, margens, interest coverage, growth 3y, EV/EBITDA) com semáforos 🟢🟡🔴.
- **P4** — Prompts aprofundados: metodologia "Stock Simplifier" partilhada (6 pilares) + reestruturação da tese/réplica para walkthrough obrigatório com citações quantificadas, adaptado ao viés de cada persona.

### Decisões locked

- Schema Pydantic mantém-se magro — profundidade vive no `reasoning`, não em campos estruturados novos.
- Ordem: P1 primeiro (sem ele, prompts mais profundos = mais drops).
- Empírico: P1 começa com captura raw de 1 chamada MiniMax real antes de codificar o parser.

## Sprint P1 — Fallback safety net (fundação)

### Output Criteria
| # | Criterion | Weight |
|---|-----------|--------|
| 1 | `_invoke_with_fallback(provider, schema, messages, defaults, callback)` envolve tudo em try/except, nunca levanta | MUST |
| 2 | Mock hostil (structured sempre levanta) → 15/15 theses + 15/15 rebuttals (zero drops) | MUST |
| 3 | L2 ativa (plain invoke + JSON parse) e preenche campos obrigatórios em falta com defaults | MUST |
| 4 | L3 ativa (defaults completos NEUTRAL 0.5) quando L2 devolve não-JSON | MUST |
| 5 | Aplicado a Thesis, Rebuttal E Verdict | MUST |
| 6 | Log `debate.invoke.fallback_used` com nível (1/2/3) + agente | SHOULD |

### Files
- `app/debate/engine.py` — modify
- `tests/test_debate_fallback.py` — create

## Sprint P2 — Notícias

### Output Criteria
| # | Criterion | Weight |
|---|-----------|--------|
| 1 | `fetch_recent_news(ticker)` devolve lista de dicts `{title, publisher, date, link}` | MUST |
| 2 | `fetch_material_events(cik)` filtra 8-K do submissions já cached, devolve `{date, accession, primary_doc, items}` | MUST |
| 3 | `_render_company` inclui secções `## Recent news` e `## Material events (SEC 8-K)` | MUST |
| 4 | Usa cache existente | SHOULD |

### Files
- `app/pipeline/news.py` — create
- `app/pipeline/edgar.py` — modify (add `fetch_material_events`)
- `app/pipeline/context.py` — modify (render)
- `tests/test_news.py` — create

## Sprint P3 — Métricas derivadas

### Output Criteria
| # | Criterion | Weight |
|---|-----------|--------|
| 1 | `derive_metrics(fundamentals, quote, facts)` devolve ≥10 métricas: revenue_growth_3y, gross_margin, operating_margin, net_margin, roic, fcf_conversion, net_debt_ebitda, interest_coverage, net_cash, share_count_change, pe, ev_ebitda | MUST |
| 2 | Cada métrica traz `{value, benchmark, rating}` onde rating ∈ {🟢,🟡,🔴} | MUST |
| 3 | Lida com None/missing gracamente | MUST |
| 4 | `_render_company` inclui `## Derived metrics` com semáforos | MUST |

### Files
- `app/pipeline/metrics.py` — create
- `app/pipeline/context.py` — modify (render)
- `tests/test_metrics.py` — create

## Sprint P4 — Prompts aprofundados

### Output Criteria
| # | Criterion | Weight |
|---|-----------|--------|
| 1 | `app/prompts/_shared/analysis_pillars.md` define 6 pilares (Lifecycle, Moat×5, Growth Engines, Financial Health, Bear Case, Valuation) com benchmarks | MUST |
| 2 | `build_thesis_messages` carrega pillars no system prompt | MUST |
| 3 | User prompt da tese OBRIGA os 6 pilares com citação de data point | MUST |
| 4 | Schema Thesis inalterado | MUST |
| 5 | `build_rebuttal_messages` reforçado para desafiar pilares com dados | SHOULD |

### Files
- `app/prompts/_shared/analysis_pillars.md` — create
- `app/debate/engine.py` — modify
- `tests/test_deep_prompts.py` — create

## Outcome Criteria
- 47 testes existentes + novos todos verdes
- `ruff check app/ tests/` limpo
- Debate TSLA/JPM com MiniMax real: 15/15 theses + 15/15 rebuttals + verdict (zero drops) — SHOULD
- Contexto de empresa contém fundamentals + métricas derivadas + notícias + 8-K + macro

## Quality Dimensions
- Correctness: 100% MUST
- No Regressions
- Robustez MiniMax: zero drops sob mocks hostis
- Pattern compliance: structlog, sem comentários, snake_case

## Risks & mitigations
- yfinance `.news` formato/limites → graceful lista vazia + cache 1h
- 8-K items parse defensivo
- Métricas None → skip sem crash
- Prompts mais longos → aceitável; schema mantém-se magro
- MiniMax raw capture (P1 step 0) → ajusta parser antes de avançar

## Execution
Sequencial P1 → P2 → P3 → P4. Por sprint: Executor → Validator → commit. Step 0 do P1 = captura empírica MiniMax.