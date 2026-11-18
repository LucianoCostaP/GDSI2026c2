"""HU-23B US5: retirar un evento publicado (escenarios 1 a 11).

Cada Partido de `Club` (HU-39) tiene 10 socios rankeados en 5 olas de 2, con apertura a dos
días y una hora entre olas. Los escenarios 1 y 2 (la confirmación y "Cancelar") son de la
pantalla: acá se prueba que sin la confirmación explícita no cambia nada.
"""

from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.date_utils import a_hora_buenos_aires
from app.models import (
    AuditLog,
    EventoVisibleDB,
    Notification,
    User,
    WaveSchedule,
    WaveSegmentation,
)
from app.models.auth import utcnow
from app.notifications import generators
from app.notifications import notify as notify_module
from app.notifications.catalog import BY_KEY
from app.services.ranking_inputs import (
    load_institutional_events_by_dni,
    load_loaded_matches,
)
from tests.conftest import BOCA_HEADERS, MakeMember, Outbox
from tests.hu25_helpers import load_attendance, make_event
from tests.hu36_helpers import DAY, HOUR
from tests.hu36_helpers import generate as generate_waves
from tests.test_hu23b_reschedule_waves import (
    code_of,
    move_schedule_to,
    reprogramar,
)
from tests.test_hu39_own_slot import Club

MINUTE = timedelta(minutes=1)
SUSPENDIDO = "Este evento fue suspendido."


@pytest.fixture
def boca_club(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    admin: User,
    make_member: MakeMember,
) -> Club:
    from tests.hu25_helpers import headers_for, publish_rules

    headers = headers_for(client, outbox, admin)
    publish_rules(client, headers)
    return Club(client, db, outbox, admin, headers, make_member)


def retirar(
    club: Club,
    event_id: str | None = None,
    *,
    confirmed: bool = True,
    expected_version: int = 1,
    **extra: Any,
):
    return club.client.post(
        f"/admin/events/{event_id or club.event.id_interno}/withdraw",
        json={
            "confirmed": confirmed,
            "expected_version": expected_version,
            **extra,
        },
        headers=club.headers,
    )


def event_of(club: Club) -> EventoVisibleDB:
    club.db.expire_all()
    return club.db.get_one(EventoVisibleDB, club.event.id_interno)


def segmentation_of(club: Club) -> WaveSegmentation | None:
    club.db.expire_all()
    return club.db.scalar(
        select(WaveSegmentation).where(
            WaveSegmentation.event_id == club.event.id_interno
        )
    )


def schedule_or_none(club: Club) -> WaveSchedule | None:
    club.db.expire_all()
    return club.db.scalar(
        select(WaveSchedule).where(WaveSchedule.event_id == club.event.id_interno)
    )


def of_type(club: Club, type: str) -> list[Notification]:
    club.db.expire_all()
    return list(club.db.scalars(select(Notification).where(Notification.type == type)))


def fecha_hora(moment: datetime) -> tuple[str, str]:
    local = a_hora_buenos_aires(moment)
    return local.strftime("%d/%m/%Y"), local.strftime("%H:%M")


