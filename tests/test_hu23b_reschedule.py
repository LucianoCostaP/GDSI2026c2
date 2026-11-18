"""HU-23B US2, escenarios 1 a 6: reprogramar la fecha y hora de un evento publicado.

El escenario 1 (el formulario con la fecha y hora editables y el resto de solo lectura) es
de la pantalla; el back entrega en el listado los datos que se muestran, incluida la
descripción. La vista previa y el ajuste de las olas (escenario 7, US3), la auditoría, la
concurrencia y las notificaciones (escenarios 8 a 10) están en
`test_hu23b_reschedule_waves.py`.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.date_utils import BUENOS_AIRES_TZ
from app.models import (
    EventoPendienteDB,
    EventoVisibleDB,
    User,
    WaveSchedule,
    utcnow,
)
from tests.conftest import (
    RIVER_ID,
    MakeMember,
    Outbox,
    bearer,
    member_token,
)
from tests.hu25_helpers import headers_for, make_event, publish_rules
from tests.hu36_helpers import DAY, HOUR, partido, ranking_with
from tests.hu36_helpers import generate as generate_waves


def evento(
    db: Session,
    *,
    when: datetime | None = None,
    tipo: str = "Partido",
    clase: str | None = "B",
    puntos: int | None = None,
    club_id: uuid.UUID | None = None,
) -> EventoVisibleDB:
    kwargs = {"club_id": club_id} if club_id else {}
    event = make_event(
        db,
        id_externo=f"E-{uuid.uuid4().hex[:8]}",
        when=when or utcnow() + 10 * DAY,
        tipo=tipo,
        clase=clase,
        puntos=puntos,
        **kwargs,
    )
    event.descripcion = "Fecha 5 del torneo"
    db.commit()
    return event


def reprogramar(
    client: TestClient,
    headers: dict[str, str],
    event: EventoVisibleDB | str,
    fecha_hora: datetime | str,
    **extra: object,
):
    event_id = event if isinstance(event, str) else event.id_interno
    value = fecha_hora.isoformat() if isinstance(fecha_hora, datetime) else fecha_hora
    # La versión del listado: un evento recién creado está en la 1 (escenario 9).
    body = {"fecha_hora": value, "expected_version": 1, **extra}
    return client.post(
        f"/admin/events/{event_id}/reschedule", json=body, headers=headers
    )


def code_of(response) -> str:
    return response.json()["detail"]["code"]


def as_utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def in_listado(client: TestClient, headers: dict[str, str], event_id: str) -> dict:
    (item,) = [
        i
        for i in client.get("/admin/events/published", headers=headers).json()
        if i["id_interno"] == event_id
    ]
    return item


@pytest.fixture
def headers(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    return headers_for(client, outbox, admin)


# --- Escenario 1: los datos del formulario ---


def test_el_listado_trae_los_datos_de_solo_lectura_del_formulario(
    client: TestClient, db: Session, headers: dict[str, str]
) -> None:
    event = evento(db)

    item = in_listado(client, headers, event.id_interno)

    assert item["titulo"] == event.titulo
    assert item["tipo"] == "Partido"
    assert item["lugar"] == "La Bombonera"
    assert item["descripcion"] == "Fecha 5 del torneo"
    assert item["clase"] == "B"
    assert as_utc(item["fecha_hora"]) == event.fecha_hora


# --- Escenario 2: la reprogramación se aplica ---


def test_reprogramar_cambia_solo_la_fecha_y_hora_y_sigue_publicado(
    client: TestClient, db: Session, headers: dict[str, str]
) -> None:
    event = evento(db)
    nueva = (utcnow() + 12 * DAY).replace(microsecond=0)

    response = reprogramar(client, headers, event, nueva, expected_version=1)

    assert response.status_code == 200
    body = response.json()
    assert as_utc(body["fecha_hora"]) == nueva
    assert body["version"] == 2
    db.refresh(event)
    assert event.estado == "publicado"
    assert event.fecha_hora == nueva
    assert (event.tipo, event.clase, event.puntos) == ("Partido", "B", None)
    assert event.titulo == body["titulo"]
    assert event.lugar == "La Bombonera"
    assert event.descripcion == "Fecha 5 del torneo"
    assert as_utc(in_listado(client, headers, event.id_interno)["fecha_hora"]) == nueva


def test_un_institucional_conserva_sus_puntos(
    client: TestClient, db: Session, headers: dict[str, str]
) -> None:
    event = evento(db, tipo="Institucional", clase=None, puntos=30)
    nueva = (utcnow() + 3 * DAY).replace(microsecond=0)

    response = reprogramar(client, headers, event, nueva)

    assert response.status_code == 200
    assert response.json()["puntos"] == 30
    assert response.json()["tipo"] == "Institucional"


def test_el_socio_ve_la_fecha_nueva_sin_otra_publicacion(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    headers: dict[str, str],
    make_member: MakeMember,
) -> None:
    event = evento(db)
    nueva = datetime(2031, 6, 20, 23, 15, tzinfo=UTC)
    socio = bearer(member_token(client, outbox, make_member(activated=True)))

    assert reprogramar(client, headers, event, nueva).status_code == 200

    proximos = client.get("/member/events/upcoming", headers=socio).json()["eventos"]
    (visto,) = [e for e in proximos if e["id_interno"] == event.id_interno]
    assert as_utc(visto["fecha_hora"]) == nueva
    # 23:15 UTC es 20:15 en Buenos Aires.
    assert (visto["fecha"], visto["hora"]) == ("2031-06-20", "20:15")


def test_una_fecha_sin_zona_horaria_se_lee_en_buenos_aires(
    client: TestClient, db: Session, headers: dict[str, str]
) -> None:
    event = evento(db)

    response = reprogramar(client, headers, event, "2031-06-20T20:15:00")

    assert response.status_code == 200
    esperado = datetime(2031, 6, 20, 20, 15, tzinfo=BUENOS_AIRES_TZ)
    assert as_utc(response.json()["fecha_hora"]) == esperado


def test_se_puede_reprogramar_con_menos_de_48_horas(
    client: TestClient, db: Session, headers: dict[str, str]
) -> None:
    event = evento(db)

    response = reprogramar(client, headers, event, utcnow() + 3 * HOUR)

    assert response.status_code == 200


def test_reprogramar_borra_la_marca_de_cancelado_por_el_club(
    client: TestClient, db: Session, headers: dict[str, str]
) -> None:
    event = evento(db)
    event.cancelado_por_el_club = True
    db.commit()

    response = reprogramar(client, headers, event, utcnow() + 15 * DAY)

    assert response.status_code == 200
    assert response.json()["cancelado_por_el_club"] is False


def test_un_partido_movido_despues_del_cierre_conserva_su_cronograma(
    client: TestClient, db: Session, headers: dict[str, str], admin: User
) -> None:
    # US3 escenario 2: el cierre no es posterior al nuevo inicio, el cronograma no cambia.
    publish_rules(client, headers)
    ranking_with(db, admin, 10)
    event = partido(db, when=utcnow() + 10 * DAY)
    assert generate_waves(client, headers, event).status_code == 201
    opening = (utcnow() + 2 * DAY).replace(microsecond=0)
    created = client.post(
        f"/admin/events/{event.id_interno}/schedule",
        json={
            "opening_at": opening.isoformat(),
            "closing_at": (opening + DAY).isoformat(),
        },
        headers=headers,
    )
    assert created.status_code == 201

    response = reprogramar(client, headers, event, utcnow() + 20 * DAY)

    assert response.status_code == 200
    assert response.json()["impact"]["schedule_effect"] == "none"
    assert response.json()["schedule"]["status"] == "draft"
    assert as_utc(response.json()["schedule"]["opening_at"]) == opening
    assert db.query(WaveSchedule).filter_by(event_id=event.id_interno).count() == 1


# --- Escenario 3: solo la fecha y la hora son editables ---


@pytest.mark.parametrize(
    "campo",
    [
        {"tipo": "Institucional"},
        {"clase": "A"},
        {"puntos": 50},
        {"titulo": "Otro título"},
        {"lugar": "Otro estadio"},
        {"descripcion": "Otra descripción"},
    ],
    ids=lambda c: next(iter(c)),
)
def test_otro_campo_se_rechaza_y_nada_cambia(
    client: TestClient, db: Session, headers: dict[str, str], campo: dict
) -> None:
    event = evento(db)
    original = (event.fecha_hora, event.titulo)

    response = reprogramar(client, headers, event, utcnow() + 15 * DAY, **campo)

    assert response.status_code == 422
    assert code_of(response) == "FIELD_NOT_EDITABLE"
    assert (
        response.json()["detail"]["message"]
        == "Al reprogramar solo se puede cambiar la fecha y la hora."
    )
    db.refresh(event)
    assert (event.fecha_hora, event.titulo) == original
    assert event.version == 1
    assert (event.tipo, event.clase, event.puntos) == ("Partido", "B", None)
    assert (event.lugar, event.descripcion) == ("La Bombonera", "Fecha 5 del torneo")


# --- Escenario 4: sin cambios ---


def test_la_misma_fecha_y_hora_no_guarda_nada(
    client: TestClient, db: Session, headers: dict[str, str]
) -> None:
    event = evento(db, when=datetime(2031, 3, 14, 21, 30, tzinfo=UTC))

    # El mismo instante, escrito en hora de Buenos Aires.
    response = reprogramar(client, headers, event, "2031-03-14T18:30:00-03:00")

    assert response.status_code == 422
    assert code_of(response) == "NO_CHANGES"
    assert response.json()["detail"]["message"] == "No hay cambios para guardar."
    db.refresh(event)
    assert event.version == 1


# --- Escenario 5: la fecha nueva tiene que ser futura ---


@pytest.mark.parametrize("delta", [timedelta(hours=-2), timedelta(0)])
def test_una_fecha_que_no_es_futura_se_rechaza(
    client: TestClient, db: Session, headers: dict[str, str], delta: timedelta
) -> None:
    event = evento(db)
    original = event.fecha_hora

    response = reprogramar(client, headers, event, utcnow() + delta)

    assert response.status_code == 422
    assert code_of(response) == "START_NOT_IN_FUTURE"
    assert (
        response.json()["detail"]["message"]
        == "La nueva fecha y hora tiene que ser posterior a este momento."
    )
    db.refresh(event)
    assert event.fecha_hora == original
    assert event.version == 1


# --- Escenario 6: formato inválido ---


@pytest.mark.parametrize(
    "valor",
    ["20/06/2031 20:15", "2031-06-20", "mañana a la tarde", "2031-13-01T10:00", ""],
)
def test_una_fecha_con_formato_invalido_se_rechaza_con_el_motivo(
    client: TestClient, db: Session, headers: dict[str, str], valor: str
) -> None:
    event = evento(db)
    original = event.fecha_hora

    response = reprogramar(client, headers, event, valor)

    assert response.status_code == 422
    assert code_of(response) == "INVALID_DATETIME"
    assert (
        response.json()["detail"]["message"]
        == "La fecha y hora no es válida: usá el formato AAAA-MM-DD HH:MM."
    )
    db.refresh(event)
    assert (event.fecha_hora, event.version) == (original, 1)


def test_sin_fecha_y_hora_se_rechaza_con_el_motivo(
    client: TestClient, db: Session, headers: dict[str, str]
) -> None:
    event = evento(db)

    response = client.post(
        f"/admin/events/{event.id_interno}/reschedule",
        json={"expected_version": 1},
        headers=headers,
    )

    assert response.status_code == 422
    assert code_of(response) == "INVALID_DATETIME"


# --- Eventos que no se pueden reprogramar (edge cases) ---


def test_un_evento_de_otro_club_responde_como_desconocido(
    client: TestClient, db: Session, headers: dict[str, str]
) -> None:
    de_river = evento(db, club_id=RIVER_ID)

    response = reprogramar(client, headers, de_river, utcnow() + 15 * DAY)

    assert response.status_code == 404
    assert code_of(response) == "EVENT_NOT_FOUND"


def test_un_evento_inexistente_retirado_o_historico_no_se_encuentra(
    client: TestClient, db: Session, headers: dict[str, str]
) -> None:
    retirado = evento(db)
    retirado.estado = "withdrawn"
    historico = evento(db, tipo="Historico")
    db.commit()

    for event_id in ("NO-EXISTE", retirado.id_interno, historico.id_interno):
        response = reprogramar(client, headers, event_id, utcnow() + 15 * DAY)
        assert response.status_code == 404, event_id
        assert code_of(response) == "EVENT_NOT_FOUND"


def test_un_evento_pendiente_no_esta_publicado(
    client: TestClient, db: Session, headers: dict[str, str], admin: User
) -> None:
    pendiente = EventoPendienteDB(
        id_interno=f"PEND-{uuid.uuid4().hex[:8]}",
        club_id=admin.club_id,
        id_externo=f"P-{uuid.uuid4().hex[:8]}",
        titulo="Pendiente",
        fecha_hora=utcnow() + 10 * DAY,
        lugar="La Bombonera",
        tipo="Partido",
        estado="pendiente_definicion_importancia",
    )
    db.add(pendiente)
    db.commit()

    response = reprogramar(client, headers, pendiente.id_interno, utcnow() + 15 * DAY)

    assert response.status_code == 409
    assert code_of(response) == "EVENT_NOT_PUBLISHED"


def test_un_evento_que_ya_empezo_no_se_reprograma(
    client: TestClient, db: Session, headers: dict[str, str]
) -> None:
    empezado = evento(db, when=utcnow() - HOUR)

    response = reprogramar(client, headers, empezado, utcnow() + 15 * DAY)

    assert response.status_code == 409
    assert code_of(response) == "EVENT_ALREADY_STARTED"


def test_solo_un_admin_puede_reprogramar(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    event = evento(db)
    body = {"fecha_hora": (utcnow() + 15 * DAY).isoformat(), "expected_version": 1}
    url = f"/admin/events/{event.id_interno}/reschedule"

    assert client.post(url, json=body).status_code == 401
    socio = bearer(member_token(client, outbox, make_member(activated=True)))
    assert client.post(url, json=body, headers=socio).status_code == 403
