"""HU-20: bandeja de notificaciones del Socio, por la API.

Hasta que existan los generadores de HU-19, las notificaciones se crean directo en la base, como
haría el contrato `notify` (notificaciones §4 y §10).
"""

from datetime import UTC, datetime
from itertools import count
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Member, Notification, User
from tests.conftest import BOCA_ID, MakeMember, Outbox, bearer, member_token

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
) -> Notification:
    notification = Notification(
        club_id=user.club_id or BOCA_ID,
        user_id=user.id,
        type=type,
        reference=reference or {"event_id": "evt-1"},
        title=title,
        message=message,
        created_at=created_at,
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
