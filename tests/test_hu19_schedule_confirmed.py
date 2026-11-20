"""HU-19 user story 3, escenarios 10 y 11 (decisión 63): aviso del cronograma confirmado.

Escenario 10: cuando el Admin confirma el cronograma de un Partido (HU-37), los socios de
todas las olas reciben `wave_schedule_confirmed` con la hora de inicio de su propia ola. Un
borrador no avisa; confirmar de nuevo después de regenerar avisa las horas nuevas.
Escenario 11: `wave_schedule_confirmed` y `wave_opened` llevan a "Mi turno" (HU-39): su
referencia es el evento del turno del Socio.
"""

from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.date_utils import BUENOS_AIRES_TZ
from app.models import Socio, WaveSchedule, WaveScheduleStatus
from app.notifications import generators
from tests.conftest import BOCA_ID, MakeAdmin, MakeMember, Outbox
from tests.hu25_helpers import headers_for, publish_rules
from tests.hu36_helpers import HOUR
from tests.test_hu19_generators import inbox_with, notifications_count
from tests.test_hu39_own_slot import MINUTE, Club, slot_url

TYPE = "wave_schedule_confirmed"


@pytest.fixture
def club(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    make_admin: MakeAdmin,
    make_member: MakeMember,
) -> Club:
    """Un Partido de Boca con 10 socios rankeados: 5 olas de 2, una por hora."""
    admin = make_admin(BOCA_ID)
    headers = headers_for(client, outbox, admin)
    publish_rules(client, headers)
    return Club(client, db, outbox, admin, headers, make_member)


def confirm(club: Club) -> int:
    response = club.client.post(
        f"/admin/events/{club.event.id_interno}/schedule/confirm",
        headers=club.headers,
    )
    assert response.status_code == 200, response.text
    return response.status_code


def regenerate(club: Club, opening: datetime) -> None:
    club.opening, club.closing = opening, opening + 5 * HOUR
    response = club.client.post(
        f"/admin/events/{club.event.id_interno}/schedule",
        json={
            "opening_at": club.opening.isoformat(),
            "closing_at": club.closing.isoformat(),
            "confirmed": True,
        },
        headers=club.headers,
    )
    assert response.status_code == 200, response.text


def of_type(items: list[dict[str, Any]], type: str = TYPE) -> list[dict[str, Any]]:
    return [i for i in items if i["type"] == type]


def message_for(club: Club, order: int) -> str:
    start = club.wave_start(order).astimezone(BUENOS_AIRES_TZ)
    return (
        f"Ya está el cronograma de reservas para {club.event.titulo}. "
        f"Tu turno se habilita el {start:%d/%m/%Y} a las {start:%H:%M}."
    )


# === Escenario 10 ============================================================================


def test_al_confirmar_cada_socio_recibe_la_hora_de_su_propia_ola(club: Club) -> None:
    # Cuentas activadas antes de confirmar: posición 1 (ola 1), 5 (ola 3) y 10 (ola 5).
    socios = {
        order: club.member_at(position) for order, position in ((1, 1), (3, 5), (5, 10))
    }

    club.ready()

    for order, auth in socios.items():
        [item] = inbox_with(club.client, auth)
        assert {
            k: item[k] for k in ("type", "title", "message", "state", "reference")
        } == {
            "type": TYPE,
            "title": "Ya tenés tu turno de reserva",
            "message": message_for(club, order),
            "state": "unread",
            "reference": {"event_id": club.event.id_interno},
        }


def test_un_socio_fuera_del_ranking_no_recibe_el_aviso(club: Club) -> None:
    afuera = club.member()

    club.ready()

    assert inbox_with(club.client, afuera) == []


def test_un_socio_dado_de_baja_no_recibe_el_aviso(club: Club) -> None:
    auth = club.member_at(1)
    socio: Socio = club.socio_at(1)
    socio.activo = False
    club.db.commit()

    club.ready()

    assert inbox_with(club.client, auth) == []


def test_generar_un_borrador_no_avisa(club: Club) -> None:
    auth = club.member_at(1)
    club.segment()

    club.schedule(confirm=False)

    assert inbox_with(club.client, auth) == []
    assert notifications_count(club.db, type=TYPE) == 0


def test_reintentar_la_misma_confirmacion_no_duplica(club: Club) -> None:
    auth = club.member_at(1)
    club.ready()
    schedule_id = club.db.query(WaveSchedule.id).scalar()

    generators.schedule_confirmed(club.db, schedule_id)
    again = club.client.post(
        f"/admin/events/{club.event.id_interno}/schedule/confirm",
        headers=club.headers,
    )

    assert again.status_code == 409
    assert len(of_type(inbox_with(club.client, auth))) == 1


def test_confirmar_de_nuevo_despues_de_regenerar_avisa_las_horas_nuevas(
    club: Club,
) -> None:
    auth = club.member_at(3)  # ola 2
    club.ready()
    first = message_for(club, 2)

    regenerate(club, club.opening + 2 * HOUR)
    assert of_type(inbox_with(club.client, auth))[0]["message"] == first
    confirm(club)

    messages = [i["message"] for i in of_type(inbox_with(club.client, auth))]
    assert messages == [message_for(club, 2), first]
    assert messages[0] != first


def test_el_cronograma_queda_confirmado_aunque_falle_el_aviso(
    club: Club, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = club.member_at(1)

    def boom(*args: Any, **kwargs: Any) -> list[int]:
        raise RuntimeError("falla de prueba")

    monkeypatch.setattr(generators, "_ranked_members", boom)
    club.ready()

    schedule = club.db.query(WaveSchedule).one()
    club.db.refresh(schedule)
    assert schedule.status == WaveScheduleStatus.CONFIRMED
    assert inbox_with(club.client, auth) == []


def test_un_cronograma_sin_confirmar_no_genera_nada(club: Club) -> None:
    club.member_at(1)
    club.segment()
    club.schedule(confirm=False)
    schedule_id = club.db.query(WaveSchedule.id).scalar()

    assert generators.schedule_confirmed(club.db, schedule_id) == 0


# === Escenario 11: los dos avisos de turno llevan a "Mi turno" ==============================


def test_el_aviso_del_cronograma_y_el_de_la_ola_llevan_al_turno_del_socio(
    club: Club,
) -> None:
    auth = club.member_at(3)  # ola 2
    club.ready()
    generators.open_waves(club.db, now=club.wave_start(2) + MINUTE)

    items = inbox_with(club.client, auth)
    assert [i["type"] for i in items] == ["wave_opened", TYPE]
    for item in items:
        # El front abre `/member/events/{event_id}/slot` (notificaciones §3).
        response = club.client.get(
            slot_url(item["reference"]["event_id"]), headers=auth
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["event"]["id_interno"] == club.event.id_interno
        assert body["wave"]["order"] == 2
