"""HU-23B US1: listado de los eventos publicados que todavía no empezaron.

El escenario 2 (los botones "Reprogramar" y "Retirar evento") es de la pantalla; el back
entrega la `version` que esas acciones mandan. El escenario 6 (la acción sobre un evento que
empezó con la pantalla abierta) se prueba con cada acción (US2 y US5).
"""

import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import EventoPendienteDB, EventoVisibleDB, User, utcnow
from tests.conftest import (
    BOCA_ID,
    RIVER_ID,
    MakeMember,
    Outbox,
    bearer,
    member_token,
)
from tests.hu25_helpers import headers_for, make_event, publish_rules
from tests.hu36_helpers import DAY, HOUR, partido, ranking_with
from tests.hu36_helpers import generate as generate_waves

URL = "/admin/events/published"


def evento(
    db: Session,
    *,
    when: datetime,
    tipo: str = "Partido",
    clase: str | None = "B",
    puntos: int | None = None,
    club_id: uuid.UUID = BOCA_ID,
) -> EventoVisibleDB:
    return make_event(
        db,
        id_externo=f"E-{uuid.uuid4().hex[:8]}",
        when=when,
        tipo=tipo,
        clase=clase,
        puntos=puntos,
        club_id=club_id,
    )


def listado(client: TestClient, headers: dict[str, str]) -> list[dict]:
    response = client.get(URL, headers=headers)
    assert response.status_code == 200
    return response.json()


def ids(items: list[dict]) -> list[str]:
    return [item["id_interno"] for item in items]


def as_utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


# --- Escenario 1: todos los publicados próximos, el más cercano primero ---


def test_lista_los_publicados_proximos_del_club_ordenados_por_inicio(
    client: TestClient, db: Session, outbox: Outbox, admin: User
) -> None:
    headers = headers_for(client, outbox, admin)
    lejano = evento(db, when=utcnow() + 20 * DAY)
    cercano = evento(db, when=utcnow() + 3 * DAY)
    medio = evento(
        db,
        when=utcnow() + 10 * DAY,
        tipo="Institucional",
        clase=None,
        puntos=40,
    )

    assert ids(listado(client, headers)) == [
        cercano.id_interno,
        medio.id_interno,
        lejano.id_interno,
    ]


def test_cada_evento_trae_sus_datos_clase_o_puntos_y_version(
    client: TestClient, db: Session, outbox: Outbox, admin: User
) -> None:
    headers = headers_for(client, outbox, admin)
    when = datetime(2031, 3, 14, 21, 30, tzinfo=UTC)
    match = evento(db, when=when, clase="A")
    asamblea = evento(
        db,
        when=when + DAY,
        tipo="Institucional",
        clase=None,
        puntos=25,
    )

    by_id = {item["id_interno"]: item for item in listado(client, headers)}

    partido_out = by_id[match.id_interno]
    assert partido_out["id_externo"] == match.id_externo
    assert partido_out["titulo"] == match.titulo
    assert partido_out["tipo"] == "Partido"
    assert as_utc(partido_out["fecha_hora"]) == when
    assert partido_out["lugar"] == "La Bombonera"
    assert partido_out["clase"] == "A"
    assert partido_out["puntos"] is None
    assert partido_out["cancelado_por_el_club"] is False
    assert partido_out["version"] == 1
    assert partido_out["schedule"] is None

    institucional = by_id[asamblea.id_interno]
    assert institucional["tipo"] == "Institucional"
    assert institucional["clase"] is None
    assert institucional["puntos"] == 25
    assert institucional["schedule"] is None


def test_un_partido_con_cronograma_muestra_su_estado_y_periodo(
    client: TestClient, db: Session, outbox: Outbox, admin: User
) -> None:
    headers = headers_for(client, outbox, admin)
    publish_rules(client, headers)
    ranking_with(db, admin, 10)
    event = partido(db, when=utcnow() + 10 * DAY)
    assert generate_waves(client, headers, event).status_code == 201
    opening = (utcnow() + 2 * DAY).replace(microsecond=0)
    closing = opening + DAY
    created = client.post(
        f"/admin/events/{event.id_interno}/schedule",
        json={"opening_at": opening.isoformat(), "closing_at": closing.isoformat()},
        headers=headers,
    )
    assert created.status_code == 201

    def schedule() -> dict:
        (item,) = [
            i for i in listado(client, headers) if i["id_interno"] == event.id_interno
        ]
        return item["schedule"]

    assert schedule()["status"] == "draft"
    assert as_utc(schedule()["opening_at"]) == opening
    assert as_utc(schedule()["closing_at"]) == closing

    confirmed = client.post(
        f"/admin/events/{event.id_interno}/schedule/confirm", headers=headers
    )
    assert confirmed.status_code == 200
    assert schedule()["status"] == "confirmed"


