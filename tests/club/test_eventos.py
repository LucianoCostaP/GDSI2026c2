"""
Suite completa de pruebas unitarias y de integración para la API de Carga de Eventos (Alcance MVP).
Cubre:
- Autenticación Bearer y rechazo 401.
- Validación de campos obligatorios y formato (400 Bad Request).
- Restricción estricta de ENUM tipo_evento.
- Regla de 48 horas y excepción 'es_historico' (422 Unprocessable Entity).
- Carga individual exitosa (201 Created) con estado 'pendiente_definicion_importancia'.
- Idempotencia en POST individual (409 Conflict).
- Carga masiva POST /api/v1/eventos/batch con manejo de 48hs, fechas pasadas e idempotencia.
- Nuevo endpoint POST /api/v1/eventos/historicos/batch:
  - Sin regla de 48hs.
  - Guarda en estado 'Historico'.
  - Idempotencia: omisión segura de duplicados.
  - Manejo de fallos por formato (400).
  - 207 Multi-Status con reporte detallado.
- Consulta con filtros GET (200 OK).
- Seguridad y aislamiento Multi-Tenant entre clubes.
- Verificación de que los endpoints PUT (HU-23) fueron eliminados.
"""

from datetime import UTC, datetime, timedelta


def test_auth_missing_header(client):
    """Verifica que peticiones sin Authorization devuelvan 401 Unauthorized."""
    res = client.post("/api/v1/eventos", json={})
    assert res.status_code == 401


def test_auth_invalid_token(client):
    """Verifica que peticiones con token no registrado devuelvan 401 Unauthorized."""
    headers = {"Authorization": "Bearer token_falso_invalido"}
    res = client.get("/api/v1/eventos", headers=headers)
    assert res.status_code == 401
    assert "No autorizado" in res.json()["detail"]


def test_missing_mandatory_fields(client, headers_boca):
    """Verifica que campos faltantes retornen 400 Bad Request."""
    payload_incompleto = {
        "id_externo": "EVT-TEST",
        # Falta titulo
        "fecha_hora": (datetime.now(UTC) + timedelta(days=5)).isoformat(),
        # Falta lugar
        "tipo": "Partido",
    }
    res = client.post("/api/v1/eventos", json=payload_incompleto, headers=headers_boca)
    assert res.status_code == 400
    assert "Faltan campos obligatorios" in res.json()["error"]


def test_tipo_invalido_enum(client, headers_boca):
    """Verifica que un valor ajeno al ENUM sea rechazado con 400."""
    payload = {
        "id_externo": "EVT-RECITAL",
        "titulo": "Recital de Rock",
        "fecha_hora": (datetime.now(UTC) + timedelta(days=5)).isoformat(),
        "lugar": "Estadio",
        "tipo": "ConciertoMusical",  # No pertenece al ENUM
    }
    res = client.post("/api/v1/eventos", json=payload, headers=headers_boca)
    assert res.status_code == 400


def test_regla_48_horas_partido_rechazado(client, headers_boca):
    """Si es Partido y la antelación es menor a 48 horas, devuelve 422 Unprocessable Entity."""
    fecha_proxima = datetime.now(UTC) + timedelta(hours=24)  # 24hs < 48hs
    payload = {
        "id_externo": "EVT-URGENTE",
        "titulo": "Partido Rápido",
        "fecha_hora": fecha_proxima.isoformat(),
        "lugar": "Estadio Principal",
        "tipo": "Partido",
    }
    res = client.post("/api/v1/eventos", json=payload, headers=headers_boca)
    assert res.status_code == 422
    assert "No cumple con la antelación mínima de 48 horas" in res.json()["error"]


def test_regla_48_horas_excepcion_es_historico(client, headers_boca):
    """Si es_historico: true, se permite cargar un Partido con menos de 48hs o fecha pasada."""
    fecha_pasada = datetime.now(UTC) - timedelta(days=10)
    payload = {
        "id_externo": "EVT-HIST-01",
        "titulo": "Final Torneo 2020",
        "fecha_hora": fecha_pasada.isoformat(),
        "lugar": "Estadio Histórico",
        "tipo": "Partido",
        "es_historico": True,
    }
    res = client.post("/api/v1/eventos", json=payload, headers=headers_boca)
    assert res.status_code == 201
    assert res.json()["id_interno"].startswith("EVT-INT-")


