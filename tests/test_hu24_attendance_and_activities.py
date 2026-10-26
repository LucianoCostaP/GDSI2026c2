"""
Suite completa de pruebas unitarias y de integración para HU-24:
Carga de Asistencias y Actividades Recurrentes.

Cubre:
1. Push del Club: Asistencia multipágina con registros válidos e inválidos (SOCIO_NOT_FOUND, NUMERO_SOCIO_MISMATCH, DUPLICATE_DNI_PAGE).
2. Push del Club: Evento no elegible (futuro o inexistente -> 422 EVENT_NOT_ELIGIBLE).
3. Push del Club: DNI duplicado entre páginas aborta la carga completa (DUPLICATE_DNI_ACROSS_PAGES).
4. Push del Club: Idempotencia en reenvío de páginas (202 mismo payload) y detección de conflicto (409 payload alterado).
5. Push del Club: Asistencia a evento que ya posee asistencia previa entra en 'pending_approval'.
6. Admin: Flujo de Aprobación de Reemplazo (POST /admin/attendance/{carga_id}/approve) con sustitución atómica y carga anterior 'replaced'.
7. Admin: Flujo de Rechazo de Reemplazo (POST /admin/attendance/{carga_id}/reject) con retención de la asistencia previa intacta.
8. Push del Club: Actividades Recurrentes por lotes (upsert, validación de tipo, rangos de fecha y no-futuros).
9. Push del Club: Actividades Recurrentes con control de marca de agua (WATERMARK_GAP).
10. Admin: Carga manual por CSV de asistencias con validación cruzada de 'fecha_evento' (EVENT_DATE_MISMATCH).
11. Admin: Carga manual por CSV de asistencias con regla de tolerancia de error del 5% (<5% pasa, >5% rechaza todo con 422 TOLERANCE_EXCEEDED).
12. Admin: Confirmación obligatoria de reemplazo en CSV si ya existe asistencia previa.
13. Admin: Carga manual por CSV de actividades recurrentes con regla de 5% de tolerancia.
14. Admin / FR-008: Descarga de archivo CSV con el detalle de registros rechazados (GET /admin/attendance/cargas/{carga_id}/rejections/csv).
15. Seguridad y Control de Acceso (401 sin token, 403 con rol Socio).
"""

import io
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import FeeStatus, User
from app.models.domain import (
    ActividadRecurrenteDB,
    AsistenciaDB,
    AsistenciaStagingDB,
    CargaParticipacionDB,
    EventoVisibleDB,
    Socio,
)
from app.models.enums import (
    EstadoCargaParticipacion,
)
from tests.conftest import (
    BOCA_HEADERS,
    MakeMember,
    Outbox,
    admin_token,
    bearer,
    member_token,
)

BOCA_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture
def socio_boca(make_member: MakeMember) -> tuple[User, str]:
    return make_member(activated=True, fee_status=FeeStatus.UP_TO_DATE)


def seed_socios_boca(db: Session) -> list[Socio]:
    socios = [
        Socio(
            id=uuid.uuid4(),
            club_id=BOCA_ID,
            id_externo="SOC-001",
            dni="30111222",
            numero_socio="B-001",
            nombre="Juan Pérez",
            fecha_nacimiento=date(1990, 5, 15),
            fecha_alta=date(2015, 2, 1),
            estado_cuota="al_dia",
            email="juan.perez@example.com",
            distancia_km=Decimal("5.5"),
            localidad="La Boca",
            activo=True,
        ),
        Socio(
            id=uuid.uuid4(),
            club_id=BOCA_ID,
            id_externo="SOC-002",
            dni="30222333",
            numero_socio="B-002",
            nombre="Martín Gómez",
            fecha_nacimiento=date(1988, 11, 20),
            fecha_alta=date(2018, 6, 10),
            estado_cuota="al_dia",
            email="martin.gomez@example.com",
            distancia_km=Decimal("15.0"),
            localidad="Quilmes",
            activo=True,
        ),
        Socio(
            id=uuid.uuid4(),
            club_id=BOCA_ID,
            id_externo="SOC-003",
            dni="30333444",
            numero_socio="B-003",
            nombre="Carlos Tevez",
            fecha_nacimiento=date(1984, 2, 5),
            fecha_alta=date(2001, 1, 1),
            estado_cuota="al_dia",
            email="carlos.tevez@example.com",
            distancia_km=Decimal("2.0"),
            localidad="La Boca",
            activo=True,
        ),
    ]
    db.add_all(socios)
    db.commit()
    return socios


