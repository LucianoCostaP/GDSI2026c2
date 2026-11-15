"""Ayudas compartidas por los tests de HU-15 (historial de eventos y reglas aplicadas).

Reutiliza los datos de prueba de HU-25 (`tests/hu25_helpers.py`): socios del padrón, eventos
publicados, cargas de asistencia y publicación de reglas.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import EventoPendienteDB, Member, RulesVersion, Socio
from tests.conftest import (
    BOCA_ID,
    MakeMember,
    Outbox,
    bearer,
    member_token,
)
from tests.hu25_helpers import make_socio

HISTORY = "/member/events/history"
RULES = "/member/scoring/rules/{}"


@dataclass(frozen=True)
class SocioConCuenta:
    """Un socio del padrón del club y su cuenta activada, unidos por DNI (como en HU-14)."""

    socio: Socio
    member: Member


def uid(prefix: str) -> str:
    """Id externo único por test: la base de SQLite de los tests no vacía los eventos."""
    return f"{prefix}-{uuid.uuid4().hex[:6]}"


def titles(response: Any) -> list[str]:
    """Títulos de los eventos del historial, en el orden en que llegan."""
    return [event["titulo"] for event in response.json()["events"]]


def utc(text: str) -> datetime:
    """`"2026-03-10T20:00:00Z"` → datetime con zona UTC."""
    return datetime.fromisoformat(text)


def socio_with_account(
    db: Session,
    make_member: MakeMember,
    *,
    club_id: uuid.UUID = BOCA_ID,
    **socio_fields: object,
) -> SocioConCuenta:
    """Socio del padrón del club con su cuenta activada y el mismo DNI.

    La cuenta se crea antes que el socio, como en HU-14: en Postgres, el trigger
    `trg_sync_socio_to_member` crea un `members` por cada socio nuevo cuyo DNI no exista, y la
    cuenta creada después chocaría con ese DNI.
    """
    dni = str(socio_fields.pop("dni", str(uuid.uuid4().int)[:8]))
    member = make_member(activated=True, dni=dni, club_id=club_id)
    socio = make_socio(db, club_id=club_id, dni=dni, **socio_fields)
    return SocioConCuenta(socio=socio, member=member)


def member_headers(
    client: TestClient, outbox: Outbox, member: Member
) -> dict[str, str]:
    """Cabeceras con la sesión del socio (login con código, como en el resto de los tests)."""
    headers = bearer(member_token(client, outbox, member))
    outbox.clear()
    return headers


def backdate_rules(
    db: Session, number: int, when: datetime, *, club_id: uuid.UUID = BOCA_ID
) -> None:
    """Fija la fecha de publicación de una versión de reglas.

    La API publica con el reloj real; los escenarios necesitan versiones en fechas dadas.
    """
    db.execute(
        update(RulesVersion)
        .where(RulesVersion.club_id == club_id, RulesVersion.number == number)
        .values(published_at=when)
    )
    db.commit()


def make_historical_event(
    db: Session,
    *,
    id_externo: str,
    when: datetime,
    club_id: uuid.UUID = BOCA_ID,
    tipo: str = "Partido",
) -> EventoPendienteDB:
    """Evento histórico del club (enviado por el endpoint de históricos, HU-21)."""
    event = EventoPendienteDB(
        id_interno=f"HIST-{club_id}-{id_externo}",
        club_id=club_id,
        id_externo=id_externo,
        titulo=f"Histórico {id_externo}",
        fecha_hora=when,
        lugar="La Bombonera",
        tipo=tipo,
        es_historico=True,
        estado="Historico",
    )
    db.add(event)
    db.commit()
    return event
