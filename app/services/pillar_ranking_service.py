"""Rankings por pilar del ranking vigente (HU-44).

Se derivan al leerlos de las entradas que guardó HU-25: no se copia nada por socio ni se agrega
trabajo a la corrida, así que las tres tablas salen siempre de la misma corrida que el ranking
general. Nada se guarda ni se audita.
"""

import uuid
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Ranking, RankingEntry, RankingState, RulesVersion, Socio, utcnow
from ..schemas.ranking import (
    PillarRankingOut,
    PillarRankingRowOut,
    PillarRankingSourceOut,
    PillarRankingsOut,
)
from ..scoring.pillar_ranking import (
    PILLARS_BY_FORMULA,
    Pillar,
    PillarSource,
    PillarTop,
    top_by_pillar,
)
from .ranking_run_service import RUN_TIMEOUT, get_latest_run
from .ranking_service import get_ranking_in_force

NO_RANKING_MESSAGE = "Todavía no hay un ranking calculado."
PILLARS_NOT_DEFINED_MESSAGE = "La fórmula de este ranking no define rankings por pilar."
EMPTY_PILLAR_MESSAGE = "Ningún socio sumó puntos en este pilar en el último cálculo."

_COMPONENT_COLUMNS = {
    "attendance_frequency": RankingEntry.attendance_frequency,
    "attendance_distance": RankingEntry.attendance_distance,
    "institutional": RankingEntry.institutional,
    "seniority_age": RankingEntry.seniority_age,
}


def get_pillar_rankings(
    db: Session, club_id: uuid.UUID, now: datetime | None = None
) -> PillarRankingsOut:
    """El top 10 de cada pilar del ranking vigente del club.

    Mientras corre un cálculo (o si el último falló) se siguen mostrando las tablas del último
    completado; `updating` avisa que hay uno en curso.
    """
    updating = _is_updating(db, club_id, now or utcnow())
    ranking = get_ranking_in_force(db, club_id)
    if ranking is None or ranking.completed_at is None:
        return PillarRankingsOut(
            has_ranking=False, message=NO_RANKING_MESSAGE, updating=updating
        )

    rules = db.get_one(RulesVersion, ranking.rules_version_id)
    source = PillarRankingSourceOut(
        id=ranking.id,
        rules_version=rules.number,
        calculation_date=ranking.calculation_date,
        completed_at=ranking.completed_at,
    )
    pillars = PILLARS_BY_FORMULA.get(rules.formula_id)
    if pillars is None:
        return PillarRankingsOut(
            has_ranking=True,
            message=PILLARS_NOT_DEFINED_MESSAGE,
            updating=updating,
            ranking=source,
        )

    tops = top_by_pillar(pillars, _sources(db, ranking, pillars))
    socios = _socios(db, club_id, tops)
    return PillarRankingsOut(
        has_ranking=True,
        updating=updating,
        ranking=source,
        pillars=[_pillar_out(top, socios) for top in tops],
    )


def _is_updating(db: Session, club_id: uuid.UUID, now: datetime) -> bool:
    """Si la última corrida del club está en curso.

    Una corrida de más de 15 minutos cuenta como abandonada, igual que en
    `GET /admin/ranking/runs/latest`; acá solo se lee, no se la marca `failed`.
    """
    latest = get_latest_run(db, club_id)
    return (
        latest is not None
        and latest.status == RankingState.RUNNING
        and now - latest.calculated_at <= RUN_TIMEOUT
    )


def _sources(
    db: Session, ranking: Ranking, pillars: tuple[Pillar, ...]
) -> Iterator[PillarSource]:
    """Las entradas de la corrida con solo los componentes y desempates que hacen falta.

    No trae la instantánea entera: solo las tres claves del desempate (modelo de scoring,
    regla 4), para no leer el JSON completo de cada socio.
    """
    names = sorted({name for pillar in pillars for name in pillar.components})
    membership = RankingEntry.inputs["membership"]
    rows = db.execute(
        select(
            RankingEntry.socio_id,
            membership["seniority_start"].astext,
            membership["birth_date"].astext,
            RankingEntry.inputs["tiebreak"]["dni"].astext,
            *(_COMPONENT_COLUMNS[name] for name in names),
        ).where(RankingEntry.ranking_id == ranking.id)
    )
    for socio_id, seniority_start, birth_date, dni, *values in rows:
        yield PillarSource(
            socio_id=socio_id,
            components={
                name: Decimal(value) for name, value in zip(names, values, strict=True)
            },
            seniority_start=date.fromisoformat(seniority_start),
            birth_date=date.fromisoformat(birth_date),
            dni=dni,
        )


def _socios(
    db: Session, club_id: uuid.UUID, tops: list[PillarTop]
) -> dict[uuid.UUID, Socio]:
    """Nombre y número de socio, del padrón actual: la instantánea no los guarda."""
    ids = {row.socio_id for top in tops for row in top.rows}
    if not ids:
        return {}
    found = db.scalars(select(Socio).where(Socio.club_id == club_id, Socio.id.in_(ids)))
    return {socio.id: socio for socio in found}


def _pillar_out(top: PillarTop, socios: dict[uuid.UUID, Socio]) -> PillarRankingOut:
    return PillarRankingOut(
        key=top.pillar.key,
        name=top.pillar.name,
        rows=[
            PillarRankingRowOut(
                position=row.position,
                numero_socio=socios[row.socio_id].numero_socio,
                nombre=socios[row.socio_id].nombre,
                points=f"{row.points:.2f}",
            )
            for row in top.rows
        ],
        empty_message=None if top.rows else EMPTY_PILLAR_MESSAGE,
    )
