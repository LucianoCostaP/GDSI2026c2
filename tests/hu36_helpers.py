"""Ayudas compartidas por los tests de las olas (HU-36) y de su cronograma (HU-37)."""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import (
    EventoVisibleDB,
    Ranking,
    RankingEntry,
    RankingState,
    Socio,
    User,
    utcnow,
)
from tests.conftest import BOCA_ID
from tests.hu25_helpers import make_event, make_ranking

DAY = timedelta(days=1)
HOUR = timedelta(hours=1)


def segmentation_url(event: EventoVisibleDB | str) -> str:
    event_id = event if isinstance(event, str) else event.id_interno
    return f"/admin/events/{event_id}/segmentation"


def partido(
    db: Session,
    *,
    when: datetime | None = None,
    tipo: str = "Partido",
    club_id: uuid.UUID = BOCA_ID,
) -> EventoVisibleDB:
    return make_event(
        db,
        id_externo=f"P-{uuid.uuid4().hex[:8]}",
        when=when or utcnow() + 10 * DAY,
        tipo=tipo,
        club_id=club_id,
    )


def ranking_with(
    db: Session, admin: User, socios: int, *, at: datetime | None = None
) -> Ranking:
    """Un ranking completado del club de Boca con `socios` posiciones."""
    moment = at or utcnow() - HOUR
    ranking = make_ranking(
        db, admin, RankingState.COMPLETED, calculated_at=moment, completed_at=moment
    )
    zero = Decimal("0.00")
    for position in range(1, socios + 1):
        suffix = uuid.uuid4().hex[:8]
        socio = Socio(
            club_id=BOCA_ID,
            id_externo=f"ext-{suffix}",
            dni=str(uuid.uuid4().int)[:8],
            numero_socio=f"N-{suffix}",
            nombre="Ana Socia",
            fecha_nacimiento=date(1980, 1, 1),
            fecha_alta=date(2015, 3, 1),
            estado_cuota="al_dia",
            email=f"{suffix}@example.com",
            distancia_km=Decimal("10.00"),
        )
        db.add(socio)
        db.flush()
        db.add(
            RankingEntry(
                ranking_id=ranking.id,
                socio_id=socio.id,
                position=position,
                attendance_frequency=zero,
                attendance_distance=zero,
                institutional=zero,
                seniority_age=zero,
                new_member_bonus=zero,
                cap_adjustment=zero,
                total=zero,
                inputs={},
            )
        )
    db.commit()
    return ranking


def generate(
    client: TestClient,
    headers: dict[str, str],
    event: EventoVisibleDB | str,
    confirmed: bool = False,
):
    return client.post(
        segmentation_url(event), json={"confirmed": confirmed}, headers=headers
    )


def code_of(response) -> str:
    return response.json()["detail"]["code"]
