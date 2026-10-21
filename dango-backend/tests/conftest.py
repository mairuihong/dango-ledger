"""pytest fixtures：每个用例使用独立的临时 SQLite。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import create_app  # noqa: E402


@pytest.fixture()
def app(tmp_path: Path):
    return create_app(database_path=tmp_path / "dango-test.db", dev_token_enabled=True)


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db(app):
    return app.state.db