def seed_evento_pasado(
    db: Session, id_externo: str = "EVT-PAST-01", days_ago: int = 2
) -> EventoVisibleDB:
    past_date = datetime.now(UTC) - timedelta(days=days_ago)
    evt = EventoVisibleDB(
        id_interno=f"INT-{id_externo}",
        club_id=BOCA_ID,
        id_externo=id_externo,
        titulo="Boca vs River Superclásico Pasado",
        fecha_hora=past_date,
        lugar="La Bombonera",
        tipo="Partido",
        clase="A",
        publicado_por="admin",
        es_default=False,
    )
    db.add(evt)
    db.commit()
    return evt


def seed_evento_futuro(
    db: Session, id_externo: str = "EVT-FUT-01", days_ahead: int = 5
) -> EventoVisibleDB:
    fut_date = datetime.now(UTC) + timedelta(days=days_ahead)
    evt = EventoVisibleDB(
        id_interno=f"INT-{id_externo}",
        club_id=BOCA_ID,
        id_externo=id_externo,
        titulo="Boca vs San Lorenzo Futuro",
        fecha_hora=fut_date,
        lugar="La Bombonera",
        tipo="Partido",
        clase="B",
        publicado_por="admin",
        es_default=False,
    )
    db.add(evt)
    db.commit()
    return evt


# ==============================================================================
# SEGURIDAD Y CONTROL DE ACCESO
# ==============================================================================
def test_seguridad_endpoints_admin_participacion_401_y_403(
    client: TestClient, outbox: Outbox, socio_boca: tuple[User, str]
) -> None:
    # 401 Sin autenticación
    res = client.get("/admin/events/eligible-for-attendance")
    assert res.status_code == 401

    res = client.get("/admin/attendance/pending-approvals")
    assert res.status_code == 401

    # 403 Con rol Socio
    token_socio = member_token(client, outbox, socio_boca)
    headers = bearer(token_socio)

    res = client.get("/admin/events/eligible-for-attendance", headers=headers)
    assert res.status_code == 403

    res = client.get("/admin/attendance/pending-approvals", headers=headers)
    assert res.status_code == 403


# ==============================================================================
# 1. PUSH DEL CLUB: ASISTENCIA A EVENTOS MULTIPÁGINA
# ==============================================================================
def test_club_asistencia_multipagina_exitosa(client: TestClient, db: Session) -> None:
    seed_socios_boca(db)
    seed_evento_pasado(db, "EVT-PAST-01")

    carga_id = "att-boca-001"

    # Página 1 de 2:
    # - 30111222 (B-001) -> válido
    # - 99999999 -> SOCIO_NOT_FOUND
    # - 30222333 con socio equivocado B-999 -> NUMERO_SOCIO_MISMATCH
    # - 30111222 repetido en página -> DUPLICATE_DNI_PAGE
    p1 = {
        "carga_id": carga_id,
        "pagina": 1,
        "total_paginas": 2,
        "es_ultima_pagina": False,
        "registros": [
            {"dni": "30111222", "numero_socio": "B-001"},
            {"dni": "99999999", "numero_socio": "B-999"},
            {"dni": "30222333", "numero_socio": "B-999"},
            {"dni": "30111222", "numero_socio": "B-001"},
        ],
    }
    res_p1 = client.post(
        "/api/v1/eventos/EVT-PAST-01/asistencia",
        json=p1,
        headers=BOCA_HEADERS,
    )
    assert res_p1.status_code == 202
    d1 = res_p1.json()
    assert d1["estado"] == "receiving"
    assert d1["registros_validos_pagina"] == 1
    assert d1["registros_rechazados_pagina"] == 3
    assert len(d1["rechazos"]) == 3

    # Verificar que el registro válido quedó en staging
    staged = (
        db.query(AsistenciaStagingDB)
        .filter(AsistenciaStagingDB.dni == "30111222")
        .first()
    )
    assert staged is not None

    # Página 2 de 2 (última):
    # - 30333444 (B-003) -> válido
    p2 = {
        "carga_id": carga_id,
        "pagina": 2,
        "total_paginas": 2,
        "es_ultima_pagina": True,
        "registros": [
            {"dni": "30333444", "numero_socio": "B-003"},
        ],
    }
    res_p2 = client.post(
        "/api/v1/eventos/EVT-PAST-01/asistencia",
        json=p2,
        headers=BOCA_HEADERS,
    )
    assert res_p2.status_code == 202
    d2 = res_p2.json()
    assert d2["estado"] == "successful"
    assert d2["registros_validos_pagina"] == 1

    # Verificar consulta de estado de la carga
    res_status = client.get(
        f"/api/v1/participacion/cargas/{carga_id}", headers=BOCA_HEADERS
    )
    assert res_status.status_code == 200
    st_data = res_status.json()
    assert st_data["estado"] == "successful"
    assert st_data["total_registros"] == 5
    assert st_data["registros_incorporados"] == 2
    assert st_data["registros_rechazados"] == 3
    assert len(st_data["rechazos"]) == 3

    # Verificar que en asistencias definitivas están los 2 socios y staging fue purgado
    asistencias = (
        db.query(AsistenciaDB)
        .filter(AsistenciaDB.evento_id_externo == "EVT-PAST-01")
        .all()
    )
    assert len(asistencias) == 2
    dnis = {a.dni for a in asistencias}
    assert dnis == {"30111222", "30333444"}

    assert (
        db.query(AsistenciaStagingDB)
        .join(CargaParticipacionDB)
        .filter(CargaParticipacionDB.carga_id_externo == carga_id)
        .count()
        == 0
    )


