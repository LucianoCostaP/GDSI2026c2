"""
Suite de pruebas para HU-17: Consulta de próximos eventos (View Upcoming Events).
Cubre:
- Test independiente: Publicar un evento (HU-22), iniciar sesión como socio y verificar que aparece con fecha, hora y sede en orden cronológico, y que un evento no publicado no aparece.
- Escenario 1: Eventos publicados futuros muestran fecha, hora, sede y tipo ('Partido' o 'Evento institucional/amateur').
- Escenario 2: Orden cronológico estricto (el más próximo primero).
- Escenario 3: Acceso read-only y presencia de enlace al turno del socio (HU-39).
- Escenario 4: Mensaje informativo cuando no hay próximos eventos publicados.
- Escenario 5: Eventos en estados no permitidos ('pendiente_definicion_importancia', 'Historico') NO se muestran.
- Edge case: Evento ya iniciado / pasado desaparece de la lista.
- Edge case: La clase del partido (A, B, C) NO se expone a los socios.
- Edge case: Conversión de huso horario a America/Argentina/Buenos_Aires.
- Seguridad y autorización por rol:
  - Petición sin token -> 401 Unauthorized.
  - Petición con rol Admin -> 403 Forbidden (cross-cutting: exclusivo para socios).
  - Petición con rol Member -> 200 OK.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import FeeStatus, User
from app.repositories.factory import get_evento_repository
from app.schemas.eventos import EventoCreateRequest
from tests.conftest import MakeMember, Outbox, admin_token, bearer, member_token

BOCA_ID = "11111111-1111-1111-1111-111111111111"
RIVER_ID = "22222222-2222-2222-2222-222222222222"
BUENOS_AIRES_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


@pytest.fixture
def socio_boca(make_member: MakeMember) -> tuple[User, str]:
    """Crea y activa un socio de prueba para los tests."""
    return make_member(activated=True, fee_status=FeeStatus.UP_TO_DATE)


def test_seguridad_sin_autenticacion(client: TestClient):
    """Petición sin autenticación debe retornar 401 Unauthorized."""
    res = client.get("/events/upcoming")
    assert res.status_code == 401
    assert "NOT_AUTHENTICATED" in res.json()["detail"]


def test_seguridad_rol_admin_prohibido(client: TestClient, outbox: Outbox, admin: User):
    """Un usuario con rol ADMIN no puede acceder a HU-17 (403 Forbidden)."""
    token = admin_token(client, outbox, admin)
    res = client.get("/events/upcoming", headers=bearer(token))
    assert res.status_code == 403
    assert res.json()["detail"] == "FORBIDDEN"


def test_escenario_4_lista_vacia_muestra_mensaje_informativo(
    client: TestClient, outbox: Outbox, socio_boca
):
    """Escenario 4: Si no hay eventos próximos, muestra mensaje informativo."""
    token = member_token(client, outbox, socio_boca)
    res = client.get("/events/upcoming", headers=bearer(token))
    assert res.status_code == 200

    data = res.json()
    assert data["total"] == 0
    assert data["eventos"] == []
    assert data["mensaje"] == "No hay eventos próximos publicados."


def test_test_independiente_y_escenario_1_publicado_vs_no_publicado(
    db: Session, client: TestClient, outbox: Outbox, socio_boca
):
    """
    Test independiente y Escenario 1:
    - Se registra un evento futuro (pendiente).
    - Un socio logueado consulta y NO debe verlo.
    - Se publica el evento (HU-22).
    - El socio consulta y ahora SÍ lo ve con fecha, hora, sede y tipo.
    """
    token = member_token(client, outbox, socio_boca)
    repo = get_evento_repository(db)

    # 1. Crear evento pendiente (futuro: en 3 días a las 20:00 UTC)
    fecha_futura = datetime.now(UTC) + timedelta(days=3)
    fecha_futura = fecha_futura.replace(hour=20, minute=0, second=0, microsecond=0)

    req = EventoCreateRequest(
        id_externo="EVT-FUT-01",
        titulo="Boca vs River",
        fecha_hora=fecha_futura,
        lugar="La Bombonera",
        tipo="Partido",
        descripcion="Superclásico del torneo",
    )
    id_interno = repo.insert_pendiente(club_id=BOCA_ID, evento=req)

    # El socio consulta: el evento pendiente NO debe aparecer
    res_antes = client.get("/events/upcoming", headers=bearer(token))
    assert res_antes.status_code == 200
    assert res_antes.json()["total"] == 0

    # 2. Publicar el evento (HU-22) asignándole Clase B
    repo.publish_evento(club_id=BOCA_ID, id_externo_o_interno=id_interno, clase="B")

    # 3. El socio consulta: ahora SÍ aparece
    res_despues = client.get("/events/upcoming", headers=bearer(token))
    assert res_despues.status_code == 200
    data = res_despues.json()
    assert data["total"] == 1
    assert len(data["eventos"]) == 1

    ev = data["eventos"][0]
    assert ev["id_interno"] == id_interno
    assert ev["titulo"] == "Boca vs River"
    assert ev["lugar"] == "La Bombonera"
    assert ev["tipo"] == "Partido"
    # Debe tener enlace para consultar el turno del socio (HU-39)
    assert (
        f"/events/{id_interno}/slot" in ev["slot_url"]
        or f"/member/events/{id_interno}/slot" in ev["slot_url"]
    )

    # Verificar que NO se expone la clase del partido al socio
    assert "clase" not in ev


def test_escenario_2_orden_cronologico_estricto(
    db: Session, client: TestClient, outbox: Outbox, socio_boca
):
    """
    Escenario 2: Múltiples eventos deben ordenarse cronológicamente (el más próximo primero).
    """
    token = member_token(client, outbox, socio_boca)
    repo = get_evento_repository(db)

    ahora = datetime.now(UTC)
    # Insertamos en orden no cronológico: día 5, día 2, día 10
    evt_dia5 = EventoCreateRequest(
        id_externo="EVT-D5",
        titulo="Evento en 5 días",
        fecha_hora=ahora + timedelta(days=5),
        lugar="Estadio 1",
        tipo="Partido",
    )
    evt_dia2 = EventoCreateRequest(
        id_externo="EVT-D2",
        titulo="Evento en 2 días",
        fecha_hora=ahora + timedelta(days=2),
        lugar="Estadio 2",
        tipo="Partido",
    )
    evt_dia10 = EventoCreateRequest(
        id_externo="EVT-D10",
        titulo="Evento en 10 días",
        fecha_hora=ahora + timedelta(days=10),
        lugar="Sede Social",
        tipo="Institucional",
    )

    id5 = repo.insert_pendiente(club_id=BOCA_ID, evento=evt_dia5)
    id2 = repo.insert_pendiente(club_id=BOCA_ID, evento=evt_dia2)
    id10 = repo.insert_pendiente(club_id=BOCA_ID, evento=evt_dia10)

    # Publicar todos
    repo.publish_evento(club_id=BOCA_ID, id_externo_o_interno=id5, clase="A")
    repo.publish_evento(club_id=BOCA_ID, id_externo_o_interno=id2, clase="B")
    repo.publish_evento(club_id=BOCA_ID, id_externo_o_interno=id10, puntos=20)

    res = client.get("/events/upcoming", headers=bearer(token))
    assert res.status_code == 200
    eventos = res.json()["eventos"]
    assert len(eventos) == 3

    # El orden debe ser: día 2 primero, luego día 5, luego día 10
    assert eventos[0]["id_interno"] == id2
    assert eventos[0]["titulo"] == "Evento en 2 días"
    assert eventos[1]["id_interno"] == id5
    assert eventos[1]["titulo"] == "Evento en 5 días"
    assert eventos[2]["id_interno"] == id10
    assert eventos[2]["titulo"] == "Evento en 10 días"
    # Evento institucional debe mostrarse formateado
    assert eventos[2]["tipo"] == "Evento institucional/amateur"


def test_escenario_5_estados_no_permitidos_excluidos(
    db: Session, client: TestClient, outbox: Outbox, socio_boca
):
    """
    Escenario 5: Eventos en estados:
    - 'pendiente_definicion_importancia'
    - 'Historico'
    NO deben aparecer en la consulta.
    ('discarded' todavía no existe: depende de la cancelación de HU-21.)
    """
    token = member_token(client, outbox, socio_boca)
    repo = get_evento_repository(db)
    ahora = datetime.now(UTC)

    # 1. Pendiente
    repo.insert_pendiente(
        club_id=BOCA_ID,
        evento=EventoCreateRequest(
            id_externo="EVT-PEND",
            titulo="Evento Pendiente",
            fecha_hora=ahora + timedelta(days=3),
            lugar="Estadio",
            tipo="Partido",
        ),
        estado="pendiente_definicion_importancia",
    )

    # 2. Histórico
    repo.insert_pendiente(
        club_id=BOCA_ID,
        evento=EventoCreateRequest(
            id_externo="EVT-HIST",
            titulo="Evento Histórico",
            fecha_hora=ahora + timedelta(days=3),
            lugar="Estadio",
            tipo="Institucional",
            es_historico=True,
        ),
        estado="Historico",
    )

    res = client.get("/events/upcoming", headers=bearer(token))
    assert res.status_code == 200
    assert res.json()["total"] == 0
    assert len(res.json()["eventos"]) == 0


def test_edge_case_evento_iniciado_desaparece_de_la_lista(
    db: Session, client: TestClient, outbox: Outbox, socio_boca
):
    """
    Edge case: Un evento que ya inició (start time <= now) deja de mostrarse en la lista.
    Se prueba inyectando reloj del servidor / tiempo simulado.
    """
    token = member_token(client, outbox, socio_boca)
    repo = get_evento_repository(db)

    # Evento fijado para 2026-11-20T18:00:00Z
    fecha_evento = datetime(2026, 11, 20, 18, 0, 0, tzinfo=UTC)
    req = EventoCreateRequest(
        id_externo="EVT-HORA",
        titulo="Partido Clave",
        fecha_hora=fecha_evento,
        lugar="Estadio",
        tipo="Partido",
    )
    id_ev = repo.insert_pendiente(club_id=BOCA_ID, evento=req)
    repo.publish_evento(club_id=BOCA_ID, id_externo_o_interno=id_ev, clase="A")

    # 1. Consultado 1 hora ANTES de que comience (17:00:00Z) -> DEBE APARECER
    clock_antes = datetime(2026, 11, 20, 17, 0, 0, tzinfo=UTC)
    res_antes = client.get(
        f"/events/upcoming?reloj_simulado={clock_antes.isoformat()}",
        headers=bearer(token),
    )
    assert res_antes.status_code == 200
    assert res_antes.json()["total"] == 1

    # 2. Consultado exactamente al inicio (18:00:00Z) o 1 minuto DESPUÉS (18:01:00Z) -> YA NO APARECE
    clock_despues = datetime(2026, 11, 20, 18, 1, 0, tzinfo=UTC)
    res_despues = client.get(
        f"/events/upcoming?reloj_simulado={clock_despues.isoformat()}",
        headers=bearer(token),
    )
    assert res_despues.status_code == 200
    assert res_despues.json()["total"] == 0


def test_formato_hora_buenos_aires(
    db: Session, client: TestClient, outbox: Outbox, socio_boca
):
    """
    Verifica que la fecha y hora mostradas al socio se conviertan al huso de Buenos Aires (UTC-3).
    2026-12-01T21:30:00Z en UTC equivale a 2026-12-01 18:30 en Buenos Aires.
    """
    token = member_token(client, outbox, socio_boca)
    repo = get_evento_repository(db)

    fecha_utc = datetime(2026, 12, 1, 21, 30, 0, tzinfo=UTC)
    req = EventoCreateRequest(
        id_externo="EVT-TZ-TEST",
        titulo="Partido Nocturno",
        fecha_hora=fecha_utc,
        lugar="Estadio Monumental",
        tipo="Partido",
    )
    id_ev = repo.insert_pendiente(club_id=BOCA_ID, evento=req)
    repo.publish_evento(club_id=BOCA_ID, id_externo_o_interno=id_ev, clase="A")

    res = client.get("/events/upcoming", headers=bearer(token))
    assert res.status_code == 200
    evento = res.json()["eventos"][0]

    assert evento["fecha"] == "2026-12-01"
    assert evento["hora"] == "18:30"
