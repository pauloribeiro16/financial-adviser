from app.models import Bloc, Category, Frequency, Indicator, Transformation

CATALOG_US: list[Indicator] = [
    Indicator(
        indicator_id="US.FFR",
        bloc=Bloc.US,
        category=Category.MONETARY,
        name="Fed Funds Effective Rate",
        source="FRED",
        source_series="DFF",
        frequency=Frequency.D,
        units="percent",
        transformation=Transformation.LEVEL,
        tier=1,
    ),
    Indicator(
        indicator_id="US.CPI.YOY",
        bloc=Bloc.US,
        category=Category.INFLATION,
        name="CPI YoY (Headline)",
        source="FRED",
        source_series="CPIAUCSL",
        frequency=Frequency.M,
        units="percent",
        transformation=Transformation.YOY,
        tier=1,
    ),
    Indicator(
        indicator_id="US.GDP.QOQ",
        bloc=Bloc.US,
        category=Category.GROWTH,
        name="Real GDP QoQ (annualized)",
        source="FRED",
        source_series="GDPC1",
        frequency=Frequency.Q,
        units="percent",
        transformation=Transformation.QOQ,
        tier=2,
    ),
    Indicator(
        indicator_id="US.SP500",
        bloc=Bloc.US,
        category=Category.EQUITIES,
        name="S&P 500 Index",
        source="FRED",
        source_series="SP500",
        frequency=Frequency.D,
        units="index",
        transformation=Transformation.LEVEL,
        tier=1,
    ),
    Indicator(
        indicator_id="US.CREDIT.SPREAD",
        bloc=Bloc.US,
        category=Category.CREDIT,
        name="ICE BofA US High Yield OAS",
        source="FRED",
        source_series="BAMLH0A0HYM2",
        frequency=Frequency.D,
        units="percent",
        transformation=Transformation.SPREAD,
        tier=1,
    ),
    Indicator(
        indicator_id="US.UNRATE",
        bloc=Bloc.US,
        category=Category.LABOR,
        name="Unemployment Rate",
        source="FRED",
        source_series="UNRATE",
        frequency=Frequency.M,
        units="percent",
        transformation=Transformation.LEVEL,
        tier=2,
    ),
    Indicator(
        indicator_id="US.UST10Y",
        bloc=Bloc.US,
        category=Category.YIELDS,
        name="10-Year Treasury Yield",
        source="FRED",
        source_series="DGS10",
        frequency=Frequency.D,
        units="percent",
        transformation=Transformation.LEVEL,
        tier=1,
    ),
    Indicator(
        indicator_id="US.VIX",
        bloc=Bloc.US,
        category=Category.SENTIMENT,
        name="CBOE Volatility Index",
        source="FRED",
        source_series="VIXCLS",
        frequency=Frequency.D,
        units="index",
        transformation=Transformation.LEVEL,
        tier=2,
    ),
]

ALL_CATALOG: list[Indicator] = CATALOG_US


def get_catalog() -> list[Indicator]:
    return ALL_CATALOG


def get_target_indicators() -> list[str]:
    return [i.indicator_id for i in ALL_CATALOG]
