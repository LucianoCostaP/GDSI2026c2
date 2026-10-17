from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.bootstrap import create_initial_admin
from app.models import AuditLog, Role, User


def remove_admins(db: Session) -> None:
    # La base de desarrollo puede tener admins: se pasan a otro rol dentro de la transacción del test.
    db.execute(update(User).where(User.role == Role.ADMIN).values(role=Role.MEMBER))


def test_creates_first_admin_when_there_is_none(db: Session) -> None:
    remove_admins(db)

    admin = create_initial_admin(db, " Primera@Example.com ", "Primera Admin")

    assert admin is not None
    assert (admin.email, admin.role, admin.admin_state) == (
        "primera@example.com",
        "admin",
        "active",
    )
    audit = db.scalars(
        select(AuditLog).where(AuditLog.entity_id == str(admin.id))
    ).one()
    assert (audit.action, audit.actor_user_id) == ("admin_account.seeded", None)


def test_does_nothing_when_an_admin_exists(db: Session, admin: User) -> None:
    assert create_initial_admin(db, "otra@example.com", "Otra") is None
    assert db.scalar(select(User).where(User.email == "otra@example.com")) is None
