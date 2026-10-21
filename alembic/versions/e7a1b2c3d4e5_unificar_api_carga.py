"""unificar api carga

Revision ID: e7a1b2c3d4e5
Revises: de589cd5f0eb
Create Date: 2026-10-21 00:10:00.000000

"""

from collections.abc import Sequence
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7a1b2c3d4e5"
down_revision: str | Sequence[str] | None = "de589cd5f0eb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Habilitar extensión pgcrypto para gen_random_uuid()
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')

    # 2. Tipos ENUM de negocio
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE tipo_evento AS ENUM ('Partido', 'Institucional', 'Historico');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # 3. Tabla clubes
    op.execute("""
        CREATE TABLE IF NOT EXISTS clubes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            nombre VARCHAR(150) NOT NULL,
            codigo_identificador VARCHAR(20) NOT NULL UNIQUE,
            api_token VARCHAR(100) NOT NULL UNIQUE,
            activo BOOLEAN NOT NULL DEFAULT TRUE,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            actualizado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 4. Tablas del ciclo de vida de Eventos (HU-21 / HU-22)
    op.execute("""
        CREATE TABLE IF NOT EXISTS eventos_pendientes_verificacion (
            id_interno VARCHAR(64) PRIMARY KEY,
            club_id UUID NOT NULL REFERENCES clubes(id) ON DELETE CASCADE,
            id_externo VARCHAR(100) NOT NULL,
            titulo VARCHAR(200) NOT NULL,
            fecha_hora TIMESTAMPTZ NOT NULL,
            lugar VARCHAR(200) NOT NULL,
            tipo tipo_evento NOT NULL,
            descripcion TEXT,
            es_historico BOOLEAN NOT NULL DEFAULT FALSE,
            estado VARCHAR(50) NOT NULL DEFAULT 'pendiente_definicion_importancia',
            creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            actualizado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_eventos_pendientes_club_externo UNIQUE (club_id, id_externo)
        );

        CREATE TABLE IF NOT EXISTS eventos_visibles (
            id_interno VARCHAR(64) PRIMARY KEY,
            club_id UUID NOT NULL REFERENCES clubes(id) ON DELETE CASCADE,
            id_externo VARCHAR(100) NOT NULL,
            titulo VARCHAR(200) NOT NULL,
            fecha_hora TIMESTAMPTZ NOT NULL,
            lugar VARCHAR(200) NOT NULL,
            tipo tipo_evento NOT NULL,
            descripcion TEXT,
            clase VARCHAR(1) CHECK (clase IN ('A', 'B', 'C')),
            puntos INTEGER CHECK (puntos >= 0),
            publicado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            actualizado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_eventos_visibles_club_externo UNIQUE (club_id, id_externo)
        );

        CREATE TABLE IF NOT EXISTS eventos_cambios_pendientes (
            id_cambio UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            id_interno VARCHAR(64) NOT NULL,
            club_id UUID NOT NULL REFERENCES clubes(id) ON DELETE CASCADE,
            titulo VARCHAR(200),
            fecha_hora TIMESTAMPTZ,
            lugar VARCHAR(200),
            descripcion TEXT,
            estado_revision VARCHAR(50) NOT NULL DEFAULT 'pendiente_revision',
            solicitado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 5. Tabla de Socios del Club (Padrón oficial sincronizado por HU-43)
    op.execute("""
        CREATE TABLE IF NOT EXISTS socios (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            club_id UUID NOT NULL REFERENCES clubes(id) ON DELETE CASCADE,
            id_externo VARCHAR(100) NOT NULL,
            dni VARCHAR(50) NOT NULL,
            numero_socio VARCHAR(50) NOT NULL,
            nombre VARCHAR(255) NOT NULL,
            fecha_nacimiento DATE NOT NULL,
            fecha_alta DATE NOT NULL,
            fecha_baja_previa DATE,
            estado_cuota VARCHAR(20) NOT NULL CHECK (estado_cuota IN ('al_dia', 'moroso')),
            email VARCHAR(255) NOT NULL,
            distancia_km NUMERIC(10, 2) NOT NULL CHECK (distancia_km >= 0),
            localidad VARCHAR(255),
            activo BOOLEAN NOT NULL DEFAULT TRUE,
            fecha_modificacion TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            actualizado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_socios_club_id_externo UNIQUE (club_id, id_externo),
            CONSTRAINT uq_socios_club_dni UNIQUE (club_id, dni),
            CONSTRAINT uq_socios_club_numero_socio UNIQUE (club_id, numero_socio)
        );
    """)

    # 6. Tablas de Ingesta, Auditoría y Staging de Socios (HU-43)
    op.execute("""
        CREATE TABLE IF NOT EXISTS socios_cargas (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            club_id UUID NOT NULL REFERENCES clubes(id) ON DELETE CASCADE,
            carga_id VARCHAR(100) NOT NULL,
            tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('completa', 'incremental')),
            estado VARCHAR(20) NOT NULL DEFAULT 'recibiendo' CHECK (estado IN ('recibiendo', 'procesando', 'completada', 'error')),
            total_paginas INTEGER,
            paginas_recibidas INTEGER NOT NULL DEFAULT 0,
            desde TIMESTAMPTZ,
            hasta TIMESTAMPTZ,
            total_registros INTEGER NOT NULL DEFAULT 0,
            creados INTEGER NOT NULL DEFAULT 0,
            actualizados INTEGER NOT NULL DEFAULT 0,
            desactivados INTEGER NOT NULL DEFAULT 0,
            rechazados INTEGER NOT NULL DEFAULT 0,
            iniciado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completado_en TIMESTAMPTZ,
            error_mensaje TEXT,
            CONSTRAINT uq_socios_cargas_club_carga_id UNIQUE (club_id, carga_id)
        );

        CREATE TABLE IF NOT EXISTS socios_cargas_paginas (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            carga_id_uuid UUID NOT NULL REFERENCES socios_cargas(id) ON DELETE CASCADE,
            numero_pagina INTEGER NOT NULL,
            recibido_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_socios_cargas_paginas_pagina UNIQUE (carga_id_uuid, numero_pagina)
        );

        CREATE TABLE IF NOT EXISTS socios_staging_completa (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            carga_id_uuid UUID NOT NULL REFERENCES socios_cargas(id) ON DELETE CASCADE,
            payload JSONB NOT NULL,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS socios_cargas_rechazos (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            carga_id_uuid UUID NOT NULL REFERENCES socios_cargas(id) ON DELETE CASCADE,
            id_externo VARCHAR(100),
            field VARCHAR(100),
            codigo VARCHAR(100),
            motivo TEXT NOT NULL,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 7. Vistas Multi-Tenant
    op.execute("""
        DROP VIEW IF EXISTS vw_eventos_club_consulta CASCADE;
        DROP VIEW IF EXISTS vw_eventos_cambios_pendientes CASCADE;
        DROP VIEW IF EXISTS vw_eventos_visibles CASCADE;
        DROP VIEW IF EXISTS vw_eventos_pendientes_verificacion CASCADE;
        DROP VIEW IF EXISTS vw_socios_cargas_rechazos CASCADE;
        DROP VIEW IF EXISTS vw_socios_cargas CASCADE;
        DROP VIEW IF EXISTS vw_socios CASCADE;

        CREATE OR REPLACE VIEW vw_eventos_pendientes_verificacion AS
        SELECT 
            id_interno, club_id, id_externo, titulo, fecha_hora, lugar, tipo,
            descripcion, es_historico, estado, creado_en, actualizado_en
        FROM eventos_pendientes_verificacion
        WHERE club_id = NULLIF(current_setting('app.current_club_id', true), '')::UUID
        WITH CHECK OPTION;

        CREATE OR REPLACE VIEW vw_eventos_visibles AS
        SELECT 
            id_interno, club_id, id_externo, titulo, fecha_hora, lugar, tipo,
            descripcion, clase, puntos, publicado_en, actualizado_en
        FROM eventos_visibles
        WHERE club_id = NULLIF(current_setting('app.current_club_id', true), '')::UUID
        WITH CHECK OPTION;

        CREATE OR REPLACE VIEW vw_eventos_cambios_pendientes AS
        SELECT 
            id_cambio, id_interno, club_id, titulo, fecha_hora, lugar, descripcion,
            estado_revision, solicitado_en
        FROM eventos_cambios_pendientes
        WHERE club_id = NULLIF(current_setting('app.current_club_id', true), '')::UUID
        WITH CHECK OPTION;

        CREATE OR REPLACE VIEW vw_eventos_club_consulta AS
        SELECT 
            id_interno,
            id_externo,
            club_id,
            titulo,
            fecha_hora,
            lugar,
            tipo,
            descripcion,
            estado::VARCHAR(50) AS estado_ciclo,
            NULL::VARCHAR(1) AS clase,
            NULL::INTEGER AS puntos,
            creado_en,
            actualizado_en
        FROM eventos_pendientes_verificacion
        WHERE club_id = NULLIF(current_setting('app.current_club_id', true), '')::UUID
        UNION ALL
        SELECT 
            id_interno,
            id_externo,
            club_id,
            titulo,
            fecha_hora,
            lugar,
            tipo,
            descripcion,
            'visible'::VARCHAR(50) AS estado_ciclo,
            clase,
            puntos,
            publicado_en AS creado_en,
            actualizado_en
        FROM eventos_visibles
        WHERE club_id = NULLIF(current_setting('app.current_club_id', true), '')::UUID;

        CREATE OR REPLACE VIEW vw_socios AS
        SELECT 
            id, club_id, id_externo, dni, numero_socio, nombre, fecha_nacimiento,
            fecha_alta, fecha_baja_previa, estado_cuota, email, distancia_km,
            localidad, activo, fecha_modificacion, creado_en, actualizado_en
        FROM socios
        WHERE club_id = NULLIF(current_setting('app.current_club_id', true), '')::UUID
        WITH CHECK OPTION;

        CREATE OR REPLACE VIEW vw_socios_cargas AS
        SELECT 
            id, club_id, carga_id, tipo, estado, total_paginas, paginas_recibidas,
            desde, hasta, total_registros, creados, actualizados, desactivados,
            rechazados, iniciado_en, completado_en, error_mensaje
        FROM socios_cargas
        WHERE club_id = NULLIF(current_setting('app.current_club_id', true), '')::UUID
        WITH CHECK OPTION;

        CREATE OR REPLACE VIEW vw_socios_cargas_rechazos AS
        SELECT 
            r.id, c.club_id, r.carga_id_uuid, c.carga_id, r.id_externo,
            r.field, r.codigo, r.motivo, r.creado_en
        FROM socios_cargas_rechazos r
        JOIN socios_cargas c ON r.carga_id_uuid = c.id
        WHERE c.club_id = NULLIF(current_setting('app.current_club_id', true), '')::UUID;
    """)

    # 8. Funciones y Triggers
    op.execute("""
        CREATE OR REPLACE FUNCTION trg_insert_vw_eventos_pendientes()
        RETURNS TRIGGER AS $$
        DECLARE
            v_club_id UUID;
            v_id_gen VARCHAR(64);
        BEGIN
            v_club_id := NULLIF(current_setting('app.current_club_id', true), '')::UUID;
            IF v_club_id IS NULL THEN
                RAISE EXCEPTION 'Acceso denegado: app.current_club_id no está definido en el contexto de sesión.'
                    USING ERRCODE = '28000';
            END IF;

            v_id_gen := COALESCE(NEW.id_interno, 'EVT-INT-' || UPPER(SUBSTRING(gen_random_uuid()::TEXT, 1, 8)));

            INSERT INTO eventos_pendientes_verificacion (
                id_interno, club_id, id_externo, titulo, fecha_hora, lugar, tipo,
                descripcion, es_historico, estado, creado_en, actualizado_en
            ) VALUES (
                v_id_gen, v_club_id, NEW.id_externo, NEW.titulo, NEW.fecha_hora, NEW.lugar, NEW.tipo,
                NEW.descripcion, COALESCE(NEW.es_historico, FALSE),
                COALESCE(NEW.estado, 'pendiente_definicion_importancia'),
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            RETURNING id_interno, club_id, id_externo, titulo, fecha_hora, lugar, tipo, descripcion, es_historico, estado, creado_en, actualizado_en
            INTO NEW;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_vw_eventos_pendientes_insert ON vw_eventos_pendientes_verificacion;
        CREATE TRIGGER trg_vw_eventos_pendientes_insert
        INSTEAD OF INSERT ON vw_eventos_pendientes_verificacion
        FOR EACH ROW EXECUTE FUNCTION trg_insert_vw_eventos_pendientes();

        CREATE OR REPLACE FUNCTION trg_update_vw_eventos_pendientes()
        RETURNS TRIGGER AS $$
        DECLARE
            v_club_id UUID;
        BEGIN
            v_club_id := NULLIF(current_setting('app.current_club_id', true), '')::UUID;
            IF v_club_id IS NULL THEN
                RAISE EXCEPTION 'Acceso denegado: app.current_club_id no está definido en el contexto de sesión.'
                    USING ERRCODE = '28000';
            END IF;

            UPDATE eventos_pendientes_verificacion
            SET titulo = COALESCE(NEW.titulo, titulo),
                fecha_hora = COALESCE(NEW.fecha_hora, fecha_hora),
                lugar = COALESCE(NEW.lugar, lugar),
                descripcion = COALESCE(NEW.descripcion, descripcion),
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id_interno = OLD.id_interno
              AND club_id = v_club_id;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_vw_eventos_pendientes_update ON vw_eventos_pendientes_verificacion;
        CREATE TRIGGER trg_vw_eventos_pendientes_update
        INSTEAD OF UPDATE ON vw_eventos_pendientes_verificacion
        FOR EACH ROW EXECUTE FUNCTION trg_update_vw_eventos_pendientes();

        CREATE OR REPLACE FUNCTION trg_insert_vw_eventos_cambios()
        RETURNS TRIGGER AS $$
        DECLARE
            v_club_id UUID;
        BEGIN
            v_club_id := NULLIF(current_setting('app.current_club_id', true), '')::UUID;
            IF v_club_id IS NULL THEN
                RAISE EXCEPTION 'Acceso denegado: app.current_club_id no está definido en el contexto de sesión.'
                    USING ERRCODE = '28000';
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM eventos_visibles 
                WHERE id_interno = NEW.id_interno AND club_id = v_club_id
            ) THEN
                RAISE EXCEPTION 'Acceso denegado o evento inexistente: el evento % no pertenece al club.', NEW.id_interno
                    USING ERRCODE = 'P0002';
            END IF;

            INSERT INTO eventos_cambios_pendientes (
                id_cambio, id_interno, club_id, titulo, fecha_hora, lugar, descripcion,
                estado_revision, solicitado_en
            ) VALUES (
                COALESCE(NEW.id_cambio, gen_random_uuid()),
                NEW.id_interno, v_club_id, NEW.titulo, NEW.fecha_hora, NEW.lugar,
                NEW.descripcion, COALESCE(NEW.estado_revision, 'pendiente_revision'),
                CURRENT_TIMESTAMP
            )
            RETURNING id_cambio, id_interno, club_id, titulo, fecha_hora, lugar, descripcion, estado_revision, solicitado_en
            INTO NEW;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_vw_eventos_cambios_insert ON vw_eventos_cambios_pendientes;
        CREATE TRIGGER trg_vw_eventos_cambios_insert
        INSTEAD OF INSERT ON vw_eventos_cambios_pendientes
        FOR EACH ROW EXECUTE FUNCTION trg_insert_vw_eventos_cambios();

        CREATE OR REPLACE FUNCTION trg_socios_update_timestamp()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.actualizado_en = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_socios_actualizado_en ON socios;
        CREATE TRIGGER trg_socios_actualizado_en
        BEFORE UPDATE ON socios
        FOR EACH ROW EXECUTE FUNCTION trg_socios_update_timestamp();
    """)

    # 9. Trigger de sincronización bidireccional entre socios y members
    # Cuando un socio es cargado o actualizado por el club, impacta automáticamente en members.
    op.execute("""
        CREATE OR REPLACE FUNCTION trg_sync_socio_to_member()
        RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO members (member_id, dni, email, name, fee_status, account_state)
            VALUES (
                NEW.id_externo,
                NEW.dni,
                NEW.email,
                NEW.nombre,
                CASE WHEN NEW.estado_cuota = 'al_dia' THEN 'up_to_date'::fee_status ELSE 'overdue'::fee_status END,
                'not_activated'::member_account_state
            )
            ON CONFLICT (member_id) DO UPDATE SET
                dni = EXCLUDED.dni,
                email = EXCLUDED.email,
                name = EXCLUDED.name,
                fee_status = EXCLUDED.fee_status;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_socios_sync_members ON socios;
        CREATE TRIGGER trg_socios_sync_members
        AFTER INSERT OR UPDATE ON socios
        FOR EACH ROW EXECUTE FUNCTION trg_sync_socio_to_member();
    """)

    # 10. Datos semilla de Clubes
    op.execute("""
        INSERT INTO clubes (id, nombre, codigo_identificador, api_token, activo)
        VALUES 
            ('11111111-1111-1111-1111-111111111111', 'Club Atlético Boca Juniors', 'CABJ', 'token_boca_abc123', true),
            ('22222222-2222-2222-2222-222222222222', 'Club Atlético River Plate', 'CARP', 'token_river_def456', true),
            ('33333333-3333-3333-3333-333333333333', 'Racing Club de Avellaneda', 'RC', 'token_racing_ghi789', true)
        ON CONFLICT (id) DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_socios_sync_members ON socios;")
    op.execute("DROP FUNCTION IF EXISTS trg_sync_socio_to_member;")
    op.execute("DROP TRIGGER IF EXISTS trg_socios_actualizado_en ON socios;")
    op.execute("DROP FUNCTION IF EXISTS trg_socios_update_timestamp;")
    op.execute("DROP TRIGGER IF EXISTS trg_vw_eventos_cambios_insert ON vw_eventos_cambios_pendientes;")
    op.execute("DROP FUNCTION IF EXISTS trg_insert_vw_eventos_cambios;")
    op.execute("DROP TRIGGER IF EXISTS trg_vw_eventos_pendientes_update ON vw_eventos_pendientes_verificacion;")
    op.execute("DROP FUNCTION IF EXISTS trg_update_vw_eventos_pendientes;")
    op.execute("DROP TRIGGER IF EXISTS trg_vw_eventos_pendientes_insert ON vw_eventos_pendientes_verificacion;")
    op.execute("DROP FUNCTION IF EXISTS trg_insert_vw_eventos_pendientes;")

    op.execute("DROP VIEW IF EXISTS vw_socios_cargas_rechazos;")
    op.execute("DROP VIEW IF EXISTS vw_socios_cargas;")
    op.execute("DROP VIEW IF EXISTS vw_socios;")
    op.execute("DROP VIEW IF EXISTS vw_eventos_club_consulta;")
    op.execute("DROP VIEW IF EXISTS vw_eventos_cambios_pendientes;")
    op.execute("DROP VIEW IF EXISTS vw_eventos_visibles;")
    op.execute("DROP VIEW IF EXISTS vw_eventos_pendientes_verificacion;")

    op.execute("DROP TABLE IF EXISTS socios_cargas_rechazos;")
    op.execute("DROP TABLE IF EXISTS socios_staging_completa;")
    op.execute("DROP TABLE IF EXISTS socios_cargas_paginas;")
    op.execute("DROP TABLE IF EXISTS socios_cargas;")
    op.execute("DROP TABLE IF EXISTS socios;")
    op.execute("DROP TABLE IF EXISTS eventos_cambios_pendientes;")
    op.execute("DROP TABLE IF EXISTS eventos_visibles;")
    op.execute("DROP TABLE IF EXISTS eventos_pendientes_verificacion;")
    op.execute("DROP TABLE IF EXISTS clubes;")
    op.execute("DROP TYPE IF EXISTS tipo_evento;")
