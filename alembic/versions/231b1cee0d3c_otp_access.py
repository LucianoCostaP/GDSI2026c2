"""otp access

Acceso por código (HU-01, HU-05, HU-06) en lugar de contraseña, y cuentas de admin
pendientes de activación (HU-07, HU-08).

Revision ID: 231b1cee0d3c
Revises: 63fa065d1c57
Create Date: 2026-10-17 12:06:38.224382

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "231b1cee0d3c"
down_revision: str | Sequence[str] | None = "63fa065d1c57"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUMS = {
    "fee_status": ("up_to_date", "overdue"),
    "member_account_state": ("not_activated", "activated"),
    "admin_account_state": ("pending_activation", "active"),
    "code_purpose": ("login", "activation"),
}


def enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind)

    # members: DNI, estado de cuotas y estado de la cuenta.
    op.add_column("members", sa.Column("dni", sa.String(16), nullable=True))
    # Valor provisorio para las filas de prueba existentes; `app.seed` carga el DNI real.
    op.execute("UPDATE members SET dni = member_id WHERE dni IS NULL")
    op.alter_column("members", "dni", nullable=False)
    op.create_unique_constraint("members_dni_key", "members", ["dni"])
    op.add_column(
        "members",
        sa.Column(
            "fee_status",
            enum("fee_status"),
            nullable=False,
            server_default="up_to_date",
        ),
    )
    op.add_column(
        "members",
        sa.Column(
            "account_state",
            enum("member_account_state"),
            nullable=False,
            server_default="not_activated",
        ),
    )
    op.execute(
        "UPDATE members SET account_state = 'activated' WHERE member_id IN "
        "(SELECT member_id FROM users WHERE member_id IS NOT NULL)"
    )
    op.alter_column("members", "fee_status", server_default=None)
    op.alter_column("members", "account_state", server_default=None)
    op.alter_column("members", "email", existing_type=sa.String(320), nullable=True)
    op.create_index("ix_members_email", "members", ["email"])

    # users: sin contraseña; el email es único solo entre admins.
    op.drop_column("users", "password_hash")
    op.add_column(
        "users",
        sa.Column(
            "admin_state",
            enum("admin_account_state"),
            nullable=False,
            server_default="active",
        ),
    )
    op.alter_column("users", "admin_state", server_default=None)
    op.drop_constraint("users_email_key", "users", type_="unique")
    op.create_index(
        "uq_users_admin_email",
        "users",
        [sa.text("lower(email)")],
        unique=True,
        postgresql_where=sa.text("role = 'admin'"),
    )

    # admin_invitations: apunta a la cuenta pendiente en lugar de a un email.
    op.add_column("admin_invitations", sa.Column("user_id", sa.Integer()))
    op.execute(
        "UPDATE admin_invitations AS i SET user_id = u.id FROM users AS u "
        "WHERE u.role = 'admin' AND lower(u.email) = i.email"
    )
    # Invitaciones sin aceptar del modelo anterior: no tienen cuenta a la que apuntar.
    op.execute("DELETE FROM admin_invitations WHERE user_id IS NULL")
    op.alter_column("admin_invitations", "user_id", nullable=False)
    op.create_foreign_key(
        "admin_invitations_user_id_fkey",
        "admin_invitations",
        "users",
        ["user_id"],
        ["id"],
    )
    op.create_index("ix_admin_invitations_user_id", "admin_invitations", ["user_id"])
    op.drop_index("ix_admin_invitations_email", table_name="admin_invitations")
    op.drop_column("admin_invitations", "email")

    op.create_table(
        "access_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("purpose", enum("code_purpose"), nullable=False),
        sa.Column("member_id", sa.String(32), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("challenge_hash", sa.String(64), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exhausted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["member_id"], ["members.member_id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("challenge_hash"),
    )
    op.create_index("ix_access_codes_member_id", "access_codes", ["member_id"])
    op.create_index("ix_access_codes_user_id", "access_codes", ["user_id"])

    op.drop_index("ix_password_resets_user_id", table_name="password_resets")
    op.drop_table("password_resets")
    op.drop_index("ix_activation_tokens_member_id", table_name="activation_tokens")
    op.drop_table("activation_tokens")


def downgrade() -> None:
    """Vuelve al esquema con contraseñas. Las contraseñas no se pueden recuperar:
    las cuentas quedan con una contraseña vacía que no coincide con ninguna."""
    op.create_table(
        "activation_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.String(32), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["member_id"], ["members.member_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_activation_tokens_member_id", "activation_tokens", ["member_id"]
    )
    op.create_table(
        "password_resets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_password_resets_user_id", "password_resets", ["user_id"])

    op.drop_index("ix_access_codes_user_id", table_name="access_codes")
    op.drop_index("ix_access_codes_member_id", table_name="access_codes")
    op.drop_table("access_codes")

    op.add_column("admin_invitations", sa.Column("email", sa.String(320)))
    op.execute(
        "UPDATE admin_invitations AS i SET email = lower(u.email) FROM users AS u "
        "WHERE u.id = i.user_id"
    )
    op.alter_column("admin_invitations", "email", nullable=False)
    op.create_index("ix_admin_invitations_email", "admin_invitations", ["email"])
    op.drop_index("ix_admin_invitations_user_id", table_name="admin_invitations")
    op.drop_constraint(
        "admin_invitations_user_id_fkey", "admin_invitations", type_="foreignkey"
    )
    op.drop_column("admin_invitations", "user_id")

    # Las cuentas de admin pendientes no existían en el modelo anterior.
    op.execute(
        "DELETE FROM sessions WHERE user_id IN "
        "(SELECT id FROM users WHERE admin_state = 'pending_activation')"
    )
    op.execute("DELETE FROM users WHERE admin_state = 'pending_activation'")
    op.drop_index("uq_users_admin_email", table_name="users")
    op.create_unique_constraint("users_email_key", "users", ["email"])
    op.drop_column("users", "admin_state")
    op.add_column(
        "users",
        sa.Column("password_hash", sa.String(255), nullable=False, server_default=""),
    )
    op.alter_column("users", "password_hash", server_default=None)

    op.drop_index("ix_members_email", table_name="members")
    op.execute("UPDATE members SET email = '' WHERE email IS NULL")
    op.alter_column("members", "email", existing_type=sa.String(320), nullable=False)
    op.drop_column("members", "account_state")
    op.drop_column("members", "fee_status")
    op.drop_constraint("members_dni_key", "members", type_="unique")
    op.drop_column("members", "dni")

    bind = op.get_bind()
    for name in ENUMS:
        postgresql.ENUM(name=name).drop(bind)
