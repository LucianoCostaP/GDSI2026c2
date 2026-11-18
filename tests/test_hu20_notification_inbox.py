"""HU-20: bandeja de notificaciones del Socio, por la API.

Hasta que existan los generadores de HU-19, las notificaciones se crean directo en la base, como
haría el contrato `notify` (notificaciones §4 y §10).
"""

from datetime import UTC, datetime, timedelta
from itertools import count
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.main import app
from app.models import Member, Notification, NotificationState, User
from app.notifications.catalog import ACTIVE_TYPES, BY_KEY, CATALOG
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


# === User Story 2: abrir y marcar como leída ================================================


def read(client: TestClient, auth: dict[str, str], notification: Notification) -> Any:
    return client.post(f"{INBOX}/{notification.id}/read", headers=auth)


# --- US2 escenario 1: al abrirla queda leída y el front tiene con qué ir al destino ----------


def test_abrir_una_no_leida_la_marca_como_leida_con_la_hora_de_lectura(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    notification = notify(
        db,
        account_of(db, member),
        created_at=at("2026-11-05T13:00:04Z"),
        type="wave_opened",
        title="Tu turno de reserva está habilitado",
        message="Ya podés reservar para Fecha 12 vs. Rival.",
        reference={"event_id": "evt-7f3a"},
    )
    auth = headers(client, outbox, member)
    before = datetime.now(UTC)

    response = read(client, auth, notification)

    after = datetime.now(UTC)
    assert response.status_code == 200
    body = response.json()
    read_at = datetime.fromisoformat(body.pop("read_at"))
    assert before - timedelta(seconds=1) <= read_at <= after + timedelta(seconds=1)
    assert body == {
        "id": notification.id,
        "type": "wave_opened",
        "title": "Tu turno de reserva está habilitado",
        "message": "Ya podés reservar para Fecha 12 vs. Rival.",
        "created_at": "2026-11-05T13:00:04Z",
        "state": "read",
        "reference": {"event_id": "evt-7f3a"},
    }


def test_la_lectura_queda_guardada_y_baja_el_contador(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    user = account_of(db, member)
    opened = notify(db, user, created_at=at("2026-11-05T13:00:00Z"), message="abierta")
    notify(db, user, created_at=at("2026-11-04T13:00:00Z"), message="pendiente")
    auth = headers(client, outbox, member)

    marked = read(client, auth, opened).json()
    inbox = client.get(INBOX, headers=auth).json()

    assert [(i["message"], i["state"]) for i in inbox["items"]] == [
        ("abierta", "read"),
        ("pendiente", "unread"),
    ]
    assert inbox["items"][0]["read_at"] == marked["read_at"]
    assert inbox["unread_count"] == 1


@pytest.mark.parametrize(
    ("type", "reference"),
    [
        ("event_published", {"event_id": "evt-1"}),
        ("event_rescheduled", {"event_id": "evt-2"}),
        ("event_withdrawn", {"event_id": "evt-4"}),
        ("event_restored", {"event_id": "evt-5"}),
        ("wave_opened", {"event_id": "evt-3"}),
        ("ranking_completed", {"ranking_id": 42}),
    ],
)
def test_la_respuesta_trae_tipo_y_referencia_para_armar_el_destino(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    make_member: MakeMember,
    type: str,
    reference: dict[str, Any],
) -> None:
    """El front arma la ruta con el tipo y la referencia (contrato §7): el evento, el turno
    propio o "Mi puntaje". La notificación nunca guarda una URL."""
    member = make_member(activated=True)
    notification = notify(
        db,
        account_of(db, member),
        created_at=at("2026-11-05T13:00:00Z"),
        type=type,
        reference=reference,
    )

    body = read(client, headers(client, outbox, member), notification).json()

    assert (body["type"], body["reference"]) == (type, reference)


def test_marcar_como_leida_no_cambia_las_demas(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    other = make_member(activated=True)
    user = account_of(db, member)
    opened = notify(db, user, created_at=at("2026-11-05T13:00:00Z"))
    mine = notify(db, user, created_at=at("2026-11-04T13:00:00Z"))
    theirs = notify(db, account_of(db, other), created_at=at("2026-11-05T13:00:00Z"))

    read(client, headers(client, outbox, member), opened)

    for untouched in (mine, theirs):
        db.refresh(untouched)
        assert (untouched.state, untouched.read_at) == (NotificationState.UNREAD, None)


# --- US2 escenario 2: el evento ya no está disponible ----------------------------------------


def test_se_marca_como_leida_aunque_el_evento_ya_no_exista(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    """Marcar como leída no consulta el evento: el front muestra "Este evento ya no está
    disponible." cuando el destino no lo encuentra (contrato §7)."""
    member = make_member(activated=True)
    notification = notify(
        db,
        account_of(db, member),
        created_at=at("2026-11-05T13:00:00Z"),
        reference={"event_id": "evento-que-no-existe"},
    )

    response = read(client, headers(client, outbox, member), notification)

    assert response.status_code == 200
    assert response.json()["state"] == "read"
    assert response.json()["reference"] == {"event_id": "evento-que-no-existe"}


def test_despues_de_un_evento_no_disponible_la_bandeja_sigue_accesible(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    user = account_of(db, member)
    gone = notify(
        db,
        user,
        created_at=at("2026-11-05T13:00:00Z"),
        reference={"event_id": "evento-que-no-existe"},
    )
    notify(db, user, created_at=at("2026-11-04T13:00:00Z"))
    auth = headers(client, outbox, member)

    read(client, auth, gone)
    inbox = client.get(INBOX, headers=auth)

    assert inbox.status_code == 200
    assert [i["state"] for i in inbox.json()["items"]] == ["read", "unread"]


# --- US2 escenario 3: abrir una ya leída no cambia nada --------------------------------------


def test_abrir_una_ya_leida_conserva_la_primera_hora_de_lectura(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    notification = notify(
        db,
        account_of(db, member),
        created_at=at("2026-10-29T15:00:05Z"),
        read_at=at("2026-10-29T18:22:10Z"),
    )

    response = read(client, headers(client, outbox, member), notification)

    assert response.status_code == 200
    assert (response.json()["state"], response.json()["read_at"]) == (
        "read",
        "2026-10-29T18:22:10Z",
    )
    db.refresh(notification)
    assert notification.read_at == at("2026-10-29T18:22:10Z")


def test_abrirla_dos_veces_responde_lo_mismo(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    """Dos dispositivos o dos toques: marcar como leída es idempotente (FR-009)."""
    member = make_member(activated=True)
    notification = notify(
        db, account_of(db, member), created_at=at("2026-11-05T13:00:00Z")
    )
    auth = headers(client, outbox, member)

    first = read(client, auth, notification).json()
    second = read(client, auth, notification).json()

    assert second == first


def test_abrir_una_ya_leida_no_cambia_el_contador(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    user = account_of(db, member)
    already = notify(
        db,
        user,
        created_at=at("2026-11-05T13:00:00Z"),
        read_at=at("2026-11-05T14:00:00Z"),
    )
    notify(db, user, created_at=at("2026-11-04T13:00:00Z"))
    auth = headers(client, outbox, member)

    read(client, auth, already)

    assert client.get(INBOX, headers=auth).json()["unread_count"] == 1


# --- US2 escenario 4: "Marcar todas como leídas" ---------------------------------------------

READ_ALL = f"{INBOX}/read-all"


def test_marcar_todas_como_leidas_deja_el_contador_en_cero(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    user = account_of(db, member)
    for day in (3, 4, 5):
        notify(db, user, created_at=at(f"2026-11-0{day}T13:00:00Z"))
    auth = headers(client, outbox, member)
    before = datetime.now(UTC)

    response = client.post(READ_ALL, headers=auth)

    assert response.status_code == 200
    assert response.json() == {"marked": 3, "unread_count": 0}
    inbox = client.get(INBOX, headers=auth).json()
    assert inbox["unread_count"] == 0
    assert {i["state"] for i in inbox["items"]} == {"read"}
    for item in inbox["items"]:
        assert datetime.fromisoformat(item["read_at"]) >= before - timedelta(seconds=1)


def test_marcar_todas_conserva_la_hora_de_las_ya_leidas(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    user = account_of(db, member)
    already = notify(
        db,
        user,
        created_at=at("2026-10-29T15:00:05Z"),
        read_at=at("2026-10-29T18:22:10Z"),
    )
    notify(db, user, created_at=at("2026-11-05T13:00:00Z"))

    response = client.post(READ_ALL, headers=headers(client, outbox, member))

    assert response.json() == {"marked": 1, "unread_count": 0}
    db.refresh(already)
    assert already.read_at == at("2026-10-29T18:22:10Z")


def test_marcar_todas_sin_ninguna_pendiente_marca_cero(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    notify(
        db,
        account_of(db, member),
        created_at=at("2026-11-05T13:00:00Z"),
        read_at=at("2026-11-05T14:00:00Z"),
    )

    response = client.post(READ_ALL, headers=headers(client, outbox, member))

    assert (response.status_code, response.json()) == (
        200,
        {"marked": 0, "unread_count": 0},
    )


def test_marcar_todas_no_toca_las_de_otro_socio_ni_las_de_otro_club(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    other = make_member(activated=True)
    user = account_of(db, member)
    notify(db, user, created_at=at("2026-11-05T13:00:00Z"))
    foreign_club = notify(db, user, created_at=at("2026-11-05T13:00:00Z"))
    foreign_club.club_id = RIVER_ID
    db.commit()
    theirs = notify(db, account_of(db, other), created_at=at("2026-11-05T13:00:00Z"))

    response = client.post(READ_ALL, headers=headers(client, outbox, member))

    assert response.json() == {"marked": 1, "unread_count": 0}
    for untouched in (foreign_club, theirs):
        db.refresh(untouched)
        assert (untouched.state, untouched.read_at) == (NotificationState.UNREAD, None)


def test_marcar_todas_marca_mas_que_una_pagina(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    """ "Todas" son todas las del Socio, no solo las de la página cargada."""
    member = make_member(activated=True)
    many(db, account_of(db, member), 25)
    auth = headers(client, outbox, member)

    response = client.post(READ_ALL, headers=auth)

    assert response.json() == {"marked": 25, "unread_count": 0}
    assert (
        client.get(INBOX, params={"offset": 20}, headers=auth).json()["unread_count"]
        == 0
    )


# --- US2 escenario 5: el contador del menú ----------------------------------------------------
#
# El front muestra el número junto a "Notificaciones", `99+` por encima de 99 y nada con 0
# (contrato §3.2). El backend manda el número exacto.

UNREAD_COUNT = f"{INBOX}/unread-count"


def test_el_contador_dice_cuantas_hay_sin_leer(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    user = account_of(db, member)
    notify(db, user, created_at=at("2026-11-05T13:00:00Z"))
    notify(db, user, created_at=at("2026-11-04T13:00:00Z"))
    notify(
        db,
        user,
        created_at=at("2026-11-03T13:00:00Z"),
        read_at=at("2026-11-03T14:00:00Z"),
    )

    response = client.get(UNREAD_COUNT, headers=headers(client, outbox, member))

    assert response.status_code == 200
    assert response.json() == {"unread_count": 2}


def test_sin_notificaciones_sin_leer_el_contador_es_cero(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    notify(
        db,
        account_of(db, member),
        created_at=at("2026-11-05T13:00:00Z"),
        read_at=at("2026-11-05T14:00:00Z"),
    )

    response = client.get(UNREAD_COUNT, headers=headers(client, outbox, member))

    assert response.json() == {"unread_count": 0}


def test_por_encima_de_99_el_contador_manda_el_numero_exacto(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    """El `99+` lo arma el front; el backend no recorta."""
    member = make_member(activated=True)
    user = account_of(db, member)
    db.add_all(
        Notification(
            club_id=BOCA_ID,
            user_id=user.id,
            type="event_published",
            reference={"event_id": f"evt-{n}"},
            title="Nuevo evento publicado",
            message="Ya podés verlo.",
            created_at=at("2026-11-05T13:00:00Z"),
            occurrence_key=f"test:muchas:{n}",
        )
        for n in range(105)
    )
    db.commit()

    response = client.get(UNREAD_COUNT, headers=headers(client, outbox, member))

    assert response.json() == {"unread_count": 105}


def test_el_contador_es_igual_al_de_la_bandeja(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    many(db, account_of(db, member), 25)
    auth = headers(client, outbox, member)

    counter = client.get(UNREAD_COUNT, headers=auth).json()["unread_count"]
    inbox = client.get(INBOX, params={"limit": 5}, headers=auth).json()

    assert counter == inbox["unread_count"] == 25


def test_el_contador_solo_cuenta_las_del_socio_y_su_club(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    other = make_member(activated=True)
    user = account_of(db, member)
    notify(db, user, created_at=at("2026-11-05T13:00:00Z"))
    foreign_club = notify(db, user, created_at=at("2026-11-05T13:00:00Z"))
    foreign_club.club_id = RIVER_ID
    db.commit()
    notify(db, account_of(db, other), created_at=at("2026-11-05T13:00:00Z"))

    response = client.get(
        UNREAD_COUNT,
        params={"club_id": str(RIVER_ID)},
        headers={**headers(client, outbox, member), "X-Club-ID": str(RIVER_ID)},
    )

    assert response.json() == {"unread_count": 1}


def test_el_contador_responde_sin_cache(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)

    response = client.get(UNREAD_COUNT, headers=headers(client, outbox, member))

    assert response.headers["Cache-Control"] == "no-store"


def test_el_contador_es_solo_para_socios(
    client: TestClient, outbox: Outbox, make_admin: MakeAdmin
) -> None:
    anonymous = client.get(UNREAD_COUNT)
    as_admin = client.get(
        UNREAD_COUNT, headers=bearer(admin_token(client, outbox, make_admin(BOCA_ID)))
    )

    assert (anonymous.status_code, anonymous.json()["detail"]) == (
        401,
        "NOT_AUTHENTICATED",
    )
    assert (as_admin.status_code, as_admin.json()["detail"]) == (403, "FORBIDDEN")


# --- US2 escenario 6: lo marcado se ve en la próxima carga -----------------------------------


def test_al_abrir_una_el_contador_y_la_lista_lo_reflejan(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    user = account_of(db, member)
    opened = notify(db, user, created_at=at("2026-11-05T13:00:00Z"), message="abierta")
    notify(db, user, created_at=at("2026-11-04T13:00:00Z"), message="pendiente")
    auth = headers(client, outbox, member)
    assert client.get(UNREAD_COUNT, headers=auth).json() == {"unread_count": 2}

    read(client, auth, opened)

    assert client.get(UNREAD_COUNT, headers=auth).json() == {"unread_count": 1}
    inbox = client.get(INBOX, headers=auth).json()
    assert [(i["message"], i["state"]) for i in inbox["items"]] == [
        ("abierta", "read"),
        ("pendiente", "unread"),
    ]


def test_al_marcar_todas_el_contador_y_la_lista_lo_reflejan(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    many(db, account_of(db, member), 3)
    auth = headers(client, outbox, member)

    client.post(READ_ALL, headers=auth)

    assert client.get(UNREAD_COUNT, headers=auth).json() == {"unread_count": 0}
    inbox = client.get(INBOX, headers=auth).json()
    assert {i["state"] for i in inbox["items"]} == {"read"}


def test_lo_marcado_en_un_dispositivo_se_ve_en_otro(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    """Dos sesiones del mismo Socio: la segunda ve el estado en su próxima carga."""
    member = make_member(activated=True)
    notification = notify(
        db, account_of(db, member), created_at=at("2026-11-05T13:00:00Z")
    )
    phone = headers(client, outbox, member)
    laptop = headers(client, outbox, member)
    assert phone != laptop

    marked = read(client, phone, notification).json()

    assert client.get(UNREAD_COUNT, headers=laptop).json() == {"unread_count": 0}
    [item] = client.get(INBOX, headers=laptop).json()["items"]
    assert (item["state"], item["read_at"]) == ("read", marked["read_at"])


def test_una_notificacion_nueva_aparece_en_la_proxima_carga(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    """Sin tiempo real: lo generado con la pantalla abierta se ve al volver a pedir."""
    member = make_member(activated=True)
    user = account_of(db, member)
    auth = headers(client, outbox, member)
    assert client.get(UNREAD_COUNT, headers=auth).json() == {"unread_count": 0}

    notify(db, user, created_at=at("2026-11-05T13:00:00Z"), message="recién llegada")

    assert client.get(UNREAD_COUNT, headers=auth).json() == {"unread_count": 1}
    assert [i["message"] for i in client.get(INBOX, headers=auth).json()["items"]] == [
        "recién llegada"
    ]


# --- US2 escenario 7: una notificación ajena o inexistente -----------------------------------

NOT_FOUND = {
    "code": "NOTIFICATION_NOT_FOUND",
    "message": "No encontramos esa notificación.",
}


def test_marcar_una_notificacion_de_otro_socio_responde_como_inexistente(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    other = make_member(activated=True)
    theirs = notify(db, account_of(db, other), created_at=at("2026-11-05T13:00:00Z"))

    response = read(client, headers(client, outbox, member), theirs)

    assert (response.status_code, response.json()["detail"]) == (404, NOT_FOUND)
    db.refresh(theirs)
    assert (theirs.state, theirs.read_at) == (NotificationState.UNREAD, None)


def test_marcar_una_notificacion_inexistente_responde_404(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    gone = notify(db, account_of(db, member), created_at=at("2026-11-05T13:00:00Z"))
    missing_id = gone.id + 1_000_000

    response = client.post(
        f"{INBOX}/{missing_id}/read", headers=headers(client, outbox, member)
    )

    assert (response.status_code, response.json()["detail"]) == (404, NOT_FOUND)


def test_marcar_una_de_otro_club_responde_404_aunque_sea_de_la_misma_cuenta(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    foreign = notify(db, account_of(db, member), created_at=at("2026-11-05T13:00:00Z"))
    foreign.club_id = RIVER_ID
    db.commit()

    response = read(client, headers(client, outbox, member), foreign)

    assert (response.status_code, response.json()["detail"]) == (404, NOT_FOUND)
    db.refresh(foreign)
    assert foreign.state == NotificationState.UNREAD


def test_un_id_que_no_es_numero_responde_422(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)

    response = client.post(
        f"{INBOX}/no-es-un-id/read", headers=headers(client, outbox, member)
    )

    assert response.status_code == 422


@pytest.mark.parametrize("path", ["/1/read", "/read-all"])
def test_marcar_como_leida_es_solo_para_socios(
    client: TestClient, outbox: Outbox, make_admin: MakeAdmin, path: str
) -> None:
    anonymous = client.post(f"{INBOX}{path}")
    as_admin = client.post(
        f"{INBOX}{path}",
        headers=bearer(admin_token(client, outbox, make_admin(BOCA_ID))),
    )

    assert (anonymous.status_code, anonymous.json()["detail"]) == (
        401,
        "NOT_AUTHENTICATED",
    )
    assert (as_admin.status_code, as_admin.json()["detail"]) == (403, "FORBIDDEN")


# --- Catálogo: un tipo inactivo no aparece en ningún lado (notificaciones §2) ----------------


def test_el_catalogo_trae_los_siete_tipos_activos_desde_hu23b() -> None:
    assert [(t.key, t.active) for t in CATALOG] == [
        ("event_published", True),
        ("event_rescheduled", True),
        ("event_withdrawn", True),
        ("event_restored", True),
        ("wave_rescheduled", True),
        ("wave_opened", True),
        ("ranking_completed", True),
    ]
    assert ACTIVE_TYPES == (
        "event_published",
        "event_rescheduled",
        "event_withdrawn",
        "event_restored",
        "wave_rescheduled",
        "wave_opened",
        "ranking_completed",
    )


def test_el_catalogo_tiene_los_nombres_y_textos_del_spec() -> None:
    assert {t.key: (t.name, t.title) for t in CATALOG} == {
        "event_published": ("Nuevo evento publicado", "Nuevo evento publicado"),
        "event_rescheduled": ("Evento reprogramado", "Evento reprogramado"),
        "event_withdrawn": ("Evento cancelado", "Evento cancelado"),
        "event_restored": ("Evento restaurado", "Evento restaurado"),
        "wave_rescheduled": (
            "Turno de reserva reprogramado",
            "Tu turno de reserva cambió",
        ),
        "wave_opened": (
            "Turno de reserva habilitado",
            "Tu turno de reserva está habilitado",
        ),
        "ranking_completed": ("Ejecución del ranking", "Se actualizó el ranking"),
    }
    assert BY_KEY["wave_opened"].message.format(
        titulo="Fecha 12 vs. Rival", fecha="07/11/2026", hora="18:00"
    ) == (
        "Ya podés reservar para Fecha 12 vs. Rival. "
        "Tu acceso está habilitado hasta el 07/11/2026 a las 18:00."
    )
    assert BY_KEY["wave_rescheduled"].message.format(
        titulo="Fecha 12 vs. Rival", fecha="07/11/2026", hora="15:00"
    ) == (
        "Tu turno de reserva para Fecha 12 vs. Rival cambió: se habilita el 07/11/2026 "
        "a las 15:00."
    )


def inactive_and_active(
    db: Session, user: User, inactive_type: str
) -> tuple[Notification, Notification]:
    hidden = notify(db, user, created_at=at("2026-11-05T13:00:00Z"), type=inactive_type)
    shown = notify(db, user, created_at=at("2026-11-04T13:00:00Z"))
    return hidden, shown


def test_un_tipo_inactivo_no_aparece_en_la_bandeja_ni_en_sus_cuentas(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    make_member: MakeMember,
    inactive_type: str,
) -> None:
    member = make_member(activated=True)
    _, shown = inactive_and_active(db, account_of(db, member), inactive_type)

    body = client.get(INBOX, headers=headers(client, outbox, member)).json()

    assert [item["id"] for item in body["items"]] == [shown.id]
    assert (body["total"], body["unread_count"]) == (1, 1)


def test_un_tipo_inactivo_no_suma_al_contador(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    make_member: MakeMember,
    inactive_type: str,
) -> None:
    member = make_member(activated=True)
    inactive_and_active(db, account_of(db, member), inactive_type)

    response = client.get(UNREAD_COUNT, headers=headers(client, outbox, member))

    assert response.json() == {"unread_count": 1}


def test_una_notificacion_de_tipo_inactivo_no_se_encuentra_al_marcarla(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    make_member: MakeMember,
    inactive_type: str,
) -> None:
    member = make_member(activated=True)
    hidden, _ = inactive_and_active(db, account_of(db, member), inactive_type)

    response = read(client, headers(client, outbox, member), hidden)

    assert (response.status_code, response.json()["detail"]) == (404, NOT_FOUND)


def test_marcar_todas_no_cuenta_ni_toca_las_de_tipo_inactivo(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    make_member: MakeMember,
    inactive_type: str,
) -> None:
    member = make_member(activated=True)
    hidden, _ = inactive_and_active(db, account_of(db, member), inactive_type)

    response = client.post(READ_ALL, headers=headers(client, outbox, member))

    assert response.json() == {"marked": 1, "unread_count": 0}
    db.refresh(hidden)
    assert hidden.state == NotificationState.UNREAD
