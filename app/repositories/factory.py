from ..config import settings
from .base import EventoRepository
from .memory_repo import MemoryEventoRepository
from .postgres_repo import PostgresEventoRepository

# Instancia singleton para uso en memoria durante ciclo de vida o tests
_memory_repo_instance = MemoryEventoRepository()


def get_evento_repository() -> EventoRepository:
    """
    Retorna la implementación de repositorio correspondiente según DB_ENGINE.
    - 'postgres': Conexión con PostgreSQL real ejecutando sobre las VIEWs.
    - 'memory': Simulador en memoria con las 3 tablas, ENUM y Vistas de aislamiento.
    """
    if settings.db_engine.lower() == "postgres":
        return PostgresEventoRepository()
    return _memory_repo_instance
