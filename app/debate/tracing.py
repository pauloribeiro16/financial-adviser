from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


class _NoopHandler:
    def __repr__(self) -> str:
        return "<NoopHandler>"


class _NoopContext:
    def update_current_trace(self, **_kw: Any) -> None:
        return None

    def update_current_observation(self, **_kw: Any) -> None:
        return None


class DebateTrace:
    """Langfuse v4 wiring for one debate.

    When ``LANGFUSE_PUBLIC_KEY`` and ``LANGFUSE_SECRET_KEY`` are set, exposes a
    real ``langfuse.langchain.CallbackHandler`` (so every ``invoke(..., config=cfg)``
    auto-creates a child span) plus an ``attributes(...)`` context manager that
    forwards ``session_id`` / ``tags`` / ``metadata`` / ``trace_name`` to
    ``langfuse.propagate_attributes`` so the active trace picks them up.

    When the env vars are missing, both pieces degrade to no-op stand-ins so
    the runner still works offline.
    """

    def __init__(self) -> None:
        self._enabled = bool(
            os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
        )
        self._handler: Any = _NoopHandler()
        self._ctx: Any = _NoopContext()
        if self._enabled:
            try:
                from langfuse.langchain import CallbackHandler

                self._handler = CallbackHandler()
                self._ctx = _NoopContext()
            except Exception:
                self._enabled = False
                self._handler = _NoopHandler()
                self._ctx = _NoopContext()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def callback(self) -> Any:
        return self._handler

    @contextmanager
    def attributes(
        self,
        *,
        session_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        name: str | None = None,
    ) -> Iterator[Any]:
        """Apply trace-level attributes to the active span for the duration of
        the ``with`` block. No-op when Langfuse env vars are missing.

        Uses ``langfuse.propagate_attributes`` under the hood (Langfuse v4's
        OTEL-based replacement for the legacy ``langfuse_context.update_current_trace``
        call). Returns the callback handler as the yielded value so callers can
        both scope attributes AND pipe the handler into ``engine.run_debate``.
        """
        if not self._enabled:
            yield self._handler
            return
        try:
            from langfuse import propagate_attributes

            kw: dict[str, Any] = {}
            if session_id is not None:
                kw["session_id"] = session_id
            if tags is not None:
                kw["tags"] = tags
            if metadata is not None:
                kw["metadata"] = metadata
            if name is not None:
                kw["trace_name"] = name
            if kw:
                with propagate_attributes(**kw):
                    yield self._handler
            else:
                yield self._handler
        except Exception:
            yield self._handler
