from typing import Any

from sqlalchemy.orm import Session

from .models import AuditLog


def record(
    db: Session,
    action: str,
    *,
    actor_id: int | None,
    entity: str,
    entity_id: str | int,
    **details: Any,
) -> None:
    """Agrega una entrada de auditoría a la transacción en curso: se guarda con el cambio."""
    db.add(
        AuditLog(
            action=action,
            actor_user_id=actor_id,
            entity=entity,
            entity_id=str(entity_id),
            details=details,
        )
    )
