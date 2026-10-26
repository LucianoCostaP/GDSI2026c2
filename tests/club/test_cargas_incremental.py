from fastapi.testclient import TestClient

from tests.conftest import BOCA_HEADERS


def test_carga_incremental_alta_modificacion_baja(client: TestClient) -> None:
    # 1. Cargar socio inicial con snapshot
    snapshot = {
        "carga_id": "full-init",
        "pagina": 1,
        "total_paginas": 1,
        "socios": [
            {
                "id_externo": "SOC-INC-1",
                "dni": "20000001",
                "numero_socio": "B-INC-1",
                "nombre": "Socio Base",
                "fecha_nacimiento": "1985-04-12",
                "fecha_alta": "2010-03-01",
                "estado_cuota": "al_dia",
                "email": "base@example.org",
                "distancia_km": 12.4,
                "fecha_modificacion": "2026-10-16T12:30:00Z",
            }
        ],
    }
    client.post("/api/v1/socios/cargas/completa", json=snapshot, headers=BOCA_HEADERS)

    # 2. Enviar delta incremental:
    # - Modificar SOC-INC-1 (pasa a moroso y cambia email)
    # - Dar de alta SOC-INC-2
    # - Dar de baja SOC-INC-3 (no existe, reportará rechazo)
    delta = {
        "lote_id": "delta-001",
        "desde": "2026-10-16T12:00:00Z",
        "hasta": "2026-10-17T12:00:00Z",
        "cambios": [
            {
                "accion": "modificacion",
                "socio": {
                    "id_externo": "SOC-INC-1",
                    "dni": "20000001",
                    "numero_socio": "B-INC-1",
                    "nombre": "Socio Base Modificado",
                    "fecha_nacimiento": "1985-04-12",
                    "fecha_alta": "2010-03-01",
                    "estado_cuota": "moroso",
                    "email": "nuevo_email@example.org",
                    "distancia_km": 12.4,
                    "fecha_modificacion": "2026-10-17T11:00:00Z",
                },
            },
            {
                "accion": "alta",
                "socio": {
                    "id_externo": "SOC-INC-2",
                    "dni": "20000002",
                    "numero_socio": "B-INC-2",
                    "nombre": "Nuevo Socio Alta",
                    "fecha_nacimiento": "1995-08-20",
                    "fecha_alta": "2026-10-17",
                    "estado_cuota": "al_dia",
                    "email": "alta@example.org",
                    "distancia_km": 5.0,
                    "fecha_modificacion": "2026-10-17T11:30:00Z",
                },
            },
            {
                "accion": "baja",
                "id_externo": "SOC-INEXISTENTE",
            },
        ],
    }

    res = client.post(
        "/api/v1/socios/cargas/incremental", json=delta, headers=BOCA_HEADERS
    )
    assert res.status_code == 202
    data = res.json()
    assert data["lote_id"] == "delta-001"
    assert data["estado"] == "exitosa"
    assert data["creados"] == 1
    assert data["actualizados"] == 1
    assert data["desactivados"] == 0
    assert data["rechazados"] == 1
    assert len(data["detalles_rechazos"]) == 1
    assert data["detalles_rechazos"][0]["id_externo"] == "SOC-INEXISTENTE"
    assert data["detalles_rechazos"][0]["codigo"] == "SOCIO_NOT_FOUND"

    # Verificar efectos en la base de datos
    socios = client.get("/api/v1/socios", headers=BOCA_HEADERS).json()
    assert len(socios) == 2
    s1 = next(s for s in socios if s["id_externo"] == "SOC-INC-1")
    assert s1["estado_cuota"] == "moroso"
    assert s1["email"] == "nuevo_email@example.org"

    s2 = next(s for s in socios if s["id_externo"] == "SOC-INC-2")
    assert s2["activo"] is True
    assert s2["nombre"] == "Nuevo Socio Alta"


def test_carga_incremental_baja_deactivates_socio(client: TestClient) -> None:
    # 1. Cargar socio
    snapshot = {
        "carga_id": "full-baja-test",
        "pagina": 1,
        "total_paginas": 1,
        "socios": [
            {
                "id_externo": "SOC-BAJA-1",
                "dni": "33333333",
                "numero_socio": "B-333",
                "nombre": "Socio Para Baja",
                "fecha_nacimiento": "1990-01-01",
                "fecha_alta": "2015-01-01",
                "estado_cuota": "al_dia",
                "email": "baja@example.org",
                "distancia_km": 8.0,
                "fecha_modificacion": "2026-10-16T12:00:00Z",
            }
        ],
    }
    client.post("/api/v1/socios/cargas/completa", json=snapshot, headers=BOCA_HEADERS)

    # 2. Aplicar baja
    delta = {
        "lote_id": "delta-baja-01",
        "desde": "2026-10-16T12:00:00Z",
        "hasta": "2026-10-17T12:00:00Z",
        "cambios": [
            {
                "accion": "baja",
                "id_externo": "SOC-BAJA-1",
            }
        ],
    }
    res = client.post(
        "/api/v1/socios/cargas/incremental", json=delta, headers=BOCA_HEADERS
    )
    assert res.status_code == 202
    assert res.json()["desactivados"] == 1

    # Verificar que el socio está inactivo
    socio = client.get(
        "/api/v1/socios?id_externo=SOC-BAJA-1", headers=BOCA_HEADERS
    ).json()[0]
    assert socio["activo"] is False


def test_carga_incremental_idempotency(client: TestClient) -> None:
    delta = {
        "lote_id": "delta-idem-01",
        "desde": "2026-10-16T12:00:00Z",
        "hasta": "2026-10-17T12:00:00Z",
        "cambios": [
            {
                "accion": "alta",
                "socio": {
                    "id_externo": "SOC-IDEM",
                    "dni": "44444444",
                    "numero_socio": "B-IDEM",
                    "nombre": "Idem Socio",
                    "fecha_nacimiento": "1990-01-01",
                    "fecha_alta": "2020-01-01",
                    "estado_cuota": "al_dia",
                    "email": "idem@example.org",
                    "distancia_km": 1.0,
                    "fecha_modificacion": "2026-10-17T12:00:00Z",
                },
            }
        ],
    }
    res1 = client.post(
        "/api/v1/socios/cargas/incremental", json=delta, headers=BOCA_HEADERS
    )
    assert res1.status_code == 202
    assert res1.json()["creados"] == 1

    # Reintento con mismo lote_id y contenido
    res2 = client.post(
        "/api/v1/socios/cargas/incremental", json=delta, headers=BOCA_HEADERS
    )
    assert res2.status_code == 202
    assert res2.json()["creados"] == 1

    # Verificar que no se duplicó el registro
    socios = client.get(
        "/api/v1/socios?id_externo=SOC-IDEM", headers=BOCA_HEADERS
    ).json()
    assert len(socios) == 1
