"""merge hu19-20 notifications and hu23

Revision ID: 03658fcda9ee
Revises: c4e8a1f0d2b7, c7e2a9b4d1f8
Create Date: 2026-11-17 22:32:55.450529

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "03658fcda9ee"
down_revision: str | Sequence[str] | None = ("c4e8a1f0d2b7", "c7e2a9b4d1f8")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge point: no schema changes."""


def downgrade() -> None:
    """Merge point: no schema changes."""
