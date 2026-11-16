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
    def descartar_evento_pendiente(
        self,
        id_interno: str,
    ) -> None:
        """Marca un evento pendiente como descartado."""

    @abstractmethod
    def restaurar_evento_pendiente(
        self,
        id_interno: str,
    ) -> None:
        """Restaura un evento pendiente descartado a pendiente de definición de importancia."""

    @abstractmethod
    def ajustar_clase_o_puntos_pendiente(
        self,
        id_interno: str,
        clase: str | None = None,
        puntos: int | None = None,
    ) -> None:
        """Ajusta clase o puntos en un evento pendiente."""

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
        publicado_por: str = "admin",
        es_default: bool = False,
    ) -> str:
        """
        Publica un evento para que pase al estado 'visible'/'published' (HU-22).
        La transición es exclusiva (FR-006): si el evento ya no está pendiente
        lanza EventoYaPublicadoError o EventoNoEncontradoError.
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

    @abstractmethod
    def find_eventos_visibles_admin(
        self,
        club_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Lista todos los eventos visibles (publicados y retirados) para el panel de administración."""

    @abstractmethod
    def get_evento_visible(
        self,
        id_externo_o_interno: str,
        club_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Obtiene un evento publicado/visible por su id_externo o id_interno."""

    @abstractmethod
    def insert_o_reemplazar_cambio_pendiente(
        self,
        club_id: str,
        id_interno: str,
        valores_nuevos: dict[str, Any],
        valores_previos: dict[str, Any],
    ) -> str:
        """
        Registra un cambio enviado por el club sobre un evento publicado (HU-23).
        Si ya existía un cambio en 'pendiente_revision', lo marca como 'reemplazado'.
        Retorna el id_cambio generado.
        """

    @abstractmethod
    def find_cambios_pendientes(
        self,
        club_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Lista las solicitudes de cambio en estado 'pendiente_revision' (HU-23)."""

    @abstractmethod
    def get_cambio_pendiente(
        self,
        id_cambio: str,
    ) -> dict[str, Any] | None:
        """Obtiene un cambio pendiente por su id_cambio."""

    @abstractmethod
    def update_cambio_estado(
        self,
        id_cambio: str,
        estado_revision: str,
        revisado_por_id: int | None = None,
    ) -> None:
        """Actualiza el estado de una solicitud de cambio ('aprobado', 'rechazado', 'reemplazado')."""

    @abstractmethod
    def aplicar_cambio_evento(
        self,
        id_interno: str,
        valores: dict[str, Any],
        fin_ajuste_clase_puntos: datetime,
    ) -> None:
        """Aplica la reprogramación aprobada en eventos_visibles fijando la ventana de 24h."""

    @abstractmethod
    def marcar_cancelado_club(
        self,
        club_id: str,
        id_externo_o_interno: str,
    ) -> dict[str, Any] | None:
        """Marca un evento (pendiente o visible) como cancelado por el club."""

    @abstractmethod
    def retirar_evento(
        self,
        id_interno: str,
        admin_id: int,
        motivo: str,
    ) -> None:
        """Pasa el evento publicado al estado 'retirado' con motivo y autor (HU-23)."""

    @abstractmethod
    def restaurar_evento(
        self,
        id_interno: str,
        admin_id: int,
    ) -> None:
        """Restaura un evento retirado volviéndolo al estado 'publicado' (HU-23)."""

    @abstractmethod
    def ajustar_clase_o_puntos(
        self,
        id_interno: str,
        clase: str | None = None,
        puntos: int | None = None,
    ) -> None:
        """Ajusta la clase o puntos dentro de la ventana de 24h tras reprogramación."""
