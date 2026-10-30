"""Ayudas compartidas por los tests de HU-25 (un archivo por ciclo, mismos datos de prueba)."""

import uuid
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ActividadRecurrenteDB,
    AsistenciaDB,
    CargaParticipacionDB,
    EstadoCargaParticipacion,
    EventoVisibleDB,
    Ranking,
    RankingEntry,
    Socio,
    User,
)
from app.scoring.catalog import SCORING_MODEL_V1
from tests.conftest import BOCA_ID, Outbox, admin_token, bearer

RUNS = "/admin/ranking/runs"
PUBLISH = "/admin/formulas/scoring-model/1/publish"
DEFAULTS = {p.key: str(p.default) for p in SCORING_MODEL_V1.parameters}


def headers_for(client: TestClient, outbox: Outbox, user: User) -> dict[str, str]:
    headers = bearer(admin_token(client, outbox, user))
    outbox.clear()
    return headers


def publish_rules(
    client: TestClient, headers: dict[str, str], **overrides: str
) -> None:
    """Publica las reglas por defecto; `overrides` cambia parámetros (clave=valor en texto)."""
    response = client.post(
        PUBLISH,
        json={
            "values": {**DEFAULTS, **overrides},
            "expected_rules_version": None,
            "confirmed": True,
        },
        headers=headers,
    )
    assert response.status_code == 201


def make_socio(db: Session, *, club_id: uuid.UUID = BOCA_ID, **overrides) -> Socio:
    suffix = uuid.uuid4().hex[:8]
    socio = Socio(
        club_id=club_id,
        id_externo=f"ext-{suffix}",
        dni=str(uuid.uuid4().int)[:8],
        numero_socio=f"N-{suffix}",
        nombre="Ana Socia",
        fecha_nacimiento=date(1980, 1, 1),
        fecha_alta=date(2015, 3, 1),
        estado_cuota="al_dia",
        email=f"{suffix}@example.com",
        distancia_km=Decimal("120.00"),
    )
    for field, value in overrides.items():
        setattr(socio, field, value)
    db.add(socio)
    db.commit()
    return socio


def rankings_of(db: Session, club_id: uuid.UUID = BOCA_ID) -> list[Ranking]:
    return list(db.scalars(select(Ranking).where(Ranking.club_id == club_id)))


def entries_of(db: Session, ranking: Ranking) -> list[RankingEntry]:
    return list(
        db.scalars(
            select(RankingEntry)
            .where(RankingEntry.ranking_id == ranking.id)
            .order_by(RankingEntry.position)
        )
    )

def make_event(
    db: Session,
    *,
    id_externo: str,
    when: datetime,
    tipo: str = "Partido",
    clase: str | None = "B",
    puntos: int | None = None,
    club_id: uuid.UUID = BOCA_ID,
) -> EventoVisibleDB:
    """Evento ya publicado (visible) del club. `when` tiene que traer zona horaria."""
    event = EventoVisibleDB(
        id_interno=f"INT-{club_id}-{id_externo}",
        club_id=club_id,
        id_externo=id_externo,
        titulo=f"Evento {id_externo}",
        fecha_hora=when,
        lugar="La Bombonera",
        tipo=tipo,
        clase=clase,
        puntos=puntos,
    )
    db.add(event)
    db.commit()
    return event


def load_attendance(
    db: Session,
    event: EventoVisibleDB,
    attendees: Iterable[Socio],
    *,
    estado: EstadoCargaParticipacion = EstadoCargaParticipacion.SUCCESSFUL,
) -> CargaParticipacionDB:
    """Carga de asistencia del evento (HU-24) con los socios que fueron.

    Solo una carga `SUCCESSFUL` deja asistencias definitivas; en cualquier otro estado la
    carga existe pero no hay filas en `asistencias`, igual que en el sistema real.
    """
    carga = CargaParticipacionDB(
        club_id=event.club_id,
        tipo="asistencia",
        origen="club",
        carga_id_externo=f"carga-{uuid.uuid4().hex[:8]}",
        evento_id_externo=event.id_externo,
        estado=estado.value,
    )
    db.add(carga)
    db.flush()
    if estado == EstadoCargaParticipacion.SUCCESSFUL:
        for socio in attendees:
            db.add(
                AsistenciaDB(
                    club_id=event.club_id,
                    evento_id_externo=event.id_externo,
                    dni=socio.dni,
                    numero_socio=socio.numero_socio,
                    carga_id=carga.id,
                )
            )
    db.commit()
    return carga

def make_activity(
    db: Session, socio: Socio, *, tipo: str, desde: date, hasta: date
) -> ActividadRecurrenteDB:
    """Registro de actividad recurrente del socio (HU-24), con su carga exitosa."""
    carga = CargaParticipacionDB(
        club_id=socio.club_id,
        tipo="actividades",
        origen="club",
        carga_id_externo=f"carga-{uuid.uuid4().hex[:8]}",
        estado=EstadoCargaParticipacion.SUCCESSFUL.value,
    )
    db.add(carga)
    db.flush()
    activity = ActividadRecurrenteDB(
        club_id=socio.club_id,
        dni=socio.dni,
        tipo=tipo,
        fecha_desde=desde,
        fecha_hasta=hasta,
        carga_id=carga.id,
    )
    db.add(activity)
    db.commit()
    return activity