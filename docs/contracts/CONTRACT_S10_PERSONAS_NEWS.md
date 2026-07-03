# CONTRACT — S10: Domain filtering + Impact-ranked news

**Date:** 2026-07-03
**Status:** APPROVED → IMPLEMENTING
**Sprints:** P1 → P2 → P3 (sequential)

## Scope

- **Parte A** — `domains` + `company_sectors` por persona; `personas_for_domain()`. Central bankers (greenspan/bernanke/volcker) só `{macro}`. Dimon só `{company}` + `company_sectors={Financial Services}`. Restantes `{company, macro}`.
- **Parte B** — Reescrever `fetch_material_events` para seleção por impacto (24 meses, item codes da SEC em 3 tiers). Sem digest LLM.
- **Parte C** — `fetch_recent_news` top 5, capturar `summary`.
- **Parte D** — CLI persona multi-select usa `personas_for_domain(domain, sector)`.

### Decisões locked
- 8-K window: 24 meses
- Headlines: top 5 como sentimento
- Sem digest LLM
- Persona filtering via campo `domains`

## Sprint P1 — Persona domain filtering + CLI

### Output Criteria
| # | Criterion | Weight |
|---|-----------|--------|
| 1 | `_PERSONA_DOMAINS` correto (3 central bankers → {macro}; dimon → {company}; restantes → {company, macro}) | MUST |
| 2 | `_PERSONA_COMPANY_SECTORS` correto (dimon → {Financial Services}; restantes None) | MUST |
| 3 | `personas_for_domain("company", "Technology")` exclui dimon E os 3 central bankers | MUST |
| 4 | `personas_for_domain("company", "Financial Services")` inclui dimon, exclui 3 central bankers | MUST |
| 5 | `personas_for_domain("macro")` inclui 3 central bankers, exclui dimon | MUST |
| 6 | CLI multi-select personas usa `personas_for_domain(domain, sector)` | MUST |

## Sprint P2 — Impact-ranked 8-Ks + sentiment headlines

### Output Criteria
| # | Criterion | Weight |
|---|-----------|--------|
| 1 | `_8K_ITEM_TIERS` (T1: 1.01/1.02/1.03/2.01/4.01/4.02/5.02; T2: 2.02/5.01/2.05/3.01/8.01; T3: 7.01/5.07/5.03/9.01) | MUST |
| 2 | `fetch_material_events` janela 24 meses | MUST |
| 3 | Cada 8-K scored pelo tier mais alto entre os seus codes | MUST |
| 4 | Seleção: todos T1 → T2 (2.02 capped 4) → poucos T3 | MUST |
| 5 | Rendered events com tier label + item-code description | MUST |
| 6 | fetch_recent_news top 5 + captura summary | MUST |
| 7 | Rendered context: impact-ranked + sentiment, sem digest | MUST |

## Sprint P3 — Validator final

### Outcome
- ≥145 testes verdes (133 + ≥12 novos)
- ruff limpo
- CLI smoke filtra corretamente
- Real-provider smoke confirmando 8-Ks no contexto

## Execution
P1 → P2 → P3. Por sprint: Executor → Validator → commit.

## Files
**P1:** `app/agents.py`, `app/cli_menu.py`, `tests/test_persona_domains.py`
**P2:** `app/pipeline/edgar.py`, `app/pipeline/news.py`, `app/pipeline/context.py`, `tests/test_impact_ranked_events.py`

Sem tocar em: `app/debate/*`, `app/models.py`, `app/providers.py`, `app/main.py`, `app/formatter.py`, `app/runner.py`, `app/prompts/*`, `app/pipeline/{market,macro,cache,metrics}.py`, testes existentes.