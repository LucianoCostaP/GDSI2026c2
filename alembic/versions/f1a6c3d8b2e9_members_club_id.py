"""members club_id: cada socio pertenece a un club y su cuenta lo hereda

Revision ID: f1a6c3d8b2e9
Revises: d5e2b7c9a1f3
Create Date: 2026-10-26 23:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a6c3d8b2e9"
down_revision: str | Sequence[str] | None = "d5e2b7c9a1f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "members", sa.Column("club_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_members_club_id", "members", "clubes", ["club_id"], ["id"]
    )
    op.create_index(op.f("ix_members_club_id"), "members", ["club_id"], unique=False)

    # Desde ahora, la carga del padrón por parte del club define el club del socio: el trigger
    # que copia `socios` a `members` también copia el club.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_sync_socio_to_member()
        RETURNS TRIGGER AS $$
        DECLARE
            v_existing_member_id VARCHAR(32);
        BEGIN
            -- Verificar si ya existe un miembro con ese DNI
            SELECT member_id INTO v_existing_member_id FROM members WHERE dni = NEW.dni LIMIT 1;

            IF v_existing_member_id IS NOT NULL THEN
                -- El club de un socio que ya lo tiene no se cambia: solo se completa si faltaba.
                UPDATE members SET
                    email = NEW.email,
                    name = NEW.nombre,
                    fee_status = CASE WHEN NEW.estado_cuota = 'al_dia' THEN 'up_to_date'::fee_status ELSE 'overdue'::fee_status END,
                    club_id = COALESCE(club_id, NEW.club_id)
                WHERE member_id = v_existing_member_id;
            ELSE
                -- Verificar si existe por member_id
                SELECT member_id INTO v_existing_member_id FROM members WHERE member_id = NEW.id_externo LIMIT 1;

                IF v_existing_member_id IS NOT NULL THEN
                    UPDATE members SET
                        dni = NEW.dni,
                        email = NEW.email,
                        name = NEW.nombre,
                        fee_status = CASE WHEN NEW.estado_cuota = 'al_dia' THEN 'up_to_date'::fee_status ELSE 'overdue'::fee_status END,
                        club_id = COALESCE(club_id, NEW.club_id)
                    WHERE member_id = v_existing_member_id;
                ELSE
                    -- Insertar nuevo socio en members, en el club que lo cargó
                    INSERT INTO members (member_id, dni, email, name, fee_status, account_state, club_id)
                    VALUES (
                        NEW.id_externo,
                        NEW.dni,
                        NEW.email,
                        NEW.nombre,
                        CASE WHEN NEW.estado_cuota = 'al_dia' THEN 'up_to_date'::fee_status ELSE 'overdue'::fee_status END,
                        'not_activated'::member_account_state,
                        NEW.club_id
                    );
                END IF;
            END IF;

            -- Una cuenta que se activó cuando el socio todavía no tenía club lo hereda ahora,
            -- siempre que el socio sea de este mismo club.
            UPDATE users SET club_id = NEW.club_id
            WHERE member_id = COALESCE(v_existing_member_id, NEW.id_externo)
              AND role = 'member'
              AND club_id IS NULL
              AND EXISTS (
                  SELECT 1 FROM members m
                  WHERE m.member_id = users.member_id AND m.club_id = NEW.club_id
              );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    # Relleno de los socios que ya existen: el club del padrón (`socios`) donde figuran por
    # identificador externo, número de socio o DNI. Solo se completa cuando hay exactamente un
    # club; si no figuran en ninguno o figuran en varios, queda sin club en vez de elegir uno
    # (el socio recibe `MEMBER_WITHOUT_CLUB` hasta que el club lo cargue o se corrija a mano).
    op.execute(
        """
        UPDATE members AS m
        SET club_id = matched.club_id
        FROM (
            SELECT m2.member_id AS member_id, (array_agg(DISTINCT s.club_id))[1] AS club_id
            FROM members AS m2
            JOIN socios AS s
              ON s.id_externo = m2.member_id
              OR s.numero_socio = m2.member_id
              OR s.dni = m2.dni
            GROUP BY m2.member_id
            HAVING count(DISTINCT s.club_id) = 1
        ) AS matched
        WHERE m.member_id = matched.member_id AND m.club_id IS NULL
        """
    )
    # Las cuentas de socio ya activadas heredan el club de su socio.
    op.execute(
        """
        UPDATE users AS u
        SET club_id = m.club_id
        FROM members AS m
        WHERE u.member_id = m.member_id
          AND u.role = 'member'
          AND u.club_id IS NULL
          AND m.club_id IS NOT NULL
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    # El trigger vuelve a su versión anterior, que no conoce el club del socio.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_sync_socio_to_member()
        RETURNS TRIGGER AS $$
        DECLARE
            v_existing_member_id VARCHAR(32);
        BEGIN
            -- Verificar si ya existe un miembro con ese DNI
            SELECT member_id INTO v_existing_member_id FROM members WHERE dni = NEW.dni LIMIT 1;
            
            IF v_existing_member_id IS NOT NULL THEN
                UPDATE members SET
                    email = NEW.email,
                    name = NEW.nombre,
                    fee_status = CASE WHEN NEW.estado_cuota = 'al_dia' THEN 'up_to_date'::fee_status ELSE 'overdue'::fee_status END
                WHERE member_id = v_existing_member_id;
            ELSE
                -- Verificar si existe por member_id
                SELECT member_id INTO v_existing_member_id FROM members WHERE member_id = NEW.id_externo LIMIT 1;
                
                IF v_existing_member_id IS NOT NULL THEN
                    UPDATE members SET
                        dni = NEW.dni,
                        email = NEW.email,
                        name = NEW.nombre,
                        fee_status = CASE WHEN NEW.estado_cuota = 'al_dia' THEN 'up_to_date'::fee_status ELSE 'overdue'::fee_status END
                    WHERE member_id = v_existing_member_id;
                ELSE
                    -- Insertar nuevo socio en members
                    INSERT INTO members (member_id, dni, email, name, fee_status, account_state)
                    VALUES (
                        NEW.id_externo,
                        NEW.dni,
                        NEW.email,
                        NEW.nombre,
                        CASE WHEN NEW.estado_cuota = 'al_dia' THEN 'up_to_date'::fee_status ELSE 'overdue'::fee_status END,
                        'not_activated'::member_account_state
                    );
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    # Las cuentas de socio vuelven a quedar sin club, como antes de esta migración.
    op.execute("UPDATE users SET club_id = NULL WHERE role = 'member'")
    op.drop_index(op.f("ix_members_club_id"), table_name="members")
    op.drop_constraint("fk_members_club_id", "members", type_="foreignkey")
    op.drop_column("members", "club_id")
