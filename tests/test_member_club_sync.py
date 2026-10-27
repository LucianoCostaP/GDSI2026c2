"""El club que carga el padrón define el club del socio (decisión 34).

El trigger `trg_sync_socio_to_member` copia cada socio cargado a `members`: ahora también copia
el club, no mueve a un socio que ya tiene uno y completa la cuenta que se activó sin club.
Solo corre con PostgreSQL, donde existe el trigger.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Member, User
from app.models.domain import Socio
from tests.conftest import BOCA_ID, RIVER_ID, MakeMember


@pytest.fixture(autouse=True)
def _requires_postgres(db: Session) -> None:
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("El trigger socios -> members solo existe en PostgreSQL")


def load_socio(db: Session, club_id: uuid.UUID, *, dni: str, external_id: str) -> None:
    """Carga un socio como lo hace el club; el trigger actualiza `members`."""
    db.add(
        Socio(
            club_id=club_id,
            id_externo=external_id,
            dni=dni,
            numero_socio=external_id,
            nombre="Socio Cargado",
            fecha_nacimiento=date(1990, 1, 1),
            fecha_alta=date(2010, 1, 1),
            estado_cuota="al_dia",
            email=f"{external_id}@example.com",
            distancia_km=Decimal("5.00"),
        )
    )
    db.flush()


def test_a_new_socio_is_created_in_the_club_that_loaded_it(db: Session) -> None:
    load_socio(db, RIVER_ID, dni="40111222", external_id="RIV-1")

    member = db.get_one(Member, "RIV-1")
    assert member.club_id == RIVER_ID


def test_a_member_without_club_gets_the_club_that_loads_it_and_its_account_too(
    db: Session, make_member: MakeMember
) -> None:
    member = make_member(activated=True, club_id=None)
    user = db.scalars(select(User).where(User.member_id == member.member_id)).one()
    assert (member.club_id, user.club_id) == (None, None)

    load_socio(db, RIVER_ID, dni=member.dni, external_id="RIV-2")

    db.refresh(member)
    db.refresh(user)
    assert (member.club_id, user.club_id) == (RIVER_ID, RIVER_ID)


def test_a_member_that_already_has_a_club_is_not_moved_by_another_club(
    db: Session, make_member: MakeMember
) -> None:
    member = make_member(activated=True, club_id=BOCA_ID)

    load_socio(db, RIVER_ID, dni=member.dni, external_id="RIV-3")

    db.refresh(member)
    assert member.club_id == BOCA_ID


def test_an_account_does_not_inherit_the_club_of_a_different_club(
    db: Session, make_member: MakeMember
) -> None:
    member = make_member(activated=True, club_id=BOCA_ID)
    user = db.scalars(select(User).where(User.member_id == member.member_id)).one()
    user.club_id = None
    db.flush()

    load_socio(db, RIVER_ID, dni=member.dni, external_id="RIV-4")

    db.refresh(user)
    assert user.club_id is None
