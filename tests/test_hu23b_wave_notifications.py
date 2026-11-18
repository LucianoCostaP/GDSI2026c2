"""HU-23B US4: los avisos de una reprogramación.

Cada Partido de `Club` (HU-39) tiene 10 socios rankeados en 5 olas de 2, apertura a dos días
y una hora entre olas: la ola k abre en `opening + (k − 1) h` y el cierre es `opening + 5 h`.
Con un inicio nuevo en `opening + 2 h 30 min`, las olas 4 y 5 (posiciones 7 a 10) se suman a
la ola 3 (posiciones 5 y 6).
"""

from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.date_utils import a_hora_buenos_aires
from app.models import Notification, User
from app.models.auth import utcnow
from app.notifications import generators
from app.notifications import notify as notify_module
from tests.conftest import MakeMember, Outbox
from tests.hu36_helpers import DAY, HOUR
from tests.test_hu23b_reschedule_waves import (
    move_schedule_to,
    preview,
    reprogramar,
    schedule_of,
)
from tests.test_hu39_own_slot import Club, as_utc

MINUTE = timedelta(minutes=1)
INBOX = "/member/notifications"


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


def inbox(club: Club, auth: dict[str, str]) -> list[dict[str, Any]]:
    response = club.client.get(INBOX, headers=auth)
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


def types_of(club: Club, auth: dict[str, str]) -> list[str]:
    return sorted(item["type"] for item in inbox(club, auth))


def of_type(club: Club, type: str) -> list[Notification]:
    club.db.expire_all()
    return list(club.db.scalars(select(Notification).where(Notification.type == type)))


def fecha_hora(moment: datetime) -> tuple[str, str]:
    local = a_hora_buenos_aires(moment)
    return local.strftime("%d/%m/%Y"), local.strftime("%H:%M")


def merge_into_wave_3(club: Club) -> datetime:
    return club.opening + 2 * HOUR + 30 * MINUTE


# --- Escenario 1: todos los socios activados reciben `event_rescheduled` ---


