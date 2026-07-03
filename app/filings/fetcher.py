"""Download 10-K HTML from SEC archives with retry."""

from __future__ import annotations

import time

import httpx

from app.logging import get_logger

log = get_logger(__name__)

_SEC_ARCHIVES = "https://www.sec.gov/Archives"

_MAX_ATTEMPTS = 3
_RETRY_DELAY_S = 0.1
_USER_AGENT = "FinancialAdviser research@example.com"


def ten_k_url(cik: str, accession: str, primary_document: str) -> str:
    """Build URL for the 10-K primary document on SEC archives."""
    clean_acc = accession.replace("-", "")
    return f"{_SEC_ARCHIVES}/{int(cik)}/{clean_acc}/{primary_document}"


def download_10k_html(cik: str, accession: str, primary_document: str) -> str:
    """Download 10-K HTML with up to 3 retries on HTTP errors."""
    url = ten_k_url(cik, accession, primary_document)
    headers = {"User-Agent": _USER_AGENT, "Accept-Encoding": "gzip, deflate"}
    last_error: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            with httpx.Client(timeout=30.0, follow_redirects=True, headers=headers) as client:
                resp = client.get(url)
                resp.raise_for_status()
                log.info(
                    "filings.downloaded",
                    url=url,
                    attempt=attempt,
                    status=resp.status_code,
                )
                return resp.text
        except httpx.HTTPError as e:
            last_error = e
            log.warning("filings.download_retry", attempt=attempt, error=str(e), url=url)
            if attempt < _MAX_ATTEMPTS:
                time.sleep(_RETRY_DELAY_S * attempt)
    raise httpx.HTTPError(
        f"failed to download {url} after {_MAX_ATTEMPTS} attempts: {last_error}"
    )