def test_club_asistencia_evento_futuro_o_inexistente_rechazado(
    client: TestClient, db: Session
) -> None:
    seed_socios_boca(db)
    seed_evento_futuro(db, "EVT-FUT-01")

    payload = {
        "carga_id": "att-futuro",
        "pagina": 1,
        "total_paginas": 1,
        "es_ultima_pagina": True,
        "registros": [{"dni": "30111222", "numero_socio": "B-001"}],
    }

    # Evento futuro -> 422 EVENT_NOT_ELIGIBLE
    res_fut = client.post(
        "/api/v1/eventos/EVT-FUT-01/asistencia",
        json=payload,
        headers=BOCA_HEADERS,
    )
    assert res_fut.status_code == 422
    assert res_fut.json()["error"]["code"] == "EVENT_NOT_ELIGIBLE"

    # Evento inexistente -> 422 EVENT_NOT_ELIGIBLE
    res_no_existe = client.post(
        "/api/v1/eventos/EVT-INEXISTENTE/asistencia",
        json=payload,
        headers=BOCA_HEADERS,
    )
    assert res_no_existe.status_code == 422
    assert res_no_existe.json()["error"]["code"] == "EVENT_NOT_ELIGIBLE"


def test_club_asistencia_duplicado_inter_paginas_falla_carga(
    client: TestClient, db: Session
) -> None:
    seed_socios_boca(db)
    seed_evento_pasado(db, "EVT-PAST-02")

    carga_id = "att-cross-dup"

    # Página 1 con socio 30111222
    p1 = {
        "carga_id": carga_id,
        "pagina": 1,
        "total_paginas": 2,
        "es_ultima_pagina": False,
        "registros": [{"dni": "30111222", "numero_socio": "B-001"}],
    }
    res_p1 = client.post(
        "/api/v1/eventos/EVT-PAST-02/asistencia",
        json=p1,
        headers=BOCA_HEADERS,
    )
    assert res_p1.status_code == 202

    # Página 2 repite socio 30111222
    p2 = {
        "carga_id": carga_id,
        "pagina": 2,
        "total_paginas": 2,
        "es_ultima_pagina": True,
        "registros": [{"dni": "30111222", "numero_socio": "B-001"}],
    }
    res_p2 = client.post(
        "/api/v1/eventos/EVT-PAST-02/asistencia",
        json=p2,
        headers=BOCA_HEADERS,
    )
    assert res_p2.status_code == 422
    assert res_p2.json()["error"]["code"] == "DUPLICATE_DNI_ACROSS_PAGES"

    # La carga debe haber quedado en fallida y staging vacío
    carga_db = (
        db.query(CargaParticipacionDB)
        .filter(CargaParticipacionDB.carga_id_externo == carga_id)
        .first()
    )
    assert carga_db is not None
    assert carga_db.estado == EstadoCargaParticipacion.FAILED


