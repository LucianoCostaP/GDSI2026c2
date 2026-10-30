"""Insumos de antigüedad, edad y alta de un socio (modelo de scoring, 2.3 y 3; HU-25 FR-002).

Código puro: sin base de datos ni reloj. Convierte las fechas del padrón (nacimiento, alta y
baja previa) en los datos crudos que usa el motor (Ciclo 0) y que se guardan en la instantánea
de cada entrada.

- Antigüedad T: años cumplidos de pertenencia ininterrumpida. Se cuenta desde la fecha de alta
  y una baja previa reinicia el conteo: nunca se suma tiempo anterior a la baja.
- Edad E: años cumplidos a la fecha de cálculo.
- La fecha de nacimiento y la de inicio de la antigüedad también quedan en la instantánea: son
  las que usa el desempate del ranking (`ranking_order`).
- `t` del bono de nuevo socio: días desde la fecha de alta (no desde la baja).
- Carencia: días entre la baja previa y el alta actual (`days_between_previous_baja_and_alta`).
"""

from dataclasses import dataclass
from datetime import date
from typing import Any


def completed_years(since: date, until: date) -> int:
    """Años cumplidos entre dos fechas; 0 si `since` es posterior o igual a `until`.

    Un 29 de febrero se cumple el 1 de marzo en los años no bisiestos.
    """
    had_anniversary = (until.month, until.day) >= (since.month, since.day)
    return max(0, until.year - since.year - (0 if had_anniversary else 1))


def days_between_previous_baja_and_alta(
    previous_baja: date | None, alta: date
) -> int | None:
    """Días entre la baja previa del socio y su alta actual.

    Devuelve `None` si el socio nunca tuvo una baja. Una baja posterior al alta es un dato
    incoherente del club: cuenta como 0 días, así que el bono de nuevo socio no se otorga.
    """
    if previous_baja is None:
        return None
    return max(0, (alta - previous_baja).days)


@dataclass(frozen=True)
class MembershipInputs:
    """Datos crudos de pertenencia de un socio a la fecha de cálculo."""

    birth_date: date
    seniority_start: date
    seniority_years: int
    age_years: int
    days_since_alta: int
    days_between_previous_baja_and_alta: int | None

    def as_dict(self) -> dict[str, Any]:
        """Forma serializable (JSON) para la instantánea de la entrada."""
        return {
            "birth_date": self.birth_date.isoformat(),
            "seniority_start": self.seniority_start.isoformat(),
            "seniority_years": self.seniority_years,
            "age_years": self.age_years,
            "days_since_alta": self.days_since_alta,
            "days_between_previous_baja_and_alta": (
                self.days_between_previous_baja_and_alta
            ),
        }


def build_membership_inputs(
    *,
    birth_date: date,
    alta: date,
    previous_baja: date | None,
    calculation_date: date,
) -> MembershipInputs:
    """Arma los datos de pertenencia de un socio.

    La antigüedad arranca en el alta; si hay una baja previa posterior al alta (dato
    incoherente), arranca en la baja, porque una baja interrumpe la pertenencia.
    """
    seniority_start = alta if previous_baja is None else max(alta, previous_baja)
    return MembershipInputs(
        birth_date=birth_date,
        seniority_start=seniority_start,
        seniority_years=completed_years(seniority_start, calculation_date),
        age_years=completed_years(birth_date, calculation_date),
        days_since_alta=max(0, (calculation_date - alta).days),
        days_between_previous_baja_and_alta=days_between_previous_baja_and_alta(
            previous_baja, alta
        ),
    )