def test_regla_48_horas_tipo_historico(client, headers_boca):
    """Si tipo == 'Historico', no aplica la regla de 48 horas."""
    fecha_pasada = datetime.now(UTC) - timedelta(days=365)
    payload = {
        "id_externo": "EVT-ANIVERSARIO",
        "titulo": "Centenario del Club",
        "fecha_hora": fecha_pasada.isoformat(),
        "lugar": "Sede Social",
        "tipo": "Historico",
    }
    res = client.post("/api/v1/eventos", json=payload, headers=headers_boca)
    assert res.status_code == 201


def test_creacion_exitosa_evento_partido(client, headers_boca):
    """Carga exitosa individual y verificación de estado 'pendiente_definicion_importancia'."""
    fecha_valida = datetime.now(UTC) + timedelta(days=4)
    payload = {
        "id_externo": "EVT-1029",
        "titulo": "Partido vs Rivales FC",
        "fecha_hora": fecha_valida.isoformat(),
        "lugar": "Estadio Visitante, calle ejemplo 1234",
        "tipo": "Partido",
        "descripcion": "Fecha 12 del torneo local",
    }
    res = client.post("/api/v1/eventos", json=payload, headers=headers_boca)
    assert res.status_code == 201
    body = res.json()
    assert body["mensaje"] == "Evento creado exitosamente."
    assert body["id_interno"].startswith("EVT-INT-")

    # Verificar que NO se guardó como visible, sino como pendiente
    res_get = client.get("/api/v1/eventos?id_externo=EVT-1029", headers=headers_boca)
    assert res_get.status_code == 200
    evento = res_get.json()[0]
    assert evento["estado_ciclo"] == "pendiente_definicion_importancia"
    assert evento["clase"] is None


def test_conflicto_id_externo_duplicado_individual(client, headers_boca):
    """POST individual retorna 409 Conflict si ya existe el id_externo."""
    fecha_valida = datetime.now(UTC) + timedelta(days=4)
    payload = {
        "id_externo": "EVT-DUP-01",
        "titulo": "Evento Original",
        "fecha_hora": fecha_valida.isoformat(),
        "lugar": "Sede Central",
        "tipo": "Institucional",
    }
    r1 = client.post("/api/v1/eventos", json=payload, headers=headers_boca)
    assert r1.status_code == 201

    r2 = client.post("/api/v1/eventos", json=payload, headers=headers_boca)
    assert r2.status_code == 409
    assert "Ya existe un evento registrado con ese id_externo" in r2.json()["error"]


