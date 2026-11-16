import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.exceptions import (
    EventoDuplicadoError,
    EventoNoEncontradoError,
    EventoYaPublicadoError,
)
from ..database import set_current_club_context
from ..models.domain import ClubDomain
from ..schemas.eventos import EventoCreateRequest
from .base import EventoRepository


class PostgresEventoRepository(EventoRepository):
    """
    Repositorio PostgreSQL que delega la seguridad en las VIEWs y variables de sesión.

    Trabaja sobre la sesión del request: no confirma nada por su cuenta, así el
    cambio y su auditoría se guardan juntos en el commit del router.
    """

    def __init__(self, db: Session):
        self.db = db

    def _rows(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        return [dict(row) for row in self.db.execute(text(query), params).mappings()]

    def _row(self, query: str, params: dict[str, Any]) -> dict[str, Any] | None:
        row = self.db.execute(text(query), params).mappings().first()
        return dict(row) if row else None

    def get_club_by_token(self, api_token: str) -> ClubDomain | None:
        """Consulta el club a partir de su Bearer token."""
        row = self._row(
            """
            SELECT id, nombre, codigo_identificador, api_token, activo, creado_en
            FROM clubes
            WHERE api_token = :api_token AND activo = TRUE;
            """,
            {"api_token": api_token},
        )
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
        set_current_club_context(self.db, club_id)
        row = self._row(
            """
            SELECT 1 AS existe FROM vw_eventos_club_consulta
            WHERE id_externo = :id_externo
            LIMIT 1;
            """,
            {"id_externo": id_externo},
        )
        return row is not None

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
        set_current_club_context(self.db, club_id)
        try:
            # Savepoint propio: si el insert falla, en un batch se pierde solo
            # este evento y no los demás (contrato de la API de clubes).
            with self.db.begin_nested():
                row = self._insert_pendiente(evento, estado, es_historico)
        except IntegrityError as err:
            # Otro request registró el mismo id_externo entre el chequeo y el insert.
            raise EventoDuplicadoError(
                "Ya existe un evento registrado con ese id_externo."
            ) from err
        if not row:
            raise RuntimeError("No se pudo obtener el id_interno del evento.")
        return str(row["id_interno"])

    def _insert_pendiente(
        self, evento: EventoCreateRequest, estado: str, es_historico: bool
    ) -> dict[str, Any] | None:
        return self._row(
            """
            INSERT INTO vw_eventos_pendientes_verificacion (
                id_interno, id_externo, titulo, fecha_hora, lugar, tipo, descripcion, es_historico, estado
            ) VALUES (
                :id_interno, :id_externo, :titulo, :fecha_hora, :lugar, :tipo, :descripcion, :es_historico, :estado
            )
            RETURNING id_interno;
            """,
            {
                "id_interno": f"EVT-INT-{uuid.uuid4().hex[:12].upper()}",
                "id_externo": evento.id_externo,
                "titulo": evento.titulo,
                "fecha_hora": evento.fecha_hora,
                "lugar": evento.lugar,
                "tipo": evento.tipo,
                "descripcion": evento.descripcion,
                "es_historico": es_historico or evento.es_historico or False,
                "estado": estado,
            },
        )

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
        params: dict[str, Any] = {}

        if id_externo:
            condiciones.append("id_externo = :id_externo")
            params["id_externo"] = id_externo
        if id_interno:
            condiciones.append("id_interno = :id_interno")
            params["id_interno"] = id_interno
        if titulo:
            condiciones.append("titulo ILIKE :titulo")
            params["titulo"] = f"%{titulo}%"

        where_clause = " AND ".join(condiciones)
        set_current_club_context(self.db, club_id)
        return self._rows(
            f"""
            SELECT id_interno, id_externo, titulo, fecha_hora, lugar, tipo,
                   descripcion, estado_ciclo, clase, puntos, creado_en, actualizado_en
            FROM vw_eventos_club_consulta
            WHERE {where_clause}
            ORDER BY fecha_hora ASC;
            """,
            params,
        )

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
        params: dict[str, Any] = {}
        if club_id:
            condiciones.append("club_id = :club_id")
            params["club_id"] = club_id

        where_clause = " AND ".join(condiciones)
        return self._rows(
            f"""
            SELECT id_interno, id_externo, club_id, titulo, fecha_hora, lugar, tipo,
                   descripcion, estado, creado_en, actualizado_en
            FROM eventos_pendientes_verificacion
            WHERE {where_clause}
            ORDER BY fecha_hora ASC;
            """,
            params,
        )

    def get_evento_pendiente(
        self,
        club_id: str | None,
        id_externo_o_interno: str,
    ) -> dict[str, Any] | None:
        filtro_club = "club_id = :club_id AND " if club_id else ""
        return self._row(
            f"""
            SELECT id_interno, id_externo, club_id, titulo, fecha_hora, lugar, tipo,
                   descripcion, estado, creado_en, actualizado_en
            FROM eventos_pendientes_verificacion
            WHERE {filtro_club}(
                id_externo = :id 
                OR id_interno = :id 
                OR LOWER(TRIM(titulo)) = LOWER(TRIM(:id))
            )
            ORDER BY creado_en DESC
            LIMIT 1;
            """,
            {"club_id": club_id, "id": id_externo_o_interno.strip()},
        )

    def descartar_evento_pendiente(
        self,
        id_interno: str,
    ) -> None:
        self.db.execute(
            text(
                """
                UPDATE eventos_pendientes_verificacion
                SET estado = 'descartado',
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id_interno = :id_interno;
                """
            ),
            {"id_interno": id_interno},
        )

    def restaurar_evento_pendiente(
        self,
        id_interno: str,
    ) -> None:
        self.db.execute(
            text(
                """
                UPDATE eventos_pendientes_verificacion
                SET estado = 'pendiente_definicion_importancia',
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id_interno = :id_interno;
                """
            ),
            {"id_interno": id_interno},
        )

    def ajustar_clase_o_puntos_pendiente(
        self,
        id_interno: str,
        clase: str | None = None,
        puntos: int | None = None,
    ) -> None:
        updates = ["actualizado_en = CURRENT_TIMESTAMP"]
        params: dict[str, Any] = {"id_interno": id_interno}
        if clase is not None:
            updates.append("clase = :clase")
            params["clase"] = clase
        if puntos is not None:
            updates.append("puntos = :puntos")
            params["puntos"] = puntos

        set_clause = ", ".join(updates)
        self.db.execute(
            text(
                f"""
                UPDATE eventos_pendientes_verificacion
                SET {set_clause}
                WHERE id_interno = :id_interno;
                """
            ),
            params,
        )

    def is_already_published(
        self,
        club_id: str | None,
        id_externo_o_interno: str,
    ) -> bool:
        filtro_club = "club_id = :club_id AND " if club_id else ""
        row = self._row(
            f"""
            SELECT 1 AS existe FROM eventos_visibles
            WHERE {filtro_club}(id_externo = :id OR id_interno = :id)
            LIMIT 1;
            """,
            {"club_id": club_id, "id": id_externo_o_interno},
        )
        return row is not None

    def publish_evento(
        self,
        club_id: str | None,
        id_externo_o_interno: str,
        clase: str | None = None,
        puntos: int | None = None,
        publicado_por: str = "admin",
        es_default: bool = False,
    ) -> str:
        """
        Publica un evento para que pase a estar visible a los socios (HU-22).
        Retorna el id_interno del evento publicado.

        FR-006: la transición es un compare-and-set en una sola sentencia. El
        DELETE solo toma la fila si sigue pendiente; si dos publicaciones
        compiten, la segunda espera el bloqueo de la fila, no la encuentra y
        no publica nada. Sin club solo se acepta el id_interno (único global).
        """
        filtro = (
            "club_id = :club_id AND (id_externo = :id OR id_interno = :id)"
            if club_id
            else "id_interno = :id"
        )
        row = self._row(
            f"""
            WITH tomado AS (
                DELETE FROM eventos_pendientes_verificacion
                WHERE {filtro}
                  AND estado = 'pendiente_definicion_importancia'
                  AND es_historico = FALSE
                RETURNING id_interno, club_id, id_externo, titulo, fecha_hora,
                          lugar, tipo, descripcion
            )
            INSERT INTO eventos_visibles (
                id_interno, club_id, id_externo, titulo, fecha_hora, lugar, tipo,
                descripcion, clase, puntos, publicado_por, es_default
            )
            SELECT id_interno, club_id, id_externo, titulo, fecha_hora, lugar, tipo,
                   descripcion, :clase, :puntos, :publicado_por, :es_default
            FROM tomado
            RETURNING id_interno;
            """,
            {
                "club_id": club_id,
                "id": id_externo_o_interno,
                "clase": clase,
                "puntos": puntos,
                "publicado_por": publicado_por,
                "es_default": es_default,
            },
        )
        if row:
            return str(row["id_interno"])

        if self.is_already_published(club_id, id_externo_o_interno):
            raise EventoYaPublicadoError("El evento ya se encuentra publicado.")
        raise EventoNoEncontradoError(
            f"No se encontró un evento pendiente con identificador '{id_externo_o_interno}'."
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
        condiciones = [
            "fecha_hora > :ahora",
            "COALESCE(estado, 'publicado') = 'publicado'",
        ]
        params: dict[str, Any] = {"ahora": now or datetime.now(UTC)}

        if club_id:
            condiciones.append("club_id = :club_id")
            params["club_id"] = club_id

        where_clause = " AND ".join(condiciones)
        return self._rows(
            f"""
            SELECT id_interno, id_externo, club_id, titulo, fecha_hora, lugar, tipo,
                   descripcion, clase, puntos, publicado_por, es_default,
                   publicado_en, actualizado_en, estado, cancelado_por_el_club,
                   fin_ajuste_clase_puntos, retirado_en, retirado_por_id, motivo_retiro,
                   restaurado_en, restaurado_por_id
            FROM eventos_visibles
            WHERE {where_clause}
            ORDER BY fecha_hora ASC;
            """,
            params,
        )

    def find_eventos_visibles_admin(
        self,
        club_id: str | None = None,
    ) -> list[dict[str, Any]]:
        filtro_club = "WHERE club_id = :club_id" if club_id else ""
        return self._rows(
            f"""
            SELECT id_interno, id_externo, club_id, titulo, fecha_hora, lugar, tipo,
                   clase, puntos, estado, cancelado_por_el_club, fin_ajuste_clase_puntos
            FROM eventos_visibles
            {filtro_club}
            ORDER BY fecha_hora ASC;
            """,
            {"club_id": club_id} if club_id else {},
        )

    def get_evento_visible(
        self,
        id_externo_o_interno: str,
        club_id: str | None = None,
    ) -> dict[str, Any] | None:
        filtro_club = "club_id = :club_id AND " if club_id else ""
        return self._row(
            f"""
            SELECT id_interno, id_externo, club_id, titulo, fecha_hora, lugar, tipo,
                   descripcion, clase, puntos, publicado_por, es_default,
                   publicado_en, actualizado_en, estado, cancelado_por_el_club,
                   fin_ajuste_clase_puntos, retirado_en, retirado_por_id, motivo_retiro,
                   restaurado_en, restaurado_por_id
            FROM eventos_visibles
            WHERE {filtro_club}(
                id_externo = :id 
                OR id_interno = :id 
                OR LOWER(TRIM(titulo)) = LOWER(TRIM(:id))
            )
            ORDER BY publicado_en DESC
            LIMIT 1;
            """,
            {"club_id": club_id, "id": id_externo_o_interno.strip()},
        )

    def insert_o_reemplazar_cambio_pendiente(
        self,
        club_id: str,
        id_interno: str,
        valores_nuevos: dict[str, Any],
        valores_previos: dict[str, Any],
    ) -> str:
        # 1. Si existía uno en pendiente_revision, marcar como reemplazado
        self.db.execute(
            text(
                """
                UPDATE eventos_cambios_pendientes
                SET estado_revision = 'reemplazado'
                WHERE id_interno = :id_interno
                  AND club_id = :club_id
                  AND estado_revision = 'pendiente_revision';
                """
            ),
            {"id_interno": id_interno, "club_id": club_id},
        )
        import json

        row = self._row(
            """
            INSERT INTO eventos_cambios_pendientes (
                id_interno, club_id, titulo, fecha_hora, lugar, tipo, descripcion,
                estado_revision, valores_previos, solicitado_en
            ) VALUES (
                :id_interno, :club_id, :titulo, :fecha_hora, :lugar, :tipo, :descripcion,
                'pendiente_revision', :valores_previos, CURRENT_TIMESTAMP
            )
            RETURNING id_cambio;
            """,
            {
                "id_interno": id_interno,
                "club_id": club_id,
                "titulo": valores_nuevos.get("titulo"),
                "fecha_hora": valores_nuevos.get("fecha_hora"),
                "lugar": valores_nuevos.get("lugar"),
                "tipo": valores_nuevos.get("tipo"),
                "descripcion": valores_nuevos.get("descripcion"),
                "valores_previos": json.dumps(valores_previos, default=str),
            },
        )
        if not row:
            raise RuntimeError("No se pudo registrar la solicitud de cambio.")
        return str(row["id_cambio"])

    def find_cambios_pendientes(
        self,
        club_id: str | None = None,
    ) -> list[dict[str, Any]]:
        filtro_club = "WHERE club_id = :club_id AND estado_revision = 'pendiente_revision'" if club_id else "WHERE estado_revision = 'pendiente_revision'"
        return self._rows(
            f"""
            SELECT c.id_cambio, c.id_interno, c.club_id, c.titulo, c.fecha_hora, c.lugar,
                   c.tipo, c.descripcion, c.estado_revision, c.valores_previos, c.solicitado_en,
                   v.id_externo, v.titulo AS titulo_actual, v.fecha_hora AS fecha_hora_actual,
                   v.lugar AS lugar_actual, v.descripcion AS descripcion_actual, v.tipo AS tipo_actual
            FROM eventos_cambios_pendientes c
            JOIN eventos_visibles v ON c.id_interno = v.id_interno
            {filtro_club}
            ORDER BY c.solicitado_en ASC;
            """,
            {"club_id": club_id} if club_id else {},
        )

    def get_cambio_pendiente(
        self,
        id_cambio: str,
    ) -> dict[str, Any] | None:
        return self._row(
            """
            SELECT c.id_cambio, c.id_interno, c.club_id, c.titulo, c.fecha_hora, c.lugar,
                   c.tipo, c.descripcion, c.estado_revision, c.valores_previos, c.solicitado_en,
                   c.revisado_por_id, c.revisado_en,
                   v.id_externo, v.titulo AS titulo_actual, v.fecha_hora AS fecha_hora_actual,
                   v.lugar AS lugar_actual, v.descripcion AS descripcion_actual, v.tipo AS tipo_actual,
                   v.clase, v.puntos
            FROM eventos_cambios_pendientes c
            JOIN eventos_visibles v ON c.id_interno = v.id_interno
            WHERE c.id_cambio = :id_cambio;
            """,
            {"id_cambio": id_cambio},
        )

    def update_cambio_estado(
        self,
        id_cambio: str,
        estado_revision: str,
        revisado_por_id: int | None = None,
    ) -> None:
        self.db.execute(
            text(
                """
                UPDATE eventos_cambios_pendientes
                SET estado_revision = :estado,
                    revisado_por_id = :revisado_por_id,
                    revisado_en = CURRENT_TIMESTAMP
                WHERE id_cambio = :id_cambio;
                """
            ),
            {
                "id_cambio": id_cambio,
                "estado": estado_revision,
                "revisado_por_id": revisado_por_id,
            },
        )

    def aplicar_cambio_evento(
        self,
        id_interno: str,
        valores: dict[str, Any],
        fin_ajuste_clase_puntos: datetime,
    ) -> None:
        updates = [
            "actualizado_en = CURRENT_TIMESTAMP",
            "fin_ajuste_clase_puntos = :fin_ajuste",
        ]
        params: dict[str, Any] = {
            "id_interno": id_interno,
            "fin_ajuste": fin_ajuste_clase_puntos,
        }
        if "fecha_hora" in valores and valores["fecha_hora"] is not None:
            updates.append("fecha_hora = :fecha_hora")
            params["fecha_hora"] = valores["fecha_hora"]
        if "lugar" in valores and valores["lugar"] is not None:
            updates.append("lugar = :lugar")
            params["lugar"] = valores["lugar"]
        if "descripcion" in valores:
            updates.append("descripcion = :descripcion")
            params["descripcion"] = valores["descripcion"]
        if "titulo" in valores and valores["titulo"] is not None:
            updates.append("titulo = :titulo")
            params["titulo"] = valores["titulo"]

        set_clause = ", ".join(updates)
        self.db.execute(
            text(
                f"""
                UPDATE eventos_visibles
                SET {set_clause}
                WHERE id_interno = :id_interno;
                """
            ),
            params,
        )

    def marcar_cancelado_club(
        self,
        club_id: str,
        id_externo_o_interno: str,
    ) -> dict[str, Any] | None:
        # Primero buscar en eventos_visibles
        row = self._row(
            """
            UPDATE eventos_visibles
            SET cancelado_por_el_club = TRUE,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE club_id = :club_id AND (id_externo = :id OR id_interno = :id)
            RETURNING id_interno, id_externo, estado;
            """,
            {"club_id": club_id, "id": id_externo_o_interno},
        )
        if row:
            return dict(row)

        # Si no está en visibles, buscar en pendientes
        row_p = self._row(
            """
            UPDATE eventos_pendientes_verificacion
            SET cancelado_por_el_club = TRUE,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE club_id = :club_id AND (id_externo = :id OR id_interno = :id)
            RETURNING id_interno, id_externo, estado;
            """,
            {"club_id": club_id, "id": id_externo_o_interno},
        )
        return dict(row_p) if row_p else None

    def retirar_evento(
        self,
        id_interno: str,
        admin_id: int,
        motivo: str,
    ) -> None:
        self.db.execute(
            text(
                """
                UPDATE eventos_visibles
                SET estado = 'retirado',
                    retirado_en = CURRENT_TIMESTAMP,
                    retirado_por_id = :admin_id,
                    motivo_retiro = :motivo,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id_interno = :id_interno;
                """
            ),
            {"id_interno": id_interno, "admin_id": admin_id, "motivo": motivo},
        )

    def restaurar_evento(
        self,
        id_interno: str,
        admin_id: int,
    ) -> None:
        self.db.execute(
            text(
                """
                UPDATE eventos_visibles
                SET estado = 'publicado',
                    restaurado_en = CURRENT_TIMESTAMP,
                    restaurado_por_id = :admin_id,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id_interno = :id_interno;
                """
            ),
            {"id_interno": id_interno, "admin_id": admin_id},
        )

    def ajustar_clase_o_puntos(
        self,
        id_interno: str,
        clase: str | None = None,
        puntos: int | None = None,
    ) -> None:
        updates = ["actualizado_en = CURRENT_TIMESTAMP"]
        params: dict[str, Any] = {"id_interno": id_interno}
        if clase is not None:
            updates.append("clase = :clase")
            params["clase"] = clase
        if puntos is not None:
            updates.append("puntos = :puntos")
            params["puntos"] = puntos

        set_clause = ", ".join(updates)
        self.db.execute(
            text(
                f"""
                UPDATE eventos_visibles
                SET {set_clause}
                WHERE id_interno = :id_interno;
                """
            ),
            params,
        )

