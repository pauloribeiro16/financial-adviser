from __future__ import annotations

import pytest

from app.providers import ProviderRegistry


@pytest.fixture(scope="session", autouse=True)
def _initialize_providers() -> None:
    ProviderRegistry.initialize_defaults()
