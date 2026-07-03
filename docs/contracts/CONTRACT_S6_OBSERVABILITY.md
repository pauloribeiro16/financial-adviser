# CONTRACT — Observabilidade Langfuse v4 + Síntese + Dados

**Date:** 2026-07-01
**Status:** APPROVED → IMPLEMENTING
**Phases:** 3 sprints sequenciais (S1 → S2 → S3)

## Scope

Corrigir os 3 problemas encontrados na análise do debate MSFT (2026-07-01):

- **S1 (Crítico)**: Langfuse não recebe traces. `tracing.py` usa API v2/v3 (`client.trace()`) contra o SDK v4.11.0 (OTEL). Reescrever para v4 (`@observe` + `CallbackHandler` passado a cada `invoke` + `session_id`).
- **S2 (Alto)**: Síntese do moderador cai em heuristic fallback. Adicionar JSON fallback + pré-calcular contagens bull/bear/neutral.
- **S3 (Médio)**: Dados não chegam aos agentes. Renderizar `fundamentals` (FCF/CapEx/dívida), adicionar contexto macro leve (VIX + UST10Y + credit spread) a empresa, filtrar XBRL tags stale.

## Decisões locked (aprovadas)

- **Langfuse v4**: `@observe(name="debate")` em `orchestrate_debate` + `langfuse_context.update_current_trace(session_id=, tags=)` + `CallbackHandler()` em `config["callbacks"]` de cada `invoke`. SDK v4 faz degrade automático sem env vars.
- **Validação Langfuse**: wiring via spies + verificação manual no UI Cloud (SHOULD).
- **Macro em empresa**: VIX (`VIXCLS`), UST10Y (`DGS10`), credit spread (`BAMLH0A0HYM2`).
- **Síntese**: contagens pré-calculadas em Python e passadas no prompt; JSON fallback quando structured falha.

## Execution strategy

Sequencial S1→S2→S3 (S1 e S2 tocam `engine.py`). Por sprint: Executor implementa → Validator verifica critérios T3 + ruff + 26 testes existentes → commit.

## Files to change (resumo)

| Sprint | File | Action |
|--------|------|--------|
| S1 | `app/debate/tracing.py` | rewrite v4 |
| S1 | `app/debate/engine.py` | passar callback handler em _invoke_structured |
| S1 | `app/debate/orchestrator.py` | @observe + update_current_trace |
| S1 | `tests/test_tracing_v4.py` | create |
| S2 | `app/debate/engine.py` | _run_synthesis JSON fallback + counts in prompt |
| S2 | `tests/test_debate_synthesis.py` | create |
| S3 | `app/pipeline/context.py` | render fundamentals + macro |
| S3 | `app/pipeline/edgar.py` | filter stale XBRL tags |
| S3 | `tests/test_context_enrichment.py` | create |

## Risks & mitigations

- **S1**: API `observe`/`langfuse_context` pode diferir entre minor versions v4 → Executor verifica assinaturas reais via `inspect.signature` antes de aplicar.
- **S2**: JSON fallback pode mascarar erros reais → logar warning sempre que ativa.
- **S3**: macro fetch em company eval adiciona latência (~1s) → usar cache 6h (já existe em `macro.py`).
- **Rollback**: cada sprint é commit isolado; `git revert` por sprint.