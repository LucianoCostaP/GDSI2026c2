"""Crea el primer admin (tarea de arranque, cross-cutting sección 7): `uv run python -m app.bootstrap`.

Usa INITIAL_ADMIN_EMAIL e INITIAL_ADMIN_NAME. Solo actúa si todavía no hay ningún admin, así que
se puede correr en cada arranque. La cuenta queda activa: entra por la puerta de admin con código.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import record
from .config import settings
from .db import SessionLocal
from .models import AdminAccountState, Role, User


def create_initial_admin(db: Session, email: str, name: str) -> User | None:
    if db.scalar(select(User.id).where(User.role == Role.ADMIN).limit(1)) is not None:
        return None
    admin = User(
        name=name,
        email=email.strip().lower(),
        role=Role.ADMIN,
        admin_state=AdminAccountState.ACTIVE,
    )
    db.add(admin)
    db.flush()
    record(
        db,
        "admin_account.seeded",
        actor_id=None,
        entity="user",
        entity_id=admin.id,
        email=admin.email,
        name=admin.name,
    )
    db.commit()
    return admin


def main() -> None:
    email, name = settings.initial_admin_email, settings.initial_admin_name
    if not email or not name:
        print(
            "Sin INITIAL_ADMIN_EMAIL e INITIAL_ADMIN_NAME: no se crea el primer admin"
        )
        return
    with SessionLocal() as db:
        admin = create_initial_admin(db, email, name)
    print(f"Primer admin creado: {admin.email}" if admin else "Ya hay un admin")


if __name__ == "__main__":
    main()
