from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from ..models.domain import ClubDomain
from ..schemas.eventos import EventoCreateRequest


class EventoRepository(ABC):
    """
    Interfaz base del repositorio de eventos.
    Garantiza que cualquier implementación ejecute las consultas respetando
    el aislamiento multi-tenant del club_id.
    """

    @abstractmethod
    def get_club_by_token(self, api_token: str) -> ClubDomain | None:
        """Obtiene el club asociado al Bearer token."""

    @abstractmethod
    def exists_externo(self, club_id: str, id_externo: str) -> bool:
        """Verifica si ya existe un evento con ese id_externo para el club."""

    @abstractmethod
    def insert_pendiente(
        self,
        club_id: str,
        evento: EventoCreateRequest,
        estado: str = "pendiente_definicion_importancia",
        es_historico: bool = False,
    ) -> str:
        """
        Inserta un evento en la vista de pendientes y retorna el id_interno.
        Permite fijar el estado (ej. 'pendiente_definicion_importancia' o 'Historico').
        """

    @abstractmethod
    def find_eventos(
        self,
        club_id: str,
        id_externo: str | None = None,
        id_interno: str | None = None,
        titulo: str | None = None,
    ) -> list[dict[str, Any]]:
        """Consulta eventos del club filtrando por criterios opcionales."""

    @abstractmethod
    def find_eventos_pendientes(
        self,
        club_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Lista los eventos pendientes de definición de importancia (HU-22).
        Excluye eventos históricos y descartados.
        """

    @abstractmethod
    def get_evento_pendiente(
        self,
        club_id: str | None,
        id_externo_o_interno: str,
    ) -> dict[str, Any] | None:
        """Obtiene un evento pendiente por su id_externo o id_interno."""

    @abstractmethod
    def is_already_published(
        self,
        club_id: str | None,
        id_externo_o_interno: str,
    ) -> bool:
        """Verifica si un evento ya fue publicado."""

    @abstractmethod
    def publish_evento(
        self,
        club_id: str | None,
        id_externo_o_interno: str,
        clase: str | None = None,
        puntos: int | None = None,
    ) -> str:
        """
        Publica un evento para que pase al estado 'visible'/'published' (HU-22).
        Retorna el id_interno del evento publicado.
        """

    @abstractmethod
    def find_proximos_eventos_publicados(
        self,
        club_id: str | None = None,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """
        Consulta los próximos eventos publicados (visibles para socios) ordenados
        cronológicamente (HU-17).
        """
