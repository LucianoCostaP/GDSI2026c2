"""users club_id: cada cuenta de admin pertenece a un club

Revision ID: c3d9a1f4b2e7
Revises: 7c0c6b83a6be
Create Date: 2026-10-26 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d9a1f4b2e7"
down_revision: str | Sequence[str] | None = "7c0c6b83a6be"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users", sa.Column("club_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key("fk_users_club_id", "users", "clubes", ["club_id"], ["id"])
    op.create_index(op.f("ix_users_club_id"), "users", ["club_id"], unique=False)
    # Los admins que ya existen quedan en el club más antiguo: hasta ahora el sistema
    # trataba "el club" como el primero de la tabla. Las cuentas de socio quedan sin club.
    op.execute(
        """
        UPDATE users
        SET club_id = (SELECT id FROM clubes ORDER BY creado_en, nombre LIMIT 1)
        WHERE role = 'admin' AND club_id IS NULL
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_users_club_id"), table_name="users")
    op.drop_constraint("fk_users_club_id", "users", type_="foreignkey")
    op.drop_column("users", "club_id")
