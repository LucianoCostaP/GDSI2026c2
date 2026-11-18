"""HU-23B US3: el cronograma de olas después de una reprogramación.

Cada Partido de `Club` (HU-39) tiene 10 socios rankeados en 5 olas de 2, apertura a dos días
y una hora entre olas: la ola k abre en `opening + (k − 1) h` y el cierre es `opening + 5 h`.
Las reglas puras están en `tests/test_hu23b_schedule_adjustment.py`; acá se prueban por la API.
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Notification,
    User,
    WaveSchedule,
    WaveScheduleStatus,
    WaveSegmentation,
    utcnow,
)
from tests.conftest import MakeMember, Outbox
from tests.hu36_helpers import DAY, HOUR, segmentation_url
from tests.test_hu23b_reschedule_waves import (
    admin_schedule,
    audit_of,
    move_schedule_to,
    preview,
    reprogramar,
    schedule_of,
)
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


def segmentation_of(club: Club) -> WaveSegmentation:
    club.db.expire_all()
    return club.db.scalars(
        select(WaveSegmentation).where(
            WaveSegmentation.event_id == club.event.id_interno
        )
    ).one()


def schedule_audits(club: Club) -> list[AuditLog]:
    return list(
        club.db.scalars(select(AuditLog).where(AuditLog.action.like("wave_schedule.%")))
    )


def schedule_values(schedule: WaveSchedule) -> tuple:
    return (
        schedule.status,
        schedule.opening_at,
        schedule.closing_at,
        schedule.effective_closing_at,
        schedule.merged_into_order,
        schedule.invalidation_reason,
    )


# --- Escenario 1: sin segmentación o sin cronograma, solo cambia el evento ---


def test_un_partido_sin_olas_solo_cambia_el_evento(boca_club: Club) -> None:
    club = boca_club
    nuevo_inicio = club.event.fecha_hora + DAY

    response = reprogramar(club, nuevo_inicio)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["impact"]["schedule_effect"] == "no_schedule"
    assert body["impact"]["moved_waves"] == []
    assert body["schedule"] is None
    assert as_utc(body["fecha_hora"]) == as_utc(nuevo_inicio.isoformat())
    club.db.expire_all()
    assert club.db.scalars(select(WaveSegmentation)).first() is None
    assert club.db.scalars(select(WaveSchedule)).first() is None
    assert schedule_audits(club) == []


def test_un_partido_con_olas_y_sin_cronograma_conserva_sus_olas(
    boca_club: Club,
) -> None:
    club = boca_club
    club.segment()
    antes = segmentation_of(club)
    valores = (antes.id, antes.ranking_id, antes.ranked_total, antes.percentile_step)

    response = reprogramar(club, club.event.fecha_hora - DAY)

    assert response.json()["impact"]["schedule_effect"] == "no_schedule"
    despues = segmentation_of(club)
    assert (
        despues.id,
        despues.ranking_id,
        despues.ranked_total,
        despues.percentile_step,
    ) == valores
    assert club.db.scalars(select(WaveSchedule)).first() is None
    assert schedule_audits(club) == []


# --- Escenario 2: el cierre no es posterior al nuevo inicio ---


@pytest.mark.parametrize(
    "desde_el_cierre",
    [timedelta(0), HOUR, 3 * DAY],
    ids=["justo-al-cierre", "antes-pero-despues-del-cierre", "mas-tarde"],
)
def test_si_el_cierre_no_es_posterior_al_nuevo_inicio_el_cronograma_no_cambia(
    boca_club: Club, desde_el_cierre: timedelta
) -> None:
    club = boca_club
    club.ready()
    antes = schedule_values(schedule_of(club))
    olas_antes = admin_schedule(club)["waves"]
    auditorias_antes = len(schedule_audits(club))

    response = reprogramar(club, club.closing + desde_el_cierre)

    assert response.status_code == 200, response.text
    impact = response.json()["impact"]
    assert impact["schedule_effect"] == "none"
    assert as_utc(impact["previous_closing_at"]) == club.closing
    assert as_utc(impact["new_closing_at"]) == club.closing
    assert impact["moved_waves"] == []
    assert schedule_values(schedule_of(club)) == antes
    assert admin_schedule(club)["waves"] == olas_antes
    assert len(schedule_audits(club)) == auditorias_antes


# --- Escenario 3: ninguna ola afectada, solo se mueve el cierre ---


def test_el_socio_conserva_su_hora_y_ve_el_cierre_nuevo(boca_club: Club) -> None:
    club = boca_club
    club.ready()
    nuevo_inicio = club.opening + 4 * HOUR + 30 * MINUTE

    response = reprogramar(club, nuevo_inicio)

    assert response.json()["impact"]["schedule_effect"] == "closing_adjusted"
    schedule = schedule_of(club)
    assert as_utc(schedule.closing_at.isoformat()) == club.closing
    assert as_utc(schedule.effective_closing.isoformat()) == nuevo_inicio
    assert schedule.merged_into_order is None
    ultimo = club.slot(club.member_at(10))
    assert ultimo["wave"] == {"order": 5, "total": 5}
    assert as_utc(ultimo["starts_at"]) == club.wave_start(5)
    assert as_utc(ultimo["closing_at"]) == nuevo_inicio


def test_una_ola_justo_al_paso_minimo_del_inicio_no_queda_afectada(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    # La ola 5 abre a las opening + 4 h: con el partido 5 minutos después, le alcanza.
    nuevo_inicio = club.wave_start(5) + 5 * MINUTE

    impact = reprogramar(club, nuevo_inicio).json()["impact"]

    assert impact["schedule_effect"] == "closing_adjusted"
    assert impact["merged_into_order"] is None
    assert as_utc(impact["new_closing_at"]) == nuevo_inicio


# --- Escenario 4: las olas afectadas se suman a la última no afectada ---


def test_las_olas_a_menos_del_paso_minimo_se_suman_a_la_ola_anterior(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    # La ola 3 abriría 4 minutos antes del partido: queda afectada y se suma con la 4 y la 5
    # a la ola 2.
    nuevo_inicio = club.wave_start(3) + 4 * MINUTE

    response = reprogramar(club, nuevo_inicio)

    impact = response.json()["impact"]
    assert impact["schedule_effect"] == "waves_merged"
    assert impact["merged_into_order"] == 2
    assert [wave["order"] for wave in impact["moved_waves"]] == [3, 4, 5]
    assert as_utc(impact["target_wave_starts_at"]) == club.wave_start(2)
    vista = admin_schedule(club)
    assert vista["merged_into_order"] == 2
    assert as_utc(vista["closing_at"]) == nuevo_inicio
    assert as_utc(vista["generated_closing_at"]) == club.closing
    assert [as_utc(w["starts_at"]) for w in vista["waves"]] == [
        club.wave_start(1),
        club.wave_start(2),
        club.wave_start(2),
        club.wave_start(2),
        club.wave_start(2),
    ]
    # Cada ola conserva sus socios y sus posiciones: solo cambia la hora de las movidas.
    assert [(w["order"], w["socios"]) for w in vista["waves"]] == [
        (order, 2) for order in range(1, 6)
    ]


def test_la_fusion_no_cambia_la_segmentacion(boca_club: Club) -> None:
    club = boca_club
    club.ready()
    antes = segmentation_of(club)
    valores = (antes.id, antes.ranking_id, antes.ranked_total, antes.percentile_step)

    assert reprogramar(club, club.opening + 2 * HOUR + 30 * MINUTE).status_code == 200

    despues = segmentation_of(club)
    assert (
        despues.id,
        despues.ranking_id,
        despues.ranked_total,
        despues.percentile_step,
    ) == valores


# --- Escenario 5: la ola de destino ya abrió ---


def test_las_olas_sumadas_a_una_ola_abierta_quedan_habilitadas_ya(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    # Hace 2 h 30 min que abrió la ola 1: ya abrieron las olas 1 a 3.
    move_schedule_to(club, utcnow() - 2 * HOUR - 30 * MINUTE)
    nuevo_inicio = utcnow() + 20 * MINUTE

    impact = reprogramar(club, nuevo_inicio).json()["impact"]

    assert impact["target_wave_open"] is True
    vista = admin_schedule(club)
    assert [w["state"] for w in vista["waves"]] == ["open"] * 5
    assert [as_utc(w["starts_at"]) for w in vista["waves"]][2:] == [
        club.wave_start(3)
    ] * 3
    for position in (7, 10):  # olas 4 y 5
        slot = club.slot(club.member_at(position))
        assert slot["status"] == "open"
        assert slot["wave"] == {"order": 3, "total": 3}
        assert as_utc(slot["closing_at"]) == as_utc(impact["new_fecha_hora"])


def test_una_ola_ya_abierta_nunca_queda_afectada(boca_club: Club) -> None:
    club = boca_club
    club.ready()
    # Ya abrió la ola 1 (hace 10 minutos) y el partido pasa a dentro de 2 minutos: la ola 1
    # tiene menos del paso mínimo, pero sus socios ya tienen acceso y no se invalida.
    move_schedule_to(club, utcnow() - 10 * MINUTE)

    impact = preview(club, utcnow() + 2 * MINUTE).json()

    assert impact["schedule_effect"] == "waves_merged"
    assert impact["merged_into_order"] == 1
    assert [wave["order"] for wave in impact["moved_waves"]] == [2, 3, 4, 5]
    assert impact["target_wave_open"] is True


# --- Escenario 6: todas las olas afectadas ---


@pytest.mark.parametrize(
    "desde_la_apertura",
    [-HOUR, timedelta(0), 4 * MINUTE],
    ids=["antes-de-la-apertura", "en-la-apertura", "a-menos-del-paso-minimo"],
)
def test_si_todas_las_olas_quedan_afectadas_el_cronograma_se_invalida(
    boca_club: Club, desde_la_apertura: timedelta
) -> None:
    club = boca_club
    club.ready()
    segmentacion = segmentation_of(club).id

    response = reprogramar(club, club.opening + desde_la_apertura)

    impact = response.json()["impact"]
    assert impact["schedule_effect"] == "invalidated"
    assert impact["moved_waves"] == []
    assert response.json()["schedule"]["status"] == "invalidated"
    schedule = schedule_of(club)
    assert schedule.status == WaveScheduleStatus.INVALIDATED
    # No se recorta a una sola ola: las horas y el cierre quedan como estaban.
    assert (schedule.effective_closing_at, schedule.merged_into_order) == (None, None)
    assert segmentation_of(club).id == segmentacion


def test_con_la_primera_ola_al_paso_minimo_las_demas_se_suman_a_ella(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()

    impact = preview(club, club.opening + 5 * MINUTE).json()

    assert impact["schedule_effect"] == "waves_merged"
    assert impact["merged_into_order"] == 1


def test_el_admin_ve_por_que_se_invalido_y_puede_generarlo_de_nuevo(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    nuevo_inicio = club.opening + 3 * MINUTE
    assert reprogramar(club, nuevo_inicio).status_code == 200

    vista = admin_schedule(club)
    assert vista["status"] == "invalidated"
    assert vista["invalidation_reason"] == "event_rescheduled"
    assert vista["locked"] is False
    assert [w["state"] for w in vista["waves"]] == [None] * 5
    # El socio ve que el cronograma no está definido (HU-39).
    assert club.slot(club.member_at(1))["status"] == "no_schedule"

    # Uno invalidado se pisa sin pedir confirmación, y el nuevo ya no tiene motivo.
    regenerado = club.client.post(
        f"/admin/events/{club.event.id_interno}/schedule",
        json={
            "opening_at": (nuevo_inicio - 2 * HOUR).isoformat(),
            "closing_at": nuevo_inicio.isoformat(),
        },
        headers=club.headers,
    )
    assert regenerado.status_code in (200, 201), regenerado.text
    body = regenerado.json()
    assert body["status"] == "draft"
    assert body["invalidation_reason"] is None
    assert schedule_of(club).invalidation_reason is None


def test_un_borrador_invalidado_por_una_reprogramacion_lo_dice(
    boca_club: Club,
) -> None:
    club = boca_club
    club.segment()
    club.schedule(confirm=False)

    assert reprogramar(club, club.opening + 2 * HOUR).status_code == 200

    assert admin_schedule(club)["invalidation_reason"] == "event_rescheduled"


def regenerar(club: Club, opening, closing):
    return club.client.post(
        f"/admin/events/{club.event.id_interno}/schedule",
        json={
            "opening_at": opening.isoformat(),
            "closing_at": closing.isoformat(),
            "confirmed": True,
        },
        headers=club.headers,
    )


def admin_segmentation(club: Club) -> dict:
    response = club.client.get(segmentation_url(club.event), headers=club.headers)
    assert response.status_code == 200, response.text
    return response.json()


def notification_types(club: Club) -> set[str]:
    club.db.expire_all()
    return set(club.db.scalars(select(Notification.type)))


# --- Escenario 7: un borrador solapado ---


def test_un_borrador_solapado_se_invalida_y_no_se_avisa_nada_de_olas(
    boca_club: Club,
) -> None:
    club = boca_club
    club.segment()
    club.schedule(confirm=False)
    for position in (1, 5, 10):
        club.member_at(position)

    response = reprogramar(club, club.closing - MINUTE)

    impact = response.json()["impact"]
    assert impact["schedule_effect"] == "invalidated"
    assert impact["notifications"]["wave_rescheduled"] == 0
    assert impact["notifications"]["wave_opened"] == 0
    schedule = schedule_of(club)
    assert schedule.status == WaveScheduleStatus.INVALIDATED
    assert schedule.invalidation_reason == "event_rescheduled"
    # Los socios nunca vieron el borrador: solo reciben el aviso de la fecha nueva.
    assert notification_types(club) == {"event_rescheduled"}


def test_un_borrador_que_no_se_solapa_queda_como_estaba(boca_club: Club) -> None:
    club = boca_club
    club.segment()
    club.schedule(confirm=False)
    antes = schedule_values(schedule_of(club))

    impact = reprogramar(club, club.closing + HOUR).json()["impact"]

    assert impact["schedule_effect"] == "none"
    assert schedule_values(schedule_of(club)) == antes
    assert schedule_of(club).status == WaveScheduleStatus.DRAFT


def test_la_vista_previa_de_un_borrador_solapado_avisa_que_se_invalida(
    boca_club: Club,
) -> None:
    club = boca_club
    club.segment()
    club.schedule(confirm=False)

    body = preview(club, club.opening + 2 * HOUR).json()

    assert body["schedule_effect"] == "invalidated"
    assert schedule_of(club).status == WaveScheduleStatus.DRAFT


# --- Escenario 8: una segunda reprogramación sobre un cronograma ajustado ---


def test_un_inicio_anterior_suma_las_olas_ya_fusionadas_a_una_ola_previa(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    assert reprogramar(club, club.opening + 2 * HOUR + 30 * MINUTE).status_code == 200
    segundo = club.opening + HOUR + 30 * MINUTE

    response = reprogramar(club, segundo, expected_version=2)

    impact = response.json()["impact"]
    assert impact["schedule_effect"] == "waves_merged"
    assert impact["merged_into_order"] == 2
    assert [wave["order"] for wave in impact["moved_waves"]] == [3, 4, 5]
    assert (
        as_utc(impact["previous_closing_at"]) == club.opening + 2 * HOUR + 30 * MINUTE
    )
    vista = admin_schedule(club)
    assert as_utc(vista["closing_at"]) == segundo
    assert [as_utc(w["starts_at"]) for w in vista["waves"]] == [club.wave_start(1)] + [
        club.wave_start(2)
    ] * 4


def test_un_cierre_movido_sin_olas_afectadas_mantiene_la_fusion(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    assert reprogramar(club, club.opening + 2 * HOUR + 30 * MINUTE).status_code == 200
    segundo = club.opening + 2 * HOUR + 20 * MINUTE

    impact = reprogramar(club, segundo, expected_version=2).json()["impact"]

    assert impact["schedule_effect"] == "closing_adjusted"
    assert impact["merged_into_order"] == 3
    schedule = schedule_of(club)
    assert schedule.merged_into_order == 3
    assert as_utc(schedule.effective_closing.isoformat()) == segundo


def test_un_inicio_posterior_nunca_atrasa_el_cierre(boca_club: Club) -> None:
    club = boca_club
    club.ready()
    primero = club.opening + 4 * HOUR + 30 * MINUTE
    assert reprogramar(club, primero).status_code == 200

    impact = reprogramar(club, club.closing + DAY, expected_version=2).json()["impact"]

    assert impact["schedule_effect"] == "none"
    assert as_utc(impact["new_closing_at"]) == primero
    vista = admin_schedule(club)
    assert as_utc(vista["closing_at"]) == primero
    assert vista["merged_into_order"] is None


def test_regenerar_antes_de_la_primera_ola_descarta_los_ajustes_y_vuelve_a_borrador(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    nuevo_inicio = club.opening + 2 * HOUR + 30 * MINUTE
    assert reprogramar(club, nuevo_inicio).status_code == 200

    response = regenerar(club, club.opening, nuevo_inicio)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "draft"
    assert body["merged_into_order"] is None
    assert body["closing_at"] == body["generated_closing_at"]
    assert as_utc(body["closing_at"]) == nuevo_inicio
    (regenerado,) = audit_of(club, "wave_schedule.regenerated")
    assert regenerado.details["previous"]["merged_into_order"] == 3
    assert regenerado.details["previous"]["effective_closing_at"] == (
        nuevo_inicio.isoformat()
    )
    assert "merged_into_order" not in regenerado.details["new"]


def test_con_la_primera_ola_abierta_no_se_regenera_y_los_ajustes_siguen(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    move_schedule_to(club, utcnow() - 2 * HOUR - 30 * MINUTE)
    nuevo_inicio = utcnow() + 20 * MINUTE
    assert reprogramar(club, nuevo_inicio).status_code == 200

    response = regenerar(club, utcnow() + 5 * MINUTE, nuevo_inicio)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "SCHEDULE_LOCKED"
    assert schedule_of(club).merged_into_order == 3


# --- Escenario 9: auditoría del ajuste o la invalidación ---


def test_el_cierre_adelantado_queda_auditado(boca_club: Club, admin: User) -> None:
    club = boca_club
    club.ready()
    nuevo_inicio = club.opening + 4 * HOUR + 30 * MINUTE

    reprogramar(club, nuevo_inicio)

    (ajuste,) = audit_of(club, "wave_schedule.adjusted")
    assert ajuste.actor_user_id == admin.id
    assert ajuste.entity == "wave_schedule"
    assert ajuste.entity_id == str(schedule_of(club).id)
    assert ajuste.details["reason"] == "event.rescheduled"
    assert ajuste.details["previous"] == {
        "status": "confirmed",
        "closing_at": club.closing.isoformat(),
        "merged_into_order": None,
    }
    assert ajuste.details["new"] == {
        "status": "confirmed",
        "closing_at": nuevo_inicio.isoformat(),
        "merged_into_order": None,
    }
    assert ajuste.details["moved_waves"] == []


def test_la_invalidacion_de_un_borrador_queda_auditada(
    boca_club: Club, admin: User
) -> None:
    club = boca_club
    club.segment()
    club.schedule(confirm=False)

    reprogramar(club, club.opening + 2 * HOUR)

    (invalidado,) = audit_of(club, "wave_schedule.invalidated")
    assert invalidado.actor_user_id == admin.id
    assert invalidado.details["reason"] == "event.rescheduled"
    assert invalidado.details["previous"] == {
        "status": "draft",
        "closing_at": club.closing.isoformat(),
        "merged_into_order": None,
    }
    assert invalidado.details["new"]["status"] == "invalidated"
    assert invalidado.details["moved_waves"] == []


def test_la_segunda_fusion_audita_las_olas_que_se_movieron(boca_club: Club) -> None:
    club = boca_club
    club.ready()
    primero = club.opening + 2 * HOUR + 30 * MINUTE
    segundo = club.opening + HOUR + 30 * MINUTE
    reprogramar(club, primero)
    reprogramar(club, segundo, expected_version=2)

    primera, segunda = audit_of(club, "wave_schedule.adjusted")

    assert primera.details["moved_waves"] == [4, 5]
    assert segunda.details["previous"]["merged_into_order"] == 3
    assert segunda.details["previous"]["closing_at"] == primero.isoformat()
    assert segunda.details["new"]["merged_into_order"] == 2
    assert segunda.details["new"]["closing_at"] == segundo.isoformat()
    assert segunda.details["moved_waves"] == [3, 4, 5]


def test_si_el_cronograma_no_cambia_no_se_audita_nada_del_cronograma(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    antes = len(schedule_audits(club))

    reprogramar(club, club.closing + HOUR)

    assert len(schedule_audits(club)) == antes
    assert len(audit_of(club, "event.rescheduled")) == 1


# --- Escenario 10: la segmentación no cambia ---


@pytest.mark.parametrize(
    "desde_la_apertura",
    [4 * HOUR + 30 * MINUTE, 2 * HOUR + 30 * MINUTE, 3 * MINUTE, 10 * HOUR],
    ids=["cierre", "fusion", "invalidado", "sin-cambios"],
)
def test_la_reprogramacion_no_cambia_la_segmentacion(
    boca_club: Club, desde_la_apertura: timedelta
) -> None:
    club = boca_club
    club.ready()
    antes = admin_segmentation(club)

    assert reprogramar(club, club.opening + desde_la_apertura).status_code == 200

    despues = admin_segmentation(club)
    assert despues["waves"] == antes["waves"]
    assert despues["ranking"] == antes["ranking"]


def test_cada_socio_sigue_en_la_ola_de_su_posicion(boca_club: Club) -> None:
    club = boca_club
    club.ready()
    assert reprogramar(club, club.opening + 2 * HOUR + 30 * MINUTE).status_code == 200

    # Posiciones 1 a 10 en olas de 2: las olas 4 y 5 abren con la 3, en "Ola 3 de 3".
    esperado = {1: 1, 3: 2, 5: 3, 7: 3, 9: 3, 10: 3}
    for position, order in esperado.items():
        slot = club.slot(club.member_at(position))
        assert slot["wave"] == {"order": order, "total": 3}
        assert as_utc(slot["starts_at"]) == club.wave_start(order)
    # La segmentación sigue teniendo 5 olas con sus posiciones.
    olas = admin_segmentation(club)["waves"]
    assert [(w["order"], w["position_from"], w["position_to"]) for w in olas] == [
        (1, 1, 2),
        (2, 3, 4),
        (3, 5, 6),
        (4, 7, 8),
        (5, 9, 10),
    ]
