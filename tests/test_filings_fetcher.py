from __future__ import annotations

from app.filings.fetcher import ten_k_url


def test_ten_k_url_constructs_correct_path() -> None:
    """Regression: filings.fetcher.ten_k_url must include /edgar/data/ segment.

    Before the fix, _SEC_ARCHIVES was 'https://www.sec.gov/Archives' which
    produced a 404 for every 10-K. The canonical SEC path is
    /Archives/edgar/data/{cik}/{accession-no-dashes}/{primary_document}.
    """
    url = ten_k_url(
        cik="0000087347",
        accession="0001193125-26-021017",
        primary_document="slb-20251231.htm",
    )
    assert url == (
        "https://www.sec.gov/Archives/edgar/data/"
        "87347/000119312526021017/slb-20251231.htm"
    ), url


def test_ten_k_url_strips_accession_dashes() -> None:
    """Accession dashes must be removed for the directory path."""
    url = ten_k_url(
        cik="0000789019",
        accession="0001193125-26-021017",
        primary_document="msft.htm",
    )
    assert "000119312526021017" in url
    assert "0001193125-26-021017" not in url


def test_ten_k_url_strips_cik_leading_zeros() -> None:
    """CIK leading zeros are stripped (int() cast) — canonical SEC format."""
    url = ten_k_url(
        cik="0000789019",
        accession="000119312526021017",
        primary_document="msft.htm",
    )
    assert "/Archives/edgar/data/789019/" in url
    assert "/Archives/edgar/data/0000789019/" not in url
