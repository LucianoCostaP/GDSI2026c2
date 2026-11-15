"""HU-15: tests de aceptación del historial de eventos del Socio, por la API."""

from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RulesVersion, User
from app.services.formula_service import explanation_of
from tests.conftest import BOCA_ID, MakeMember, Outbox
from tests.hu15_helpers import (
    HISTORY,
    RULES,
    backdate_rules,
    make_historical_event,
    member_headers,
    socio_with_account,
    titles,
    uid,
    utc,
)
from tests.hu25_helpers import (
    adjust_rules,
    headers_for,
    load_attendance,
    make_event,
    publish_rules,
)


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


def test_cada_evento_muestra_fecha_y_tipo_sin_la_clase(
    db: Session, client: TestClient, outbox: Outbox, make_member: MakeMember
) -> None:
    ana = socio_with_account(db, make_member)
    partido = make_event(
        db, id_externo=uid("EVT-01"), when=utc("2026-03-10T20:00:00Z"), clase="C"
    )
    institucional = make_event(
        db,
        id_externo=uid("EVT-02"),
        when=utc("2026-05-02T18:00:00Z"),
        tipo="Institucional",
        clase=None,
        puntos=10,
    )
    load_attendance(db, partido, [ana.socio])
    load_attendance(db, institucional, [ana.socio])

    response = client.get(HISTORY, headers=member_headers(client, outbox, ana.member))

    assert response.status_code == 200
    by_title = {event["titulo"]: event for event in response.json()["events"]}
    assert utc(by_title[partido.titulo]["fecha_hora"]) == utc("2026-03-10T20:00:00Z")
    assert by_title[partido.titulo]["tipo"] == "Partido"
    assert utc(by_title[institucional.titulo]["fecha_hora"]) == utc(
        "2026-05-02T18:00:00Z"
    )
    assert by_title[institucional.titulo]["tipo"] == "Evento institucional/amateur"
    assert all("clase" not in event for event in by_title.values())


def events_by_title(response) -> dict[str, dict]:
    return {event["titulo"]: event for event in response.json()["events"]}


def publish_v1_and_v2(
    db: Session, client: TestClient, outbox: Outbox, admin: User
) -> None:
    """Reglas v1 publicadas el 01/01/2026 y v2 (ajuste de HU-28) el 01/06/2026."""
    boca = headers_for(client, outbox, admin)
    publish_rules(client, boca)
    backdate_rules(db, 1, utc("2026-01-01T12:00:00Z"))
    adjust_rules(client, boca, 1, b_max="10.0")
    backdate_rules(db, 2, utc("2026-06-01T12:00:00Z"))


def test_cada_evento_referencia_la_version_de_reglas_vigente_en_su_fecha(
    db: Session,
    client: TestClient,
    outbox: Outbox,
    make_member: MakeMember,
    admin: User,
) -> None:
    publish_v1_and_v2(db, client, outbox, admin)
    ana = socio_with_account(db, make_member)
    marzo = make_event(db, id_externo=uid("MAR"), when=utc("2026-03-10T20:00:00Z"))
    agosto = make_event(db, id_externo=uid("AGO"), when=utc("2026-08-15T21:30:00Z"))
    load_attendance(db, marzo, [ana.socio])
    load_attendance(db, agosto, [ana.socio])
    headers = member_headers(client, outbox, ana.member)

    response = client.get(HISTORY, headers=headers)

    assert response.status_code == 200
    events = events_by_title(response)
    assert events[marzo.titulo]["rules_version"]["number"] == 1
    assert events[agosto.titulo]["rules_version"]["number"] == 2
    assert events[agosto.titulo]["rules_message"] is None
    # El enlace de cada evento abre esa versión.
    linked = client.get(events[marzo.titulo]["rules_version"]["url"], headers=headers)
    assert linked.status_code == 200
    assert linked.json()["rules_version"] == 1


def test_el_socio_lee_las_reglas_de_una_version_reemplazada(
    db: Session,
    client: TestClient,
    outbox: Outbox,
    make_member: MakeMember,
    admin: User,
) -> None:
    publish_v1_and_v2(db, client, outbox, admin)
    ana = socio_with_account(db, make_member)
    v1 = db.scalars(
        select(RulesVersion).where(
            RulesVersion.club_id == BOCA_ID, RulesVersion.number == 1
        )
    ).one()

    response = client.get(
        RULES.format(1), headers=member_headers(client, outbox, ana.member)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["rules_version"] == 1
    assert body["in_force"] is False
    # La explicación viaja como JSON: las tuplas de `explanation_of` llegan como listas.
    assert body["explanation"] == jsonable_encoder(explanation_of(v1)[1])
    assert "published_by" not in response.text


def test_un_evento_anterior_a_la_primera_publicacion_no_tiene_reglas(
    db: Session,
    client: TestClient,
    outbox: Outbox,
    make_member: MakeMember,
    admin: User,
) -> None:
    publish_rules(client, headers_for(client, outbox, admin))
    backdate_rules(db, 1, utc("2026-01-01T12:00:00Z"))
    ana = socio_with_account(db, make_member)
    viejo = make_event(db, id_externo=uid("OLD"), when=utc("2025-11-20T20:00:00Z"))
    load_attendance(db, viejo, [ana.socio])

    response = client.get(HISTORY, headers=member_headers(client, outbox, ana.member))

    assert response.status_code == 200
    [event] = response.json()["events"]
    assert event["rules_version"] is None
    assert (
        event["rules_message"]
        == "No había reglas de puntaje publicadas en ese momento."
    )