def test_club_asistencia_idempotencia_y_conflicto_payload(
    client: TestClient, db: Session
) -> None:
    seed_socios_boca(db)
    seed_evento_pasado(db, "EVT-PAST-03")

    carga_id = "att-idempotente"

    p1 = {
        "carga_id": carga_id,
        "pagina": 1,
        "total_paginas": 2,
        "es_ultima_pagina": False,
        "registros": [{"dni": "30111222", "numero_socio": "B-001"}],
    }
    res1 = client.post(
        "/api/v1/eventos/EVT-PAST-03/asistencia",
        json=p1,
        headers=BOCA_HEADERS,
    )
    assert res1.status_code == 202

    # Reenvío idéntico -> 202 idempotente
    res2 = client.post(
        "/api/v1/eventos/EVT-PAST-03/asistencia",
        json=p1,
        headers=BOCA_HEADERS,
    )
    assert res2.status_code == 202
    assert "idempotente" in res2.json()["mensaje"].lower()

    # Reenvío de la misma página pero con contenido alterado -> 409 CONFLICT
    p1_alterado = {
        "carga_id": carga_id,
        "pagina": 1,
        "total_paginas": 2,
        "es_ultima_pagina": False,
        "registros": [{"dni": "30222333", "numero_socio": "B-002"}],
    }
    res_conflict = client.post(
        "/api/v1/eventos/EVT-PAST-03/asistencia",
        json=p1_alterado,
        headers=BOCA_HEADERS,
    )
    assert res_conflict.status_code == 409
    assert res_conflict.json()["error"]["code"] == "CONFLICT"


# ==============================================================================
# 2. REEMPLAZO DE ASISTENCIA: PENDING APPROVAL, ADMIN APROBAR / RECHAZAR
# ==============================================================================
def test_club_asistencia_previa_entra_en_pending_approval_y_admin_aprueba(
    client: TestClient, db: Session, outbox: Outbox, admin: User
) -> None:
    token_admin = admin_token(client, outbox, admin)
    headers_adm = bearer(token_admin)

    seed_socios_boca(db)
    seed_evento_pasado(db, "EVT-PAST-04")

    # 1. Primera carga exitosa
    carga1 = {
        "carga_id": "att-primera",
        "pagina": 1,
        "total_paginas": 1,
        "es_ultima_pagina": True,
        "registros": [{"dni": "30111222", "numero_socio": "B-001"}],
    }
    res1 = client.post(
        "/api/v1/eventos/EVT-PAST-04/asistencia",
        json=carga1,
        headers=BOCA_HEADERS,
    )
    assert res1.status_code == 202
    assert res1.json()["estado"] == "successful"

    # 2. Segunda carga para el MISMO evento (reemplazo enviado por el club)
    carga2 = {
        "carga_id": "att-reemplazo",
        "pagina": 1,
        "total_paginas": 1,
        "es_ultima_pagina": True,
        "registros": [
            {"dni": "30222333", "numero_socio": "B-002"},
            {"dni": "30333444", "numero_socio": "B-003"},
        ],
    }
    res2 = client.post(
        "/api/v1/eventos/EVT-PAST-04/asistencia",
        json=carga2,
        headers=BOCA_HEADERS,
    )
    assert res2.status_code == 202
    assert res2.json()["estado"] == "pending_approval"

    # 3. El Admin lista pendientes de aprobación
    res_pending = client.get("/admin/attendance/pending-approvals", headers=headers_adm)
    assert res_pending.status_code == 200
    pendientes = res_pending.json()
    assert len(pendientes) == 1
    p_info = pendientes[0]
    assert p_info["carga_id"] == "att-reemplazo"
    assert p_info["evento_id_externo"] == "EVT-PAST-04"
    assert p_info["registros_a_incorporar"] == 2
    assert p_info["carga_previa"] is not None
    assert p_info["carga_previa"]["carga_id"] == "att-primera"

    # 4. El Admin aprueba el reemplazo
    res_apr = client.post(
        "/admin/attendance/att-reemplazo/approve", headers=headers_adm
    )
    assert res_apr.status_code == 200
    assert res_apr.json()["estado"] == "successful"

    # 5. Verificar que la carga anterior quedó en 'reemplazada' y la nueva en 'exitosa'
    c1_db = (
        db.query(CargaParticipacionDB)
        .filter(CargaParticipacionDB.carga_id_externo == "att-primera")
        .first()
    )
    c2_db = (
        db.query(CargaParticipacionDB)
        .filter(CargaParticipacionDB.carga_id_externo == "att-reemplazo")
        .first()
    )
    assert c1_db.estado == EstadoCargaParticipacion.REPLACED
    assert c2_db.estado == EstadoCargaParticipacion.SUCCESSFUL

    # Verificar que en asistencias están los nuevos registros (30222333, 30333444) y no el viejo (30111222)
    asistencias = (
        db.query(AsistenciaDB)
        .filter(AsistenciaDB.evento_id_externo == "EVT-PAST-04")
        .all()
    )
    assert len(asistencias) == 2
    assert {a.dni for a in asistencias} == {"30222333", "30333444"}