def slot(club: Club, auth: dict[str, str]) -> dict[str, Any]:
    response = club.client.get(
        f"/member/events/{club.event.id_interno}/slot", headers=auth
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


# --- Escenarios 1 y 2: sin la confirmación explícita no cambia nada ---


@pytest.mark.parametrize("body", [{"confirmed": False}, {}])
def test_sin_confirmar_no_se_retira_nada(boca_club: Club, body: dict) -> None:
    club = boca_club
    club.ready()
    club.member()

    response = club.client.post(
        f"/admin/events/{club.event.id_interno}/withdraw",
        json={"expected_version": 1, **body},
        headers=club.headers,
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "CONFIRMATION_REQUIRED",
        "message": "Confirmá el retiro del evento.",
    }
    event = event_of(club)
    assert event.estado == "publicado"
    assert event.version == 1
    assert segmentation_of(club) is not None
    assert schedule_or_none(club) is not None
    assert of_type(club, "event_withdrawn") == []


# --- Escenario 3: el evento pasa a `withdrawn` y desaparece de todos lados ---


def test_el_evento_pasa_a_withdrawn_y_sale_del_listado_del_admin(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()

    response = retirar(club)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "id_interno": club.event.id_interno,
        "estado": "withdrawn",
        "segmentation_deleted": True,
        "schedule_deleted": True,
    }
    event = event_of(club)
    assert event.estado == "withdrawn"
    assert event.retirado_en is not None
    listado = club.client.get("/admin/events/published", headers=club.headers).json()
    assert club.event.id_interno not in {e["id_interno"] for e in listado}


def test_el_evento_retirado_sale_de_las_olas_y_el_cronograma_del_admin(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    event_id = club.event.id_interno
    assert retirar(club).status_code == 200

    segmentables = club.client.get(
        "/admin/segmentation/events", headers=club.headers
    ).json()
    assert event_id not in str(segmentables)
    for path in (
        f"/admin/events/{event_id}/segmentation",
        f"/admin/events/{event_id}/schedule",
    ):
        assert club.client.get(path, headers=club.headers).status_code == 404
    # Tampoco se le pueden generar olas ni cronograma de nuevo.
    regenerar = generate_waves(club.client, club.headers, event_id, confirmed=True)
    assert regenerar.status_code == 404
    assert code_of(regenerar) == "EVENT_NOT_FOUND"
    cronograma = club.client.post(
        f"/admin/events/{event_id}/schedule",
        json={
            "opening_at": club.opening.isoformat(),
            "closing_at": club.closing.isoformat(),
        },
        headers=club.headers,
    )
    assert cronograma.status_code == 404


def test_el_evento_retirado_sale_de_lo_que_ven_los_socios(boca_club: Club) -> None:
    club = boca_club
    club.ready()
    socio = club.member_at(1)
    event_id = club.event.id_interno
    proximos = club.client.get("/member/events/upcoming", headers=socio).json()
    assert event_id in {e["id_interno"] for e in proximos["eventos"]}

    assert retirar(club).status_code == 200

    # HU-17
    proximos = club.client.get("/member/events/upcoming", headers=socio).json()
    assert event_id not in {e["id_interno"] for e in proximos["eventos"]}
    # HU-18
    simulacion = club.client.get(f"/member/scoring/simulator/{event_id}", headers=socio)
    assert simulacion.status_code == 404
    assert code_of(simulacion) == "EVENT_NOT_FOUND"
    # HU-39: no hay turno, solo el aviso de que se suspendió (escenario 6).
    turno = slot(club, socio)
    assert turno["status"] == "withdrawn"
    assert turno.get("wave") is None


def test_un_evento_institucional_tambien_se_retira(boca_club: Club) -> None:
    club = boca_club
    club.member()
    institucional = make_event(
        club.db,
        id_externo="I-retiro",
        when=club.opening,
        tipo="Institucional",
        clase=None,
        puntos=10,
    )

    response = retirar(club, institucional.id_interno)

    assert response.status_code == 200, response.text
    assert response.json()["segmentation_deleted"] is False
    assert response.json()["schedule_deleted"] is False
    club.db.expire_all()
    assert club.db.get_one(EventoVisibleDB, institucional.id_interno).estado == (
        "withdrawn"
    )
    assert len(of_type(club, "event_withdrawn")) == 1


def test_un_evento_retirado_no_se_puede_retirar_ni_reprogramar_de_nuevo(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    assert retirar(club).status_code == 200

    otra_vez = retirar(club, expected_version=2)
    reprogramado = reprogramar(club, club.opening + 24 * HOUR, expected_version=2)

    for response in (otra_vez, reprogramado):
        assert response.status_code == 404
        assert code_of(response) == "EVENT_NOT_FOUND"


# --- Escenario 4: se borran la segmentación y el cronograma, en cualquier estado ---


@pytest.mark.parametrize(
    "estado", ["solo_segmentacion", "borrador", "confirmado", "invalidado"]
)
def test_se_borran_la_segmentacion_y_el_cronograma_en_cualquier_estado(
    boca_club: Club, estado: str
) -> None:
    club = boca_club
    club.segment()
    if estado != "solo_segmentacion":
        club.schedule(confirm=estado != "borrador")
    if estado == "invalidado":
        # Una reprogramación que deja todas las olas afectadas invalida el cronograma.
        assert reprogramar(club, club.opening + 10 * MINUTE).status_code == 200

    response = retirar(club, expected_version=2 if estado == "invalidado" else 1)

    assert response.status_code == 200, response.text
    assert response.json()["segmentation_deleted"] is True
    assert response.json()["schedule_deleted"] is (estado != "solo_segmentacion")
    assert segmentation_of(club) is None
    assert schedule_or_none(club) is None


def test_un_partido_sin_olas_se_retira_sin_borrar_nada(boca_club: Club) -> None:
    club = boca_club

    response = retirar(club)

    assert response.status_code == 200, response.text
    assert response.json()["segmentation_deleted"] is False
    assert response.json()["schedule_deleted"] is False


def test_con_olas_ya_abiertas_se_borra_todo_y_el_trabajo_no_genera_nada(
    boca_club: Club, db: Session
) -> None:
    club = boca_club
    club.ready()
    club.member_at(3)  # ola 2, que acaba de abrir
    club.member_at(5)  # ola 3
    # Las olas 1 y 2 ya abrieron; la 3 abre en 55 minutos.
    move_schedule_to(club, datetime.now(club.opening.tzinfo) - HOUR - 5 * MINUTE)
    assert generators.open_waves(db, club_id=club.event.club_id) == 1
    assert len(of_type(club, "wave_opened")) == 1

    assert retirar(club).status_code == 200

    assert segmentation_of(club) is None
    assert schedule_or_none(club) is None
    # Ni las olas que faltaban, ni ninguna otra, abren después del retiro.
    for later in (club.wave_start(3) + MINUTE, club.wave_start(5) + MINUTE):
        assert generators.open_waves(db, now=later, club_id=club.event.club_id) == 0
    assert len(of_type(club, "wave_opened")) == 1


# --- Escenario 5: todos los socios activados reciben `event_withdrawn` ---


def test_todo_socio_activado_recibe_el_aviso_generico_de_suspension(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    de_la_ola_1 = club.member_at(1)
    de_la_ola_5 = club.member_at(10)
    fuera_de_la_segmentacion = club.member()
    inicio = club.event.fecha_hora

    assert retirar(club).status_code == 200

    fecha, hora = fecha_hora(inicio)
    avisos = of_type(club, "event_withdrawn")
    assert len(avisos) == 3
    assert {a.title for a in avisos} == {"Evento suspendido"}
    assert {a.message for a in avisos} == {
        (
            f"{club.event.titulo}, del {fecha} a las {hora}, se suspendió. Si compraste "
            "entradas, comunicate con el club."
        )
    }
    assert {a.occurrence_key for a in avisos} == {
        f"event:{club.event.id_interno}:withdrawn"
    }
    assert {str(a.reference) for a in avisos} == {
        str({"event_id": club.event.id_interno})
    }
    for auth in (de_la_ola_1, de_la_ola_5, fuera_de_la_segmentacion):
        items = club.client.get("/member/notifications", headers=auth).json()["items"]
        assert [i["type"] for i in items].count("event_withdrawn") == 1


def test_el_aviso_lleva_la_fecha_vigente_tras_una_reprogramacion(
    boca_club: Club,
) -> None:
    club = boca_club
    club.member()
    nuevo_inicio = club.opening + 3 * HOUR
    assert reprogramar(club, nuevo_inicio).status_code == 200

    assert retirar(club, expected_version=2).status_code == 200

    fecha, hora = fecha_hora(nuevo_inicio)
    (aviso,) = of_type(club, "event_withdrawn")
    assert f"del {fecha} a las {hora}, se suspendió" in aviso.message


def test_el_socio_dado_de_baja_no_recibe_el_aviso(boca_club: Club) -> None:
    club = boca_club
    club.member_at(1)
    club.member_at(2)
    de_baja = club.socio_at(2)
    de_baja.activo = False
    club.db.commit()

    assert retirar(club).status_code == 200

    assert len(of_type(club, "event_withdrawn")) == 1


def test_el_texto_es_el_mismo_para_todo_evento_y_no_lleva_motivo(
    boca_club: Club,
) -> None:
    club = boca_club
    club.member()

    assert retirar(club, motivo="Lluvia").status_code == 200

    (aviso,) = of_type(club, "event_withdrawn")
    assert "Lluvia" not in aviso.message
    assert "Motivo" not in aviso.message
    assert BY_KEY["event_withdrawn"].message == (
        "{titulo}, del {fecha} a las {hora}, se suspendió. "
        "Si compraste entradas, comunicate con el club."
    )


def test_repetir_el_aviso_no_crea_nada_nuevo(boca_club: Club, db: Session) -> None:
    club = boca_club
    club.member()
    assert retirar(club).status_code == 200

    assert generators.event_withdrawn(db, club.event.id_interno) == 0
    assert len(of_type(club, "event_withdrawn")) == 1


def test_event_restored_queda_inactivo(boca_club: Club) -> None:
    assert BY_KEY["event_restored"].active is False
    restaurar = boca_club.client.post(
        f"/admin/events/{boca_club.event.id_interno}/restore",
        headers=boca_club.headers,
    )
    # HU-23B no tiene restauración: el endpoint ya no existe.
    assert restaurar.status_code == 404


# --- Escenario 6: el socio que llega por un enlace viejo ve que se suspendió ---


def test_el_turno_de_un_evento_retirado_dice_que_se_suspendio(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    socio = club.member_at(3)
    assert slot(club, socio)["status"] == "pending"

    assert retirar(club).status_code == 200

    turno = slot(club, socio)
    assert turno["status"] == "withdrawn"
    assert turno["message"] == SUSPENDIDO
    assert turno["event"]["id_interno"] == club.event.id_interno


def test_las_notificaciones_viejas_siguen_apuntando_al_evento_retirado(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    socio = club.member_at(1)
    move_schedule_to(club, datetime.now(club.opening.tzinfo) - 5 * MINUTE)
    generators.event_published(club.db, club.event.id_interno)
    generators.open_waves(club.db, club_id=club.event.club_id)
    assert reprogramar(club, club.opening + 6 * HOUR).status_code == 200

    assert retirar(club, expected_version=2).status_code == 200

    items = club.client.get("/member/notifications", headers=socio).json()["items"]
    assert sorted(i["type"] for i in items) == [
        "event_published",
        "event_rescheduled",
        "event_withdrawn",
        "wave_opened",
    ]
    # Todas llevan al evento, cuyo turno dice que se suspendió, y la app sigue andando.
    assert {i["reference"]["event_id"] for i in items} == {club.event.id_interno}
    assert slot(club, socio)["message"] == SUSPENDIDO
    assert club.client.get("/member/events/upcoming", headers=socio).status_code == 200


# --- Escenario 7: el club no puede mandar nada más para un evento retirado ---

EVENT_WITHDRAWN = {
    "code": "EVENT_WITHDRAWN",
    "message": "El evento fue retirado y no acepta cambios ni asistencias.",
    "field": "id_externo",
}


def club_error(response) -> dict[str, Any]:
    error: dict[str, Any] = response.json()["error"]
    return error


def retirado(club: Club) -> str:
    """Retira el Partido de `club` y devuelve su `id_externo`."""
    club.ready()
    assert retirar(club).status_code == 200
    return club.event.id_externo


def test_la_asistencia_de_un_evento_retirado_se_rechaza(boca_club: Club) -> None:
    club = boca_club
    id_externo = retirado(club)
    socio = club.socio_at(1)

    response = club.client.post(
        f"/api/v1/eventos/{id_externo}/asistencia",
        json={
            "carga_id": "att-retirado",
            "pagina": 1,
            "total_paginas": 1,
            "es_ultima_pagina": True,
            "registros": [{"dni": socio.dni, "numero_socio": socio.numero_socio}],
        },
        headers=BOCA_HEADERS,
    )

    assert response.status_code == 422, response.text
    assert club_error(response) == EVENT_WITHDRAWN
    assert event_of(club).estado == "withdrawn"


def test_una_actualizacion_de_un_evento_retirado_se_rechaza(boca_club: Club) -> None:
    club = boca_club
    id_externo = retirado(club)

    response = club.client.put(
        f"/api/v1/eventos/{id_externo}",
        json={"lugar": "Otra sede"},
        headers=BOCA_HEADERS,
    )

    assert response.status_code == 422, response.text
    assert club_error(response) == EVENT_WITHDRAWN
    event = event_of(club)
    assert event.estado == "withdrawn"
    assert event.lugar != "Otra sede"


def test_la_cancelacion_de_un_evento_retirado_se_rechaza(boca_club: Club) -> None:
    club = boca_club
    id_externo = retirado(club)

    response = club.client.post(
        f"/api/v1/eventos/{id_externo}/cancelacion",
        json={"motivo": "Lluvia"},
        headers=BOCA_HEADERS,
    )

    assert response.status_code == 422, response.text
    assert club_error(response) == EVENT_WITHDRAWN
    event = event_of(club)
    assert event.estado == "withdrawn"
    assert event.cancelado_por_el_club is False


def nuevo_evento(id_externo: str) -> dict[str, Any]:
    return {
        "id_externo": id_externo,
        "titulo": "Boca vs. Rival (otra fecha)",
        "fecha_hora": (utcnow() + 5 * DAY).isoformat(),
        "lugar": "La Bombonera",
        "tipo": "Partido",
    }


def test_reenviar_el_id_externo_de_un_retirado_se_rechaza(boca_club: Club) -> None:
    club = boca_club
    id_externo = retirado(club)

    response = club.client.post(
        "/api/v1/eventos", json=nuevo_evento(id_externo), headers=BOCA_HEADERS
    )

    assert response.status_code == 422, response.text
    assert club_error(response) == EVENT_WITHDRAWN
    assert event_of(club).estado == "withdrawn"
    # Con un `id_externo` nuevo, el club lo vuelve a mandar (edge case "Withdrawal is final").
    otro = club.client.post(
        "/api/v1/eventos", json=nuevo_evento(f"{id_externo}-b"), headers=BOCA_HEADERS
    )
    assert otro.status_code == 201, otro.text


def test_en_un_lote_el_id_externo_de_un_retirado_falla(boca_club: Club) -> None:
    club = boca_club
    id_externo = retirado(club)

    response = club.client.post(
        "/api/v1/eventos/batch",
        json=[nuevo_evento(id_externo), nuevo_evento(f"{id_externo}-b")],
        headers=BOCA_HEADERS,
    )

    assert response.status_code == 207, response.text
    body = response.json()
    assert [(f["id_externo"], f["codigo"], f["error"]) for f in body["fallidos"]] == [
        (id_externo, 422, EVENT_WITHDRAWN["message"])
    ]
    assert [c["id_externo"] for c in body["creados"]] == [f"{id_externo}-b"]


# --- Escenario 8: un evento retirado no cuenta para el ranking ---


def test_un_evento_retirado_no_cuenta_para_el_ranking(boca_club: Club) -> None:
    club = boca_club
    socio = club.socio_at(1)
    institucional = make_event(
        club.db,
        id_externo="I-retirado",
        when=club.opening,
        tipo="Institucional",
        clase=None,
        puntos=10,
    )
    assert retirar(club).status_code == 200
    assert retirar(club, institucional.id_interno).status_code == 200
    # Pasó la fecha que tenían y alguien cargó su asistencia por otra vía: igual no cuentan.
    jugado = make_event(club.db, id_externo="P-jugado", when=utcnow() - 3 * DAY)
    for event in (event_of(club), institucional, jugado):
        event.fecha_hora = utcnow() - 2 * DAY
        club.db.commit()
        load_attendance(club.db, event, [socio])
    window_start = (utcnow() - 30 * DAY).date()

    matches = load_loaded_matches(
        club.db, club.event.club_id, window_start=window_start, until=utcnow()
    )
    institutional = load_institutional_events_by_dni(
        club.db, club.event.club_id, window_start=window_start, until=utcnow()
    )

    # El denominador de la frecuencia es la lista de partidos: el retirado no está.
    assert [m.event_id for m in matches] == [jugado.id_externo]
    assert institutional.get(socio.dni, []) == []


# --- Escenario 9: el retiro queda auditado con lo que se borró ---


def details_of(club: Club, action: str) -> list[dict[str, Any]]:
    club.db.expire_all()
    return [
        {"actor": entry.actor_user_id, "entity_id": entry.entity_id, **entry.details}
        for entry in club.db.scalars(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id)
        )
    ]


def test_el_retiro_queda_auditado_con_la_segmentacion_y_el_cronograma_borrados(
    boca_club: Club, admin: User
) -> None:
    club = boca_club
    club.ready()
    segmentation, schedule = segmentation_of(club), schedule_or_none(club)
    assert segmentation is not None and schedule is not None
    segmentation_id, schedule_id = segmentation.id, schedule.id
    ranking_id = segmentation.ranking_id

    assert retirar(club).status_code == 200

    (evento,) = details_of(club, "event.withdrawn")
    assert evento["actor"] == admin.id
    assert evento["entity_id"] == club.event.id_interno
    assert evento["previous"] == {"estado": "publicado"}
    assert evento["new"] == {"estado": "withdrawn"}
    assert evento["segmentation_deleted"] is True
    assert evento["schedule_deleted"] is True

    (olas,) = details_of(club, "wave_segmentation.deleted")
    assert olas["actor"] == admin.id
    assert olas["entity_id"] == str(segmentation_id)
    assert olas["event_id"] == club.event.id_interno
    assert olas["reason"] == "event.withdrawn"
    assert olas["previous"]["ranking_id"] == ranking_id
    assert olas["previous"]["ranked_total"] == 10

    (cronograma,) = details_of(club, "wave_schedule.deleted")
    assert cronograma["actor"] == admin.id
    assert cronograma["entity_id"] == str(schedule_id)
    assert cronograma["reason"] == "event.withdrawn"
    previous = cronograma["previous"]
    assert previous["status"] == "confirmed"
    assert previous["segmentation_id"] == segmentation_id
    assert datetime.fromisoformat(previous["opening_at"]) == club.opening
    assert datetime.fromisoformat(previous["closing_at"]) == club.closing


def test_un_retiro_rechazado_no_deja_auditoria(boca_club: Club) -> None:
    club = boca_club
    club.ready()

    assert retirar(club, confirmed=False).status_code == 422
    assert retirar(club, expected_version=7).status_code == 409

    for action in (
        "event.withdrawn",
        "wave_segmentation.deleted",
        "wave_schedule.deleted",
    ):
        assert details_of(club, action) == []


# --- Escenario 10: dos Admins a la vez, una sola acción ---


def test_retirar_con_una_version_vieja_falla_si_otro_admin_reprogramo(
    boca_club: Club,
) -> None:
    club = boca_club
    club.member()
    assert reprogramar(club, club.opening + 3 * HOUR).status_code == 200

    response = retirar(club, expected_version=1)

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "EVENT_CHANGED",
        "message": (
            "El evento cambió mientras lo editabas. Revisá los datos actuales y volvé a "
            "intentar."
        ),
    }
    assert event_of(club).estado == "publicado"
    assert of_type(club, "event_withdrawn") == []


def test_reprogramar_con_una_version_vieja_falla_si_otro_admin_retiro(
    boca_club: Club,
) -> None:
    club = boca_club
    assert retirar(club).status_code == 200

    response = reprogramar(club, club.opening + 3 * HOUR, expected_version=1)

    assert response.status_code == 404
    assert code_of(response) == "EVENT_NOT_FOUND"
    assert event_of(club).estado == "withdrawn"


def test_el_segundo_retiro_falla_y_hay_un_solo_aviso_por_socio(
    boca_club: Club,
) -> None:
    club = boca_club
    club.member_at(1)
    club.member()
    assert retirar(club).status_code == 200

    segundo = retirar(club, expected_version=1)

    assert segundo.status_code == 404
    assert code_of(segundo) == "EVENT_NOT_FOUND"
    avisos = of_type(club, "event_withdrawn")
    assert len(avisos) == 2
    assert len({a.user_id for a in avisos}) == 2
    assert len(details_of(club, "event.withdrawn")) == 1


def test_el_retiro_suma_uno_a_la_version(boca_club: Club) -> None:
    club = boca_club

    assert retirar(club).status_code == 200

    assert event_of(club).version == 2


# --- Escenario 11: si fallan los avisos, el retiro queda aplicado ---


def test_si_falla_el_aviso_el_retiro_queda_aplicado(
    boca_club: Club, monkeypatch: pytest.MonkeyPatch
) -> None:
    club = boca_club
    club.ready()
    socio = club.member_at(1)
    monkeypatch.setattr(notify_module, "BY_KEY", {})

    response = retirar(club)

    assert response.status_code == 200, response.text
    assert event_of(club).estado == "withdrawn"
    assert segmentation_of(club) is None
    assert schedule_or_none(club) is None
    assert of_type(club, "event_withdrawn") == []
    assert slot(club, socio)["message"] == SUSPENDIDO


def test_si_fallan_los_destinatarios_el_retiro_queda_aplicado(
    boca_club: Club, monkeypatch: pytest.MonkeyPatch
) -> None:
    club = boca_club
    club.member()

    def broken(*_: object, **__: object) -> list[int]:
        raise RuntimeError("se cayó la base")

    monkeypatch.setattr(generators, "_club_members", broken)

    response = retirar(club)

    assert response.status_code == 200, response.text
    assert event_of(club).estado == "withdrawn"
    assert of_type(club, "event_withdrawn") == []
