import uuid
from typing import Any

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
            return res["id_interno"]

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