def test_batch_endpoint_multi_status_207_con_idempotencia(client, headers_boca):
    """
    POST /api/v1/eventos/batch:
    - 207 Multi-Status
    - Omite duplicados de forma segura por idempotencia
    - Reporta fallos por regla de 48hs y fechas pasadas
    """
    ahora = datetime.now(UTC)
    # Primero creamos un evento existente para probar idempotencia
    client.post(
        "/api/v1/eventos",
        headers=headers_boca,
        json={
            "id_externo": "BATCH-EXISTENTE",
            "titulo": "Evento Ya Creado",
            "fecha_hora": (ahora + timedelta(days=5)).isoformat(),
            "lugar": "Cancha",
            "tipo": "Institucional",
        },
    )

    batch_payload = [
        # 1. Válido (>48hs)
        {
            "id_externo": "BATCH-NUEVO-01",
            "titulo": "Partido Clásico",
            "fecha_hora": (ahora + timedelta(days=5)).isoformat(),
            "lugar": "Estadio Principal",
            "tipo": "Partido",
        },
        # 2. Duplicado (debe omitirse de forma segura)
        {
            "id_externo": "BATCH-EXISTENTE",
            "titulo": "Intento Duplicado",
            "fecha_hora": (ahora + timedelta(days=6)).isoformat(),
            "lugar": "Cancha",
            "tipo": "Institucional",
        },
        # 3. Inválido (<48hs para Partido)
        {
            "id_externo": "BATCH-FALLO-48H",
            "titulo": "Partido Urgente",
            "fecha_hora": (ahora + timedelta(hours=12)).isoformat(),
            "lugar": "Estadio Auxiliar",
            "tipo": "Partido",
        },
        # 4. Inválido (Fecha pasada no permitida en batch regular)
        {
            "id_externo": "BATCH-FALLO-PASADO",
            "titulo": "Evento Pasado",
            "fecha_hora": (ahora - timedelta(days=2)).isoformat(),
            "lugar": "Sede",
            "tipo": "Institucional",
        },
    ]

    res = client.post("/api/v1/eventos/batch", json=batch_payload, headers=headers_boca)
    assert res.status_code == 207
    data = res.json()
    assert data["resumen"]["total"] == 4
    assert data["resumen"]["creados"] == 1
    assert data["resumen"]["omitidos"] == 1
    assert data["resumen"]["fallidos"] == 2

    assert len(data["creados"]) == 1
    assert data["creados"][0]["id_externo"] == "BATCH-NUEVO-01"

    assert len(data["omitidos"]) == 1
    assert data["omitidos"][0]["id_externo"] == "BATCH-EXISTENTE"
    assert data["omitidos"][0]["estado"] == "omitido"

    assert len(data["fallidos"]) == 2


def test_batch_historicos_endpoint(client, headers_boca):
    """
    POST /api/v1/eventos/historicos/batch:
    - No aplica regla de 48 horas.
    - Guarda con estado 'Historico' (nunca visible para socios).
    - Omite duplicados de forma segura (idempotencia).
    - Reporta errores de formato (400).
    - Retorna 207 Multi-Status.
    """
    ahora = datetime.now(UTC)
    # Primero creamos un evento existente para probar idempotencia
    client.post(
        "/api/v1/eventos",
        headers=headers_boca,
        json={
            "id_externo": "HIST-PREVIO",
            "titulo": "Partido Década 90",
            "fecha_hora": (ahora - timedelta(days=500)).isoformat(),
            "lugar": "Estadio Antiguo",
            "tipo": "Partido",
            "es_historico": True,
        },
    )

    payload_historicos = [
        # 1. Válido pasado (no aplica 48hs)
        {
            "id_externo": "HIST-001",
            "titulo": "Partido vs Club Atlético Pasado",
            "fecha_hora": "2025-05-10T15:00:00Z",
            "lugar": "Estadio Local",
            "tipo": "Partido",
        },
        # 2. Válido institucional pasado
        {
            "id_externo": "HIST-002",
            "titulo": "Asamblea Histórica 2024",
            "fecha_hora": "2024-03-15T18:00:00Z",
            "lugar": "Sede Fundacional",
            "tipo": "Institucional",
        },
        # 3. Duplicado (debe omitirse de forma segura)
        {
            "id_externo": "HIST-PREVIO",
            "titulo": "Partido Década 90 Reintento",
            "fecha_hora": "2020-01-01T12:00:00Z",
            "lugar": "Estadio Antiguo",
            "tipo": "Partido",
        },
        # 4. Fallido por formato (falta campo obligatorio 'lugar')
        {
            "id_externo": "HIST-MAL-FORMATO",
            "titulo": "Partido Sin Sede",
            "fecha_hora": "2023-01-01T12:00:00Z",
            # falta "lugar"
            "tipo": "Partido",
        },
    ]

    res = client.post(
        "/api/v1/eventos/historicos/batch",
        json=payload_historicos,
        headers=headers_boca,
    )
    assert res.status_code == 207
    data = res.json()

    assert data["resumen"]["total"] == 4
    assert data["resumen"]["creados"] == 2
    assert data["resumen"]["omitidos"] == 1
    assert data["resumen"]["fallidos"] == 1

    # Verificar items creados
    creados_ids = [c["id_externo"] for c in data["creados"]]
    assert "HIST-001" in creados_ids
    assert "HIST-002" in creados_ids

    # Verificar omitido
    assert data["omitidos"][0]["id_externo"] == "HIST-PREVIO"
    assert data["omitidos"][0]["estado"] == "omitido"

    # Verificar fallido por formato (código 400)
    assert data["fallidos"][0]["id_externo"] == "HIST-MAL-FORMATO"
    assert data["fallidos"][0]["codigo"] == 400

    # Comprobar que en la base de datos quedaron en estado 'Historico'
    res_get = client.get("/api/v1/eventos?id_externo=HIST-001", headers=headers_boca)
    assert res_get.status_code == 200
    evento_db = res_get.json()[0]
    assert evento_db["estado_ciclo"] == "Historico"
    assert evento_db["clase"] is None


