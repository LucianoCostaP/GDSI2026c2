from collections.abc import Generator as TypingGenerator
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

connect_args = {"connect_timeout": 2} if "postgresql" in settings.database_url else {}
engine = create_engine(
    settings.database_url, pool_pre_ping=True, connect_args=connect_args
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def set_current_club_context(session: Session, club_id: UUID | str) -> None:
    """
    Configura la variable de sesión multi-tenant 'app.current_club_id'
    con alcance local a la transacción (is_local = true), asegurando
    aislamiento estricto y previniendo fugas en el pool de conexiones.
    """
    session.execute(
        text("SELECT set_config('app.current_club_id', :club_id, true)"),
        {"club_id": str(club_id)},
    )


class DatabaseManager:
    """Administra conexiones directas y configuraciones de sesión en PostgreSQL vía psycopg."""

    def __init__(self, connection_url: str):
        self.connection_url = connection_url.replace(
            "postgresql+psycopg://", "postgresql://"
        )

    @contextmanager
    def get_connection(
        self,
    ) -> TypingGenerator[psycopg.Connection[dict[str, Any]], None, None]:
        """Provee una conexión con autocommit deshabilitado para transacciones controladas."""
        conn = psycopg.connect(self.connection_url, row_factory=dict_row)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def get_tenant_session(
        self, club_id: str
    ) -> TypingGenerator[psycopg.Connection[dict[str, Any]], None, None]:
        """
        Provee una conexión configurando la variable de sesión 'app.current_club_id'.
        Esto activa inmediatamente el filtrado de las vistas PostgreSQL.
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT set_config('app.current_club_id', %s, true);",
                    (str(club_id),),
                )
            yield conn


db_manager = DatabaseManager(settings.database_url)
