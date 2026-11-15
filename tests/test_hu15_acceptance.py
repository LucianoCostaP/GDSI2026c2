"""HU-15: tests de aceptación del historial de eventos del Socio, por la API."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import MakeMember, Outbox
from tests.hu15_helpers import (
    HISTORY,
    make_historical_event,
    member_headers,
    socio_with_account,
    titles,
    uid,
    utc,
)
from tests.hu25_helpers import load_attendance, make_event


def test_lista_los_eventos_asistidos_del_mas_reciente_al_mas_antiguo(
    db: Session, client: TestClient, outbox: Outbox, make_member: MakeMember
) -> None:
    ana = socio_with_account(db, make_member)
    e1 = make_event(db, id_externo=uid("EVT-01"), when=utc("2026-03-10T20:00:00Z"))
    e2 = make_event(
        db,
        id_externo=uid("EVT-02"),
        when=utc("2026-05-02T18:00:00Z"),
        tipo="Institucional",
        clase=None,
        puntos=10,
    )
    e3 = make_event(db, id_externo=uid("EVT-03"), when=utc("2026-08-15T21:30:00Z"))
    e4 = make_event(db, id_externo=uid("EVT-04"), when=utc("2026-09-01T21:30:00Z"))
    for event in (e1, e2, e3):
        load_attendance(db, event, [ana.socio])

    response = client.get(HISTORY, headers=member_headers(client, outbox, ana.member))

    assert response.status_code == 200
    assert titles(response) == [e3.titulo, e2.titulo, e1.titulo]
    assert e4.titulo not in titles(response)
    assert response.json()["total"] == 3


def test_un_evento_historico_forma_parte_del_historial(
    db: Session, client: TestClient, outbox: Outbox, make_member: MakeMember
) -> None:
    ana = socio_with_account(db, make_member)
    historical = make_historical_event(
        db, id_externo=uid("HIST-01"), when=utc("2025-11-20T20:00:00Z")
    )
    load_attendance(db, historical, [ana.socio])

    response = client.get(HISTORY, headers=member_headers(client, outbox, ana.member))

    assert response.status_code == 200
    assert titles(response) == [historical.titulo]
