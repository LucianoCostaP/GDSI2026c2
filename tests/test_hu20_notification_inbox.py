"""HU-20: bandeja de notificaciones del Socio, por la API.

Hasta que existan los generadores de HU-19, las notificaciones se crean directo en la base, como
haría el contrato `notify` (notificaciones §4 y §10).
"""

from datetime import UTC, datetime
from itertools import count
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.main import app
from app.models import Member, Notification, NotificationState, User
from app.services import notification_service
from tests.conftest import (
    BOCA_ID,
    RIVER_ID,
    MakeAdmin,
    MakeMember,
    Outbox,
    admin_token,
    bearer,
    member_token,
)

INBOX = "/member/notifications"

_occurrences = count(1)


def account_of(db: Session, member: Member) -> User:
    user = db.scalar(select(User).where(User.member_id == member.member_id))
    assert user is not None
    return user


def notify(
    db: Session,
    user: User,
    *,
    created_at: datetime,
    type: str = "event_published",
    title: str = "Nuevo evento publicado",
    message: str = "Ya podés ver Fecha 12 vs. Rival, el 08/11/2026 a las 17:00.",
    reference: dict[str, Any] | None = None,
    read_at: datetime | None = None,
) -> Notification:
    notification = Notification(
        club_id=user.club_id or BOCA_ID,
        user_id=user.id,
        type=type,
        reference=reference or {"event_id": "evt-1"},
        title=title,
        message=message,
        created_at=created_at,
        state=NotificationState.READ if read_at else NotificationState.UNREAD,
        read_at=read_at,
        occurrence_key=f"test:{next(_occurrences)}",
    )
    db.add(notification)
    db.commit()
    return notification


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(UTC)


def headers(client: TestClient, outbox: Outbox, member: Member) -> dict[str, str]:
    result = bearer(member_token(client, outbox, member))
    outbox.clear()
    return result


# --- Escenario 1: todas las notificaciones, la más reciente primero -------------------------


