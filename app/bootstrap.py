"""Crea el primer admin (tarea de arranque, cross-cutting sección 7): `uv run python -m app.bootstrap`.

Usa INITIAL_ADMIN_EMAIL, INITIAL_ADMIN_NAME e INITIAL_ADMIN_CLUB_CODE (el club al que pertenece).
Solo actúa si todavía no hay ningún admin, así que se puede correr en cada arranque. La cuenta
queda activa: entra por la puerta de admin con código.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import record
from .config import settings
from .db import SessionLocal
from .models import AdminAccountState, Club, Role, User


class InitialClubNotFoundError(Exception):
    """No hay un club al que asignar el primer admin."""


def resolve_initial_club(db: Session, club_code: str | None) -> Club:
    if club_code:
        club = db.scalar(select(Club).where(Club.codigo_identificador == club_code))
        if club is None:
            raise InitialClubNotFoundError(f"No existe el club con código {club_code}")
        return club
    clubs = db.scalars(select(Club).where(Club.activo.is_(True)).limit(2)).all()
    if len(clubs) != 1:
        raise InitialClubNotFoundError(
            "Hay que indicar INITIAL_ADMIN_CLUB_CODE: no hay exactamente un club activo"
        )
    return clubs[0]


def create_initial_admin(
    db: Session, email: str, name: str, club_code: str | None = None
) -> User | None:
    if db.scalar(select(User.id).where(User.role == Role.ADMIN).limit(1)) is not None:
        return None
    club = resolve_initial_club(db, club_code)
    admin = User(
        name=name,
        email=email.strip().lower(),
        role=Role.ADMIN,
        admin_state=AdminAccountState.ACTIVE,
        club_id=club.id,
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
        club_id=str(club.id),
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
        try:
            admin = create_initial_admin(
                db, email, name, settings.initial_admin_club_code
            )
        except InitialClubNotFoundError as error:
            raise SystemExit(f"No se crea el primer admin: {error}") from error
    print(f"Primer admin creado: {admin.email}" if admin else "Ya hay un admin")


if __name__ == "__main__":
    main()
