# CONTRACT S2 — Core Layer (logging + models + providers + catalog)

**Date:** 2026-07-01
**Planner:** opencode
**Status:** DRAFT → APPROVED → IMPLEMENTING → VALIDATED
**Phase:** 2 of 6
**Depends On:** S1 (repo bootstrap)
**Parent Goal:** Extract the LangChain + Langfuse agent pipeline into
`financial-adviser`.

---

## Trials

`trials: 3` — each criterion run 3 times.

---

## Scope

Create the foundational Python layer that everything else depends on:
- **Logging** (`app/core/logging.py`) — structlog wrapper, lifted from source
- **Schemas** (`app/models/schemas.py`) — Pydantic models (Bloc, Category,
  Frequency, Transformation, Indicator, Observation, AssessmentOutput,
  RunRequest, EventItem, GlobalContext), lifted from source
- **Providers** (`app/services/providers.py`) — `LLMProvider` ABC +
  `MiniMaxProvider` (lifted, with `MINIMAX_API_KEY` semantics preserved) +
  **new** `MockProvider` class for tests/CI + `ProviderRegistry` with both
  registered by default
- **Catalog** (`app/services/catalog.py`) — slim catalog with exactly **8
  US indicators** (no EU, no CROSS, no tickers, no individual equities)

No DB code yet (that's S3). No agent code yet (that's S4). This sprint is
purely importable Python.

---

## Output Criteria

| # | Criterion | Weight | Tier |
|---|-----------|--------|------|
| 1 | `app/__init__.py`, `app/core/__init__.py`, `app/models/__init__.py`, `app/services/__init__.py` exist as empty package markers | MUST | T2 |
| 2 | `app/core/logging.py` exposes `setup_logging(service: str = "mi")` and `get_logger(name: str \| None = None) -> structlog.BoundLogger` (signatures verified by import + inspect) | MUST | T3 |
| 3 | `setup_logging()` configures structlog with `TimeStamper`, `add_log_level`, and either `JSONRenderer` (env=production) or `ConsoleRenderer` (env=development); selectable via `MFL_ENV` env var | MUST | T3 |
| 4 | `get_logger("foo")` returns an object with `.info()`, `.warning()`, `.error()` methods that produce dict-like output (structlog compat) | MUST | T3 |
| 5 | `app/models/schemas.py` defines StrEnums `Bloc`, `Category`, `Frequency`, `Transformation` with their original values + Pydantic models `Indicator`, `Observation`, `AssessmentOutput`, `RunRequest`, `EventItem`, `GlobalContext` | MUST | T3 |
| 6 | `Indicator` model is constructible with `Indicator(indicator_id="US.FFR", bloc=Bloc.US, category=Category.MONETARY, name="Fed Funds Rate", source="FRED", source_series="DFF", frequency=Frequency.D, units="percent", transformation=Transformation.LEVEL, lag_days=1, is_target=True, tier=1)` | MUST | T3 |
| 7 | `app/services/providers.py` defines `LLMProvider` ABC with abstract methods `get_model()` and `provider_name() -> str` | MUST | T3 |
| 8 | `MiniMaxProvider(api_key="test-key", model="test-model")` constructs without error and `provider_name()` returns `"minimax:test-model"` | MUST | T3 |
| 9 | `MiniMaxProvider.get_model()` returns a `langchain_anthropic.ChatAnthropic` instance (NOT yet another provider) | MUST | T3 |
| 10 | `MockProvider()` constructs, `provider_name()` returns `"mock"`, and `get_model()` returns an object that responds to `.invoke()` with a configurable return value | MUST | T3 |
| 11 | `ProviderRegistry.register("foo", provider)`, `get("foo")`, `list_providers()` work as class methods; `initialize_defaults()` registers both `"minimax"` (real) and `"mock"` (no-API-key dev/test) | MUST | T3 |
| 12 | `app/services/catalog.py` defines `CATALOG_US` as a list of exactly **8** `Indicator` instances, plus `ALL_CATALOG = CATALOG_US` (no EU, no CROSS). The 8 IDs must be exactly: `US.FFR`, `US.CPI.YOY`, `US.GDP.QOQ`, `US.SP500`, `US.CREDIT.SPREAD`, `US.UNRATE`, `US.UST10Y`, `US.VIX` | MUST | T3 |
| 13 | Every entry in `ALL_CATALOG` is a valid `Indicator` Pydantic instance; `get_catalog()` and `get_target_indicators()` helpers exist and return lists | MUST | T3 |
| 14 | All 8 indicators have `bloc=Bloc.US` and `is_target=True`; categories span at least 4 of the 9 Category enum values (no all-same-category catalog) | SHOULD | T3 |
| 15 | `python3 -c "from app.services.catalog import ALL_CATALOG; ids=sorted([i.indicator_id for i in ALL_CATALOG]); expected=['US.CPI.YOY','US.CREDIT.SPREAD','US.FFR','US.GDP.QOQ','US.SP500','US.UNRATE','US.UST10Y','US.VIX']; assert ids==expected"` exits 0 | MUST | T3 |
| 16 | `ruff check app/` exits 0 | MUST | T3 |

