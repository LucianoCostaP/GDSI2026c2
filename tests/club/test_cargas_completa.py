from fastapi.testclient import TestClient

from tests.conftest import BOCA_HEADERS


def test_carga_completa_single_page_success(client: TestClient) -> None:
    payload = {
        "carga_id": "full-boca-001",
        "pagina": 1,
        "total_paginas": 1,
        "socios": [
            {
                "id_externo": "SOC-101",
                "dni": "30111222",
                "numero_socio": "B-001",
                "nombre": "Juan Pérez",
                "fecha_nacimiento": "1990-05-15",
                "fecha_alta": "2015-02-01",
                "fecha_baja_previa": None,
                "estado_cuota": "al_dia",
                "email": "juan.perez@example.com",
                "distancia_km": 5.5,
                "localidad": "La Boca",
                "fecha_modificacion": "2026-10-16T12:00:00Z",
            },
            {
                "id_externo": "SOC-102",
                "dni": "30222333",
                "numero_socio": "B-002",
                "nombre": "Martín Gómez",
                "fecha_nacimiento": "1988-11-20",
                "fecha_alta": "2018-06-10",
                "fecha_baja_previa": None,
                "estado_cuota": "moroso",
                "email": "martin.gomez@example.com",
                "distancia_km": 15.0,
                "localidad": "Quilmes",
                "fecha_modificacion": "2026-10-16T12:00:00Z",
            },
        ],
    }

    res = client.post(
        "/api/v1/socios/cargas/completa", json=payload, headers=BOCA_HEADERS
    )
    assert res.status_code == 202
    data = res.json()
    assert data["carga_id"] == "full-boca-001"
    assert data["pagina"] == 1
    assert data["total_paginas"] == 1
    assert data["estado"] == "exitosa"
    assert len(data["rechazos"]) == 0

    # Verificar que los socios fueron persistidos y activados
    socios_res = client.get("/api/v1/socios", headers=BOCA_HEADERS)
    assert socios_res.status_code == 200
    socios = socios_res.json()
    assert len(socios) == 2
    assert socios[0]["id_externo"] == "SOC-101"
    assert socios[0]["activo"] is True
    assert socios[1]["id_externo"] == "SOC-102"
    assert socios[1]["estado_cuota"] == "moroso"


def test_carga_completa_multipage_staging_and_activation(client: TestClient) -> None:
    # Página 1 de 2
    page1 = {
        "carga_id": "full-boca-multi",
        "pagina": 1,
        "total_paginas": 2,
        "socios": [
            {
                "id_externo": "SOC-201",
                "dni": "40111111",
                "numero_socio": "B-201",
                "nombre": "Carlos Tevez",
                "fecha_nacimiento": "1984-02-05",
                "fecha_alta": "2001-01-01",
                "estado_cuota": "al_dia",
                "email": "carlos@boca.org",
                "distancia_km": 0.5,
                "fecha_modificacion": "2026-10-16T10:00:00Z",
            }
        ],
    }
    res1 = client.post(
        "/api/v1/socios/cargas/completa", json=page1, headers=BOCA_HEADERS
    )
    assert res1.status_code == 202
    assert res1.json()["estado"] == "recibiendo"

    # En este punto el snapshot NO debe estar activo todavía
    socios_mid = client.get("/api/v1/socios", headers=BOCA_HEADERS).json()
    assert len(socios_mid) == 0

    # Página 2 de 2
    page2 = {
        "carga_id": "full-boca-multi",
        "pagina": 2,
        "total_paginas": 2,
        "socios": [
            {
                "id_externo": "SOC-202",
                "dni": "40222222",
                "numero_socio": "B-202",
                "nombre": "Juan Román",
                "fecha_nacimiento": "1978-06-24",
                "fecha_alta": "1996-11-10",
                "estado_cuota": "al_dia",
                "email": "roman@boca.org",
                "distancia_km": 2.1,
                "fecha_modificacion": "2026-10-16T10:00:00Z",
            }
        ],
    }
    res2 = client.post(
        "/api/v1/socios/cargas/completa", json=page2, headers=BOCA_HEADERS
    )
    assert res2.status_code == 202
    assert res2.json()["estado"] == "exitosa"

    # Ahora ambos socios deben estar activos
    socios_final = client.get("/api/v1/socios", headers=BOCA_HEADERS).json()
    assert len(socios_final) == 2
    ids = {s["id_externo"] for s in socios_final}
    assert ids == {"SOC-201", "SOC-202"}


