from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.main import app

BOCA_TOKEN = "token_boca_abc123"
RIVER_TOKEN = "token_river_def456"
RACING_TOKEN = "token_racing_ghi789"

BOCA_HEADERS = {
    "Authorization": f"Bearer {BOCA_TOKEN}",
    "Content-Type": "application/json",
}
RIVER_HEADERS = {
    "Authorization": f"Bearer {RIVER_TOKEN}",
    "Content-Type": "application/json",
}
RACING_HEADERS = {
    "Authorization": f"Bearer {RACING_TOKEN}",
    "Content-Type": "application/json",
}


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


# Fixtures individuales para compatibilidad con suite de eventos
@pytest.fixture
def token_boca():
    return BOCA_TOKEN


@pytest.fixture
def token_river():
    return RIVER_TOKEN


@pytest.fixture
def headers_boca():
    return dict(BOCA_HEADERS)


@pytest.fixture
def headers_river():
    return dict(RIVER_HEADERS)
