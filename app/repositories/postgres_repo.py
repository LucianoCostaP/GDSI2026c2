import uuid
from datetime import UTC, datetime
from typing import Any

from ..core.exceptions import EventoYaPublicadoError
from ..database import db_manager
from ..models.domain import ClubDomain
from ..schemas.eventos import EventoCreateRequest
from .base import EventoRepository


class PostgresEventoRepository(EventoRepository):
    """
    Repositorio PostgreSQL que delega la seguridad en las VIEWs y variables de sesión.
    """

    def get_club_by_token(self, api_token: str) -> ClubDomain | None:
        """Consulta el club a partir de su Bearer token."""
        query = """
            SELECT id, nombre, codigo_identificador, api_token, activo, creado_en
            FROM clubes
            WHERE api_token = %s AND activo = TRUE;
        """
        with db_manager.get_connection() as conn, conn.cursor() as cur:
            cur.execute(query, (api_token,))
            row = cur.fetchone()
            if not row:
                return None
            return ClubDomain(
                id=str(row["id"]),
                nombre=row["nombre"],
                codigo_identificador=row["codigo_identificador"],
                api_token=row["api_token"],
                activo=row["activo"],
                creado_en=row["creado_en"],
            )

    def exists_externo(self, club_id: str, id_externo: str) -> bool:
        """
        Verifica si el id_externo ya existe para el club consultando la vista unificada.
        """
        query = """
            SELECT 1 FROM vw_eventos_club_consulta
            WHERE id_externo = %s
            LIMIT 1;
        """
        with db_manager.get_tenant_session(club_id) as conn, conn.cursor() as cur:
            cur.execute(query, (id_externo,))
            return cur.fetchone() is not None

    def insert_pendiente(
        self,
        club_id: str,
        evento: EventoCreateRequest,
        estado: str = "pendiente_definicion_importancia",
        es_historico: bool = False,
    ) -> str:
        """
        Inserta a través de la VIEW vw_eventos_pendientes_verificacion.
        El trigger INSTEAD OF asigna el club_id a partir de la variable de sesión
        y genera el id_interno.
        """
        id_interno_propuesto = f"EVT-INT-{uuid.uuid4().hex[:12].upper()}"
        query = """
            INSERT INTO vw_eventos_pendientes_verificacion (
                id_interno, id_externo, titulo, fecha_hora, lugar, tipo, descripcion, es_historico, estado
            ) VALUES (
                %(id_interno)s, %(id_externo)s, %(titulo)s, %(fecha_hora)s, %(lugar)s, %(tipo)s, %(descripcion)s, %(es_historico)s, %(estado)s
            )
            RETURNING id_interno;
        """
        params = {
            "id_interno": id_interno_propuesto,
            "id_externo": evento.id_externo,
            "titulo": evento.titulo,
            "fecha_hora": evento.fecha_hora,
            "lugar": evento.lugar,
            "tipo": evento.tipo,
            "descripcion": evento.descripcion,
            "es_historico": es_historico or evento.es_historico or False,
            "estado": estado,
        }
        with db_manager.get_tenant_session(club_id) as conn, conn.cursor() as cur:
            cur.execute(query, params)
            res = cur.fetchone()
            if not res:
                raise RuntimeError("No se pudo obtener el id_interno del evento.")
            return str(res["id_interno"])

    def find_eventos(
        self,
        club_id: str,
        id_externo: str | None = None,
        id_interno: str | None = None,
        titulo: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Consulta la vista consolidada vw_eventos_club_consulta.
        PostgreSQL filtra internamente por club_id según app.current_club_id.
        """
        condiciones = ["1=1"]
        params: list[Any] = []

        if id_externo:
            condiciones.append("id_externo = %s")
            params.append(id_externo)
        if id_interno:
            condiciones.append("id_interno = %s")
            params.append(id_interno)
        if titulo:
            condiciones.append("titulo ILIKE %s")
            params.append(f"%{titulo}%")

        where_clause = " AND ".join(condiciones)
        query = f"""
            SELECT id_interno, id_externo, titulo, fecha_hora, lugar, tipo,
                   descripcion, estado_ciclo, clase, puntos, creado_en, actualizado_en
            FROM vw_eventos_club_consulta
            WHERE {where_clause}
            ORDER BY fecha_hora ASC;
        """
        with db_manager.get_tenant_session(club_id) as conn, conn.cursor() as cur:
            cur.execute(query, tuple(params))
            return [dict(row) for row in cur.fetchall()]

    def find_eventos_pendientes(
        self,
        club_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Lista los eventos pendientes de definición de importancia (HU-22).
        Excluye eventos históricos y descartados.
        """
        condiciones = [
            "estado = 'pendiente_definicion_importancia'",
            "es_historico = FALSE",
        ]
        params: list[Any] = []
        if club_id:
            condiciones.append("club_id = %s")
            params.append(club_id)

        where_clause = " AND ".join(condiciones)
        query = f"""
            SELECT id_interno, id_externo, club_id, titulo, fecha_hora, lugar, tipo,
                   descripcion, estado, creado_en, actualizado_en
            FROM eventos_pendientes_verificacion
            WHERE {where_clause}
            ORDER BY fecha_hora ASC;
        """
        with db_manager.get_connection() as conn, conn.cursor() as cur:
            cur.execute(query, tuple(params))
            return [dict(row) for row in cur.fetchall()]

    def get_evento_pendiente(
        self,
        club_id: str | None,
        id_externo_o_interno: str,
    ) -> dict[str, Any] | None:
        if club_id:
            query = """
                SELECT id_interno, id_externo, club_id, titulo, fecha_hora, lugar, tipo,
                       descripcion, estado, creado_en, actualizado_en
                FROM eventos_pendientes_verificacion
                WHERE club_id = %s AND (id_externo = %s OR id_interno = %s);
            """
            params: tuple[Any, ...] = (
                club_id,
                id_externo_o_interno,
                id_externo_o_interno,
            )
        else:
            query = """
                SELECT id_interno, id_externo, club_id, titulo, fecha_hora, lugar, tipo,
                       descripcion, estado, creado_en, actualizado_en
                FROM eventos_pendientes_verificacion
                WHERE id_externo = %s OR id_interno = %s;
            """
            params = (id_externo_o_interno, id_externo_o_interno)

        with db_manager.get_connection() as conn, conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
            return dict(row) if row else None

    def is_already_published(
        self,
        club_id: str | None,
        id_externo_o_interno: str,
    ) -> bool:
        if club_id:
            query = """
                SELECT 1 FROM eventos_visibles
                WHERE club_id = %s AND (id_externo = %s OR id_interno = %s)
                LIMIT 1;
            """
            params: tuple[Any, ...] = (
                club_id,
                id_externo_o_interno,
                id_externo_o_interno,
            )
        else:
            query = """
                SELECT 1 FROM eventos_visibles
                WHERE id_externo = %s OR id_interno = %s
                LIMIT 1;
            """
            params = (id_externo_o_interno, id_externo_o_interno)

        with db_manager.get_connection() as conn, conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone() is not None

    def publish_evento(
        self,
        club_id: str | None,
        id_externo_o_interno: str,
        clase: str | None = None,
        puntos: int | None = None,
    ) -> str:
        """
        Publica un evento para que pase a estar visible a los socios (HU-22).
        Retorna el id_interno del evento publicado.
        """
        if self.is_already_published(club_id, id_externo_o_interno):
            raise EventoYaPublicadoError("El evento ya se encuentra publicado.")

        if club_id:
            query_sel = """
                SELECT id_interno, id_externo, club_id, titulo, fecha_hora, lugar, tipo, descripcion
                FROM eventos_pendientes_verificacion
                WHERE club_id = %s AND (id_externo = %s OR id_interno = %s);
            """
            params_sel: tuple[Any, ...] = (
                club_id,
                id_externo_o_interno,
                id_externo_o_interno,
            )
        else:
            query_sel = """
                SELECT id_interno, id_externo, club_id, titulo, fecha_hora, lugar, tipo, descripcion
                FROM eventos_pendientes_verificacion
                WHERE id_externo = %s OR id_interno = %s;
            """
            params_sel = (id_externo_o_interno, id_externo_o_interno)

        with db_manager.get_connection() as conn, conn.cursor() as cur:
            cur.execute(query_sel, params_sel)
            row = cur.fetchone()
            if row:
                target_club_id = row["club_id"]
                query_ins = """
                    INSERT INTO eventos_visibles (
                        id_interno, club_id, id_externo, titulo, fecha_hora, lugar, tipo,
                        descripcion, clase, puntos
                    ) VALUES (
                        %(id_interno)s, %(club_id)s, %(id_externo)s, %(titulo)s, %(fecha_hora)s, %(lugar)s, %(tipo)s,
                        %(descripcion)s, %(clase)s, %(puntos)s
                    )
                    ON CONFLICT (club_id, id_externo) DO UPDATE SET
                        clase = EXCLUDED.clase,
                        puntos = EXCLUDED.puntos,
                        actualizado_en = CURRENT_TIMESTAMP
                    RETURNING id_interno;
                """
                params = {
                    "id_interno": row["id_interno"],
                    "club_id": target_club_id,
                    "id_externo": row["id_externo"],
                    "titulo": row["titulo"],
                    "fecha_hora": row["fecha_hora"],
                    "lugar": row["lugar"],
                    "tipo": row["tipo"],
                    "descripcion": row["descripcion"],
                    "clase": clase,
                    "puntos": puntos,
                }
                cur.execute(query_ins, params)
                res = cur.fetchone()
                cur.execute(
                    "DELETE FROM eventos_pendientes_verificacion WHERE id_interno = %s;",
                    (row["id_interno"],),
                )
                if not res:
                    raise RuntimeError(
                        "No se pudo obtener el id_interno del evento publicado."
                    )
                return str(res["id_interno"])

            raise ValueError(
                f"Evento '{id_externo_o_interno}' no encontrado para publicar en club '{club_id}'."
            )

    def find_proximos_eventos_publicados(
        self,
        club_id: str | None = None,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """
        Consulta los próximos eventos publicados (visibles para socios) ordenados
        cronológicamente (HU-17).
        """
        ahora = now or datetime.now(UTC)
        condiciones = ["fecha_hora > %s"]
        params: list[Any] = [ahora]

        if club_id:
            condiciones.append("club_id = %s")
            params.append(club_id)

        where_clause = " AND ".join(condiciones)
        query = f"""
            SELECT id_interno, id_externo, club_id, titulo, fecha_hora, lugar, tipo,
                   descripcion, clase, puntos, publicado_en, actualizado_en
            FROM eventos_visibles
            WHERE {where_clause}
            ORDER BY fecha_hora ASC;
        """
        with db_manager.get_connection() as conn, conn.cursor() as cur:
            cur.execute(query, tuple(params))
            return [dict(row) for row in cur.fetchall()]
