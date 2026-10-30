"""Ayudas compartidas por los tests de HU-25 (un archivo por ciclo, mismos datos de prueba)."""

import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Ranking, RankingEntry, Socio, User
from app.scoring.catalog import SCORING_MODEL_V1
from tests.conftest import BOCA_ID, Outbox, admin_token, bearer

RUNS = "/admin/ranking/runs"
PUBLISH = "/admin/formulas/scoring-model/1/publish"
DEFAULTS = {p.key: str(p.default) for p in SCORING_MODEL_V1.parameters}


def headers_for(client: TestClient, outbox: Outbox, user: User) -> dict[str, str]:
    headers = bearer(admin_token(client, outbox, user))
    outbox.clear()
    return headers


def publish_rules(client: TestClient, headers: dict[str, str]) -> None:
    response = client.post(
        PUBLISH,
        json={
            "values": DEFAULTS,
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