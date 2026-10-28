import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.bootstrap import InitialClubNotFoundError, create_initial_admin
from app.models import AuditLog, Role, User
from tests.conftest import BOCA_ID


def remove_admins(db: Session) -> None:
    # La base de desarrollo puede tener admins: se pasan a otro rol dentro de la transacción del test.
    db.execute(update(User).where(User.role == Role.ADMIN).values(role=Role.MEMBER))


def test_creates_first_admin_when_there_is_none(db: Session) -> None:
    remove_admins(db)

    admin = create_initial_admin(db, " Primera@Example.com ", "Primera Admin", "CABJ")

    assert admin is not None
    assert (admin.email, admin.role, admin.admin_state, admin.club_id) == (
        "primera@example.com",
        "admin",
        "active",
        BOCA_ID,
    )
    audit = db.scalars(
        select(AuditLog).where(AuditLog.entity_id == str(admin.id))
    ).one()
    assert (audit.action, audit.actor_user_id) == ("admin_account.seeded", None)
    assert audit.details["club_id"] == str(BOCA_ID)


def test_does_nothing_when_an_admin_exists(db: Session, admin: User) -> None:
    assert create_initial_admin(db, "otra@example.com", "Otra", "CABJ") is None
    assert db.scalar(select(User).where(User.email == "otra@example.com")) is None


def test_unknown_club_code_creates_no_admin(db: Session) -> None:
    remove_admins(db)

    with pytest.raises(InitialClubNotFoundError):
        create_initial_admin(db, "primera@example.com", "Primera", "NOEXISTE")

    assert db.scalar(select(User).where(User.email == "primera@example.com")) is None


def test_without_club_code_it_needs_exactly_one_club(db: Session) -> None:
    # La migración siembra más de un club: sin código no se elige uno por el admin.
    remove_admins(db)

    with pytest.raises(InitialClubNotFoundError):
        create_initial_admin(db, "primera@example.com", "Primera", None)
