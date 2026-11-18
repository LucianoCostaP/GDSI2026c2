"""HU-23B US2, escenarios 7 a 10, y el ajuste del cronograma de US3.

Cada Partido de `Club` (HU-39) tiene 10 socios rankeados en 5 olas de 2, apertura a dos días
y una hora entre olas: la ola k abre en `opening + (k − 1) h` y el cierre es `opening + 5 h`.
"""

from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    EventReprogramming,
    Notification,
    User,
    WaveSchedule,
    WaveScheduleStatus,
    WaveSegmentation,
    utcnow,
)
from app.notifications import generators
from tests.conftest import MakeMember, Outbox
from tests.hu36_helpers import DAY, HOUR
from tests.test_hu39_own_slot import Club, as_utc

MINUTE = timedelta(minutes=1)


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


def preview(club: Club, fecha_hora: datetime | str, **extra: Any):
    value = fecha_hora.isoformat() if isinstance(fecha_hora, datetime) else fecha_hora
    return club.client.post(
        f"/admin/events/{club.event.id_interno}/reschedule/preview",
        json={"fecha_hora": value, **extra},
        headers=club.headers,
    )


def reprogramar(
    club: Club, fecha_hora: datetime, *, expected_version: int = 1, **extra: Any
):
    return club.client.post(
        f"/admin/events/{club.event.id_interno}/reschedule",
        json={
            "fecha_hora": fecha_hora.isoformat(),
            "expected_version": expected_version,
            **extra,
        },
        headers=club.headers,
    )


def schedule_of(club: Club) -> WaveSchedule:
    club.db.expire_all()
    return club.db.scalars(
        select(WaveSchedule).where(WaveSchedule.event_id == club.event.id_interno)
    ).one()


def admin_schedule(club: Club) -> dict:
    response = club.client.get(
        f"/admin/events/{club.event.id_interno}/schedule", headers=club.headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def move_schedule_to(club: Club, opening: datetime) -> None:
    """Corre el cronograma confirmado para que su apertura sea `opening` (las reprogramaciones
    usan el reloj del servidor)."""
    schedule = schedule_of(club)
    schedule.opening_at = opening
    schedule.closing_at = opening + 5 * HOUR
    club.db.commit()
    club.opening, club.closing = opening, opening + 5 * HOUR


def code_of(response) -> str:
    return response.json()["detail"]["code"]


def audit_of(club: Club, action: str) -> list[AuditLog]:
    return list(
        club.db.scalars(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id)
        )
    )


# --- Escenario 7: la vista previa muestra lo que va a pasar ---


def test_la_vista_previa_de_la_fusion_no_cambia_nada(boca_club: Club) -> None:
    club = boca_club
    club.ready()
    nuevo_inicio = club.opening + 2 * HOUR + 30 * MINUTE

    response = preview(club, nuevo_inicio)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["schedule_effect"] == "waves_merged"
    assert body["merged_into_order"] == 3
    assert body["moved_waves"] == [{"order": 4, "socios": 2}, {"order": 5, "socios": 2}]
    assert as_utc(body["previous_closing_at"]) == club.closing
    assert as_utc(body["new_closing_at"]) == nuevo_inicio
    assert as_utc(body["target_wave_starts_at"]) == club.wave_start(3)
    assert body["target_wave_open"] is False
    assert as_utc(body["new_fecha_hora"]) == nuevo_inicio
    club.db.refresh(club.event)
    assert club.event.version == 1
    schedule = schedule_of(club)
    assert (schedule.effective_closing_at, schedule.merged_into_order) == (None, None)
    assert club.db.scalars(select(EventReprogramming)).first() is None


def test_la_vista_previa_valida_como_la_reprogramacion(boca_club: Club) -> None:
    club = boca_club
    club.ready()

    assert code_of(preview(club, club.event.fecha_hora)) == "NO_CHANGES"
    assert code_of(preview(club, utcnow() - HOUR)) == "START_NOT_IN_FUTURE"
    assert code_of(preview(club, "20/06/2031")) == "INVALID_DATETIME"
    assert code_of(preview(club, utcnow() + DAY, clase="A")) == "FIELD_NOT_EDITABLE"