# --- Escenario 3: lo que no se lista ---


def test_no_lista_eventos_que_ya_empezaron(
    client: TestClient, db: Session, outbox: Outbox, admin: User
) -> None:
    headers = headers_for(client, outbox, admin)
    empezado = evento(db, when=utcnow() - HOUR)
    proximo = evento(db, when=utcnow() + DAY)

    assert ids(listado(client, headers)) == [proximo.id_interno]
    assert empezado.id_interno not in ids(listado(client, headers))


def test_no_lista_eventos_retirados(
    client: TestClient, db: Session, outbox: Outbox, admin: User
) -> None:
    headers = headers_for(client, outbox, admin)
    retirado = evento(db, when=utcnow() + 5 * DAY)
    retirado.estado = "withdrawn"
    db.commit()

    assert retirado.id_interno not in ids(listado(client, headers))


def test_no_lista_eventos_historicos(
    client: TestClient, db: Session, outbox: Outbox, admin: User
) -> None:
    headers = headers_for(client, outbox, admin)
    historico = evento(db, when=utcnow() + 5 * DAY, tipo="Historico", clase="B")

    assert historico.id_interno not in ids(listado(client, headers))


def test_no_lista_eventos_pendientes_ni_descartados(
    client: TestClient, db: Session, outbox: Outbox, admin: User
) -> None:
    headers = headers_for(client, outbox, admin)
    for estado in ("pendiente_definicion_importancia", "descartado"):
        db.add(
            EventoPendienteDB(
                id_interno=f"PEND-{uuid.uuid4().hex[:8]}",
                club_id=BOCA_ID,
                id_externo=f"P-{uuid.uuid4().hex[:8]}",
                titulo=f"Evento {estado}",
                fecha_hora=utcnow() + 10 * DAY,
                lugar="La Bombonera",
                tipo="Partido",
                estado=estado,
            )
        )
    db.commit()

    assert listado(client, headers) == []


def test_no_lista_eventos_de_otro_club_aunque_se_pida_su_club_id(
    client: TestClient, db: Session, outbox: Outbox, admin: User
) -> None:
    headers = headers_for(client, outbox, admin)
    de_river = evento(db, when=utcnow() + 5 * DAY, club_id=RIVER_ID)
    de_boca = evento(db, when=utcnow() + 6 * DAY)

    assert ids(listado(client, headers)) == [de_boca.id_interno]
    # El club sale de la cuenta (decisión 34): un `club_id` o `X-Club-ID` se ignora.
    response = client.get(
        URL,
        params={"club_id": str(RIVER_ID)},
        headers={**headers, "X-Club-ID": str(RIVER_ID)},
    )
    assert response.status_code == 200
    assert ids(response.json()) == [de_boca.id_interno]
    assert de_river.id_interno not in ids(response.json())


# --- Escenario 4: marca de cancelado por el club ---


def test_un_evento_cancelado_por_el_club_trae_la_marca(
    client: TestClient, db: Session, outbox: Outbox, admin: User
) -> None:
    headers = headers_for(client, outbox, admin)
    cancelado = evento(db, when=utcnow() + 5 * DAY)
    cancelado.cancelado_por_el_club = True
    normal = evento(db, when=utcnow() + 6 * DAY)
    db.commit()

    by_id = {item["id_interno"]: item for item in listado(client, headers)}

    assert by_id[cancelado.id_interno]["cancelado_por_el_club"] is True
    assert by_id[normal.id_interno]["cancelado_por_el_club"] is False


# --- Escenario 5: sin eventos ---


def test_sin_publicados_proximos_devuelve_una_lista_vacia(
    client: TestClient, db: Session, outbox: Outbox, admin: User
) -> None:
    headers = headers_for(client, outbox, admin)
    evento(db, when=utcnow() - DAY)

    assert listado(client, headers) == []


# --- Autorización ---


def test_solo_un_admin_puede_ver_el_listado(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    make_member: MakeMember,
) -> None:
    assert client.get(URL).status_code == 401

    member = make_member(activated=True)
    socio = bearer(member_token(client, outbox, member))
    assert client.get(URL, headers=socio).status_code == 403
