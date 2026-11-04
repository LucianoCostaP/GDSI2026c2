import os
import re
import uuid
from collections.abc import Callable, Iterator

# Aislamiento de base de datos para pruebas:
os.environ.setdefault("APP_ENV", "test")

import socket


def _check_local_pg() -> bool:
    s = socket.socket()
    s.settimeout(0.2)
    try:
        s.connect(("127.0.0.1", 5432))
        s.close()
        return True
    except Exception:  # noqa: BLE001
        return False


if not _check_local_pg():
    os.environ["DB_ENGINE"] = "sqlite"
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
elif "DATABASE_URL" not in os.environ or os.environ["DATABASE_URL"].endswith("/app"):
    os.environ["DATABASE_URL"] = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://app:app@localhost:5432/app_test",
    )

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@compiles(PG_UUID, "sqlite")
def _compile_pg_uuid_sqlite(type_, compiler, **kw):
    return "TEXT"


@compiles(PG_JSONB, "sqlite")
def _compile_pg_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"


from app.config import settings
from app.db import Base, engine, get_db
from app.mailer import get_mailer
from app.main import app
from app.models import FeeStatus, Member, MemberAccountState, Role, User
from app.rate_limit import identifier_limiter, ip_limiter
from app.repositories.factory import memory_repository

Outbox = list[tuple[str, str, str]]
MakeMember = Callable[..., Member]

# Clubes que siembra la migración e7a1b2c3d4e5.
BOCA_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
RIVER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")

BOCA_TOKEN = "token_boca_abc123"
RIVER_TOKEN = "token_river_def456"
RACING_TOKEN = "token_racing_ghi789"

BOCA_HEADERS = {
    "Authorization": f"Bearer {BOCA_TOKEN}",
    "Content-Type": "application/json",
}
RIVER_HEADERS = {
    "Authorization": f"Bearer {RIVER_TOKEN}",
    "Content-Type": "application/json",
}
RACING_HEADERS = {
    "Authorization": f"Bearer {RACING_TOKEN}",
    "Content-Type": "application/json",
}

_test_sqlite_engine = None

_postgres_available: bool | None = None


def _is_postgres_available() -> bool:
    global _postgres_available
    if _postgres_available is None:
        if settings.db_engine.lower() != "postgres":
            _postgres_available = False
        else:
            import socket

            s = socket.socket()
            s.settimeout(0.3)
            try:
                s.connect(("127.0.0.1", 5432))
                s.close()
                _postgres_available = True
            except Exception:  # noqa: BLE001
                _postgres_available = False
    return _postgres_available


@pytest.fixture(scope="session", autouse=True)
def _setup_test_database() -> None:
    """Asegura que la base de datos de test exista y tenga las migraciones ejecutadas."""
    if not _is_postgres_available():
        global _test_sqlite_engine
        if _test_sqlite_engine is None:
            _test_sqlite_engine = create_engine(
                "sqlite://",
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
            Base.metadata.create_all(_test_sqlite_engine)
            from app.models.domain import Club

            with Session(bind=_test_sqlite_engine) as _s:
                if not _s.get(Club, BOCA_ID):
                    _s.add(
                        Club(
                            id=BOCA_ID,
                            nombre="Boca Juniors",
                            codigo_identificador="CABJ",
                            api_token=BOCA_TOKEN,
                            activo=True,
                        )
                    )
                if not _s.get(Club, RIVER_ID):
                    _s.add(
                        Club(
                            id=RIVER_ID,
                            nombre="River Plate",
                            codigo_identificador="CARP",
                            api_token=RIVER_TOKEN,
                            activo=True,
                        )
                    )
                _s.commit()
            import app.db

            app.db.SessionLocal.configure(bind=_test_sqlite_engine)
            settings.db_engine = "sqlite"
        return

    # Verificar / crear la base de datos de test si no existe aún
    db_name = settings.database_url.rsplit("/", 1)[-1].split("?")[0]
    if db_name:
        base_url = settings.database_url.rsplit("/", 1)[0] + "/app"
        try:
            import psycopg

            with (
                psycopg.connect(
                    base_url.replace("postgresql+psycopg://", "postgresql://"),
                    autocommit=True,
                ) as admin_conn,
                admin_conn.cursor() as cur,
            ):
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
                if not cur.fetchone():
                    cur.execute(f'CREATE DATABASE "{db_name}"')
        except Exception:  # noqa: BLE001, S110
            pass

    # Aplicar migraciones de Alembic a la base de test
    try:
        from alembic.config import Config

        from alembic import command

        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
        command.upgrade(alembic_cfg, "head")
    except Exception as exc:  # noqa: BLE001
        print(f"Aviso al aplicar migraciones en test DB: {exc}")


# Tablas que escriben los repositorios de clubes (psycopg directo, con commit
# propio): quedan fuera del rollback del fixture `db` y hay que vaciarlas.
CLUB_DATA_TABLES = (
    "asistencias_staging, cargas_participacion_rechazos, asistencias, "
    "actividades_recurrentes, cargas_participacion, "
    "socios_staging_completa, socios_cargas_rechazos, socios_cargas_paginas, "
    "socios_cargas, socios, "
    "eventos_cambios_pendientes, eventos_visibles, eventos_pendientes_verificacion"
)


@pytest.fixture(autouse=True)
def clean_club_data() -> None:
    """Aísla cada test de los datos de socios y eventos de clubes.

    Conserva los clubes semilla, admins y members (los usa el entorno local).
    """
    memory_repository.tabla_eventos_pendientes.clear()
    memory_repository.tabla_eventos_visibles.clear()
    memory_repository.tabla_eventos_cambios_pendientes.clear()
    if _is_postgres_available():
        try:
            with engine.begin() as conn:
                conn.execute(text(f"TRUNCATE TABLE {CLUB_DATA_TABLES} CASCADE;"))
        except Exception:  # noqa: BLE001, S110
            pass
    elif _test_sqlite_engine is not None:
        with _test_sqlite_engine.begin() as conn:
            for tbl in [
                "ranking_entries",
                "rankings",
                "formula_locks",
                "rules_versions",
                "socios",
                "members",
                "access_codes",
                "users",
            ]:
                try:
                    conn.execute(text(f"DELETE FROM {tbl};"))
                except Exception:  # noqa: BLE001, S110
                    pass


@pytest.fixture
def db() -> Iterator[Session]:
    # Intenta usar la conexión configurada (PostgreSQL en CI o Docker).
    # Si PostgreSQL no está corriendo, realiza fallback a SQLite en memoria.
    if _is_postgres_available():
        try:
            connection = engine.connect()
            transaction = connection.begin()
            session = Session(bind=connection, join_transaction_mode="create_savepoint")
            yield session
            session.close()
            transaction.rollback()
            connection.close()
            return
        except Exception:  # noqa: BLE001, S110
            pass

    global _test_sqlite_engine
    if _test_sqlite_engine is None:
        _test_sqlite_engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(_test_sqlite_engine)
        import app.db

        app.db.SessionLocal.configure(bind=_test_sqlite_engine)

    with _test_sqlite_engine.connect() as conn:
        session = Session(bind=conn)
        yield session
        session.close()


@pytest.fixture
def outbox() -> Outbox:
    return []


@pytest.fixture
def client(db: Session, outbox: Outbox) -> Iterator[TestClient]:
    ip_limiter.reset()
    identifier_limiter.reset()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_mailer] = lambda: lambda *email: outbox.append(email)
    yield TestClient(app)
    app.dependency_overrides.clear()


