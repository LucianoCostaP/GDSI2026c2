from fastapi.testclient import TestClient

from tests.conftest import BOCA_HEADERS, RACING_HEADERS


def test_freshness_without_loads(client: TestClient) -> None:
    # Racing no tiene ninguna carga registrada
    res = client.get("/api/v1/socios/freshness", headers=RACING_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["esta_desactualizado"] is True
    assert data["ultima_carga_exitosa"] is None
    assert data["advertencia"] is not None


def test_freshness_after_successful_load(client: TestClient) -> None:
    # Cargar socio en Boca
    payload = {
        "carga_id": "full-fresh-boca",
        "pagina": 1,
        "total_paginas": 1,
        "socios": [
            {
                "id_externo": "SOC-FRESH",
                "dni": "99990000",
                "numero_socio": "B-FRESH",
                "nombre": "Socio Fresco",
                "fecha_nacimiento": "1995-01-01",
                "fecha_alta": "2022-01-01",
                "estado_cuota": "al_dia",
                "email": "fresh@example.org",
                "distancia_km": 1.0,
                "fecha_modificacion": "2026-10-17T12:00:00Z",
            }
        ],
    }
    client.post("/api/v1/socios/cargas/completa", json=payload, headers=BOCA_HEADERS)

    res = client.get("/api/v1/socios/freshness", headers=BOCA_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["esta_desactualizado"] is False
    assert data["ultima_carga_exitosa"] is not None
    assert data["advertencia"] is None
    assert data["antiguedad_horas"] is not None
    assert data["antiguedad_horas"] < 1.0
