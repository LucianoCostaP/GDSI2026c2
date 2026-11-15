"""HU-15: tests unitarios de las consultas del historial (con la base del fixture `db`)."""

from sqlalchemy.orm import Session

from app.core.date_utils import asegurar_utc
from app.models import EstadoCargaParticipacion
from app.services.event_history_service import attended_events
from tests.conftest import BOCA_ID, RIVER_ID
from tests.hu15_helpers import make_historical_event, uid, utc
from tests.hu25_helpers import load_attendance, make_event, make_socio

MARZO = utc("2026-03-10T20:00:00Z")


def ids_of(db: Session, dni: str) -> list[str]:
    return [event.id_interno for event in attended_events(db, BOCA_ID, dni)]


def test_incluye_eventos_publicados_con_asistencia_del_socio(db: Session) -> None:
    socio = make_socio(db)
    event = make_event(db, id_externo=uid("E"), when=MARZO)
    load_attendance(db, event, [socio])

    assert ids_of(db, socio.dni) == [event.id_interno]


def test_excluye_eventos_sin_asistencia_del_socio(db: Session) -> None:
    socio, otro = make_socio(db), make_socio(db)
    event = make_event(db, id_externo=uid("E"), when=MARZO)
    load_attendance(db, event, [otro])

    assert ids_of(db, socio.dni) == []


def test_excluye_cargas_que_no_son_definitivas(db: Session) -> None:
    socio = make_socio(db)
    event = make_event(db, id_externo=uid("E"), when=MARZO)
    load_attendance(
        db, event, [socio], estado=EstadoCargaParticipacion.PENDING_APPROVAL
    )

    assert ids_of(db, socio.dni) == []


def test_incluye_eventos_historicos(db: Session) -> None:
    socio = make_socio(db)
    historical = make_historical_event(
        db, id_externo=uid("H"), when=utc("2025-11-20T20:00:00Z")
    )
    load_attendance(db, historical, [socio])

    assert ids_of(db, socio.dni) == [historical.id_interno]


def test_no_mezcla_eventos_de_otro_club(db: Session) -> None:
    socio = make_socio(db)
    mismo_dni_en_river = make_socio(db, club_id=RIVER_ID, dni=socio.dni)
    event_river = make_event(db, id_externo=uid("E"), when=MARZO, club_id=RIVER_ID)
    load_attendance(db, event_river, [mismo_dni_en_river])

    assert ids_of(db, socio.dni) == []


def test_devuelve_titulo_fecha_y_tipo_del_evento(db: Session) -> None:
    socio = make_socio(db)
    event = make_event(db, id_externo=uid("E"), when=MARZO, tipo="Institucional")
    load_attendance(db, event, [socio])

    [attended] = attended_events(db, BOCA_ID, socio.dni)
    assert attended.titulo == event.titulo
    assert attended.tipo == "Institucional"
    assert asegurar_utc(attended.fecha_hora) == MARZO
