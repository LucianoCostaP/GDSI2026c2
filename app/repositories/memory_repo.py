import uuid
from datetime import UTC, datetime
from typing import Any

from ..models.domain import ClubDomain
from ..models.enums import TipoEvento
from ..schemas.eventos import EventoCreateRequest
from .base import EventoRepository


class MemoryEventoRepository(EventoRepository):
    """
    Simulador en memoria de las tablas y vistas filtradas de PostgreSQL para el MVP.
    """

    def __init__(self):
        # 1. Tabla: clubes
        self.clubes: dict[str, ClubDomain] = {
            "11111111-1111-1111-1111-111111111111": ClubDomain(
                id="11111111-1111-1111-1111-111111111111",
                nombre="Club Atlético Boca Juniors",
                codigo_identificador="CABJ",
                api_token="token_boca_abc123",
                activo=True,
                creado_en=datetime.now(UTC),
            ),
            "22222222-2222-2222-2222-222222222222": ClubDomain(
                id="22222222-2222-2222-2222-222222222222",
                nombre="Club Atlético River Plate",
                codigo_identificador="CARP",
                api_token="token_river_def456",
                activo=True,
                creado_en=datetime.now(UTC),
            ),
            "33333333-3333-3333-3333-333333333333": ClubDomain(
                id="33333333-3333-3333-3333-333333333333",
                nombre="Racing Club de Avellaneda",
                codigo_identificador="RC",
                api_token="token_racing_ghi789",
                activo=True,
                creado_en=datetime.now(UTC),
            ),
        }

        # 2. Almacenamiento de tablas físicas
        self.tabla_eventos_pendientes: list[dict[str, Any]] = []
        self.tabla_eventos_visibles: list[dict[str, Any]] = []
        self.tabla_eventos_cambios_pendientes: list[dict[str, Any]] = []

    def get_club_by_token(self, api_token: str) -> ClubDomain | None:
        """Busca el club por su token alfanumérico."""
        for club in self.clubes.values():
            if club.api_token == api_token and club.activo:
                return club
        return None

    # =========================================================================
    # SIMULACIÓN DE VISTAS MULTI-TENANT (WHERE club_id = current_setting(...))
    # =========================================================================

    def _vw_eventos_pendientes_verificacion(self, club_id: str) -> list[dict[str, Any]]:
        """Vista filtrada para eventos pendientes e históricos del club actual."""
        return [
            e
            for e in self.tabla_eventos_pendientes
            if str(e["club_id"]) == str(club_id)
        ]

    def _vw_eventos_visibles(self, club_id: str) -> list[dict[str, Any]]:
        """Vista filtrada para eventos visibles (aprobados) del club actual."""
        return [
            e for e in self.tabla_eventos_visibles if str(e["club_id"]) == str(club_id)
        ]

    def _vw_eventos_club_consulta(self, club_id: str) -> list[dict[str, Any]]:
        """Vista unificada de consulta para el club actual."""
        resultado = []
        # Pendientes / Históricos
        for p in self._vw_eventos_pendientes_verificacion(club_id):
            resultado.append(
                {
                    "id_interno": p["id_interno"],
                    "id_externo": p["id_externo"],
                    "club_id": p["club_id"],
                    "titulo": p["titulo"],
                    "fecha_hora": p["fecha_hora"],
                    "lugar": p["lugar"],
                    "tipo": p["tipo"],
                    "descripcion": p["descripcion"],
                    "estado_ciclo": p["estado"],
                    "clase": None,
                    "puntos": None,
                    "creado_en": p["creado_en"],
                    "actualizado_en": p["actualizado_en"],
                }
            )
        # Visibles (Aprobados)
        for v in self._vw_eventos_visibles(club_id):
            resultado.append(
                {
                    "id_interno": v["id_interno"],
                    "id_externo": v["id_externo"],
                    "club_id": v["club_id"],
                    "titulo": v["titulo"],
                    "fecha_hora": v["fecha_hora"],
                    "lugar": v["lugar"],
                    "tipo": v["tipo"],
                    "descripcion": v["descripcion"],
                    "estado_ciclo": "visible",
                    "clase": v.get("clase"),
                    "puntos": v.get("puntos"),
                    "creado_en": v.get("publicado_en"),
                    "actualizado_en": v.get("actualizado_en"),
                }
            )
        return resultado

    # =========================================================================
    # IMPLEMENTACIÓN DE MÉTODOS DEL REPOSITORIO
    # =========================================================================

    def exists_externo(self, club_id: str, id_externo: str) -> bool:
        """Verifica a través de la vista si el id_externo ya existe para el club."""
        eventos = self._vw_eventos_club_consulta(club_id)
        return any(e["id_externo"] == id_externo for e in eventos)

    def insert_pendiente(
        self,
        club_id: str,
        evento: EventoCreateRequest,
        estado: str = "pendiente_definicion_importancia",
        es_historico: bool = False,
    ) -> str:
        """
        Inserta en la vista de eventos_pendientes_verificacion.
        Verifica el TYPE ENUM y genera id_interno estandarizado.
        """
        if evento.tipo not in [t.value for t in TipoEvento]:
            raise ValueError(f"Valor '{evento.tipo}' no pertenece al ENUM tipo_evento.")

        id_interno = f"EVT-INT-{uuid.uuid4().hex[:12].upper()}"
        ahora = datetime.now(UTC)

        nuevo_registro = {
            "id_interno": id_interno,
            "club_id": str(club_id),
            "id_externo": evento.id_externo,
            "titulo": evento.titulo,
            "fecha_hora": evento.fecha_hora,
            "lugar": evento.lugar,
            "tipo": evento.tipo,
            "descripcion": evento.descripcion,
            "es_historico": es_historico or evento.es_historico or False,
            "estado": estado,
            "creado_en": ahora,
            "actualizado_en": ahora,
        }
        self.tabla_eventos_pendientes.append(nuevo_registro)
        return id_interno

    def find_eventos(
        self,
        club_id: str,
        id_externo: str | None = None,
        id_interno: str | None = None,
        titulo: str | None = None,
    ) -> list[dict[str, Any]]:
        """Consulta la vista consolidada con filtros aplicados."""
        eventos = self._vw_eventos_club_consulta(club_id)
        resultado = []
        for e in eventos:
            if id_externo and e["id_externo"] != id_externo:
                continue
            if id_interno and e["id_interno"] != id_interno:
                continue
            if titulo and (titulo.lower() not in e["titulo"].lower()):
                continue
            resultado.append(e)
        return resultado
