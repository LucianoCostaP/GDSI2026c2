"""merge heads

Revision ID: 14299b328d88
Revises: b3d9f1e6a2c7, f2c7a9d4e1b6
Create Date: 2026-11-09 01:08:02.964408

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "14299b328d88"
down_revision: str | Sequence[str] | None = ("b3d9f1e6a2c7", "f2c7a9d4e1b6")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
