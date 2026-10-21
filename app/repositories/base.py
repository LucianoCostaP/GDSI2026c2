from abc import ABC, abstractmethod
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