def test_club_asistencia_previa_entra_en_pending_approval_y_admin_rechaza(
    client: TestClient, db: Session, outbox: Outbox, admin: User
) -> None:
    token_admin = admin_token(client, outbox, admin)
    headers_adm = bearer(token_admin)

    seed_socios_boca(db)
    seed_evento_pasado(db, "EVT-PAST-05")

    # Primera carga
    carga1 = {
        "carga_id": "att-base-05",
        "pagina": 1,
        "total_paginas": 1,
        "es_ultima_pagina": True,
        "registros": [{"dni": "30111222", "numero_socio": "B-001"}],
    }
    client.post(
        "/api/v1/eventos/EVT-PAST-05/asistencia",
        json=carga1,
        headers=BOCA_HEADERS,
    )

    # Segunda carga (reemplazo)
    carga2 = {
        "carga_id": "att-reemplazo-05",
        "pagina": 1,
        "total_paginas": 1,
        "es_ultima_pagina": True,
        "registros": [{"dni": "30222333", "numero_socio": "B-002"}],
    }
    client.post(
        "/api/v1/eventos/EVT-PAST-05/asistencia",
        json=carga2,
        headers=BOCA_HEADERS,
    )

    # El Admin rechaza el reemplazo
    res_rec = client.post(
        "/admin/attendance/att-reemplazo-05/reject?motivo=Registros+incorrectos",
        headers=headers_adm,
    )
    assert res_rec.status_code == 200
    assert res_rec.json()["estado"] == "rejected"

    # Verificar que la carga original sigue intacta (exitosa) y la asistencia vieja sigue activa
    c1_db = (
        db.query(CargaParticipacionDB)
        .filter(CargaParticipacionDB.carga_id_externo == "att-base-05")
        .first()
    )
    c2_db = (
        db.query(CargaParticipacionDB)
        .filter(CargaParticipacionDB.carga_id_externo == "att-reemplazo-05")
        .first()
    )
    assert c1_db.estado == EstadoCargaParticipacion.SUCCESSFUL
    assert c2_db.estado == EstadoCargaParticipacion.REJECTED

    asistencias = (
        db.query(AsistenciaDB)
        .filter(AsistenciaDB.evento_id_externo == "EVT-PAST-05")
        .all()
    )
    assert len(asistencias) == 1
    assert asistencias[0].dni == "30111222"


