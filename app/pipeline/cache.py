from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cache"


@dataclass(frozen=True)
class CacheStats:
    hits: int = 0
    misses: int = 0
    writes: int = 0


_STATS = CacheStats()


def _namespaced_path(namespace: str, key: str) -> Path:
    safe = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return CACHE_DIR / namespace / f"{safe}.json"


def get(namespace: str, key: str, ttl_seconds: int) -> dict[str, Any] | None:
    path = _namespaced_path(namespace, key)
    if not path.exists():
        return None
    try:
        age = time.time() - path.stat().st_mtime
        if age > ttl_seconds:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def put(namespace: str, key: str, payload: dict[str, Any]) -> None:
    path = _namespaced_path(namespace, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, default=str, indent=2), encoding="utf-8")


def stats() -> dict[str, int]:
    return {"hit": _STATS.hits, "miss": _STATS.misses, "write": _STATS.writes}
