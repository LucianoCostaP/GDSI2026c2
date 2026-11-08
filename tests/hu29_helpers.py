"""Ayudas compartidas por los tests de HU-29: un club con socios variados y su ranking."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EventoVisibleDB, Ranking, Socio, User
from app.services import ranking_run_service
from tests.conftest import BOCA_ID
from tests.hu25_helpers import (
    DEFAULTS,
    load_attendance,
    make_activity,
    make_event,
    make_socio,
)

SIMULATOR = "/admin/rules-simulation"
# Momento fijo del cálculo: los dos rankings de una comparación usan la misma fecha.
NOW = datetime(2026, 10, 29, 15, 0, tzinfo=UTC)
# Cambia los cuatro factores: pesos de los pilares, αA, dsat y otros (Bmax).
CHANGED = {
    **DEFAULTS,
    "w_a": "0.5",
    "w_p": "0.3",
    "w_t": "0.2",
    "alpha_a": "0.4",
    "d_sat": "600",
    "b_max": "20",
}

# Lleva al socio de `add_star_newcomer` por encima de 100: hace falta el ajuste por tope.
TO_THE_CAP = {
    **DEFAULTS,
    "w_a": "0.6",
    "w_p": "0.3",
    "w_t": "0.1",
    "d_sat": "600",
    "b_max": "25",
    "t_max": "365",
}

# Concentra los puntajes: el desvío baja a menos del 80 % (alerta de concentración).
FLATTER = {**DEFAULTS, "w_a": "0.2", "w_p": "0.2", "w_t": "0.6"}


@dataclass
class VariedClub:
    """Socios con datos distintos, para que cambiar las reglas mueva el ranking."""

    far_fan: Socio
    near_fan: Socio
    veteran: Socio
    newcomer: Socio
    institutional: Socio
    # Mismos datos, distinto documento: el desempate final es el DNI (decisión 49).
    twin_low_dni: Socio
    twin_high_dni: Socio

    @property
    def socios(self) -> list[Socio]:
        return [
            self.far_fan,
            self.near_fan,
            self.veteran,
            self.newcomer,
            self.institutional,
            self.twin_low_dni,
            self.twin_high_dni,
        ]


def make_varied_club(db: Session) -> VariedClub:
    club = VariedClub(
        far_fan=make_socio(db, distancia_km=Decimal("900.00")),
        near_fan=make_socio(db, distancia_km=Decimal("5.00")),
        veteran=make_socio(
            db,
            fecha_nacimiento=date(1940, 5, 1),
            fecha_alta=date(1965, 1, 1),
            distancia_km=Decimal("15.00"),
        ),
        newcomer=make_socio(
            db,
            fecha_nacimiento=date(2000, 1, 1),
            fecha_alta=date(2026, 9, 15),
            distancia_km=Decimal("300.00"),
        ),
        institutional=make_socio(db, distancia_km=Decimal("40.00")),
        twin_low_dni=make_socio(db, dni="4000000", distancia_km=Decimal("60.00")),
        twin_high_dni=make_socio(db, dni="30000001", distancia_km=Decimal("60.00")),
    )
    matches = [
        make_event(db, id_externo=f"EVT-{c}", clase=c, when=NOW - timedelta(days=d))
        for c, d in (("A", 3), ("B", 10), ("C", 17))
    ]
    load_attendance(db, matches[0], [club.far_fan, club.near_fan, club.newcomer])
    load_attendance(db, matches[1], [club.far_fan, club.near_fan, club.veteran])
    load_attendance(db, matches[2], [club.near_fan])
    assembly = make_event(
        db,
        id_externo="EVT-ASAMBLEA",
        tipo="Institucional",
        clase=None,
        puntos=40,
        when=NOW - timedelta(days=20),
    )
    load_attendance(db, assembly, [club.institutional, club.veteran])
    make_activity(
        db,
        club.institutional,
        tipo="deporte_federado",
        desde=date(2025, 11, 1),
        hasta=date(2026, 10, 28),
    )
    return club


def run_ranking(db: Session, admin: User) -> Ranking:
    """Un cálculo de HU-25 en el momento fijo `NOW`, con las reglas vigentes."""
    return ranking_run_service.start_run(db, admin, BOCA_ID, now=NOW)


def add_star_newcomer(db: Session) -> Socio:
    """Un socio recién asociado que va a todo: lejos, a todos los partidos y a la asamblea, con
    deporte federado. Con las reglas por defecto queda debajo de 100; con `TO_THE_CAP`, arriba.
    Se agrega después de `make_varied_club`."""
    star = make_socio(
        db,
        fecha_nacimiento=date(1990, 1, 1),
        fecha_alta=date(2026, 10, 25),
        distancia_km=Decimal("900.00"),
    )
    for event in db.scalars(select(EventoVisibleDB)):
        load_attendance(db, event, [star])
    make_activity(
        db,
        star,
        tipo="deporte_federado",
        desde=date(2025, 11, 1),
        hasta=date(2026, 10, 28),
    )
    return star


def make_saturation_club(db: Session) -> None:
    """11 socios: el club variado (7), el socio estrella y dos grupos de empatados.

    Sin asistencias ni actividades, el total depende solo de las fechas: un socio común empata
    con los dos gemelos (grupo de 3) y dos socios con otra fecha de alta empatan entre sí
    (grupo de 2).
    """
    make_varied_club(db)
    add_star_newcomer(db)
    make_socio(db, distancia_km=Decimal("7.00"))
    make_socio(db, fecha_alta=date(2010, 3, 1))
    make_socio(db, fecha_alta=date(2010, 3, 1))