# ==============================================================================
# 3. PUSH DEL CLUB: ACTIVIDADES RECURRENTES POR LOTES
# ==============================================================================
def test_club_actividades_recurrentes_lote_y_upsert(
    client: TestClient, db: Session
) -> None:
    seed_socios_boca(db)
    hoy = date.today()

    lote_payload = {
        "lote_id": "act-batch-001",
        "desde": (hoy - timedelta(days=60)).isoformat(),
        "hasta": hoy.isoformat(),
        "registros": [
            # 1. Válido deporte_federado
            {
                "dni": "30111222",
                "tipo": "deporte_federado",
                "fecha_desde": (hoy - timedelta(days=45)).isoformat(),
                "fecha_hasta": (hoy - timedelta(days=10)).isoformat(),
            },
            # 2. Válido subcomision
            {
                "dni": "30222333",
                "tipo": "subcomision",
                "fecha_desde": (hoy - timedelta(days=30)).isoformat(),
                "fecha_hasta": hoy.isoformat(),
            },
            # 3. Inválido tipo
            {
                "dni": "30333444",
                "tipo": "tipo_inexistente",
                "fecha_desde": (hoy - timedelta(days=20)).isoformat(),
                "fecha_hasta": hoy.isoformat(),
            },
            # 4. Inválido rango fechas (hasta < desde)
            {
                "dni": "30333444",
                "tipo": "subcomision",
                "fecha_desde": (hoy - timedelta(days=10)).isoformat(),
                "fecha_hasta": (hoy - timedelta(days=20)).isoformat(),
            },
            # 5. Inválido fecha futura
            {
                "dni": "30333444",
                "tipo": "subcomision",
                "fecha_desde": hoy.isoformat(),
                "fecha_hasta": (hoy + timedelta(days=5)).isoformat(),
            },
            # 6. Inválido socio no existe
            {
                "dni": "88888888",
                "tipo": "deporte_federado",
                "fecha_desde": (hoy - timedelta(days=15)).isoformat(),
                "fecha_hasta": hoy.isoformat(),
            },
        ],
    }

    res = client.post(
        "/api/v1/actividades/lotes",
        json=lote_payload,
        headers=BOCA_HEADERS,
    )
    assert res.status_code == 202
    data = res.json()
    assert data["estado"] == "successful"
    assert data["registros_incorporados"] == 2
    assert data["registros_rechazados"] == 4
    assert len(data["rechazos"]) == 4

    codigos_rechazo = {r["codigo"] for r in data["rechazos"]}
    assert "INVALID_TIPO" in codigos_rechazo
    assert "INVALID_DATE_RANGE" in codigos_rechazo
    assert "FUTURE_DATE" in codigos_rechazo
    assert "SOCIO_NOT_FOUND" in codigos_rechazo

    # Probar idempotencia y upsert:
    # Si se reenvía exactamente el mismo lote -> respuesta idempotente
    res_idempotente = client.post(
        "/api/v1/actividades/lotes",
        json=lote_payload,
        headers=BOCA_HEADERS,
    )
    assert res_idempotente.status_code == 202
    assert "idempotente" in res_idempotente.json()["mensaje"].lower()

    # Si se envía un nuevo lote que actualiza la fecha_hasta del socio 30111222
    lote2_payload = {
        "lote_id": "act-batch-002",
        "desde": (hoy - timedelta(days=50)).isoformat(),
        "hasta": hoy.isoformat(),
        "registros": [
            {
                "dni": "30111222",
                "tipo": "deporte_federado",
                "fecha_desde": (hoy - timedelta(days=45)).isoformat(),
                "fecha_hasta": hoy.isoformat(),  # Actualizada
            }
        ],
    }
    res_up = client.post(
        "/api/v1/actividades/lotes",
        json=lote2_payload,
        headers=BOCA_HEADERS,
    )
    assert res_up.status_code == 202
    d_up = res_up.json()
    assert d_up["registros_incorporados"] == 0
    assert d_up["registros_actualizados"] == 1

    act_db = (
        db.query(ActividadRecurrenteDB)
        .filter(ActividadRecurrenteDB.dni == "30111222")
        .first()
    )
    assert act_db.fecha_hasta == hoy


def test_club_actividades_recurrentes_watermark_gap(
    client: TestClient, db: Session
) -> None:
    seed_socios_boca(db)
    hoy = date.today()

    # Primer lote: hasta = hoy - 30 días
    l1 = {
        "lote_id": "act-wm-01",
        "desde": (hoy - timedelta(days=60)).isoformat(),
        "hasta": (hoy - timedelta(days=30)).isoformat(),
        "registros": [
            {
                "dni": "30111222",
                "tipo": "deporte_federado",
                "fecha_desde": (hoy - timedelta(days=50)).isoformat(),
                "fecha_hasta": (hoy - timedelta(days=35)).isoformat(),
            }
        ],
    }
    res_l1 = client.post(
        "/api/v1/actividades/lotes",
        json=l1,
        headers=BOCA_HEADERS,
    )
    assert res_l1.status_code == 202

    # Segundo lote con salto (desde = hoy - 10 días, mayor al último 'hasta' que fue hoy - 30) -> 422 WATERMARK_GAP
    l2_gap = {
        "lote_id": "act-wm-02-gap",
        "desde": (hoy - timedelta(days=10)).isoformat(),
        "hasta": hoy.isoformat(),
        "registros": [
            {
                "dni": "30111222",
                "tipo": "deporte_federado",
                "fecha_desde": (hoy - timedelta(days=5)).isoformat(),
                "fecha_hasta": hoy.isoformat(),
            }
        ],
    }
    res_gap = client.post(
        "/api/v1/actividades/lotes",
        json=l2_gap,
        headers=BOCA_HEADERS,
    )
    assert res_gap.status_code == 422
    assert res_gap.json()["error"]["code"] == "WATERMARK_GAP"