def test_todo_socio_activado_recibe_event_rescheduled_con_la_fecha_nueva(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    de_la_ola_1 = club.member_at(1)
    de_la_ola_4 = club.member_at(7)
    fuera_de_la_segmentacion = club.member()
    nuevo_inicio = merge_into_wave_3(club)

    body = reprogramar(club, nuevo_inicio).json()

    fecha, hora = fecha_hora(nuevo_inicio)
    avisos = of_type(club, "event_rescheduled")
    assert len(avisos) == 3
    assert {a.message for a in avisos} == {
        f"{club.event.titulo} cambió: ahora es el {fecha} a las {hora}."
    }
    assert {a.occurrence_key for a in avisos} == {
        f"event:{club.event.id_interno}:rescheduled:{body['id_reprogramacion']}"
    }
    for auth in (de_la_ola_1, de_la_ola_4, fuera_de_la_segmentacion):
        assert "event_rescheduled" in types_of(club, auth)
    assert body["impact"]["notifications"]["event_rescheduled"] == 3


# --- Escenario 2: olas sumadas a una ola que todavía no abrió ---


def test_los_socios_movidos_reciben_wave_rescheduled_con_el_inicio_de_su_ola(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    de_la_ola_4 = club.member_at(7)
    de_la_ola_5 = club.member_at(10)

    body = reprogramar(club, merge_into_wave_3(club)).json()

    fecha, hora = fecha_hora(club.wave_start(3))
    avisos = of_type(club, "wave_rescheduled")
    assert len(avisos) == 2
    assert {a.title for a in avisos} == {"Tu turno de reserva cambió"}
    assert {a.message for a in avisos} == {
        (
            f"Tu turno de reserva para {club.event.titulo} cambió: se habilita el {fecha} "
            f"a las {hora}."
        )
    }
    assert {a.occurrence_key for a in avisos} == {
        f"event:{club.event.id_interno}:wave-moved:{body['id_reprogramacion']}"
    }
    assert {str(a.reference) for a in avisos} == {
        str({"event_id": club.event.id_interno})
    }
    for auth in (de_la_ola_4, de_la_ola_5):
        assert types_of(club, auth) == ["event_rescheduled", "wave_rescheduled"]
    assert of_type(club, "wave_opened") == []


def test_la_vista_previa_y_la_respuesta_cuentan_los_avisos_de_turno(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    for position in (1, 5, 7, 9, 10):
        club.member_at(position)
    nuevo_inicio = merge_into_wave_3(club)

    previa = preview(club, nuevo_inicio).json()["notifications"]
    aplicada = reprogramar(club, nuevo_inicio).json()["impact"]["notifications"]

    esperado = {"event_rescheduled": 5, "wave_rescheduled": 3, "wave_opened": 0}
    assert previa == esperado
    assert aplicada == esperado
    assert len(of_type(club, "wave_rescheduled")) == 3


def test_al_llegar_su_inicio_los_movidos_reciben_wave_opened_del_trabajo(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    de_la_ola_3 = club.member_at(5)
    de_la_ola_4 = club.member_at(7)
    assert reprogramar(club, merge_into_wave_3(club)).status_code == 200

    generators.open_waves(
        club.db, now=club.wave_start(3) + MINUTE, club_id=club.event.club_id
    )

    assert types_of(club, de_la_ola_4) == [
        "event_rescheduled",
        "wave_opened",
        "wave_rescheduled",
    ]
    assert types_of(club, de_la_ola_3) == ["event_rescheduled", "wave_opened"]


def test_un_socio_movido_dado_de_baja_no_recibe_el_aviso_de_turno(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    club.member_at(7)
    club.member_at(9)
    de_baja = club.socio_at(9)
    de_baja.activo = False
    club.db.commit()

    body = reprogramar(club, merge_into_wave_3(club)).json()

    assert len(of_type(club, "wave_rescheduled")) == 1
    assert body["impact"]["notifications"]["wave_rescheduled"] == 1


def test_una_segunda_fusion_avisa_otra_vez_a_todas_las_olas_movidas(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    de_la_ola_3 = club.member_at(5)
    de_la_ola_5 = club.member_at(9)
    primera = reprogramar(club, merge_into_wave_3(club)).json()

    # Las olas 3 a 5 se suman a la ola 2.
    segunda = reprogramar(
        club, club.opening + HOUR + 30 * MINUTE, expected_version=2
    ).json()

    assert segunda["impact"]["merged_into_order"] == 2
    fecha, hora = fecha_hora(club.wave_start(2))
    nuevo = {
        item["message"]
        for item in inbox(club, de_la_ola_5)
        if item["type"] == "wave_rescheduled"
    }
    assert len(nuevo) == 2
    assert any(f"se habilita el {fecha} a las {hora}." in m for m in nuevo)
    assert types_of(club, de_la_ola_3) == [
        "event_rescheduled",
        "event_rescheduled",
        "wave_rescheduled",
    ]
    assert {a.occurrence_key for a in of_type(club, "wave_rescheduled")} == {
        f"event:{club.event.id_interno}:wave-moved:{primera['id_reprogramacion']}",
        f"event:{club.event.id_interno}:wave-moved:{segunda['id_reprogramacion']}",
    }


# --- Escenario 3: olas sumadas a una ola que ya abrió ---


def open_wave_3(club: Club) -> datetime:
    """La ola 3 abrió hace 5 minutos y la 4 abre en 55: el nuevo inicio, en 30 minutos,
    suma las olas 4 y 5 a la 3. Devuelve el nuevo inicio."""
    move_schedule_to(club, utcnow() - 2 * HOUR - 5 * MINUTE)
    return utcnow() + 30 * MINUTE


def test_los_movidos_a_una_ola_abierta_reciben_wave_opened_en_el_momento(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    de_la_ola_4 = club.member_at(7)
    de_la_ola_5 = club.member_at(10)
    nuevo_inicio = open_wave_3(club)

    body = reprogramar(club, nuevo_inicio).json()

    assert body["impact"]["target_wave_open"] is True
    assert body["impact"]["notifications"]["wave_opened"] == 2
    assert body["impact"]["notifications"]["wave_rescheduled"] == 0
    cierre = as_utc(body["schedule"]["closing_at"])
    fecha, hora = fecha_hora(cierre)
    avisos = of_type(club, "wave_opened")
    assert len(avisos) == 2
    assert {a.message for a in avisos} == {
        (
            f"Ya podés reservar para {club.event.titulo}. Tu acceso está habilitado hasta "
            f"el {fecha} a las {hora}."
        )
    }
    assert {a.occurrence_key for a in avisos} == {
        f"event:{club.event.id_interno}:wave:3:schedule:{schedule_of(club).id}"
    }
    for auth in (de_la_ola_4, de_la_ola_5):
        assert types_of(club, auth) == ["event_rescheduled", "wave_opened"]
    assert of_type(club, "wave_rescheduled") == []


def test_el_trabajo_de_olas_no_repite_el_wave_opened_de_los_movidos(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    de_la_ola_3 = club.member_at(5)
    de_la_ola_4 = club.member_at(7)
    assert reprogramar(club, open_wave_3(club)).status_code == 200

    created = generators.open_waves(club.db, now=utcnow(), club_id=club.event.club_id)

    # Solo el socio que ya estaba en la ola 3: el movido tiene el suyo, con la misma clave.
    assert created == 1
    assert types_of(club, de_la_ola_4) == ["event_rescheduled", "wave_opened"]
    assert types_of(club, de_la_ola_3) == ["event_rescheduled", "wave_opened"]


def test_la_vista_previa_cuenta_wave_opened_si_la_ola_de_destino_ya_abrio(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    club.member_at(7)
    club.member_at(10)

    notifications = preview(club, open_wave_3(club)).json()["notifications"]

    assert (notifications["wave_opened"], notifications["wave_rescheduled"]) == (2, 0)


# --- Escenario 4: un cronograma invalidado no avisa nada de olas ---


def test_un_cronograma_invalidado_solo_avisa_event_rescheduled(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    socios = [club.member_at(position) for position in (1, 7, 10)]

    body = reprogramar(club, club.opening).json()

    assert body["impact"]["schedule_effect"] == "invalidated"
    assert body["impact"]["notifications"] == {
        "event_rescheduled": 3,
        "wave_rescheduled": 0,
        "wave_opened": 0,
    }
    for auth in socios:
        assert types_of(club, auth) == ["event_rescheduled"]
    # Un cronograma invalidado no abre olas: el trabajo no avisa hasta que haya uno nuevo.
    assert (
        generators.open_waves(
            club.db, now=club.wave_start(1) + MINUTE, club_id=club.event.club_id
        )
        == 0
    )


def test_con_el_cronograma_nuevo_confirmado_vuelven_a_recibir_wave_opened(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    de_la_ola_1 = club.member_at(1)
    nuevo_inicio = club.opening
    assert reprogramar(club, nuevo_inicio).status_code == 200

    club.opening, club.closing = nuevo_inicio - 6 * HOUR, nuevo_inicio - HOUR
    response = club.client.post(
        f"/admin/events/{club.event.id_interno}/schedule",
        json={
            "opening_at": club.opening.isoformat(),
            "closing_at": club.closing.isoformat(),
        },
        headers=club.headers,
    )
    # Un cronograma invalidado se genera de nuevo sin confirmar el reemplazo.
    assert response.status_code == 201, response.text
    confirmed = club.client.post(
        f"/admin/events/{club.event.id_interno}/schedule/confirm",
        headers=club.headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    generators.open_waves(
        club.db, now=club.wave_start(1) + MINUTE, club_id=club.event.club_id
    )

    assert types_of(club, de_la_ola_1) == ["event_rescheduled", "wave_opened"]


# --- Escenario 5: las olas no afectadas reciben solo `event_rescheduled` ---


@pytest.mark.parametrize(
    "position", [1, 3, 5, 6], ids=["ola-1", "ola-2", "ola-3-a", "ola-3-b"]
)
def test_los_socios_de_olas_no_afectadas_reciben_solo_event_rescheduled(
    boca_club: Club, position: int
) -> None:
    club = boca_club
    club.ready()
    auth = club.member_at(position)

    assert reprogramar(club, merge_into_wave_3(club)).status_code == 200

    assert types_of(club, auth) == ["event_rescheduled"]


def test_un_ajuste_del_cierre_avisa_solo_event_rescheduled(boca_club: Club) -> None:
    club = boca_club
    club.ready()
    socios = [club.member_at(position) for position in (1, 10)]

    body = reprogramar(club, club.closing - 30 * MINUTE).json()

    assert body["impact"]["schedule_effect"] == "closing_adjusted"
    for auth in socios:
        assert types_of(club, auth) == ["event_rescheduled"]
    assert of_type(club, "wave_rescheduled") == of_type(club, "wave_opened") == []


# --- Escenario 6: los avisos anteriores conservan su texto ---


def test_los_avisos_anteriores_conservan_su_texto_y_su_destino(
    boca_club: Club,
) -> None:
    club = boca_club
    club.ready()
    auth = club.member_at(1)
    generators.event_published(club.db, club.event.id_interno)
    generators.open_waves(
        club.db, now=club.wave_start(1) + MINUTE, club_id=club.event.club_id
    )
    assert reprogramar(club, club.event.fecha_hora + DAY).status_code == 200
    antes = {item["id"]: item for item in inbox(club, auth)}
    assert sorted(i["type"] for i in antes.values()) == [
        "event_published",
        "event_rescheduled",
        "wave_opened",
    ]

    # Un ajuste del cierre: la reprogramación nueva no reescribe los avisos que ya estaban.
    assert (
        reprogramar(club, club.closing - 30 * MINUTE, expected_version=2).status_code
        == 200
    )

    despues = {item["id"]: item for item in inbox(club, auth)}
    assert len(despues) == 4
    for id_, item in antes.items():
        assert (despues[id_]["message"], despues[id_]["reference"]) == (
            item["message"],
            item["reference"],
        )
    fecha, hora = fecha_hora(club.closing)
    viejo = next(i for i in antes.values() if i["type"] == "wave_opened")
    assert viejo["message"].endswith(f"hasta el {fecha} a las {hora}.")


# --- Escenario 7: una falla al avisar no deshace la reprogramación ---


def test_si_fallan_los_avisos_la_reprogramacion_queda_aplicada(
    boca_club: Club, monkeypatch: pytest.MonkeyPatch
) -> None:
    club = boca_club
    club.ready()
    club.member_at(1)
    club.member_at(7)
    nuevo_inicio = merge_into_wave_3(club)
    monkeypatch.setattr(notify_module, "BY_KEY", {})

    response = reprogramar(club, nuevo_inicio)

    assert response.status_code == 200, response.text
    club.db.refresh(club.event)
    assert as_utc(club.event.fecha_hora.isoformat()) == nuevo_inicio
    assert schedule_of(club).merged_into_order == 3
    assert of_type(club, "event_rescheduled") == []
    assert of_type(club, "wave_rescheduled") == []


def test_si_falla_la_lectura_de_los_movidos_igual_se_avisa_el_evento(
    boca_club: Club, monkeypatch: pytest.MonkeyPatch
) -> None:
    club = boca_club
    club.ready()
    club.member_at(7)

    def boom(*_: Any, **__: Any) -> list[int]:
        raise RuntimeError("falla de prueba")

    original = generators._ranked_members
    nuevo_inicio = merge_into_wave_3(club)
    monkeypatch.setattr(generators, "_ranked_members", boom)
    # La vista previa del servicio cuenta con la misma consulta: se restaura para el plan.
    monkeypatch.setattr(
        "app.services.published_events_service.ranked_member_ids",
        lambda db, ranking_id, club_id, positions: original(
            db, ranking_id, club_id, positions
        ),
    )

    response = reprogramar(club, nuevo_inicio)

    assert response.status_code == 200, response.text
    assert len(of_type(club, "event_rescheduled")) == 1
    assert of_type(club, "wave_rescheduled") == []


# --- Una por acción: repetir el aviso no duplica (edge case) ---


def test_repetir_el_aviso_de_turno_no_crea_nada(boca_club: Club) -> None:
    club = boca_club
    club.ready()
    club.member_at(7)
    body = reprogramar(club, merge_into_wave_3(club)).json()

    again = generators.waves_moved(
        club.db,
        club.event.id_interno,
        body["id_reprogramacion"],
        schedule_id=schedule_of(club).id,
        joined_order=3,
        first_moved_order=4,
        joined_open=False,
    )

    assert again == 0
    assert len(of_type(club, "wave_rescheduled")) == 1
