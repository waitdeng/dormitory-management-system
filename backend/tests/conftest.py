"""Shared pytest fixtures. Integration tests use real MySQL (spec §13)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

# Ensure backend package is importable
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Default test settings — override via env in CI / Docker
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("MYSQL_HOST", os.environ.get("MYSQL_HOST", "127.0.0.1"))
os.environ.setdefault("MYSQL_PORT", os.environ.get("MYSQL_PORT", "3306"))
os.environ.setdefault("MYSQL_DATABASE", os.environ.get("MYSQL_DATABASE", "dms"))
os.environ.setdefault("MYSQL_USER", os.environ.get("MYSQL_USER", "dms_user"))
os.environ.setdefault("MYSQL_PASSWORD", os.environ.get("MYSQL_PASSWORD", "dms_dev_password"))
# Admin credentials used by seed + login tests. Never hardcode in test bodies.
os.environ.setdefault("DMS_ADMIN_USERNAME", os.environ.get("DMS_ADMIN_USERNAME", "admin"))
os.environ.setdefault("DMS_ADMIN_PASSWORD", os.environ.get("DMS_ADMIN_PASSWORD", "admin12345"))


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
async def _reset_engine_pool():
    """Dispose pooled connections so each test gets a loop-safe engine.

    SQLAlchemy async pools hold sockets bound to an event loop; pytest-asyncio
    creates a new loop per test. Disposing between tests avoids
    "Future attached to a different loop" errors.
    """
    from app.core.database import engine

    yield
    await engine.dispose()


@pytest.fixture
async def client():
    """HTTP client bound to the FastAPI app (no live server needed)."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
