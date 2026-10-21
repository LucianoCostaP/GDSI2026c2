from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.conftest import BOCA_HEADERS, RIVER_HEADERS


def test_unificada_flujo_completo_club_eventos_y_socios(client: TestClient) -> None:
    """
    Prueba integral de la API Unificada:
    1. El club Boca registra un evento futuro válido (>48hs).
    2. El club Boca registra un evento histórico (batch).
    3. El club Boca envía una carga de snapshot de socios.
    4. El club Boca envía una carga incremental de socios.
    5. Se verifica que Boca puede consultar tanto sus eventos como sus socios.
    6. Se verifica el aislamiento multi-tenant: River Plate no puede ver los eventos ni socios de Boca.
    """
    ahora = datetime.now(UTC)

    # 1. Crear evento futuro en Boca
    fecha_futura = (ahora + timedelta(days=5)).isoformat()
    res_ev = client.post(
        "/api/v1/eventos",
        headers=BOCA_HEADERS,
        json={
            "id_externo": "EVT-UNIF-01",
            "titulo": "Superclásico Apertura",
            "fecha_hora": fecha_futura,
            "lugar": "La Bombonera",
            "tipo": "Partido",
            "descripcion": "Fecha de torneo",
        },
    )
    assert res_ev.status_code == 201
    id_interno_evento = res_ev.json()["id_interno"]

    # 2. Cargar histórico en Boca
    res_hist = client.post(
        "/api/v1/eventos/historicos/batch",
        headers=BOCA_HEADERS,
        json=[
            {
                "id_externo": "EVT-HIST-UNIF-01",
                "titulo": "Final Libertadores 2000",
                "fecha_hora": "2000-06-21T21:00:00Z",
                "lugar": "Morumbi",
                "tipo": "Partido",
            }
        ],
    )
    assert res_hist.status_code == 207
    assert res_hist.json()["resumen"]["creados"] == 1

    # 3. Cargar padrón completo de socios en Boca
    res_soc = client.post(
        "/api/v1/socios/cargas/completa",
        headers=BOCA_HEADERS,
        json={
            "carga_id": "snap-unif-001",
            "pagina": 1,
            "total_paginas": 1,
            "socios": [
                {
                    "id_externo": "SOC-UNIF-1",
                    "dni": "35111222",
                    "numero_socio": "B-9901",
                    "nombre": "Socio Prueba Unificada",
                    "fecha_nacimiento": "1992-04-10",
                    "fecha_alta": "2015-01-01",
                    "estado_cuota": "al_dia",
                    "email": "socio.unif@boca.example.com",
                    "distancia_km": 3.2,
                    "fecha_modificacion": "2026-10-18T12:00:00Z",
                }
            ],
        },
    )
    assert res_soc.status_code == 202
    assert res_soc.json()["estado"] == "exitosa"

    # 4. Cargar novedad incremental en Boca
    res_inc = client.post(
        "/api/v1/socios/cargas/incremental",
        headers=BOCA_HEADERS,
        json={
            "lote_id": "lote-unif-001",
            "desde": "2026-10-18T10:00:00Z",
            "hasta": "2026-10-18T14:00:00Z",
            "cambios": [
                {
                    "accion": "alta",
                    "socio": {
                        "id_externo": "SOC-UNIF-2",
                        "dni": "35333444",
                        "numero_socio": "B-9902",
                        "nombre": "Segundo Socio Unificado",
                        "fecha_nacimiento": "1995-08-20",
                        "fecha_alta": "2020-03-15",
                        "estado_cuota": "moroso",
                        "email": "segundo@boca.example.com",
                        "distancia_km": 8.0,
                        "fecha_modificacion": "2026-10-18T13:00:00Z",
                    },
                }
            ],
        },
    )
    assert res_inc.status_code == 202
    assert res_inc.json()["creados"] == 1

    # 5. Consultas desde Boca: ambos recursos visibles
    boca_eventos = client.get("/api/v1/eventos", headers=BOCA_HEADERS).json()
    assert any(e["id_interno"] == id_interno_evento for e in boca_eventos)

    boca_socios = client.get("/api/v1/socios", headers=BOCA_HEADERS).json()
    assert len(boca_socios) == 2

    # 6. Aislamiento Multi-Tenant: River Plate NO puede ver ni eventos ni socios de Boca
    river_eventos = client.get("/api/v1/eventos", headers=RIVER_HEADERS).json()
    assert not any(e["id_interno"] == id_interno_evento for e in river_eventos)
    assert not any(e["id_externo"] == "EVT-UNIF-01" for e in river_eventos)

    river_socios = client.get("/api/v1/socios", headers=RIVER_HEADERS).json()
    assert not any(s["id_externo"] == "SOC-UNIF-1" for s in river_socios)
    assert not any(s["id_externo"] == "SOC-UNIF-2" for s in river_socios)