---

## Outcome Criteria

| # | Criterion | Weight | Tier |
|---|-----------|--------|------|
| 1 | A second operator can `pip install -e .` and run `python -c "from app.services.catalog import ALL_CATALOG; print(len(ALL_CATALOG))"` and get `8` | SHOULD | T3 |
| 2 | `python -c "from app.services.providers import ProviderRegistry; ProviderRegistry.initialize_defaults(); print(sorted(ProviderRegistry.list_providers()))"` prints `['minimax', 'mock']` (no real API call, mock returns immediately) | MUST | T3 |

---

## Validation Commands

### Tier 2 — Import & Runtime

```bash
# Layout present
ls -d /Users/pauloribeiro/Desktop/Projetos/financial-adviser/app/{core,models,services}/
test -f /Users/pauloribeiro/Desktop/Projetos/financial-adviser/app/__init__.py

# Each module imports cleanly
python3 -c "from app.core.logging import setup_logging, get_logger"
python3 -c "from app.models.schemas import Bloc, Category, Indicator, Observation, AssessmentOutput"
python3 -c "from app.services.providers import LLMProvider, MiniMaxProvider, MockProvider, ProviderRegistry"
python3 -c "from app.services.catalog import CATALOG_US, ALL_CATALOG, get_catalog, get_target_indicators"
```

### Tier 3 — Behavioral (MUST criteria)

