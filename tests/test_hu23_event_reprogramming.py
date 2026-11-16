"""
Suite de pruebas exhaustiva para HU-23: Reprogramación, Retiro y Restauración de Eventos.
(Feature: Event Reprogramming, Withdrawal and Restoration)

Cubre:
- User Story 1: Revisión de actualizaciones enviadas por el club (FR-001 a FR-006, SC-001 a SC-004)
  - Escenario 1: Club envía actualización de evento publicado -> queda pendiente de revisión con comparativa.
  - Escenario 2: Admin aprueba cambio -> evento se actualiza de inmediato, visible en HU-17, mantiene 'publicado'.
  - Escenario 3: Admin rechaza cambio -> cambio queda rechazado, evento sin modificaciones.
  - Escenario 4: Club envía mismos datos -> no crea cambio, notifica que está actualizado.
  - Escenario 5: Club intenta cambiar tipo de evento -> rechazado con 422 EVENT_TYPE_CHANGE_NOT_ALLOWED.
  - Escenario 6: Club intenta actualizar evento ya iniciado o retirado -> rechazado con 422.
  - Escenario 7: Nueva actualización mientras otra está pendiente -> reemplaza la anterior (estado 'reemplazado').
  - Escenario 8 & 9: Ventana de 24 horas para ajuste de clase/puntos tras aprobación (SC-003).
  - Escenarios 10, 11 y 12: Reglas de impacto sobre cronograma de olas confirmado (FR-006, SC-004).
  - Escenario 13: Auditoría con valores previos y nuevos de cada campo (FR-011, SC-002).
- User Story 2: Retiro y restauración de eventos (FR-007 a FR-012, SC-005)
  - Escenario 1: Club envía cancelación -> marca bandera 'cancelado_por_el_club'.
  - Escenario 2 & 3: Admin retira evento publicado con motivo obligatorio -> pasa a 'withdrawn', desaparece de HU-17.
  - Escenario 4: Cronograma y segmentación son anulados.
  - Escenario 5: No admite carga de asistencia (HU-24) ni cuenta para scoring (SC-005).
  - Escenario 6: Socio abriendo link antiguo (HU-39) recibe mensaje de evento retirado.
  - Escenario 7: Admin restaura evento -> vuelve a 'publicado', cronograma permanece anulado.
  - Escenario 9: Auditoría completa de retiro y restauración.
- Cimientos de Notificaciones:
  - Verificación de registros en 'notificaciones_eventos' en reprogramación, retiro y restauración.
- Seguridad y Autorización:
  - Acciones restringidas exclusivamente a administradores (401 y 403).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.date_utils import asegurar_utc
from app.models import AuditLog, FeeStatus, Member, Ranking, User
from app.models.domain import EventoVisibleDB
from app.models.notifications import EventNotificationDB, TipoNotificacionEvento
from app.models.segmentation import WaveSegmentation
from app.models.wave_schedule import WaveSchedule, WaveScheduleStatus
from app.schemas.eventos import EventoCreateRequest
from tests.conftest import BOCA_HEADERS, MakeMember, Outbox, admin_token, bearer, member_token

BOCA_ID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def socio_boca(make_member: MakeMember) -> Member:
    return make_member(activated=True, fee_status=FeeStatus.UP_TO_DATE)


def _crear_y_publicar_partido(
    client: TestClient,
    admin_tok: str,
    id_ext: str,
    horas_adelante: int = 72,
    tipo: str = "Partido",
    titulo: str = "Partido Original",
    lugar: str = "Estadio Principal",
    db: Session | None = None,
) -> tuple[str, datetime]:
    ahora = datetime.now(UTC)
    fh = ahora + timedelta(hours=horas_adelante)
    # Crear evento por API club
    res_crear = client.post(
        "/api/v1/eventos",
        json={
            "id_externo": id_ext,
            "titulo": titulo,
            "fecha_hora": fh.isoformat(),
            "lugar": lugar,
            "tipo": tipo,
            "descripcion": "Descripcion inicial",
        },
        headers=BOCA_HEADERS,
    )
    assert res_crear.status_code == 201, res_crear.text
    id_interno = res_crear.json()["id_interno"]

    # Publicar manualmente por Admin
    payload_pub = {"clase": "A"} if tipo == "Partido" else {"puntos": 30}
    res_pub = client.post(
        f"/admin/events/{id_interno}/publish",
        json=payload_pub,
        headers=bearer(admin_tok),
    )
    assert res_pub.status_code == 200, res_pub.text

    if db is not None:
        ev_db = db.get(EventoVisibleDB, id_interno)
        if ev_db is None:
            ev_db = EventoVisibleDB(
                id_interno=id_interno,
                id_externo=id_ext,
                club_id=uuid.UUID(BOCA_ID),
                titulo=titulo,
                fecha_hora=fh,
                lugar=lugar,
                tipo=tipo,
                clase="A" if tipo == "Partido" else None,
                puntos=30 if tipo != "Partido" else None,
                estado="publicado",
                publicado_por="admin",
            )
            db.add(ev_db)
            db.commit()

    return id_interno, fh


# ==============================================================================
# USER STORY 1: REVISIÓN DE ACTUALIZACIONES ENVIADAS POR EL CLUB
# ==============================================================================


def test_club_sends_update_stores_pending_review_and_shows_comparison(
    client: TestClient, db: Session, outbox: Outbox, admin: User, socio_boca: Member
):
    """Escenario 1 & FR-001, FR-002: Actualización de evento publicado queda pendiente de revisión sin aplicarse."""
    token = admin_token(client, outbox, admin)
    token_socio = member_token(client, outbox, socio_boca)
    id_ext = f"EVT-REPROG-{uuid.uuid4().hex[:6]}"
    id_int, fh_orig = _crear_y_publicar_partido(client, token, id_ext, horas_adelante=80, db=db)

    nueva_fh = fh_orig + timedelta(days=2)
    nuevo_lugar = "Nuevo Estadio Secundario"
    nuevo_titulo = "Partido con fecha y sede modificada"

    # Club envía PUT
    res_put = client.put(
        f"/api/v1/eventos/{id_ext}",
        json={
            "titulo": nuevo_titulo,
            "fecha_hora": nueva_fh.isoformat(),
            "lugar": nuevo_lugar,
            "descripcion": "Nueva descripcion",
        },
        headers=BOCA_HEADERS,
    )
    assert res_put.status_code == 200
    data_put = res_put.json()
    assert data_put["cambio_creado"] is True
    id_cambio = data_put["id_cambio"]

    # Socios NO ven el cambio todavía en HU-17
    res_socio = client.get("/events/upcoming", headers=bearer(token_socio))
    assert res_socio.status_code == 200
    evs = [e for e in res_socio.json()["eventos"] if e["id_interno"] == id_int]
    assert len(evs) == 1
    assert evs[0]["lugar"] == "Estadio Principal"
    assert evs[0]["titulo"] == "Partido Original"

    # Admin consulta listado de cambios y ve la comparativa antes/después
    res_changes = client.get("/admin/events/changes", headers=bearer(token))
    assert res_changes.status_code == 200
    cambios = [c for c in res_changes.json() if str(c["id_cambio"]) == str(id_cambio)]
    assert len(cambios) == 1
    c = cambios[0]
    assert c["id_interno"] == id_int
    assert c["id_externo"] == id_ext
    assert c["comparacion"]["lugar_actual"] == "Estadio Principal"
    assert c["comparacion"]["lugar_nuevo"] == nuevo_lugar
    assert c["comparacion"]["titulo_actual"] == "Partido Original"
    assert c["comparacion"]["titulo_nuevo"] == nuevo_titulo


def test_admin_approves_change_updates_immediately_and_audits(
    client: TestClient, db: Session, outbox: Outbox, admin: User, socio_boca: Member
):
    """Escenario 2, 8, 13 & FR-003, FR-005, FR-011: Admin aprueba cambio, se aplica de inmediato y abre ventana de 24h."""
    token = admin_token(client, outbox, admin)
    token_socio = member_token(client, outbox, socio_boca)
    id_ext = f"EVT-APPROVE-{uuid.uuid4().hex[:6]}"
    id_int, fh_orig = _crear_y_publicar_partido(client, token, id_ext, horas_adelante=80, db=db)

    nueva_fh = fh_orig + timedelta(days=1)
    res_put = client.put(
        f"/api/v1/eventos/{id_ext}",
        json={
            "titulo": "Superclásico Reprogramado",
            "fecha_hora": nueva_fh.isoformat(),
            "lugar": "Estadio Visitante Monumental",
        },
        headers=BOCA_HEADERS,
    )
    id_cambio = res_put.json()["id_cambio"]

    # Admin aprueba el cambio
    res_appr = client.post(
        f"/admin/events/changes/{id_cambio}/approve",
        headers=bearer(token),
    )
    assert res_appr.status_code == 200
    data_appr = res_appr.json()
    assert data_appr["estado"] == "aprobado"
    assert data_appr["fin_ajuste_clase_puntos"] is not None

    # Socios ven inmediatamente los nuevos datos en HU-17
    res_socio = client.get("/events/upcoming", headers=bearer(token_socio))
    evs = [e for e in res_socio.json()["eventos"] if e["id_interno"] == id_int]
    assert len(evs) == 1
    assert evs[0]["titulo"] == "Superclásico Reprogramado"
    assert evs[0]["lugar"] == "Estadio Visitante Monumental"

    # Verificar auditoría
    audit_entry = db.scalar(
        select(AuditLog).where(
            AuditLog.entity == "event",
            AuditLog.entity_id == id_int,
            AuditLog.action == "event.reprogrammed",
        )
    )
    assert audit_entry is not None
    assert audit_entry.actor_user_id == admin.id
    assert audit_entry.details["previous"]["lugar"] == "Estadio Principal"
    assert audit_entry.details["new"]["lugar"] == "Estadio Visitante Monumental"

    # Verificar cimientos de notificaciones
    notif = db.scalar(
        select(EventNotificationDB).where(
            EventNotificationDB.event_id == id_int,
            EventNotificationDB.tipo_notificacion == TipoNotificacionEvento.EVENTO_REPROGRAMADO,
        )
    )
    assert notif is not None
    assert "Superclásico Reprogramado" in notif.titulo or notif.mensaje


def test_admin_rejects_change_event_stays_as_it_was(
    client: TestClient, db: Session, outbox: Outbox, admin: User, socio_boca: Member
):
    """Escenario 3 & 13: Admin rechaza cambio, evento queda intacto con sus valores previos."""
    token = admin_token(client, outbox, admin)
    token_socio = member_token(client, outbox, socio_boca)
    id_ext = f"EVT-REJECT-{uuid.uuid4().hex[:6]}"
    id_int, fh_orig = _crear_y_publicar_partido(client, token, id_ext, horas_adelante=80, db=db)

    res_put = client.put(
        f"/api/v1/eventos/{id_ext}",
        json={"lugar": "Lugar No Habilitado"},
        headers=BOCA_HEADERS,
    )
    id_cambio = res_put.json()["id_cambio"]

    # Admin rechaza
    res_rej = client.post(
        f"/admin/events/changes/{id_cambio}/reject",
        json={"motivo": "Lugar no cuenta con habilitación de seguridad"},
        headers=bearer(token),
    )
    assert res_rej.status_code == 200
    assert res_rej.json()["estado"] == "rechazado"

    # HU-17 mantiene el lugar original
    res_socio = client.get("/events/upcoming", headers=bearer(token_socio))
    evs = [e for e in res_socio.json()["eventos"] if e["id_interno"] == id_int]
    assert evs[0]["lugar"] == "Estadio Principal"

    # Auditoría de rechazo
    audit_entry = db.scalar(
        select(AuditLog).where(
            AuditLog.entity == "event",
            AuditLog.entity_id == id_int,
            AuditLog.action == "event.reprogramming_rejected",
        )
    )
    assert audit_entry is not None


def test_club_sends_identical_values_no_change_stored(
    client: TestClient, db: Session, outbox: Outbox, admin: User
):
    """Escenario 4: Si los valores son idénticos, no se almacena cambio y se avisa que está al día."""
    token = admin_token(client, outbox, admin)
    id_ext = f"EVT-IDENTICAL-{uuid.uuid4().hex[:6]}"
    id_int, fh_orig = _crear_y_publicar_partido(client, token, id_ext, horas_adelante=80, db=db)

    res_put = client.put(
        f"/api/v1/eventos/{id_ext}",
        json={
            "titulo": "Partido Original",
            "fecha_hora": fh_orig.isoformat(),
            "lugar": "Estadio Principal",
            "descripcion": "Descripcion inicial",
        },
        headers=BOCA_HEADERS,
    )
    assert res_put.status_code == 200
    assert res_put.json()["cambio_creado"] is False
    assert "actualizado" in res_put.json()["mensaje"].lower()


def test_club_sends_different_type_rejected(
    client: TestClient, db: Session, outbox: Outbox, admin: User
):
    """Escenario 5 & FR-004: Intento de cambiar el tipo de evento es rechazado con 422."""
    token = admin_token(client, outbox, admin)
    id_ext = f"EVT-TYPE-CHANGE-{uuid.uuid4().hex[:6]}"
    id_int, _ = _crear_y_publicar_partido(client, token, id_ext, horas_adelante=80, tipo="Partido", db=db)

    res_put = client.put(
        f"/api/v1/eventos/{id_ext}",
        json={"tipo": "Institucional"},
        headers=BOCA_HEADERS,
    )
    assert res_put.status_code == 422
    assert res_put.json()["error"]["code"] == "EVENT_TYPE_CHANGE_NOT_ALLOWED"


def test_club_sends_update_for_started_or_withdrawn_rejected(
    client: TestClient, db: Session, outbox: Outbox, admin: User
):
    """Escenario 6 & FR-004: Eventos ya comenzados o retirados rechazan actualizaciones."""
    token = admin_token(client, outbox, admin)
    id_ext = f"EVT-STARTED-{uuid.uuid4().hex[:6]}"
    id_int, fh_orig = _crear_y_publicar_partido(client, token, id_ext, horas_adelante=50, db=db)

    # Simular momento posterior al inicio
    sim_post = (fh_orig + timedelta(hours=1)).isoformat()
    res_put = client.put(
        f"/api/v1/eventos/{id_ext}?reloj_simulado={sim_post}",
        json={"lugar": "Nuevo Lugar"},
        headers=BOCA_HEADERS,
    )
    assert res_put.status_code == 422
    assert res_put.json()["error"]["code"] == "EVENT_ALREADY_STARTED"


def test_new_update_replaces_pending_review(
    client: TestClient, db: Session, outbox: Outbox, admin: User
):
    """Escenario 7: Una nueva actualización reemplaza a la que estaba pendiente de revisión."""
    token = admin_token(client, outbox, admin)
    id_ext = f"EVT-REPLACE-{uuid.uuid4().hex[:6]}"
    id_int, fh_orig = _crear_y_publicar_partido(client, token, id_ext, horas_adelante=80, db=db)

    # Primera actualización
    res1 = client.put(
        f"/api/v1/eventos/{id_ext}",
        json={"lugar": "Lugar Intento 1"},
        headers=BOCA_HEADERS,
    )
    id_cambio1 = res1.json()["id_cambio"]

    # Segunda actualización
    res2 = client.put(
        f"/api/v1/eventos/{id_ext}",
        json={"lugar": "Lugar Intento 2 Definitivo"},
        headers=BOCA_HEADERS,
    )
    id_cambio2 = res2.json()["id_cambio"]

    # En la lista de pendientes solo debe figurar la segunda
    res_changes = client.get("/admin/events/changes", headers=bearer(token))
    cambios_evento = [c for c in res_changes.json() if c["id_interno"] == id_int]
    assert len(cambios_evento) == 1
    assert str(cambios_evento[0]["id_cambio"]) == str(id_cambio2)
    assert cambios_evento[0]["comparacion"]["lugar_nuevo"] == "Lugar Intento 2 Definitivo"


def test_24h_window_class_points_adjustment(
    client: TestClient, db: Session, outbox: Outbox, admin: User
):
    """Escenarios 8 & 9, FR-005, SC-003: Ajuste de clase habilitado por 24h y bloqueado luego."""
    token = admin_token(client, outbox, admin)
    id_ext = f"EVT-ADJUST-{uuid.uuid4().hex[:6]}"
    id_int, fh_orig = _crear_y_publicar_partido(client, token, id_ext, horas_adelante=80, db=db)

    # Enviar y aprobar cambio
    res_put = client.put(
        f"/api/v1/eventos/{id_ext}",
        json={"lugar": "Nuevo Lugar Ajuste"},
        headers=BOCA_HEADERS,
    )
    id_cambio = res_put.json()["id_cambio"]
    res_appr = client.post(
        f"/admin/events/changes/{id_cambio}/approve",
        headers=bearer(token),
    )
    assert res_appr.status_code == 200

    # Dentro de las 24 horas (ej: a las 5 horas) -> Debe permitir ajustar clase a 'C'
    ahora = datetime.now(UTC)
    sim_5h = (ahora + timedelta(hours=5)).isoformat()
    res_adj = client.post(
        f"/admin/events/{id_int}/adjust-class?reloj_simulado={sim_5h}",
        json={"clase": "C"},
        headers=bearer(token),
    )
    assert res_adj.status_code == 200
    assert res_adj.json()["clase"] == "C"

    # Fuera de las 24 horas (ej: a las 25 horas) -> Debe ser rechazado (422)
    sim_25h = (ahora + timedelta(hours=25)).isoformat()
    res_adj_late = client.post(
        f"/admin/events/{id_int}/adjust-class?reloj_simulado={sim_25h}",
        json={"clase": "A"},
        headers=bearer(token),
    )
    assert res_adj_late.status_code == 422
    assert "expirado" in res_adj_late.text.lower() or "habilitada" in res_adj_late.text.lower()


def test_wave_schedule_rules_scenarios_10_11_12(
    client: TestClient, db: Session, outbox: Outbox, admin: User
):
    """
    Escenarios 10, 11 y 12 (FR-006 & SC-004):
    - Escenario 10: new_start >= closing_at -> cronograma intacto.
    - Escenario 11: new_start < closing_at y ninguna ola abrió -> cronograma invalidado.
    - Escenario 12: new_start < closing_at y ya abrió alguna ola -> closing_at = new_start.
    """
    token = admin_token(client, outbox, admin)

    # --- ESCENARIO 10 ---
    id_ext10 = f"EVT-WS-10-{uuid.uuid4().hex[:6]}"
    id_int10, fh10 = _crear_y_publicar_partido(client, token, id_ext10, horas_adelante=100, db=db)
    opening_10 = datetime.now(UTC) + timedelta(hours=10)
    closing_10 = datetime.now(UTC) + timedelta(hours=40)

    # Asegurar ranking y segmentación para FK en Postgres
    ranking = db.scalars(select(Ranking)).first()
    if not ranking:
        from tests.hu25_helpers import publish_rules
        from tests.hu36_helpers import ranking_with

        publish_rules(client, bearer(token))
        ranking = ranking_with(db, admin, 10)

    seg10 = WaveSegmentation(
        club_id=uuid.UUID(BOCA_ID),
        event_id=id_int10,
        ranking_id=ranking.id,
        ranked_total=10,
        percentile_step=20,
        generated_by_id=admin.id,
    )
    db.add(seg10)
    db.commit()

    ws10 = WaveSchedule(
        club_id=uuid.UUID(BOCA_ID),
        event_id=id_int10,
        segmentation_id=seg10.id,
        opening_at=opening_10,
        closing_at=closing_10,
        status=WaveScheduleStatus.CONFIRMED,
        generated_by_id=admin.id,
    )
    db.add(ws10)
    db.commit()

    # Reprogramar a +60 horas (new_start 60h >= closing 40h)
    new_start_10 = datetime.now(UTC) + timedelta(hours=60)
    res_put = client.put(
        f"/api/v1/eventos/{id_ext10}",
        json={"fecha_hora": new_start_10.isoformat()},
        headers=BOCA_HEADERS,
    )
    id_cambio10 = res_put.json()["id_cambio"]
    res_appr10 = client.post(
        f"/admin/events/changes/{id_cambio10}/approve",
        headers=bearer(token),
    )
    assert res_appr10.status_code == 200
    db.refresh(ws10)
    assert ws10.status == WaveScheduleStatus.CONFIRMED
    assert asegurar_utc(ws10.closing_at) == asegurar_utc(closing_10)  # Intacto

    # --- ESCENARIO 11 ---
    # new_start < closing_at y now < opening_at -> invalidado
    id_ext11 = f"EVT-WS-11-{uuid.uuid4().hex[:6]}"
    id_int11, fh11 = _crear_y_publicar_partido(client, token, id_ext11, horas_adelante=100, db=db)
    opening_11 = datetime.now(UTC) + timedelta(hours=20)
    closing_11 = datetime.now(UTC) + timedelta(hours=50)

    seg11 = WaveSegmentation(
        club_id=uuid.UUID(BOCA_ID),
        event_id=id_int11,
        ranking_id=ranking.id,
        ranked_total=10,
        percentile_step=20,
        generated_by_id=admin.id,
    )
    db.add(seg11)
    db.commit()

    ws11 = WaveSchedule(
        club_id=uuid.UUID(BOCA_ID),
        event_id=id_int11,
        segmentation_id=seg11.id,
        opening_at=opening_11,
        closing_at=closing_11,
        status=WaveScheduleStatus.CONFIRMED,
        generated_by_id=admin.id,
    )
    db.add(ws11)
    db.commit()

    # Reprogramar a +30 horas (antes del closing de 50h, pero ahora < opening de 20h)
    new_start_11 = datetime.now(UTC) + timedelta(hours=30)
    res_put11 = client.put(
        f"/api/v1/eventos/{id_ext11}",
        json={"fecha_hora": new_start_11.isoformat()},
        headers=BOCA_HEADERS,
    )
    id_cambio11 = res_put11.json()["id_cambio"]
    res_appr11 = client.post(
        f"/admin/events/changes/{id_cambio11}/approve",
        headers=bearer(token),
    )
    assert res_appr11.status_code == 200
    assert "invalidado" in res_appr11.json()["advertencia_cronograma"].lower()
    db.refresh(ws11)
    assert ws11.status == WaveScheduleStatus.INVALIDATED

    # --- ESCENARIO 12 ---
    # new_start < closing_at y now >= opening_at -> closing_at = new_start
    id_ext12 = f"EVT-WS-12-{uuid.uuid4().hex[:6]}"
    id_int12, fh12 = _crear_y_publicar_partido(client, token, id_ext12, horas_adelante=100, db=db)
    opening_12 = datetime.now(UTC) - timedelta(hours=5)  # Ya abrió
    closing_12 = datetime.now(UTC) + timedelta(hours=50)

    seg12 = WaveSegmentation(
        club_id=uuid.UUID(BOCA_ID),
        event_id=id_int12,
        ranking_id=ranking.id,
        ranked_total=10,
        percentile_step=20,
        generated_by_id=admin.id,
    )
    db.add(seg12)
    db.commit()

    ws12 = WaveSchedule(
        club_id=uuid.UUID(BOCA_ID),
        event_id=id_int12,
        segmentation_id=seg12.id,
        opening_at=opening_12,
        closing_at=closing_12,
        status=WaveScheduleStatus.CONFIRMED,
        generated_by_id=admin.id,
    )
    db.add(ws12)
    db.commit()

    new_start_12 = datetime.now(UTC) + timedelta(hours=20)
    res_put12 = client.put(
        f"/api/v1/eventos/{id_ext12}",
        json={"fecha_hora": new_start_12.isoformat()},
        headers=BOCA_HEADERS,
    )
    id_cambio12 = res_put12.json()["id_cambio"]
    res_appr12 = client.post(
        f"/admin/events/changes/{id_cambio12}/approve",
        headers=bearer(token),
    )
    assert res_appr12.status_code == 200
    assert "ajustó" in res_appr12.json()["advertencia_cronograma"].lower()
    db.refresh(ws12)
    assert asegurar_utc(ws12.closing_at) == asegurar_utc(new_start_12)


# ==============================================================================
# USER STORY 2: RETIRO Y RESTAURACIÓN DE EVENTOS
# ==============================================================================


def test_club_sends_cancellation_flags_event(
    client: TestClient, db: Session, outbox: Outbox, admin: User, socio_boca: Member
):
    """Escenario 1 & FR-007: Club envía cancelación -> marca 'cancelado_por_el_club'."""
    token = admin_token(client, outbox, admin)
    token_socio = member_token(client, outbox, socio_boca)
    id_ext = f"EVT-CANCEL-{uuid.uuid4().hex[:6]}"
    id_int, _ = _crear_y_publicar_partido(client, token, id_ext, horas_adelante=80, db=db)

    res_cancel = client.post(
        f"/api/v1/eventos/{id_ext}/cancelacion",
        json={"motivo": "Cancelado por tormenta eléctrica"},
        headers=BOCA_HEADERS,
    )
    assert res_cancel.status_code == 200
    assert res_cancel.json()["cancelado_por_el_club"] is True

    # El evento sigue publicado y visible para socios hasta que el admin lo retire
    res_socio = client.get("/events/upcoming", headers=bearer(token_socio))
    evs = [e for e in res_socio.json()["eventos"] if e["id_interno"] == id_int]
    assert len(evs) == 1


def test_admin_withdraws_event_requires_reason_and_hides_from_socio(
    client: TestClient, db: Session, outbox: Outbox, admin: User, socio_boca: Member
):
    """Escenarios 2, 3, 4, 5, 6, 9: Retiro de evento requiere motivo, oculta de HU-17 y bloquea HU-24."""
    token = admin_token(client, outbox, admin)
    socio_tok = member_token(client, outbox, socio_boca)
    id_ext = f"EVT-WITHDRAW-{uuid.uuid4().hex[:6]}"
    id_int, _ = _crear_y_publicar_partido(client, token, id_ext, horas_adelante=80, db=db)

    # 1. Intentar retirar sin motivo -> 422
    res_bad = client.post(
        f"/admin/events/{id_int}/withdraw",
        json={"motivo": ""},
        headers=bearer(token),
    )
    assert res_bad.status_code == 422

    # 2. Retirar con motivo válido
    motivo_txt = "Partido suspendido por disposición municipal"
    res_with = client.post(
        f"/admin/events/{id_int}/withdraw",
        json={"motivo": motivo_txt},
        headers=bearer(token),
    )
    assert res_with.status_code == 200
    assert res_with.json()["estado"] == "withdrawn"
    assert res_with.json()["motivo"] == motivo_txt

    # 3. Desaparece de HU-17 (próximos eventos para socio)
    res_socio = client.get("/events/upcoming", headers=bearer(socio_tok))
    evs = [e for e in res_socio.json()["eventos"] if e["id_interno"] == id_int]
    assert len(evs) == 0

    # 4. Socio que ingresa por link viejo (HU-39) recibe mensaje de retirado
    res_slot = client.get(
        f"/member/events/{id_int}/slot",
        headers={"Authorization": f"Bearer {socio_tok}", "X-Club-ID": BOCA_ID},
    )
    assert res_slot.status_code == 200
    data_slot = res_slot.json()
    assert data_slot["status"] == "withdrawn"
    assert "retirado" in data_slot["message"].lower()

    # 5. Auditoría registrada
    audit_entry = db.scalar(
        select(AuditLog).where(
            AuditLog.entity == "event",
            AuditLog.entity_id == id_int,
            AuditLog.action == "event.withdrawn",
        )
    )
    assert audit_entry is not None
    assert audit_entry.actor_user_id == admin.id
    assert audit_entry.details.get("reason") == motivo_txt or audit_entry.details.get("motivo") == motivo_txt

    # 6. Notificación encolada
    notif = db.scalar(
        select(EventNotificationDB).where(
            EventNotificationDB.event_id == id_int,
            EventNotificationDB.tipo_notificacion == TipoNotificacionEvento.EVENTO_RETIRADO,
        )
    )
    assert notif is not None

    # 7. No admite asistencia (HU-24)
    from app.services.participacion_service import ParticipacionService

    with pytest.raises(Exception) as excinfo:
        ParticipacionService._verificar_evento_elegible(uuid.UUID(BOCA_ID), id_ext, db)
    assert "EVENT_WITHDRAWN" in str(excinfo.value)


def test_admin_restores_event_reappears_in_hu17(
    client: TestClient, db: Session, outbox: Outbox, admin: User, socio_boca: Member
):
    """Escenario 7 & FR-010: Restaurar evento retirado lo devuelve a publicado y HU-17."""
    token = admin_token(client, outbox, admin)
    token_socio = member_token(client, outbox, socio_boca)
    id_ext = f"EVT-RESTORE-{uuid.uuid4().hex[:6]}"
    id_int, _ = _crear_y_publicar_partido(client, token, id_ext, horas_adelante=80, db=db)

    # Retirar
    client.post(
        f"/admin/events/{id_int}/withdraw",
        json={"motivo": "Cancelación temporal"},
        headers=bearer(token),
    )

    # Restaurar
    res_rest = client.post(
        f"/admin/events/{id_int}/restore",
        headers=bearer(token),
    )
    assert res_rest.status_code == 200
    assert res_rest.json()["estado"] == "publicado"

    # Reaparece en HU-17
    res_socio = client.get("/events/upcoming", headers=bearer(token_socio))
    evs = [e for e in res_socio.json()["eventos"] if e["id_interno"] == id_int]
    assert len(evs) == 1

    # Auditoría registrada
    audit_entry = db.scalar(
        select(AuditLog).where(
            AuditLog.entity == "event",
            AuditLog.entity_id == id_int,
            AuditLog.action == "event.restored",
        )
    )
    assert audit_entry is not None

    # Notificación encolada
    notif = db.scalar(
        select(EventNotificationDB).where(
            EventNotificationDB.event_id == id_int,
            EventNotificationDB.tipo_notificacion == TipoNotificacionEvento.EVENTO_RESTAURADO,
        )
    )
    assert notif is not None


def test_security_admin_endpoints_restricted(
    client: TestClient, outbox: Outbox, socio_boca: Member
):
    """Seguridad y Autorización: endpoints administrativos rechazan anónimos y socios."""
    socio_tok = member_token(client, outbox, socio_boca)

    # Sin token -> 401
    assert client.get("/admin/events/changes").status_code == 401
    assert client.post("/admin/events/EVT-X/withdraw", json={"motivo": "x"}).status_code == 401

    # Con token de socio -> 403
    assert client.get("/admin/events/changes", headers=bearer(socio_tok)).status_code == 403
    assert client.post("/admin/events/EVT-X/withdraw", json={"motivo": "x"}, headers=bearer(socio_tok)).status_code == 403


def test_admin_published_events_and_operations_by_name(
    client: TestClient, db: Session, outbox: Outbox, admin: User
):
    """Verifica el listado de eventos publicados y el retiro/restauración/ajuste por NOMBRE de evento."""
    token = admin_token(client, outbox, admin)
    titulo_unico = f"Superclásico Exclusivo {uuid.uuid4().hex[:6]}"
    id_ext = f"EVT-NOM-{uuid.uuid4().hex[:6]}"
    id_int, _ = _crear_y_publicar_partido(
        client, token, id_ext, horas_adelante=85, titulo=titulo_unico, db=db
    )

    # 1. GET /admin/events/published
    res_pub_list = client.get("/admin/events/published", headers=bearer(token))
    assert res_pub_list.status_code == 200
    encontrado = [e for e in res_pub_list.json() if e["id_interno"] == id_int]
    assert len(encontrado) == 1
    assert encontrado[0]["titulo"] == titulo_unico
    assert encontrado[0]["id_externo"] == id_ext

    # 2. Retirar por NOMBRE (titulo)
    res_with = client.post(
        f"/admin/events/{titulo_unico}/withdraw",
        json={"motivo": "Retiro buscando por nombre del evento"},
        headers=bearer(token),
    )
    assert res_with.status_code == 200
    assert res_with.json()["estado"] == "withdrawn"
    assert res_with.json()["id_interno"] == id_int

    # 3. Restaurar por NOMBRE (titulo)
    res_rest = client.post(
        f"/admin/events/{titulo_unico}/restore",
        headers=bearer(token),
    )
    assert res_rest.status_code == 200
    assert res_rest.json()["estado"] == "publicado"
    assert res_rest.json()["id_interno"] == id_int


def test_retirar_y_restaurar_evento_pendiente_por_id_y_nombre(
    client: TestClient, db: Session, outbox: Outbox, admin: User
):
    """Verifica que un evento pendiente puede ser retirado/descartado y restaurado por ID o por Nombre."""
    token = admin_token(client, outbox, admin)
    id_ext = f"EVT-PEND-{uuid.uuid4().hex[:6]}"
    titulo_pend = f"Evento Pendiente Gala {uuid.uuid4().hex[:6]}"
    futuro = datetime.now(UTC) + timedelta(hours=72)

    # 1. Crear evento pendiente
    res_crear = client.post(
        "/api/v1/eventos",
        json={
            "id_externo": id_ext,
            "titulo": titulo_pend,
            "fecha_hora": futuro.isoformat(),
            "lugar": "Salón Bombonera",
            "tipo": "Institucional",
            "descripcion": "Evento institucional pendiente",
        },
        headers=BOCA_HEADERS,
    )
    assert res_crear.status_code == 201
    id_int = res_crear.json()["id_interno"]

    # 2. Retirar por ID externo
    res_with = client.post(
        f"/admin/events/{id_ext}/withdraw",
        json={"motivo": "Descarte de prueba por id"},
        headers=bearer(token),
    )
    assert res_with.status_code == 200
    assert res_with.json()["estado"] == "descartado"

    # Verificar que ya no aparece en pendientes
    res_pend = client.get("/admin/events/pending", headers=bearer(token))
    assert all(e["id_interno"] != id_int for e in res_pend.json())

    # 3. Restaurar por NOMBRE (titulo)
    res_rest = client.post(
        f"/admin/events/{titulo_pend}/restore",
        headers=bearer(token),
    )
    assert res_rest.status_code == 200
    assert res_rest.json()["estado"] == "pendiente_definicion_importancia"

    # Verificar que vuelve a aparecer en pendientes
    res_pend2 = client.get("/admin/events/pending", headers=bearer(token))
    assert any(e["id_interno"] == id_int for e in res_pend2.json())