def test_lista_todas_las_notificaciones_de_la_mas_reciente_a_la_mas_antigua(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    user = account_of(db, member)
    # Se crean fuera de orden: el orden sale de la fecha de generación, no de la inserción.
    notify(db, user, created_at=at("2026-10-29T15:00:05Z"), message="del medio")
    notify(db, user, created_at=at("2026-11-05T13:00:04Z"), message="la más nueva")
    notify(db, user, created_at=at("2026-09-01T10:00:00Z"), message="la más vieja")

    response = client.get(INBOX, headers=headers(client, outbox, member))

    assert response.status_code == 200
    body = response.json()
    assert [item["message"] for item in body["items"]] == [
        "la más nueva",
        "del medio",
        "la más vieja",
    ]
    assert body["total"] == 3


def test_con_la_misma_fecha_va_primero_la_creada_despues(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    user = account_of(db, member)
    same_moment = at("2026-11-05T13:00:04Z")
    first = notify(db, user, created_at=same_moment, message="creada primero")
    second = notify(db, user, created_at=same_moment, message="creada después")

    response = client.get(INBOX, headers=headers(client, outbox, member))

    assert [item["id"] for item in response.json()["items"]] == [second.id, first.id]


def test_la_bandeja_responde_sin_cache(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)

    response = client.get(INBOX, headers=headers(client, outbox, member))

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"


# --- Escenario 2: título, mensaje y fecha de cada notificación ------------------------------


def test_cada_notificacion_trae_titulo_mensaje_y_fecha_de_generacion(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    user = account_of(db, member)
    notification = notify(
        db,
        user,
        created_at=at("2026-11-05T13:00:04Z"),
        type="wave_opened",
        title="Tu turno de reserva está habilitado",
        message=(
            "Ya podés reservar para Fecha 12 vs. Rival. "
            "Tu acceso está habilitado hasta el 07/11/2026 a las 18:00."
        ),
        reference={"event_id": "evt-7f3a"},
    )

    response = client.get(INBOX, headers=headers(client, outbox, member))

    [item] = response.json()["items"]
    assert item == {
        "id": notification.id,
        "type": "wave_opened",
        "title": "Tu turno de reserva está habilitado",
        "message": (
            "Ya podés reservar para Fecha 12 vs. Rival. "
            "Tu acceso está habilitado hasta el 07/11/2026 a las 18:00."
        ),
        "created_at": "2026-11-05T13:00:04Z",
        "state": "unread",
        "read_at": None,
        "reference": {"event_id": "evt-7f3a"},
    }


def test_la_fecha_viaja_en_utc_para_mostrarla_en_hora_de_buenos_aires(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    """El front la muestra como `dd/mm/aaaa HH:mm` en Buenos Aires: 01:30 UTC del 6/11 es el
    05/11/2026 22:30. El backend la manda en UTC, sin perder el instante."""
    member = make_member(activated=True)
    user = account_of(db, member)
    notify(db, user, created_at=at("2026-11-05T22:30:00-03:00"))

    response = client.get(INBOX, headers=headers(client, outbox, member))

    [item] = response.json()["items"]
    assert item["created_at"] == "2026-11-06T01:30:00Z"


def test_la_referencia_de_un_ranking_trae_su_id(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    user = account_of(db, member)
    notify(
        db,
        user,
        created_at=at("2026-10-29T15:00:05Z"),
        type="ranking_completed",
        title="Se actualizó el ranking",
        message="Se calculó un nuevo ranking. Consultá tu puntaje y tu posición.",
        reference={"ranking_id": 42},
    )

    response = client.get(INBOX, headers=headers(client, outbox, member))

    [item] = response.json()["items"]
    assert item["type"] == "ranking_completed"
    assert item["reference"] == {"ranking_id": 42}


# --- Escenario 3: leídas y no leídas se distinguen ------------------------------------------


def test_cada_notificacion_dice_si_esta_leida_y_desde_cuando(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    """El front marca la no leída con negrita, "Nueva" y un marcador; para eso le alcanza el
    estado, que viaja como texto y no como color."""
    member = make_member(activated=True)
    user = account_of(db, member)
    notify(db, user, created_at=at("2026-11-05T13:00:04Z"), message="sin leer")
    notify(
        db,
        user,
        created_at=at("2026-10-29T15:00:05Z"),
        message="leída",
        read_at=at("2026-10-29T18:22:10Z"),
    )

    response = client.get(INBOX, headers=headers(client, outbox, member))

    items = response.json()["items"]
    assert [(i["message"], i["state"], i["read_at"]) for i in items] == [
        ("sin leer", "unread", None),
        ("leída", "read", "2026-10-29T18:22:10Z"),
    ]


def test_la_bandeja_trae_cuantas_quedan_sin_leer(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    user = account_of(db, member)
    notify(db, user, created_at=at("2026-11-05T13:00:04Z"))
    notify(db, user, created_at=at("2026-11-04T13:00:04Z"))
    notify(
        db,
        user,
        created_at=at("2026-11-03T13:00:04Z"),
        read_at=at("2026-11-03T14:00:00Z"),
    )

    body = client.get(INBOX, headers=headers(client, outbox, member)).json()

    assert body["total"] == 3
    assert body["unread_count"] == 2


def test_las_no_leidas_de_otro_socio_no_suman_al_contador(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    other = make_member(activated=True)
    notify(db, account_of(db, member), created_at=at("2026-11-05T13:00:04Z"))
    notify(db, account_of(db, other), created_at=at("2026-11-05T13:00:04Z"))
    notify(db, account_of(db, other), created_at=at("2026-11-04T13:00:04Z"))

    body = client.get(INBOX, headers=headers(client, outbox, member)).json()

    assert body["total"] == 1
    assert body["unread_count"] == 1


# --- Escenario 4: sin notificaciones ---------------------------------------------------------


def test_un_socio_sin_notificaciones_recibe_la_bandeja_vacia(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    """El texto "No tenés notificaciones." lo pone el front; el backend responde 200 con la
    lista vacía, nunca un error, para que el front no confunda vacío con falla (escenario 7)."""
    member = make_member(activated=True)

    response = client.get(INBOX, headers=headers(client, outbox, member))

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "total": 0,
        "unread_count": 0,
        "limit": 20,
        "offset": 0,
    }


def test_la_bandeja_esta_vacia_aunque_otro_socio_tenga_notificaciones(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    other = make_member(activated=True)
    notify(db, account_of(db, other), created_at=at("2026-11-05T13:00:04Z"))

    response = client.get(INBOX, headers=headers(client, outbox, member))

    assert response.json() == {
        "items": [],
        "total": 0,
        "unread_count": 0,
        "limit": 20,
        "offset": 0,
    }


# --- Escenario 5: la bandeja no depende del correo -------------------------------------------
#
# La bandeja nunca lee las preferencias ni el estado del correo (notificaciones §1 y §5).
# PENDIENTE (HU-19, notificaciones §10): faltan los tests con el interruptor general apagado, con
# el del tipo apagado y con el correo `failed`/`not_sent`; las preferencias y `email_status`
# todavía no existen. Está anotado en `docs/brechas-codigo.md`: sumarlos acá al hacer HU-19.


def test_la_bandeja_muestra_todos_los_tipos_activos_sin_filtrar_por_preferencias(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    user = account_of(db, member)
    notify(db, user, created_at=at("2026-11-05T13:00:00Z"), type="event_published")
    notify(db, user, created_at=at("2026-11-04T13:00:00Z"), type="wave_opened")
    notify(
        db,
        user,
        created_at=at("2026-11-03T13:00:00Z"),
        type="ranking_completed",
        reference={"ranking_id": 7},
    )

    body = client.get(INBOX, headers=headers(client, outbox, member)).json()

    assert [item["type"] for item in body["items"]] == [
        "event_published",
        "wave_opened",
        "ranking_completed",
    ]


def test_la_bandeja_no_expone_nada_del_correo(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    """El estado del envío no se le muestra al Socio (HU-20, API)."""
    member = make_member(activated=True)
    notify(db, account_of(db, member), created_at=at("2026-11-05T13:00:00Z"))

    [item] = client.get(INBOX, headers=headers(client, outbox, member)).json()["items"]

    assert not any("email" in key for key in item)


# --- Escenario 6: paginación con el orden global ---------------------------------------------


def many(db: Session, user: User, amount: int) -> None:
    """`amount` notificaciones, una por minuto; el mensaje dice su número (1 es la más vieja)."""
    for n in range(1, amount + 1):
        notify(
            db,
            user,
            created_at=at(f"2026-11-05T{10 + n // 60:02d}:{n % 60:02d}:00Z"),
            message=f"n{n}",
        )


def test_la_primera_pagina_trae_20_y_el_total_de_todas(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    many(db, account_of(db, member), 25)

    body = client.get(INBOX, headers=headers(client, outbox, member)).json()

    assert [item["message"] for item in body["items"]] == [
        f"n{n}" for n in range(25, 5, -1)
    ]
    assert (body["total"], body["unread_count"]) == (25, 25)
    assert (body["limit"], body["offset"]) == (20, 0)


def test_cargar_mas_trae_la_pagina_siguiente_manteniendo_el_orden(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    many(db, account_of(db, member), 25)
    auth = headers(client, outbox, member)

    first = client.get(INBOX, headers=auth).json()
    second = client.get(
        INBOX, params={"offset": len(first["items"])}, headers=auth
    ).json()

    assert [item["message"] for item in second["items"]] == [
        f"n{n}" for n in range(5, 0, -1)
    ]
    assert (second["total"], second["limit"], second["offset"]) == (25, 20, 20)


def test_paginas_chicas_reconstruyen_el_orden_completo_con_empates(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    user = account_of(db, member)
    same_moment = at("2026-11-05T13:00:00Z")
    created = [notify(db, user, created_at=same_moment) for _ in range(7)]
    auth = headers(client, outbox, member)

    ids: list[int] = []
    for offset in range(0, 9, 3):
        page = client.get(INBOX, params={"limit": 3, "offset": offset}, headers=auth)
        ids += [item["id"] for item in page.json()["items"]]

    assert ids == [n.id for n in reversed(created)]


def test_una_pagina_mas_alla_del_final_viene_vacia_con_el_total(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    many(db, account_of(db, member), 3)

    body = client.get(
        INBOX, params={"offset": 20}, headers=headers(client, outbox, member)
    ).json()

    assert (body["items"], body["total"]) == ([], 3)


def test_el_limite_admite_hasta_100(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)

    response = client.get(
        INBOX, params={"limit": 100}, headers=headers(client, outbox, member)
    )

    assert response.status_code == 200
    assert response.json()["limit"] == 100


@pytest.mark.parametrize(
    "params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"limit": "veinte"}]
)
def test_limite_u_offset_fuera_de_rango_responden_422(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    make_member: MakeMember,
    params: dict[str, Any],
) -> None:
    member = make_member(activated=True)

    response = client.get(INBOX, params=params, headers=headers(client, outbox, member))

    assert response.status_code == 422


# --- Escenario 7: la bandeja no se puede cargar ----------------------------------------------
#
# El texto "No pudimos cargar tus notificaciones. Intentá de nuevo." y el reintento los pone el
# front. Al backend le toca no disfrazar la falla de bandeja vacía.


def test_si_la_base_falla_responde_un_error_y_no_una_bandeja_vacia(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    make_member: MakeMember,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    member = make_member(activated=True)
    notify(db, account_of(db, member), created_at=at("2026-11-05T13:00:00Z"))
    auth = headers(client, outbox, member)
    # Con los overrides del fixture `client` activos, pero devolviendo el 500 como el server real.
    client = TestClient(app, raise_server_exceptions=False)

    def broken(*_: Any) -> int:
        raise OperationalError("SELECT count(*) FROM notifications", {}, Exception())

    monkeypatch.setattr(notification_service, "_unread_count", broken)

    response = client.get(INBOX, headers=auth)

    assert response.status_code == 500
    assert "items" not in response.text
    assert "notifications" not in response.text  # sin detalle técnico


def test_despues_de_una_falla_reintentar_trae_la_bandeja(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    make_member: MakeMember,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    member = make_member(activated=True)
    notify(db, account_of(db, member), created_at=at("2026-11-05T13:00:00Z"))
    auth = headers(client, outbox, member)
    # Con los overrides del fixture `client` activos, pero devolviendo el 500 como el server real.
    client = TestClient(app, raise_server_exceptions=False)
    working = notification_service._unread_count

    def broken(*_: Any) -> int:
        raise OperationalError("SELECT 1", {}, Exception())

    monkeypatch.setattr(notification_service, "_unread_count", broken)
    assert client.get(INBOX, headers=auth).status_code == 500
    monkeypatch.setattr(notification_service, "_unread_count", working)

    retry = client.get(INBOX, headers=auth)

    assert retry.status_code == 200
    assert retry.json()["total"] == 1


# --- Escenario 8: solo el Socio de la sesión, y solo lo suyo ---------------------------------


def test_sin_sesion_se_rechaza(client: TestClient) -> None:
    response = client.get(INBOX)

    assert (response.status_code, response.json()["detail"]) == (
        401,
        "NOT_AUTHENTICATED",
    )


def test_con_un_token_invalido_se_rechaza(client: TestClient) -> None:
    response = client.get(INBOX, headers=bearer("no-es-un-token"))

    assert response.status_code == 401


def test_un_admin_no_puede_ver_la_bandeja(
    client: TestClient, outbox: Outbox, make_admin: MakeAdmin
) -> None:
    auth = bearer(admin_token(client, outbox, make_admin(BOCA_ID)))

    response = client.get(INBOX, headers=auth)

    assert (response.status_code, response.json()["detail"]) == (403, "FORBIDDEN")


def test_una_cuenta_de_socio_sin_club_se_rechaza(
    client: TestClient, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True, club_id=None)

    response = client.get(INBOX, headers=headers(client, outbox, member))

    assert (response.status_code, response.json()["detail"]) == (
        403,
        "MEMBER_WITHOUT_CLUB",
    )


def test_un_socio_nunca_ve_las_notificaciones_de_otro_socio(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    other = make_member(activated=True)
    notify(
        db, account_of(db, member), created_at=at("2026-11-04T13:00:00Z"), message="mía"
    )
    notify(
        db,
        account_of(db, other),
        created_at=at("2026-11-05T13:00:00Z"),
        message="ajena",
    )

    body = client.get(INBOX, headers=headers(client, outbox, member)).json()

    assert [item["message"] for item in body["items"]] == ["mía"]


def test_un_socio_no_ve_las_notificaciones_de_otro_club_aunque_sean_de_su_cuenta(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    """La consulta filtra por cuenta y por el club de la sesión: una fila de otro club nunca
    aparece, aunque apunte a la misma cuenta."""
    member = make_member(activated=True)
    user = account_of(db, member)
    notify(db, user, created_at=at("2026-11-04T13:00:00Z"), message="de Boca")
    foreign = notify(
        db, user, created_at=at("2026-11-05T13:00:00Z"), message="de River"
    )
    foreign.club_id = RIVER_ID
    db.commit()

    body = client.get(INBOX, headers=headers(client, outbox, member)).json()

    assert [item["message"] for item in body["items"]] == ["de Boca"]
    assert (body["total"], body["unread_count"]) == (1, 1)


def test_el_club_y_el_socio_salen_de_la_sesion_y_no_del_pedido(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    river_member = make_member(activated=True, club_id=RIVER_ID)
    boca_member = make_member(activated=True)
    notify(
        db,
        account_of(db, river_member),
        created_at=at("2026-11-04T13:00:00Z"),
        message="mía",
    )
    boca_user = account_of(db, boca_member)
    notify(db, boca_user, created_at=at("2026-11-05T13:00:00Z"), message="ajena")

    response = client.get(
        INBOX,
        params={"club_id": str(BOCA_ID), "user_id": boca_user.id},
        headers={
            **headers(client, outbox, river_member),
            "X-Club-ID": str(BOCA_ID),
        },
    )

    assert response.status_code == 200
    assert [item["message"] for item in response.json()["items"]] == ["mía"]