# ==============================================================================
# 4. ADMIN: CARGA CSV DE ASISTENCIAS Y VALIDACIÓN DE TOLERANCIA DEL 5%
# ==============================================================================
def test_admin_upload_csv_asistencia_tolerancia_5_porciento(
    client: TestClient, db: Session, outbox: Outbox, admin: User
) -> None:
    token_admin = admin_token(client, outbox, admin)
    headers_adm = bearer(token_admin)

    # Insertar 100 socios válidos para Boca
    socios = [
        Socio(
            id=uuid.uuid4(),
            club_id=BOCA_ID,
            id_externo=f"SOC-{i:03d}",
            dni=f"20000{i:03d}",
            numero_socio=f"B-{i:03d}",
            nombre=f"Socio {i}",
            fecha_nacimiento=date(1990, 1, 1),
            fecha_alta=date(2010, 1, 1),
            estado_cuota="al_dia",
            email=f"socio{i}@example.com",
            distancia_km=Decimal("5.0"),
            localidad="CABA",
            activo=True,
        )
        for i in range(1, 101)
    ]
    db.add_all(socios)
    db.commit()

    seed_evento_pasado(db, "EVT-CSV-TOL")

    # Caso A: Archivo con 100 filas, 2 errores (2% error <= 5% tolerancia) -> Debe procesar
    csv_lines = ["dni,numero_socio"]
    # 98 válidos
    for i in range(1, 99):
        csv_lines.append(f"20000{i:03d},B-{i:03d}")
    # 2 inválidos (DNI inexistente)
    csv_lines.append("99999001,B-991")
    csv_lines.append("99999002,B-992")

    csv_content = "\n".join(csv_lines)
    files = {
        "file": (
            "asistencias.csv",
            io.BytesIO(csv_content.encode("utf-8")),
            "text/csv",
        )
    }

    res_ok = client.post(
        "/admin/events/EVT-CSV-TOL/attendance/upload-csv",
        files=files,
        data={"confirm_replace": "false"},
        headers=headers_adm,
    )
    assert res_ok.status_code == 200
    d_ok = res_ok.json()
    assert d_ok["estado"] == "successful"
    assert d_ok["total_registros"] == 100
    assert d_ok["registros_incorporados"] == 98
    assert d_ok["registros_rechazados"] == 2

    # Caso B: Archivo con 100 filas y 6 errores (6% error > 5% tolerancia) -> Rechazar todo con 422
    seed_evento_pasado(db, "EVT-CSV-TOL-FAIL")

    csv_fail_lines = ["dni,numero_socio"]
    for i in range(1, 95):
        csv_fail_lines.append(f"20000{i:03d},B-{i:03d}")
    # 6 inválidos
    for k in range(1, 7):
        csv_fail_lines.append(f"9999900{k},B-99{k}")

    csv_fail_content = "\n".join(csv_fail_lines)
    files_fail = {
        "file": (
            "asistencias_fail.csv",
            io.BytesIO(csv_fail_content.encode("utf-8")),
            "text/csv",
        )
    }

    res_fail = client.post(
        "/admin/events/EVT-CSV-TOL-FAIL/attendance/upload-csv",
        files=files_fail,
        data={"confirm_replace": "false"},
        headers=headers_adm,
    )
    assert res_fail.status_code == 422
    assert res_fail.json()["error"]["code"] == "TOLERANCE_EXCEEDED"

    # Verificar que nada se incorporó para EVT-CSV-TOL-FAIL
    assert (
        db.query(AsistenciaDB)
        .filter(AsistenciaDB.evento_id_externo == "EVT-CSV-TOL-FAIL")
        .count()
        == 0
    )