def test_carga_completa_idempotency(client: TestClient) -> None:
    payload = {
        "carga_id": "full-boca-idem",
        "pagina": 1,
        "total_paginas": 2,
        "socios": [
            {
                "id_externo": "SOC-301",
                "dni": "50111111",
                "numero_socio": "B-301",
                "nombre": "Socio Idempotente",
                "fecha_nacimiento": "1992-01-01",
                "fecha_alta": "2020-01-01",
                "estado_cuota": "al_dia",
                "email": "idem@example.com",
                "distancia_km": 10.0,
                "fecha_modificacion": "2026-10-16T10:00:00Z",
            }
        ],
    }
    res1 = client.post(
        "/api/v1/socios/cargas/completa", json=payload, headers=BOCA_HEADERS
    )
    assert res1.status_code == 202

    # Reintento idéntico
    res2 = client.post(
        "/api/v1/socios/cargas/completa", json=payload, headers=BOCA_HEADERS
    )
    assert res2.status_code == 202
    assert "idempotente" in res2.json()["mensaje"].lower()


def test_carga_completa_conflict_different_content(client: TestClient) -> None:
    payload1 = {
        "carga_id": "full-boca-conflict",
        "pagina": 1,
        "total_paginas": 2,
        "socios": [
            {
                "id_externo": "SOC-401",
                "dni": "60111111",
                "numero_socio": "B-401",
                "nombre": "Nombre Original",
                "fecha_nacimiento": "1992-01-01",
                "fecha_alta": "2020-01-01",
                "estado_cuota": "al_dia",
                "email": "orig@example.com",
                "distancia_km": 10.0,
                "fecha_modificacion": "2026-10-16T10:00:00Z",
            }
        ],
    }
    res1 = client.post(
        "/api/v1/socios/cargas/completa", json=payload1, headers=BOCA_HEADERS
    )
    assert res1.status_code == 202

    # Intento de enviar contenido diferente bajo el mismo carga_id y pagina
    payload2 = dict(payload1)
    payload2["socios"] = [
        {
            "id_externo": "SOC-401-DIFF",
            "dni": "60222222",
            "numero_socio": "B-401-DIFF",
            "nombre": "Nombre Cambiado",
            "fecha_nacimiento": "1992-01-01",
            "fecha_alta": "2020-01-01",
            "estado_cuota": "al_dia",
            "email": "diff@example.com",
            "distancia_km": 12.0,
            "fecha_modificacion": "2026-10-16T10:00:00Z",
        }
    ]
    res2 = client.post(
        "/api/v1/socios/cargas/completa", json=payload2, headers=BOCA_HEADERS
    )
    assert res2.status_code == 409
    assert res2.json()["error"]["code"] == "CONFLICT"