```bash
# C2+C3: logging setup + log emission
cd /Users/pauloribeiro/Desktop/Projetos/financial-adviser/ && MFL_ENV=production python3 -c "
from app.core.logging import setup_logging, get_logger
setup_logging()
log = get_logger('test')
log.info('test.event', key='value')
print('OK')
"

# C4: log has the right interface
cd /Users/pauloribeiro/Desktop/Projetos/financial-adviser/ && python3 -c "
from app.core.logging import setup_logging, get_logger
setup_logging()
log = get_logger('foo')
assert callable(log.info)
assert callable(log.warning)
assert callable(log.error)
print('OK')
"

# C6: Indicator constructs
cd /Users/pauloribeiro/Desktop/Projetos/financial-adviser/ && python3 -c "
from app.models.schemas import Indicator, Bloc, Category, Frequency, Transformation
i = Indicator(indicator_id='US.FFR', bloc=Bloc.US, category=Category.RATES, name='Fed Funds Rate', source='FRED', source_series='DFF', frequency=Frequency.D, units='percent', transformation=Transformation.LEVEL, lag_days=1, is_target=True, tier=1)
assert i.indicator_id == 'US.FFR'
print('OK')
"

# C7-C9: provider construction
cd /Users/pauloribeiro/Desktop/Projetos/financial-adviser/ && python3 -c "
from app.services.providers import LLMProvider, MiniMaxProvider, MockProvider, ProviderRegistry
p = MiniMaxProvider(api_key='sk-test', model='test-m')
assert p.provider_name() == 'minimax:test-m', p.provider_name()
m = p.get_model()
from langchain_anthropic import ChatAnthropic
assert isinstance(m, ChatAnthropic), type(m).__name__
print('OK')
"

# C10: MockProvider
cd /Users/pauloribeiro/Desktop/Projetos/financial-adviser/ && python3 -c "
from app.services.providers import MockProvider, LLMProvider
m = MockProvider()
assert isinstance(m, LLMProvider)
assert m.provider_name() == 'mock'
model = m.get_model()
assert hasattr(model, 'invoke')
result = model.invoke('hello')
assert result == '' or result is not None
print('OK')
"

# C11: ProviderRegistry
cd /Users/pauloribeiro/Desktop/Projetos/financial-adviser/ && python3 -c "
from app.services.providers import ProviderRegistry, MiniMaxProvider, MockProvider
ProviderRegistry.register('test_provider', MiniMaxProvider(api_key='x'))
assert ProviderRegistry.get('test_provider') is not None
assert 'test_provider' in ProviderRegistry.list_providers()
ProviderRegistry._providers.clear()
print('OK')
"

# C12+C15: catalog IDs exactly 8
cd /Users/pauloribeiro/Desktop/Projetos/financial-adviser/ && python3 -c "
from app.services.catalog import ALL_CATALOG
ids = sorted([i.indicator_id for i in ALL_CATALOG])
expected = sorted(['US.CPI.YOY','US.CREDIT.SPREAD','US.FFR','US.GDP.QOQ','US.SP500','US.UNRATE','US.UST10Y','US.VIX'])
assert ids == expected, f'mismatch: {ids} vs {expected}'
print('OK')
"

# C13+C14: every indicator is valid Indicator; helpers exist; targets correct
cd /Users/pauloribeiro/Desktop/Projetos/financial-adviser/ && python3 -c "
from app.services.catalog import ALL_CATALOG, get_catalog, get_target_indicators
from app.models.schemas import Indicator, Bloc
from collections import Counter
assert all(isinstance(i, Indicator) for i in ALL_CATALOG)
assert all(i.bloc == Bloc.US for i in ALL_CATALOG)
assert all(i.is_target for i in ALL_CATALOG)
cats = set(i.category for i in ALL_CATALOG)
assert len(cats) >= 4, cats
tgts = get_target_indicators()
assert len(tgts) == 8
print('OK')
"

# C16: ruff
cd /Users/pauloribeiro/Desktop/Projetos/financial-adviser/ && ruff check app/

# Outcome 2: initialize_defaults registers both
cd /Users/pauloribeiro/Desktop/Projetos/financial-adviser/ && python3 -c "
from app.services.providers import ProviderRegistry
ProviderRegistry.initialize_defaults()
ps = sorted(ProviderRegistry.list_providers())
assert ps == ['minimax', 'mock'], ps
print('OK')
"
```

---

## Files to Change

| File | Action | Lines (est.) | Why |
|------|--------|-------------|-----|
| `app/__init__.py` | create | 0 | Package marker |
| `app/core/__init__.py` | create | 0 | Package marker |
| `app/core/logging.py` | create | ~25 | Lift from source; keep signature |
| `app/models/__init__.py` | create | ~15 | Re-export Bloc, Category, Indicator, Observation, AssessmentOutput, RunRequest, EventItem, GlobalContext, Frequency, Transformation |
| `app/models/schemas.py` | create | ~111 | Lift from source verbatim |
| `app/services/__init__.py` | create | 0 | Package marker |
| `app/services/providers.py` | create | ~80 | Lift + add MockProvider + register mock in defaults |
| `app/services/catalog.py` | create | ~150 | Slim version: 8 US indicators + helpers |

**Catalog slim spec** — exact 8 entries:

