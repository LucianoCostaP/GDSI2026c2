"""Dataset de referencia del modelo de scoring (spec `scoring-model.md`, ejemplo trabajado).

Lo comparten los tests del motor (Ciclo 0), el de la simulación (HU-29) y la validación
contra el modelo (SC-004): un solo caso con el resultado conocido, 59,55.
"""

from decimal import Decimal

from app.scoring.engine import ScoringInputs

# Socio de 45 años y 10 de antigüedad, a 1200 km (= dsat), con 70 puntos institucionales.
REFERENCE_INPUTS = ScoringInputs(
    matches_by_class={"A": 4, "B": 10, "C": 6},
    attended_by_class={"A": 3, "B": 6, "C": 5},
    distance_km=Decimal(1200),
    institutional_points=Decimal(70),
    seniority_years=Decimal(10),
    age_years=Decimal(45),
    days_since_alta=3650,
)

REFERENCE_COMPONENTS = {
    "attendance_frequency": Decimal("34.19"),
    "attendance_distance": Decimal("4.41"),
    "institutional": Decimal("14.00"),
    "seniority_age": Decimal("6.95"),
    "new_member_bonus": Decimal("0.00"),
    "cap_adjustment": Decimal("0.00"),
}

REFERENCE_TOTAL = Decimal("59.55")