def unique() -> str:
    return uuid.uuid4().hex[:8]


@pytest.fixture
def make_member(db: Session) -> MakeMember:
    def make(
        *,
        activated: bool = False,
        fee_status: FeeStatus = FeeStatus.UP_TO_DATE,
        email: str | None = "",
        dni: str | None = None,
        member_id: str | None = None,
        club_id: uuid.UUID | None = BOCA_ID,
    ) -> Member:
        suffix = unique()
        member = Member(
            member_id=member_id or str(uuid.uuid4().int)[:10],
            dni=dni or str(uuid.uuid4().int)[:12],
            email=f"socio-{suffix}@example.com" if email == "" else email,
            name="Ana Socia",
            fee_status=fee_status,
            account_state=MemberAccountState.ACTIVATED
            if activated
            else MemberAccountState.NOT_ACTIVATED,
            club_id=club_id,
        )
        db.add(member)
        if activated:
            db.add(
                User(
                    member_id=member.member_id,
                    name=member.name,
                    email=member.email,
                    role=Role.MEMBER,
                    club_id=club_id,
                )
            )
        db.commit()
        return member

    return make


MakeAdmin = Callable[..., User]


@pytest.fixture
def make_admin(db: Session) -> MakeAdmin:
    def make(club_id: uuid.UUID | None = BOCA_ID) -> User:
        user = User(
            name="Admin",
            email=f"Admin-{unique()}@Example.com",
            role=Role.ADMIN,
            club_id=club_id,
        )
        db.add(user)
        db.commit()
        return user

    return make


@pytest.fixture
def admin(make_admin: MakeAdmin) -> User:
    """Admin del club Boca."""
    return make_admin(BOCA_ID)


def last_code(outbox: Outbox) -> str:
    match = re.search(r"\b(\d{6})\b", outbox[-1][2])
    assert match
    return match.group(1)


def admin_token(client: TestClient, outbox: Outbox, admin: User) -> str:
    sent = client.post("/auth/admin/login/request", json={"email": admin.email})
    assert sent.status_code == 202
    verified = client.post(
        "/auth/admin/login/verify",
        json={"challenge": sent.json()["challenge"], "code": last_code(outbox)},
    )
    assert verified.status_code == 200
    return str(verified.json()["token"])


def member_token(client: TestClient, outbox: Outbox, member: Member) -> str:
    sent = client.post(
        "/auth/member/login/request", json={"identifier": member.member_id}
    )
    assert sent.status_code == 202
    verified = client.post(
        "/auth/member/login/verify",
        json={"challenge": sent.json()["challenge"], "code": last_code(outbox)},
    )
    assert verified.status_code == 200
    return str(verified.json()["token"])


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