def test_sin_cronograma_la_vista_previa_lo_dice(boca_club: Club) -> None:
    club = boca_club
    club.segment()

    body = preview(club, club.event.fecha_hora + DAY).json()

    assert body["schedule_effect"] == "no_schedule"
    assert body["moved_waves"] == []


def test_confirmar_aplica_la_fusion_que_mostro_la_vista_previa(boca_club: Club) -> None:
    club = boca_club
    club.ready()
    nuevo_inicio = club.opening + 2 * HOUR + 30 * MINUTE

    response = reprogramar(
        club,
        nuevo_inicio,
        expected_schedule_effect="waves_merged",
        expected_merged_into_order=3,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["impact"]["schedule_effect"] == "waves_merged"
    assert body["schedule"]["merged_into_order"] == 3
    assert body["schedule"]["adjusted"] is True
    assert as_utc(body["schedule"]["closing_at"]) == nuevo_inicio
    # Las horas se siguen derivando del período generado: las olas 1 a 3 no se mueven.
    schedule = schedule_of(club)
    assert as_utc(schedule.closing_at.isoformat()) == club.opening + 5 * HOUR
    vista = admin_schedule(club)
    assert vista["merged_into_order"] == 3
    assert as_utc(vista["closing_at"]) == nuevo_inicio
    assert [as_utc(w["starts_at"]) for w in vista["waves"]] == [
        club.wave_start(1),
        club.wave_start(2),
        club.wave_start(3),
        club.wave_start(3),
        club.wave_start(3),
    ]
    assert [w["state"] for w in vista["waves"]] == ["pending"] * 5


def test_si_el_efecto_cambio_desde_la_vista_previa_no_se_aplica(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    nuevo_inicio = club.opening + 2 * HOUR + 30 * MINUTE

    response = reprogramar(
        club,
        nuevo_inicio,
        expected_schedule_effect="closing_adjusted",
        expected_merged_into_order=None,
    )

    assert response.status_code == 409
    assert code_of(response) == "EVENT_CHANGED"
    club.db.refresh(club.event)
    assert club.event.version == 1
    assert schedule_of(club).merged_into_order is None


def test_un_partido_sin_cronograma_solo_cambia_el_evento(boca_club: Club) -> None:
    club = boca_club
    club.segment()

    response = reprogramar(club, club.event.fecha_hora + DAY)

    assert response.status_code == 200
    assert response.json()["impact"]["schedule_effect"] == "no_schedule"
    assert response.json()["schedule"] is None


def test_si_ninguna_ola_queda_afectada_solo_se_mueve_el_cierre(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    nuevo_inicio = club.opening + 4 * HOUR + 30 * MINUTE

    response = reprogramar(club, nuevo_inicio)

    assert response.json()["impact"]["schedule_effect"] == "closing_adjusted"
    vista = admin_schedule(club)
    assert as_utc(vista["closing_at"]) == nuevo_inicio
    assert vista["merged_into_order"] is None
    assert [as_utc(w["starts_at"]) for w in vista["waves"]] == [
        club.wave_start(order) for order in range(1, 6)
    ]


def test_si_todas_las_olas_quedan_afectadas_se_invalida_y_se_conserva_la_segmentacion(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()

    response = reprogramar(club, club.opening + 3 * MINUTE)

    assert response.json()["impact"]["schedule_effect"] == "invalidated"
    assert schedule_of(club).status == WaveScheduleStatus.INVALIDATED
    assert club.db.scalars(
        select(WaveSegmentation).where(
            WaveSegmentation.event_id == club.event.id_interno
        )
    ).one()
    socio = club.member_at(1)
    assert club.slot(socio)["status"] == "no_schedule"


def test_un_borrador_solapado_se_invalida(boca_club: Club) -> None:
    club = boca_club
    club.segment()
    club.schedule(confirm=False)

    response = reprogramar(club, club.opening + 2 * HOUR)

    assert response.json()["impact"]["schedule_effect"] == "invalidated"
    assert schedule_of(club).status == WaveScheduleStatus.INVALIDATED


def test_las_olas_se_suman_a_una_ola_que_ya_abrio(boca_club: Club) -> None:
    club = boca_club
    club.ready()
    # Hace 2 h 30 min que abrió la ola 1: ya abrieron las olas 1 a 3.
    move_schedule_to(club, utcnow() - 2 * HOUR - 30 * MINUTE)

    response = reprogramar(club, utcnow() + 20 * MINUTE)

    impact = response.json()["impact"]
    assert impact["schedule_effect"] == "waves_merged"
    assert impact["merged_into_order"] == 3
    assert impact["target_wave_open"] is True
    # El socio de la ola 5 ya tiene acceso, como "Ola 3 de 3", hasta el nuevo cierre.
    slot = club.slot(club.member_at(10))
    assert slot["status"] == "open"
    assert slot["wave"] == {"order": 3, "total": 3}
    assert as_utc(slot["closing_at"]) == as_utc(impact["new_fecha_hora"])


def test_el_socio_de_una_ola_movida_ve_la_hora_de_la_ola_a_la_que_se_sumo(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    nuevo_inicio = club.opening + 2 * HOUR + 30 * MINUTE
    assert reprogramar(club, nuevo_inicio).status_code == 200

    movido = club.slot(club.member_at(9))
    separado = club.slot(club.member_at(1))

    assert movido["status"] == "pending"
    assert movido["wave"] == {"order": 3, "total": 3}
    assert as_utc(movido["starts_at"]) == club.wave_start(3)
    assert as_utc(movido["closing_at"]) == nuevo_inicio
    assert separado["wave"] == {"order": 1, "total": 3}
    assert as_utc(separado["starts_at"]) == club.wave_start(1)


def test_al_abrir_la_ola_de_destino_el_trabajo_avisa_tambien_a_los_movidos(
    boca_club: Club, db: Session
) -> None:
    club = boca_club
    club.ready()
    club.member_at(5)  # ola 3
    club.member_at(9)  # ola 5, movida a la 3
    club.member_at(7)  # ola 4, movida a la 3
    assert reprogramar(club, club.opening + 2 * HOUR + 30 * MINUTE).status_code == 200

    created = generators.open_waves(
        db, now=club.wave_start(3) + MINUTE, club_id=club.event.club_id
    )

    assert created == 3
    keys = set(
        db.scalars(
            select(Notification.occurrence_key).where(
                Notification.type == "wave_opened"
            )
        )
    )
    assert keys == {
        f"event:{club.event.id_interno}:wave:3:schedule:{schedule_of(club).id}"
    }


def test_un_inicio_posterior_no_deshace_la_fusion(boca_club: Club) -> None:
    club = boca_club
    club.ready()
    primero = club.opening + 2 * HOUR + 30 * MINUTE
    assert reprogramar(club, primero).status_code == 200

    response = reprogramar(club, club.opening + 10 * HOUR, expected_version=2)

    assert response.json()["impact"]["schedule_effect"] == "none"
    schedule = schedule_of(club)
    assert schedule.merged_into_order == 3
    assert as_utc(schedule.effective_closing.isoformat()) == primero


def test_regenerar_el_cronograma_descarta_los_ajustes(boca_club: Club) -> None:
    club = boca_club
    club.ready()
    assert reprogramar(club, club.opening + 2 * HOUR + 30 * MINUTE).status_code == 200
    club.db.refresh(club.event)

    regenerated = club.client.post(
        f"/admin/events/{club.event.id_interno}/schedule",
        json={
            "opening_at": club.opening.isoformat(),
            "closing_at": (club.opening + 2 * HOUR).isoformat(),
            "confirmed": True,
        },
        headers=club.headers,
    )

    assert regenerated.status_code == 200, regenerated.text
    schedule = schedule_of(club)
    assert (schedule.effective_closing_at, schedule.merged_into_order) == (None, None)


# --- Escenario 8: auditoría ---


def test_la_reprogramacion_queda_auditada_con_el_ajuste_del_cronograma(
    boca_club: Club, admin: User
) -> None:
    club = boca_club
    club.ready()
    anterior = club.event.fecha_hora
    nuevo_inicio = club.opening + 2 * HOUR + 30 * MINUTE

    body = reprogramar(club, nuevo_inicio).json()

    (evento,) = audit_of(club, "event.rescheduled")
    assert evento.actor_user_id == admin.id
    assert evento.entity_id == club.event.id_interno
    assert evento.details["reprogramming_id"] == body["id_reprogramacion"]
    assert evento.details["previous"] == {"fecha_hora": anterior.isoformat()}
    assert evento.details["new"] == {"fecha_hora": nuevo_inicio.isoformat()}
    assert evento.details["schedule_effect"] == "waves_merged"
    (ajuste,) = audit_of(club, "wave_schedule.adjusted")
    assert ajuste.actor_user_id == admin.id
    assert ajuste.details["previous"] == {
        "status": "confirmed",
        "closing_at": club.closing.isoformat(),
        "merged_into_order": None,
    }
    assert ajuste.details["new"] == {
        "status": "confirmed",
        "closing_at": nuevo_inicio.isoformat(),
        "merged_into_order": 3,
    }
    assert ajuste.details["moved_waves"] == [4, 5]
    reprogramacion = club.db.get_one(EventReprogramming, body["id_reprogramacion"])
    assert reprogramacion.schedule_effect == "waves_merged"
    assert reprogramacion.reprogrammed_by_id == admin.id


def test_la_invalidacion_queda_auditada(boca_club: Club) -> None:
    club = boca_club
    club.ready()

    reprogramar(club, club.opening + 3 * MINUTE)

    (invalidado,) = audit_of(club, "wave_schedule.invalidated")
    assert invalidado.details["previous"]["status"] == "confirmed"
    assert invalidado.details["new"]["status"] == "invalidated"


def test_un_rechazo_no_audita_nada(boca_club: Club) -> None:
    club = boca_club
    club.ready()

    reprogramar(club, club.event.fecha_hora)

    assert audit_of(club, "event.rescheduled") == []


# --- Escenario 9: dos Admins a la vez ---


def test_una_version_vieja_falla_con_event_changed(boca_club: Club) -> None:
    club = boca_club
    club.segment()
    assert reprogramar(club, club.event.fecha_hora + DAY).status_code == 200
    club.db.refresh(club.event)
    vigente = club.event.fecha_hora

    # El segundo Admin cargó el formulario con la versión 1.
    response = reprogramar(club, vigente + DAY, expected_version=1)

    assert response.status_code == 409
    assert code_of(response) == "EVENT_CHANGED"
    assert response.json()["detail"]["message"] == (
        "El evento cambió mientras lo editabas. Revisá los datos actuales y volvé a "
        "intentar."
    )
    club.db.refresh(club.event)
    assert (club.event.fecha_hora, club.event.version) == (vigente, 2)


# --- Escenario 10: notificaciones ---


def test_los_socios_activados_reciben_event_rescheduled_con_la_fecha_nueva(
    boca_club: Club, db: Session
) -> None:
    club = boca_club
    club.segment()
    club.member_at(1)
    club.member_at(10)
    nuevo_inicio = datetime.fromisoformat("2031-06-20T23:15:00+00:00")

    body = reprogramar(club, nuevo_inicio).json()

    avisos = list(
        db.scalars(select(Notification).where(Notification.type == "event_rescheduled"))
    )
    assert len(avisos) == 2
    assert {a.occurrence_key for a in avisos} == {
        f"event:{club.event.id_interno}:rescheduled:{body['id_reprogramacion']}"
    }
    assert {a.message for a in avisos} == {
        f"{club.event.titulo} cambió: ahora es el 20/06/2031 a las 20:15."
    }
    assert avisos[0].reference == {"event_id": club.event.id_interno}
    assert body["impact"]["notifications"]["event_rescheduled"] == 2


def test_un_rechazo_no_notifica(boca_club: Club, db: Session) -> None:
    club = boca_club
    club.segment()
    club.member_at(1)

    reprogramar(club, club.event.fecha_hora)

    assert db.scalars(select(Notification)).first() is None


def test_cada_reprogramacion_notifica_una_vez(boca_club: Club, db: Session) -> None:
    club = boca_club
    club.segment()
    club.member_at(1)

    assert reprogramar(club, club.event.fecha_hora + DAY).status_code == 200
    club.db.refresh(club.event)
    assert (
        reprogramar(club, club.event.fecha_hora + DAY, expected_version=2).status_code
        == 200
    )

    assert len(list(db.scalars(select(Notification)))) == 2