def test_carga_completa_cross_page_duplicate_dni_retains_last_good_copy(
    client: TestClient,
) -> None:
    # 1. Crear una primera carga válida previa
    primera_carga = {
        "carga_id": "full-boca-good",
        "pagina": 1,
        "total_paginas": 1,
        "socios": [
            {
                "id_externo": "SOC-GOOD-1",
                "dni": "10000001",
                "numero_socio": "B-GOOD-1",
                "nombre": "Socio Valido Anterior",
                "fecha_nacimiento": "1980-01-01",
                "fecha_alta": "2010-01-01",
                "estado_cuota": "al_dia",
                "email": "good@example.com",
                "distancia_km": 4.0,
                "fecha_modificacion": "2026-10-16T08:00:00Z",
            }
        ],
    }
    res_good = client.post(
        "/api/v1/socios/cargas/completa", json=primera_carga, headers=BOCA_HEADERS
    )
    assert res_good.status_code == 202
    assert res_good.json()["estado"] == "exitosa"

    # 2. Intentar una nueva carga de 2 páginas con DNI duplicado entre la pág 1 y la pág 2
    p1 = {
        "carga_id": "full-boca-dup-dni",
        "pagina": 1,
        "total_paginas": 2,
        "socios": [
            {
                "id_externo": "SOC-DUP-A",
                "dni": "88888888",
                "numero_socio": "B-DUPA",
                "nombre": "Persona A",
                "fecha_nacimiento": "1990-01-01",
                "fecha_alta": "2020-01-01",
                "estado_cuota": "al_dia",
                "email": "a@example.com",
                "distancia_km": 3.0,
                "fecha_modificacion": "2026-10-16T11:00:00Z",
            }
        ],
    }
    p2 = {
        "carga_id": "full-boca-dup-dni",
        "pagina": 2,
        "total_paginas": 2,
        "socios": [
            {
                "id_externo": "SOC-DUP-B",
                "dni": "88888888",  # MISMO DNI
                "numero_socio": "B-DUPB",
                "nombre": "Persona B",
                "fecha_nacimiento": "1991-01-01",
                "fecha_alta": "2021-01-01",
                "estado_cuota": "al_dia",
                "email": "b@example.com",
                "distancia_km": 3.0,
                "fecha_modificacion": "2026-10-16T11:00:00Z",
            }
        ],
    }

    res_p1 = client.post(
        "/api/v1/socios/cargas/completa", json=p1, headers=BOCA_HEADERS
    )
    assert res_p1.status_code == 202

    res_p2 = client.post(
        "/api/v1/socios/cargas/completa", json=p2, headers=BOCA_HEADERS
    )
    assert res_p2.status_code == 422
    assert res_p2.json()["error"]["code"] == "CONSISTENCY_CHECK_FAILED"

    # Verificar que el padrón retuvo la copia buena previa intacta
    socios_actuales = client.get("/api/v1/socios", headers=BOCA_HEADERS).json()
    assert len(socios_actuales) == 1
    assert socios_actuales[0]["id_externo"] == "SOC-GOOD-1"


def test_carga_completa_deactivates_omitted_members(client: TestClient) -> None:
    # Carga 1: SOC-A y SOC-B
    c1 = {
        "carga_id": "full-boca-omit-1",
        "pagina": 1,
        "total_paginas": 1,
        "socios": [
            {
                "id_externo": "SOC-A",
                "dni": "70000001",
                "numero_socio": "B-A",
                "nombre": "Socio A",
                "fecha_nacimiento": "1990-01-01",
                "fecha_alta": "2020-01-01",
                "estado_cuota": "al_dia",
                "email": "a@boca.org",
                "distancia_km": 2.0,
                "fecha_modificacion": "2026-10-16T10:00:00Z",
            },
            {
                "id_externo": "SOC-B",
                "dni": "70000002",
                "numero_socio": "B-B",
                "nombre": "Socio B",
                "fecha_nacimiento": "1991-01-01",
                "fecha_alta": "2021-01-01",
                "estado_cuota": "al_dia",
                "email": "b@boca.org",
                "distancia_km": 2.0,
                "fecha_modificacion": "2026-10-16T10:00:00Z",
            },
        ],
    }
    client.post("/api/v1/socios/cargas/completa", json=c1, headers=BOCA_HEADERS)

    # Carga 2: Solo viene SOC-A
    c2 = {
        "carga_id": "full-boca-omit-2",
        "pagina": 1,
        "total_paginas": 1,
        "socios": [
            {
                "id_externo": "SOC-A",
                "dni": "70000001",
                "numero_socio": "B-A",
                "nombre": "Socio A Actualizado",
                "fecha_nacimiento": "1990-01-01",
                "fecha_alta": "2020-01-01",
                "estado_cuota": "al_dia",
                "email": "a@boca.org",
                "distancia_km": 2.0,
                "fecha_modificacion": "2026-10-17T10:00:00Z",
            }
        ],
    }
    res_c2 = client.post(
        "/api/v1/socios/cargas/completa", json=c2, headers=BOCA_HEADERS
    )
    assert res_c2.status_code == 202
    assert res_c2.json()["estado"] == "exitosa"

    # Verificar que solo SOC-A está activo, y SOC-B fue desactivado pero permanece en la base
    activos = client.get("/api/v1/socios?activo=true", headers=BOCA_HEADERS).json()
    assert len(activos) == 1
    assert activos[0]["id_externo"] == "SOC-A"

    inactivos = client.get("/api/v1/socios?activo=false", headers=BOCA_HEADERS).json()
    assert len(inactivos) == 1
    assert inactivos[0]["id_externo"] == "SOC-B"
