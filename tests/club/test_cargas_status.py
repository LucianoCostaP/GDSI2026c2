from fastapi.testclient import TestClient

from tests.conftest import BOCA_HEADERS, RIVER_HEADERS


def test_get_carga_status_success(client: TestClient) -> None:
    # 1. Ejecutar una carga con un registro válido y uno inválido
    payload = {
        "carga_id": "full-status-test",
        "pagina": 1,
        "total_paginas": 1,
        "socios": [
            {
                "id_externo": "SOC-VAL-1",
                "dni": "55555555",
                "numero_socio": "B-555",
                "nombre": "Valido",
                "fecha_nacimiento": "1990-01-01",
                "fecha_alta": "2020-01-01",
                "estado_cuota": "al_dia",
                "email": "val@example.org",
                "distancia_km": 1.0,
                "fecha_modificacion": "2026-10-17T12:00:00Z",
            },
            {
                "id_externo": "SOC-INV-1",
                "dni": "66666666",
                "numero_socio": "B-666",
                "nombre": "Invalido",
                "fecha_nacimiento": "1990-01-01",
                "fecha_alta": "2020-01-01",
                "estado_cuota": "al_dia",
                "email": "correo_invalido_sin_arroba",  # Email inválido
                "distancia_km": 1.0,
                "fecha_modificacion": "2026-10-17T12:00:00Z",
            },
        ],
    }
    client.post("/api/v1/socios/cargas/completa", json=payload, headers=BOCA_HEADERS)

    # 2. Consultar el estado de la carga
    res = client.get("/api/v1/socios/cargas/full-status-test", headers=BOCA_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["carga_id"] == "full-status-test"
    assert data["tipo"] == "completa"
    assert data["estado"] == "exitosa"
    assert data["creados"] == 1
    assert data["rechazados"] == 1
    assert len(data["detalles_rechazos"]) == 1
    assert data["detalles_rechazos"][0]["id_externo"] == "SOC-INV-1"


def test_get_carga_status_not_found(client: TestClient) -> None:
    res = client.get("/api/v1/socios/cargas/no-existe-123", headers=BOCA_HEADERS)
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"


def test_get_carga_status_cross_club_isolation(client: TestClient) -> None:
    # Boca sube una carga
    payload = {
        "carga_id": "carga-privada-boca",
        "pagina": 1,
        "total_paginas": 1,
        "socios": [
            {
                "id_externo": "SOC-BOCA",
                "dni": "77777777",
                "numero_socio": "B-777",
                "nombre": "Socio Boca",
                "fecha_nacimiento": "1990-01-01",
                "fecha_alta": "2020-01-01",
                "estado_cuota": "al_dia",
                "email": "boca@example.org",
                "distancia_km": 1.0,
                "fecha_modificacion": "2026-10-17T12:00:00Z",
            }
        ],
    }
    client.post("/api/v1/socios/cargas/completa", json=payload, headers=BOCA_HEADERS)

    # River intenta consultar la carga de Boca -> debe devolver 404 Not Found (no revelar existencia)
    res = client.get("/api/v1/socios/cargas/carga-privada-boca", headers=RIVER_HEADERS)
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"