def test_consulta_get_y_filtros(client, headers_boca):
    """GET /api/v1/eventos y filtrado por id_externo, id_interno y título parcial."""
    ahora = datetime.now(UTC)
    client.post(
        "/api/v1/eventos",
        headers=headers_boca,
        json={
            "id_externo": "EVT-F1",
            "titulo": "Asamblea Anual de Socios",
            "fecha_hora": (ahora + timedelta(days=3)).isoformat(),
            "lugar": "Gimnasio",
            "tipo": "Institucional",
        },
    )
    r2 = client.post(
        "/api/v1/eventos",
        headers=headers_boca,
        json={
            "id_externo": "EVT-F2",
            "titulo": "Partido Liga vs Tigre",
            "fecha_hora": (ahora + timedelta(days=5)).isoformat(),
            "lugar": "Cancha",
            "tipo": "Partido",
        },
    )
    id_interno_f2 = r2.json()["id_interno"]

    # Consulta sin filtros
    res_todos = client.get("/api/v1/eventos", headers=headers_boca)
    assert res_todos.status_code == 200
    assert len(res_todos.json()) >= 2

    # Filtro por id_externo
    res_ext = client.get("/api/v1/eventos?id_externo=EVT-F1", headers=headers_boca)
    assert len(res_ext.json()) == 1
    assert res_ext.json()[0]["id_externo"] == "EVT-F1"

    # Filtro por id_interno
    res_int = client.get(
        f"/api/v1/eventos?id_interno={id_interno_f2}", headers=headers_boca
    )
    assert len(res_int.json()) == 1
    assert res_int.json()[0]["id_externo"] == "EVT-F2"

    # Filtro por título
    res_tit = client.get("/api/v1/eventos?titulo=Asamblea", headers=headers_boca)
    assert len(res_tit.json()) == 1
    assert "Asamblea" in res_tit.json()[0]["titulo"]


def test_seguridad_multi_tenant_aislamiento_estricto(
    client, headers_boca, headers_river
):
    """Garantiza que un club rival (River Plate) no pueda ver eventos de Boca Juniors."""
    ahora = datetime.now(UTC)
    res_boca = client.post(
        "/api/v1/eventos",
        headers=headers_boca,
        json={
            "id_externo": "SECRETO-BOCA",
            "titulo": "Entrenamiento a Puertas Cerradas Boca",
            "fecha_hora": (ahora + timedelta(days=4)).isoformat(),
            "lugar": "Predio Ezeiza",
            "tipo": "Institucional",
        },
    )
    id_interno_boca = res_boca.json()["id_interno"]

    # River consulta la lista de eventos: NO DEBE VER EL EVENTO DE BOCA
    res_river = client.get("/api/v1/eventos", headers=headers_river)
    eventos_river = res_river.json()
    assert not any(e["id_interno"] == id_interno_boca for e in eventos_river)
    assert not any(e["id_externo"] == "SECRETO-BOCA" for e in eventos_river)


def test_put_eliminado_fuera_del_mvp(client, headers_boca):
    """
    Verifica que cualquier intento de PUT a /api/v1/eventos/{id_interno}
    no exista en la API (405 Method Not Allowed).
    """
    res = client.put(
        "/api/v1/eventos/EVT-INT-12345",
        headers=headers_boca,
        json={"titulo": "Intento de actualización"},
    )
    assert res.status_code in (404, 405)
