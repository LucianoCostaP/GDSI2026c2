from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.repositories.factory import get_evento_repository
from app.repositories.memory_repo import MemoryEventoRepository

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


@pytest.fixture(autouse=True)
def clean_database() -> Generator[None, None, None]:
    """Limpia los datos de prueba entre tests preservando los clubes semilla."""
    if settings.db_engine.lower() == "postgres":
        try:
            db = SessionLocal()
            db.execute(
                text(
                    "TRUNCATE TABLE socios_staging_completa, socios_cargas_rechazos, "
                    "socios_cargas_paginas, socios_cargas, socios, "
                    "eventos_cambios_pendientes, eventos_visibles, eventos_pendientes_verificacion CASCADE;"
                )
            )
            db.commit()
            db.close()
        except Exception:  # noqa: BLE001, S110
            pass
    yield


@pytest.fixture(autouse=True)
def reset_memory_repo():
    """Reinicia las tablas en memoria antes de cada test para aislamiento estricto."""
    repo = get_evento_repository()
    if isinstance(repo, MemoryEventoRepository):
        repo.tabla_eventos_pendientes.clear()
        repo.tabla_eventos_visibles.clear()
        repo.tabla_eventos_cambios_pendientes.clear()


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
