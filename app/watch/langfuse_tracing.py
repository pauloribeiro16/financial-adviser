from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from app.debate.tracing import DebateTrace
from app.logging import get_logger

log = get_logger(__name__)


def build_surveillance_session_id(sector: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"surveillance-{sector.lower().replace(' ', '-')}-{ts}"


@contextmanager
def surveillance_trace(sector: str) -> Iterator[DebateTrace]:
    trace = DebateTrace()
    session_id = build_surveillance_session_id(sector)
    tags: list[str] = ["phase:surveillance", f"sector:{sector}"]
    metadata: dict[str, Any] = {"sector": sector, "phase": "surveillance"}
    name = f"surveillance.{sector.lower().replace(' ', '-')}"
    log.info(
        "watch.surveillance_trace.start",
        sector=sector,
        session_id=session_id,
        enabled=trace.enabled,
    )
    with trace.attributes(
        session_id=session_id,
        tags=tags,
        metadata=metadata,
        name=name,
    ):
        yield trace
    log.info("watch.surveillance_trace.end", sector=sector, session_id=session_id)
