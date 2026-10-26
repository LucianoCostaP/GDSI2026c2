from fastapi import Depends
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from .base import EventoRepository
from .memory_repo import MemoryEventoRepository
from .postgres_repo import PostgresEventoRepository

# Instancia singleton para uso en memoria durante ciclo de vida o tests
memory_repository = MemoryEventoRepository()


def get_evento_repository(db: Session = Depends(get_db)) -> EventoRepository:
    """
    Retorna la implementación de repositorio correspondiente según DB_ENGINE.
    - 'postgres': trabaja sobre la sesión del request (las VIEWs filtran por club).
    - 'memory': Simulador en memoria con las 3 tablas, ENUM y Vistas de aislamiento.
    """
    if settings.db_engine.lower() == "postgres":
        return PostgresEventoRepository(db)
    return memory_repository
