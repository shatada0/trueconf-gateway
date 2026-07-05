import os

# Окружение - до импорта app.* (pydantic-settings читает его при импорте)
os.environ.setdefault("TRUECONF_BASE_URL", "http://mock")
os.environ.setdefault("TRUECONF_CLIENT_ID", "cid")
os.environ.setdefault("TRUECONF_CLIENT_SECRET", "secret")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"
