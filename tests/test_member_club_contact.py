"""Contacto del club que ve el Socio en el manual de usuario."""

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import AdminAccountState, Role, User, utcnow
from app.models.domain import Club
from tests.conftest import MakeMember, Outbox, admin_token, bearer, member_token, unique

URL = "/member/club/contact"


@pytest.fixture
def club(db: Session) -> Club:
    club = Club(
        nombre="Club Atlético Prueba",
        codigo_identificador=f"T{unique()}",
        api_token=f"token-{unique()}",
    )
    db.add(club)
    db.commit()
    return club


def add_admin(
    db: Session,
    club_id: uuid.UUID,
    name: str,
    *,
    days_ago: int = 0,
    state: AdminAccountState = AdminAccountState.ACTIVE,
) -> User:
    user = User(
        name=name,
        email=f"{name.lower()}-{unique()}@mail.com",
        role=Role.ADMIN,
        club_id=club_id,
        admin_state=state,
        created_at=utcnow() - timedelta(days=days_ago),
    )
    db.add(user)
    db.commit()
    return user


def socio_headers(
    client: TestClient, outbox: Outbox, make_member: MakeMember, club_id: uuid.UUID
) -> dict[str, str]:
    headers = bearer(
        member_token(client, outbox, make_member(activated=True, club_id=club_id))
    )
    outbox.clear()
    return headers


def test_devuelve_el_admin_activo_mas_antiguo_del_club_del_socio(
    client: TestClient, outbox: Outbox, make_member: MakeMember, db: Session, club: Club
) -> None:
    otro_club = Club(
        nombre="Otro", codigo_identificador=f"O{unique()}", api_token=f"t-{unique()}"
    )
    db.add(otro_club)
    db.commit()
    add_admin(db, otro_club.id, "Ajeno", days_ago=30)
    add_admin(
        db,
        club.id,
        "Pendiente",
        days_ago=20,
        state=AdminAccountState.PENDING_ACTIVATION,
    )
    primero = add_admin(db, club.id, "Primero", days_ago=10)
    add_admin(db, club.id, "Segundo", days_ago=1)

    response = client.get(
        URL, headers=socio_headers(client, outbox, make_member, club.id)
    )

    assert response.status_code == 200
    assert response.json() == {
        "club": "Club Atlético Prueba",
        "admin": {"name": "Primero", "email": primero.email},
    }


def test_sin_admins_activos_devuelve_el_club_sin_contacto(
    client: TestClient, outbox: Outbox, make_member: MakeMember, club: Club
) -> None:
    response = client.get(
        URL, headers=socio_headers(client, outbox, make_member, club.id)
    )

    assert response.status_code == 200
    assert response.json() == {"club": "Club Atlético Prueba", "admin": None}


def test_un_admin_no_puede_consultarlo(
    client: TestClient, outbox: Outbox, db: Session, club: Club
) -> None:
    headers = bearer(admin_token(client, outbox, add_admin(db, club.id, "Admin")))

    assert client.get(URL, headers=headers).status_code == 403


def test_sin_sesion_es_401(client: TestClient) -> None:
    assert client.get(URL).status_code == 401