```python
Indicator(indicator_id="US.FFR",          bloc=Bloc.US, category=Category.MONETARY,  name="Fed Funds Effective Rate",         source="FRED", source_series="DFF",         frequency=Frequency.D, units="percent", transformation=Transformation.LEVEL, lag_days=1, is_target=True, tier=1),
Indicator(indicator_id="US.CPI.YOY",      bloc=Bloc.US, category=Category.INFLATION, name="CPI YoY (Headline)",                source="FRED", source_series="CPIAUCSL",    frequency=Frequency.M, units="percent", transformation=Transformation.YOY,   lag_days=14, is_target=True, tier=1),
Indicator(indicator_id="US.GDP.QOQ",      bloc=Bloc.US, category=Category.GROWTH,    name="Real GDP QoQ (annualized)",        source="FRED", source_series="GDPC1",       frequency=Frequency.Q, units="percent", transformation=Transformation.QOQ,   lag_days=30, is_target=True, tier=2),
Indicator(indicator_id="US.SP500",        bloc=Bloc.US, category=Category.EQUITIES,  name="S&P 500 Index",                    source="FRED", source_series="SP500",       frequency=Frequency.D, units="index",   transformation=Transformation.LEVEL, lag_days=1, is_target=True, tier=1),
Indicator(indicator_id="US.CREDIT.SPREAD",bloc=Bloc.US, category=Category.CREDIT,    name="ICE BofA US High Yield OAS",       source="FRED", source_series="BAMLH0A0HYM2",frequency=Frequency.D, units="percent", transformation=Transformation.SPREAD,lag_days=1, is_target=True, tier=1),
Indicator(indicator_id="US.UNRATE",       bloc=Bloc.US, category=Category.LABOR,     name="Unemployment Rate",                source="FRED", source_series="UNRATE",      frequency=Frequency.M, units="percent", transformation=Transformation.LEVEL, lag_days=7, is_target=True, tier=2),
Indicator(indicator_id="US.UST10Y",       bloc=Bloc.US, category=Category.YIELDS,    name="10-Year Treasury Yield",           source="FRED", source_series="DGS10",       frequency=Frequency.D, units="percent", transformation=Transformation.LEVEL, lag_days=1, is_target=True, tier=1),
Indicator(indicator_id="US.VIX",          bloc=Bloc.US, category=Category.SENTIMENT, name="CBOE Volatility Index",            source="FRED", source_series="VIXCLS",      frequency=Frequency.D, units="index",   transformation=Transformation.LEVEL, lag_days=1, is_target=True, tier=2),
```

Note: `Transformation` source enum does **NOT** have `SPREAD` or `QOQ`. The Executor must verify against `app/models/schemas.py` and:
- For `US.GDP.QOQ`: use `Transformation.YOY` as a placeholder if needed, or
- Better: extend the enum in `app/models/schemas.py` to add `Transformation.QOQ` and `Transformation.SPREAD` (small additive change to support the catalog).

This is a small additive change in scope. Add `QOQ` and `SPREAD` if missing.

Also note `Category.SPREAD`/`YIELDS` mapping: `US.UST10Y` is **yields** (not monetary), `US.CREDIT.SPREAD` is **credit** (high yield OAS is credit). Decisions made above.

---

## Risks

| Risk | Probability | Mitigation |
|------|-------------|------------|
| `MiniMaxProvider.get_model()` instantiates `ChatAnthropic` on first call → needs `langchain-anthropic` importable at runtime, but does **not** need a real API key (the constructor only requires the key string, doesn't validate it) | low | `langchain-anthropic` is in `pyproject.toml` deps already (S1) |
| `MockProvider.get_model()` returns same MagicMock for every call → tools/bind_tools/with_structured_output all return same instance → may break if S4+ agents expect fresh mocks per call | low | Document in MockProvider docstring: "single shared mock instance; tests needing per-call state should patch `ProviderRegistry.get().get_model`" |
| `Transformation` enum currently has no `QOQ` or `SPREAD` in source — need additive extension | medium | Add `QOQ = "QOQ"`, `SPREAD = "SPREAD"` to the enum in this sprint (in scope per "Files to Change") |
| `initialize_defaults()` registering `mock` makes it accidentally pickable in production if someone calls `ProviderRegistry.get(name)` with `name=None` falling back to a default | very low | None — `ProviderRegistry.get` requires explicit name |
| Some `Indicator` Pydantic fields have default values; passing all fields means `lag_days`, `is_target`, `tier` could be inferred but contract spec asks for explicit | low | Spec is explicit, follow it |

**Rollback:** `rm -rf /Users/pauloribeiro/Desktop/Projetos/financial-adviser/app/`.

---

## Correction Loop

- Max 3 cycles per failing criterion
- After 3 failures: STOP and ask user

---

## Sign-off

- [ ] User approved contract
- [ ] Executor implemented
- [ ] Validator verified
- [ ] Quality Log updated

---

## Git Workflow

Per user instruction: **no automatic commits**. Executor creates files but
does not `git add`/`git commit`. User will commit when ready (likely after
S2 alone, or after the full pipeline).

---

## Out of Scope (deferred to later sprints)

- DB code (`DuckDBStore`, schema initialization) → S3
- Indicator brief, derived signals, context builder, news agent, debate engine → S3
- All agents (base + 15 personas + prompts) → S4
- Scripts (seed_demo, run_assessment) → S5
- Tests → S6
