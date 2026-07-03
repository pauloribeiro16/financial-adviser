from __future__ import annotations

from app.filings.section_parser import _strip_html, extract_sections


def test_extract_empty_returns_all_empty() -> None:
    r = extract_sections("")
    assert r == {
        "business": "",
        "risk_factors": "",
        "md_and_a": "",
        "market_risk": "",
    }


def test_extract_only_business() -> None:
    html = """
    <html><body>
    <h1>Item 1. Business</h1>
    <p>Apple Inc. designs, manufactures and markets smartphones.</p>
    <p>iPhone, Mac, iPad, Wearables.</p>
    <h1>Item 1A. Risk Factors</h1>
    <p>Risk text too short.</p>
    </body></html>
    """
    r = extract_sections(html)
    assert "Apple" in r["business"]
    assert "Wearables" in r["business"]
    assert r["risk_factors"] == ""


def test_extract_all_four_sections() -> None:
    html = """
    <html><body>
    Item 1. Business The company makes widgets and gizmos for industrial clients worldwide.
    Item 1A. Risk Factors The company's main risks include supply chain disruptions, regulatory changes, and competition.
    Item 7. Management's Discussion and Analysis Revenue grew 12% year over year on strong demand.
    Item 7A. Quantitative and Qualitative Disclosures About Market Risk Foreign exchange exposure is the primary risk.
    </body></html>
    """
    r = extract_sections(html)
    assert "widgets" in r["business"]
    assert "supply chain" in r["risk_factors"]
    assert "12%" in r["md_and_a"]
    assert "Foreign exchange" in r["market_risk"]


def test_extract_short_section_becomes_empty() -> None:
    html = """
    <html><body>
    Item 1. Business x
    Item 1A. Risk Factors y
    Item 7. Management z
    Item 7A. Quantitative w
    </body></html>
    """
    r = extract_sections(html)
    assert r == {
        "business": "",
        "risk_factors": "",
        "md_and_a": "",
        "market_risk": "",
    }


def test_strip_html_removes_tags_and_collapses_whitespace() -> None:
    s = _strip_html("<p>Hello\n\n   world</p><br>")
    assert s == "Hello world"


def test_extract_handles_multiline_html() -> None:
    html = """
    <html>
      <head><title>nope</title></head>
      <body>
        <div>
          <h2>Item 1.<br>Business</h2>
          <p>Filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler filler.</p>
        </div>
        <div>
          <h2>Item 1A. Risk Factors</h2>
          <p>Risk risk risk risk risk risk risk risk risk risk risk risk risk risk risk risk risk risk risk risk risk.</p>
        </div>
      </body>
    </html>
    """
    r = extract_sections(html)
    assert "Filler" in r["business"]
    assert "Risk risk risk" in r["risk_factors"]


def test_extract_only_one_section_present() -> None:
    html = """
    <html><body>
    Item 1. Business The company manufactures precision instruments for laboratory use in scientific research.
    <p>more text more text more text more text more text more text more text</p>
    </body></html>
    """
    r = extract_sections(html)
    assert "precision instruments" in r["business"]
    assert r["risk_factors"] == ""
    assert r["md_and_a"] == ""
    assert r["market_risk"] == ""


def test_extract_case_insensitive() -> None:
    html = """
    <html><body>
    ITEM 1. BUSINESS The company sells alpaca wool sweaters and scarves online and in select retail stores.
    item 1A. risk factors Demand is seasonal and dependent on tourism and consumer discretionary spending.
    </body></html>
    """
    r = extract_sections(html)
    assert "alpaca wool" in r["business"]
    assert "seasonal" in r["risk_factors"]