def test_admin_upload_csv_asistencia_fecha_evento_mismatch(
    client: TestClient, db: Session, outbox: Outbox, admin: User
) -> None:
    token_admin = admin_token(client, outbox, admin)
    headers_adm = bearer(token_admin)

    seed_socios_boca(db)
    # Evento con fecha hace 3 días
    seed_evento_pasado(db, "EVT-FECHA-CHECK", days_ago=3)
    fecha_erronea = (date.today() - timedelta(days=10)).isoformat()

    csv_content = f"dni,numero_socio,fecha_evento\n30111222,B-001,{fecha_erronea}\n"
    files = {
        "file": (
            "asistencia.csv",
            io.BytesIO(csv_content.encode("utf-8")),
            "text/csv",
        )
    }

    res = client.post(
        "/admin/events/EVT-FECHA-CHECK/attendance/upload-csv",
        files=files,
        headers=headers_adm,
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "EVENT_DATE_MISMATCH"


def test_admin_upload_csv_asistencia_requiere_confirmacion_reemplazo(
    client: TestClient, db: Session, outbox: Outbox, admin: User
) -> None:
    token_admin = admin_token(client, outbox, admin)
    headers_adm = bearer(token_admin)

    seed_socios_boca(db)
    seed_evento_pasado(db, "EVT-CSV-REPLACE")

    # 1. Primera carga directa exitosa
    csv_1 = "dni,numero_socio\n30111222,B-001\n"
    res1 = client.post(
        "/admin/events/EVT-CSV-REPLACE/attendance/upload-csv",
        files={"file": ("a1.csv", io.BytesIO(csv_1.encode("utf-8")), "text/csv")},
        data={"confirm_replace": "false"},
        headers=headers_adm,
    )
    assert res1.status_code == 200
    assert res1.json()["estado"] == "successful"

    # 2. Segunda subida sin confirmar reemplazo -> estado requires_confirmation
    csv_2 = "dni,numero_socio\n30222333,B-002\n"
    res2 = client.post(
        "/admin/events/EVT-CSV-REPLACE/attendance/upload-csv",
        files={"file": ("a2.csv", io.BytesIO(csv_2.encode("utf-8")), "text/csv")},
        data={"confirm_replace": "false"},
        headers=headers_adm,
    )
    assert res2.status_code == 200
    d2 = res2.json()
    assert d2["estado"] == "requires_confirmation"
    assert d2["requiere_confirmacion_reemplazo"] is True
    assert d2["carga_previa"] is not None

    # 3. Tercera subida confirmando reemplazo (confirm_replace=True) -> Aplica y archiva vieja
    res3 = client.post(
        "/admin/events/EVT-CSV-REPLACE/attendance/upload-csv",
        files={"file": ("a2.csv", io.BytesIO(csv_2.encode("utf-8")), "text/csv")},
        data={"confirm_replace": "true"},
        headers=headers_adm,
    )
    assert res3.status_code == 200
    assert res3.json()["estado"] == "successful"

    asistencias = (
        db.query(AsistenciaDB)
        .filter(AsistenciaDB.evento_id_externo == "EVT-CSV-REPLACE")
        .all()
    )
    assert len(asistencias) == 1
    assert asistencias[0].dni == "30222333"


# ==============================================================================
# 5. ADMIN: CARGA CSV DE ACTIVIDADES RECURRENTES Y DESCARGA CSV DE RECHAZOS (FR-008)
# ==============================================================================
def test_admin_upload_csv_actividades_y_descarga_rechazos_csv(
    client: TestClient, db: Session, outbox: Outbox, admin: User
) -> None:
    token_admin = admin_token(client, outbox, admin)
    headers_adm = bearer(token_admin)

    seed_socios_boca(db)
    hoy = date.today()
    fd = (hoy - timedelta(days=30)).isoformat()
    fh = (hoy - timedelta(days=5)).isoformat()

    # CSV con 20 filas: 19 válidas y 1 inválida (socio desconocido) -> 5% error exacto
    csv_lines = ["dni,tipo,fecha_desde,fecha_hasta"]
    # 19 válidas para socio 30111222 (diferentes tipos o días)
    for i in range(1, 20):
        tipo = "deporte_federado" if i % 2 == 0 else "subcomision"
        csv_lines.append(
            f"30111222,{tipo},{(hoy - timedelta(days=30 + i)).isoformat()},{(hoy - timedelta(days=5 + i)).isoformat()}"
        )
    # 1 inválida (socio no existe)
    csv_lines.append(f"99999999,deporte_federado,{fd},{fh}")

    csv_content = "\n".join(csv_lines)
    files = {
        "file": (
            "actividades.csv",
            io.BytesIO(csv_content.encode("utf-8")),
            "text/csv",
        )
    }

    res_act = client.post(
        "/admin/activities/upload-csv",
        files=files,
        headers=headers_adm,
    )
    assert res_act.status_code == 200
    d_act = res_act.json()
    assert d_act["estado"] == "successful"
    assert d_act["registros_incorporados"] == 19
    assert d_act["registros_rechazados"] == 1
    carga_id_generada = d_act["carga_id"]

    # Descarga del reporte CSV de rechazos (Scenario 18 / FR-008)
    res_dl = client.get(
        f"/admin/attendance/cargas/{carga_id_generada}/rejections/csv",
        headers=headers_adm,
    )
    assert res_dl.status_code == 200
    assert "text/csv" in res_dl.headers["content-type"]
    assert "attachment; filename=" in res_dl.headers["content-disposition"]

    contenido_dl = res_dl.text
    assert "fila,dni,campo,codigo,motivo" in contenido_dl
    assert "99999999" in contenido_dl
    assert "SOCIO_NOT_FOUND" in contenido_dl
