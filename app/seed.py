"""Carga socios de prueba en la tabla members: `uv run python -m app.seed`.

Actualiza los datos del club de los socios que ya existen, sin tocar el estado de su cuenta.
"""

from sqlalchemy.dialects.postgresql import insert

from .config import settings
from .db import SessionLocal
from .models import FeeStatus, Member

MEMBERS = [
    {
        "member_id": "123456",
        "dni": "30111222",
        "email": "socio1@example.com",
        "name": "Lionel Messi",
        "fee_status": FeeStatus.UP_TO_DATE,
    },
    {
        "member_id": "234567",
        "dni": "30222333",
        "email": "socio2@example.com",
        "name": "Diego Maradona",
        "fee_status": FeeStatus.UP_TO_DATE,
    },
    {
        "member_id": "345678",
        "dni": "30333444",
        "email": "socio3@example.com",
        "name": "Juan Román Riquelme",
        "fee_status": FeeStatus.UP_TO_DATE,
    },
    # Casos de HU-01: cuotas en mora y sin email registrado.
    {
        "member_id": "456789",
        "dni": "30444555",
        "email": "socio4@example.com",
        "name": "Martín Palermo",
        "fee_status": FeeStatus.OVERDUE,
    },
    {
        "member_id": "567890",
        "dni": "30555666",
        "email": None,
        "name": "Carlos Tevez",
        "fee_status": FeeStatus.UP_TO_DATE,
    },
]


def main() -> None:
    if settings.app_env == "production":
        raise SystemExit("El seed de socios de prueba no se corre en producción")
    with SessionLocal() as db:
        insert_members = insert(Member).values(MEMBERS)
        club_data = ("dni", "email", "name", "fee_status")
        db.execute(
            insert_members.on_conflict_do_update(
                index_elements=[Member.member_id],
                set_={column: insert_members.excluded[column] for column in club_data},
            )
        )
        db.commit()
    print(f"{len(MEMBERS)} socios de prueba cargados")


if __name__ == "__main__":
    main()
