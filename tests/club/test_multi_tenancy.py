from fastapi.testclient import TestClient

from tests.conftest import BOCA_HEADERS, RACING_HEADERS, RIVER_HEADERS


def test_multi_tenancy_data_isolation(client: TestClient) -> None:
    # 1. Boca carga sus socios
    boca_payload = {
        "carga_id": "full-boca-mt",
        "pagina": 1,
        "total_paginas": 1,
        "socios": [
            {
                "id_externo": "SOC-CABJ-1",
                "dni": "11110000",
                "numero_socio": "CABJ-01",
                "nombre": "Socio de Boca",
                "fecha_nacimiento": "1990-01-01",
                "fecha_alta": "2020-01-01",
                "estado_cuota": "al_dia",
                "email": "socio@boca.org",
                "distancia_km": 1.0,
                "fecha_modificacion": "2026-10-17T12:00:00Z",
            }
        ],
    }
    client.post(
        "/api/v1/socios/cargas/completa", json=boca_payload, headers=BOCA_HEADERS
    )

    # 2. River carga sus socios (pudiendo incluso tener el mismo id_externo relativo o numero_socio local, aislado por club_id)
    river_payload = {
        "carga_id": "full-river-mt",
        "pagina": 1,
        "total_paginas": 1,
        "socios": [
            {
                "id_externo": "SOC-CARP-1",
                "dni": "22220000",
                "numero_socio": "CARP-01",
                "nombre": "Socio de River",
                "fecha_nacimiento": "1992-02-02",
                "fecha_alta": "2021-02-02",
                "estado_cuota": "al_dia",
                "email": "socio@river.org",
                "distancia_km": 10.0,
                "fecha_modificacion": "2026-10-17T12:00:00Z",
            }
        ],
    }
    client.post(
        "/api/v1/socios/cargas/completa", json=river_payload, headers=RIVER_HEADERS
    )

    # 3. Consulta Boca: sólo ve al socio de Boca
    boca_socios = client.get("/api/v1/socios", headers=BOCA_HEADERS).json()
    assert len(boca_socios) == 1
    assert boca_socios[0]["id_externo"] == "SOC-CABJ-1"
    assert boca_socios[0]["nombre"] == "Socio de Boca"

    # 4. Consulta River: sólo ve al socio de River
    river_socios = client.get("/api/v1/socios", headers=RIVER_HEADERS).json()
    assert len(river_socios) == 1
    assert river_socios[0]["id_externo"] == "SOC-CARP-1"
    assert river_socios[0]["nombre"] == "Socio de River"

    # 5. Consulta Racing: no ve ningún socio
    racing_socios = client.get("/api/v1/socios", headers=RACING_HEADERS).json()
    assert len(racing_socios) == 0
