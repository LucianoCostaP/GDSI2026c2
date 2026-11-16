"""HU-15: tests unitarios de las consultas del historial (con la base del fixture `db`)."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.date_utils import asegurar_utc
from app.models import EstadoCargaParticipacion, Member, RulesVersion, User
from app.services.event_history_service import (
    attended_events,
    member_history,
    member_rules_version,
    rules_timeline,
)
from app.services.formula_service import explanation_of
from tests.conftest import BOCA_ID, RIVER_ID, MakeAdmin, MakeMember, Outbox
from tests.hu15_helpers import (
    backdate_rules,
    make_historical_event,
    socio_with_account,
    uid,
    utc,
)
from tests.hu25_helpers import (
    adjust_rules,
    headers_for,
    load_attendance,
    make_event,
    make_socio,
    publish_rules,
)

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


# --- Versiones de reglas (ciclo 3) ---------------------------------------------------------


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, make_admin: MakeAdmin) -> dict[str, str]:
    return headers_for(client, outbox, make_admin(BOCA_ID))


@pytest.fixture
def river(client: TestClient, outbox: Outbox, make_admin: MakeAdmin) -> dict[str, str]:
    return headers_for(client, outbox, make_admin(RIVER_ID))


def test_rules_timeline_trae_numero_y_fecha_de_cada_version_del_club(
    db: Session, client: TestClient, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    backdate_rules(db, 1, utc("2026-01-01T12:00:00Z"))
    adjust_rules(client, boca, 1, b_max="10.0")

    timeline = sorted(rules_timeline(db, BOCA_ID), key=lambda r: r.number)

    assert [r.number for r in timeline] == [1, 2]
    assert asegurar_utc(timeline[0].published_at) == utc("2026-01-01T12:00:00Z")


def test_rules_timeline_no_trae_versiones_de_otro_club(
    db: Session, client: TestClient, river: dict[str, str]
) -> None:
    publish_rules(client, river)

    assert rules_timeline(db, BOCA_ID) == []


def test_una_version_trae_la_misma_explicacion_que_hu13(
    db: Session, client: TestClient, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    rules = db.scalars(
        select(RulesVersion).where(RulesVersion.club_id == BOCA_ID)
    ).one()

    out = member_rules_version(db, BOCA_ID, 1)

    assert out["rules_version"] == 1
    assert out["in_force"] is True
    assert out["explanation"] == explanation_of(rules)[1]
    assert out["formula"]["id"] == rules.formula_id


def test_una_version_reemplazada_se_puede_leer_y_no_esta_vigente(
    db: Session, client: TestClient, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    adjust_rules(client, boca, 1, b_max="10.0")

    assert member_rules_version(db, BOCA_ID, 1)["in_force"] is False
    assert member_rules_version(db, BOCA_ID, 2)["in_force"] is True


def test_una_version_de_otro_club_no_se_encuentra(
    db: Session, client: TestClient, river: dict[str, str]
) -> None:
    publish_rules(client, river)

    with pytest.raises(HTTPException) as raised:
        member_rules_version(db, BOCA_ID, 1)

    assert raised.value.status_code == 404
    assert raised.value.detail == {
        "code": "RULES_VERSION_NOT_FOUND",
        "message": "No encontramos esa versión de reglas.",
    }


def test_una_version_no_expone_quien_la_publico(
    db: Session, client: TestClient, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)

    assert "published_by" not in str(member_rules_version(db, BOCA_ID, 1))


# --- Historial vacío y socio moroso (ciclo 5) ----------------------------------------------


def account_of(db: Session, member: Member) -> User:
    return db.scalars(select(User).where(User.member_id == member.member_id)).one()


def test_una_cuenta_sin_socio_en_el_padron_tiene_el_historial_vacio(
    db: Session, make_member: MakeMember
) -> None:
    member = make_member(activated=True)

    out = member_history(db, account_of(db, member), BOCA_ID)

    assert (out["status"], out["total"], out["events"]) == ("empty", 0, [])


def test_un_socio_sin_asistencias_tiene_el_historial_vacio(
    db: Session, make_member: MakeMember
) -> None:
    ana = socio_with_account(db, make_member)

    assert member_history(db, account_of(db, ana.member), BOCA_ID)["status"] == "empty"


def test_la_cuota_en_mora_no_oculta_el_historial(
    db: Session, make_member: MakeMember
) -> None:
    ana = socio_with_account(db, make_member, estado_cuota="moroso")
    event = make_event(db, id_externo=uid("E"), when=MARZO)
    load_attendance(db, event, [ana.socio])

    out = member_history(db, account_of(db, ana.member), BOCA_ID)

    assert out["status"] == "ok"
    assert [e["id_interno"] for e in out["events"]] == [event.id_interno]
