"""HU-16: Desglose de componentes del puntaje para el Socio (Score Components Breakdown).

Escenarios de aceptación:
1. Componentes listados: asistencia – frecuencia, asistencia – distancia, participación
   institucional, antigüedad y edad, bonus nuevo socio, ajuste por tope.
2. Cada componente muestra los puntos sumados o restados con dos decimales.
3. La suma de los puntos coincide exactamente con el total.
4. Ajuste por tope negativo: signo menos y explicación de tope en 100.
5. Cifras subyacentes disponibles al expandir cada componente.
6. Mensaje informativo si el socio no está en el último ranking completado.
"""

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import (
    Ranking,
    RankingEntry,
    RankingState,
    RulesVersion,
    RulesVersionState,
    Socio,
    User,
    utcnow,
)
from app.scoring.catalog import SCORING_MODEL_V1
from tests.conftest import (
    BOCA_ID,
    MakeAdmin,
    MakeMember,
    Outbox,
    admin_token,
    bearer,
    member_token,
)
from tests.hu25_helpers import make_socio

URL = "/member/scoring/breakdown"
DEFAULTS = {p.key: str(p.default) for p in SCORING_MODEL_V1.parameters}


def create_completed_ranking(
    db: Session,
    club_id=BOCA_ID,
    *,
    version_number: int = 1,
    calculation_date: date | None = None,
) -> tuple[Ranking, RulesVersion]:
    """Crea una versión de reglas y un ranking en estado completado."""
    admin_user = db.query(User).first()
    admin_id = admin_user.id if admin_user else 1

    rules_version = RulesVersion(
        club_id=club_id,
        number=version_number,
        formula_id="scoring-model",
        formula_version=1,
        state=RulesVersionState.IN_FORCE,
        values=DEFAULTS,
        published_at=utcnow(),
        published_by_id=admin_id,
    )
    db.add(rules_version)
    db.flush()

    calc_date = calculation_date or date(2026, 10, 29)
    ranking = Ranking(
        club_id=club_id,
        rules_version_id=rules_version.id,
        status=RankingState.COMPLETED,
        calculation_date=calc_date,
        calculated_at=utcnow(),
        completed_at=utcnow(),
        population_size=1,
        requested_by_id=admin_id,
    )
    db.add(ranking)
    db.flush()
    return ranking, rules_version


def create_socio_with_entry(
    db: Session,
    ranking: Ranking,
    *,
    club_id=BOCA_ID,
    dni: str = "30111222",
    numero_socio: str = "SOC-101",
    attendance_frequency: Decimal = Decimal("25.00"),
    attendance_distance: Decimal = Decimal("15.50"),
    institutional: Decimal = Decimal("20.00"),
    seniority_age: Decimal = Decimal("10.00"),
    new_member_bonus: Decimal = Decimal("5.00"),
    cap_adjustment: Decimal = Decimal("0.00"),
    total: Decimal = Decimal("75.50"),
    inputs: dict | None = None,
) -> tuple[Socio, RankingEntry]:
    socio = make_socio(
        db,
        club_id=club_id,
        dni=dni,
        numero_socio=numero_socio,
        id_externo=numero_socio,
        distancia_km=Decimal("15.20"),
    )

    default_inputs = {
        "attendance": {
            "effective_start": "2025-01-01",
            "matches_by_class": {"A": 10, "B": 5, "C": 2},
            "attended_by_class": {"A": 8, "B": 3, "C": 1},
            "attended_matches": 12,
            "distance_km": "15.20",
        },
        "institutional": {
            "events": [{"event_id": "EV-1", "points": 10}],
            "event_points": 10,
            "activity_months": {"deporte_federado": 2},
            "activity_points": 10,
        },
        "membership": {
            "seniority_years": 6,
            "age_years": 36,
            "seniority_start": "2020-01-01",
            "days_since_alta": 2400,
        },
    }

    entry = RankingEntry(
        ranking_id=ranking.id,
        socio_id=socio.id,
        position=1,
        attendance_frequency=attendance_frequency,
        attendance_distance=attendance_distance,
        institutional=institutional,
        seniority_age=seniority_age,
        new_member_bonus=new_member_bonus,
        cap_adjustment=cap_adjustment,
        total=total,
        inputs=inputs if inputs is not None else default_inputs,
    )
    db.add(entry)
    db.commit()
    return socio, entry


# --- Tests de Escenarios de Aceptación -------------------------------------------


def test_breakdown_lists_all_six_components_with_exact_names(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    """Escenario 1: lista exactamente los seis componentes con nombres oficiales."""
    member_user = make_member(activated=True, club_id=BOCA_ID)
    ranking, _ = create_completed_ranking(db, BOCA_ID)
    create_socio_with_entry(
        db,
        ranking,
        club_id=BOCA_ID,
        dni=member_user.dni,
        numero_socio=member_user.member_id,
    )

    headers = bearer(member_token(client, outbox, member_user))
    response = client.get(URL, headers=headers)
    assert response.status_code == 200
    data = response.json()

    assert data["has_ranking"] is True
    assert data["message"] is None

    expected_names = [
        "asistencia – frecuencia",
        "asistencia – distancia",
        "participación institucional",
        "antigüedad y edad",
        "bonus nuevo socio",
        "ajuste por tope",
    ]
    returned_names = [comp["name"] for comp in data["components"]]
    assert returned_names == expected_names


def test_breakdown_shows_signed_points_with_two_decimals(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    """Escenario 2: cada componente muestra los puntos con dos decimales."""
    member_user = make_member(activated=True, club_id=BOCA_ID)
    ranking, _ = create_completed_ranking(db, BOCA_ID)
    create_socio_with_entry(
        db,
        ranking,
        club_id=BOCA_ID,
        dni=member_user.dni,
        numero_socio=member_user.member_id,
        attendance_frequency=Decimal("12.50"),
        attendance_distance=Decimal("0.00"),
        institutional=Decimal("20.00"),
        seniority_age=Decimal("4.25"),
        new_member_bonus=Decimal("0.00"),
        cap_adjustment=Decimal("0.00"),
        total=Decimal("36.75"),
    )

    headers = bearer(member_token(client, outbox, member_user))
    data = client.get(URL, headers=headers).json()

    for comp in data["components"]:
        assert "." in comp["points"]
        assert len(comp["points"].split(".")[1]) == 2


def test_breakdown_sum_equals_total(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    """Escenario 3: la suma de componentes coincide exactamente con el total."""
    member_user = make_member(activated=True, club_id=BOCA_ID)
    ranking, _ = create_completed_ranking(db, BOCA_ID)
    create_socio_with_entry(
        db,
        ranking,
        club_id=BOCA_ID,
        dni=member_user.dni,
        numero_socio=member_user.member_id,
        attendance_frequency=Decimal("30.20"),
        attendance_distance=Decimal("18.30"),
        institutional=Decimal("15.00"),
        seniority_age=Decimal("12.00"),
        new_member_bonus=Decimal("10.00"),
        cap_adjustment=Decimal("0.00"),
        total=Decimal("85.50"),
    )

    headers = bearer(member_token(client, outbox, member_user))
    data = client.get(URL, headers=headers).json()

    component_sum = sum(Decimal(comp["points"]) for comp in data["components"])
    total = Decimal(data["total"])
    assert component_sum == total == Decimal("85.50")


def test_negative_cap_adjustment_shows_minus_and_explanation(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    """Escenario 4: ajuste por tope negativo muestra signo menos y explicación de tope en 100."""
    member_user = make_member(activated=True, club_id=BOCA_ID)
    ranking, _ = create_completed_ranking(db, BOCA_ID)
    # Suma sin ajuste = 40 + 25 + 30 + 15 + 10 = 120 -> tope 100 -> ajuste = -20.00
    create_socio_with_entry(
        db,
        ranking,
        club_id=BOCA_ID,
        dni=member_user.dni,
        numero_socio=member_user.member_id,
        attendance_frequency=Decimal("40.00"),
        attendance_distance=Decimal("25.00"),
        institutional=Decimal("30.00"),
        seniority_age=Decimal("15.00"),
        new_member_bonus=Decimal("10.00"),
        cap_adjustment=Decimal("-20.00"),
        total=Decimal("100.00"),
    )

    headers = bearer(member_token(client, outbox, member_user))
    data = client.get(URL, headers=headers).json()

    cap_comp = next(c for c in data["components"] if c["key"] == "cap_adjustment")
    assert cap_comp["points"] == "-20.00"
    assert cap_comp["explanation"] is not None
    assert "100" in cap_comp["explanation"]


def test_component_expand_shows_supporting_figures(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    """Escenario 5: las cifras subyacentes están presentes para cada componente."""
    member_user = make_member(activated=True, club_id=BOCA_ID)
    ranking, _ = create_completed_ranking(db, BOCA_ID)
    create_socio_with_entry(
        db,
        ranking,
        club_id=BOCA_ID,
        dni=member_user.dni,
        numero_socio=member_user.member_id,
    )

    headers = bearer(member_token(client, outbox, member_user))
    data = client.get(URL, headers=headers).json()
    comps = {c["key"]: c for c in data["components"]}

    # Asistencia frecuencia
    freq_figures = comps["attendance_frequency"]["supporting_figures"]
    assert "matches_by_class" in freq_figures
    assert "attended_by_class" in freq_figures
    assert freq_figures["total_matches"] == 17
    assert freq_figures["total_attended"] == 12

    # Asistencia distancia
    dist_figures = comps["attendance_distance"]["supporting_figures"]
    assert dist_figures["distance_km"] == "15.20"
    assert dist_figures["attended_matches"] == 12

    # Institucional
    inst_figures = comps["institutional"]["supporting_figures"]
    assert inst_figures["event_points"] == 10
    assert inst_figures["activity_points"] == 10
    assert inst_figures["total_points_before_cap"] == 20

    # Antigüedad y edad
    sen_figures = comps["seniority_age"]["supporting_figures"]
    assert sen_figures["seniority_years"] == 6
    assert sen_figures["age_years"] == 36

    # Bonus nuevo socio
    bonus_figures = comps["new_member_bonus"]["supporting_figures"]
    assert bonus_figures["days_since_alta"] == 2400

    # Ajuste por tope
    cap_figures = comps["cap_adjustment"]["supporting_figures"]
    assert cap_figures["max_cap"] == "100.00"


def test_member_not_in_ranking_gets_informative_message(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    """Escenario 6: socio sin ranking completado recibe mensaje informativo."""
    member_user = make_member(activated=True, club_id=BOCA_ID)
    # No hay ranking creado

    headers = bearer(member_token(client, outbox, member_user))
    response = client.get(URL, headers=headers)
    assert response.status_code == 200
    data = response.json()

    assert data["has_ranking"] is False
    assert data["message"] is not None
    assert "ranking" in data["message"].lower()
    assert data["components"] == []


def test_zero_components_are_not_hidden(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    """Edge case: componentes en cero no se ocultan y muestran '0.00'."""
    member_user = make_member(activated=True, club_id=BOCA_ID)
    ranking, _ = create_completed_ranking(db, BOCA_ID)
    create_socio_with_entry(
        db,
        ranking,
        club_id=BOCA_ID,
        dni=member_user.dni,
        numero_socio=member_user.member_id,
        attendance_frequency=Decimal("0.00"),
        attendance_distance=Decimal("0.00"),
        institutional=Decimal("0.00"),
        seniority_age=Decimal("0.00"),
        new_member_bonus=Decimal("0.00"),
        cap_adjustment=Decimal("0.00"),
        total=Decimal("0.00"),
    )

    headers = bearer(member_token(client, outbox, member_user))
    data = client.get(URL, headers=headers).json()

    assert len(data["components"]) == 6
    for comp in data["components"]:
        assert comp["points"] == "0.00"


def test_breakdown_shows_rules_version_of_ranking(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    """Edge case: muestra la versión de reglas del ranking evaluado."""
    member_user = make_member(activated=True, club_id=BOCA_ID)
    ranking, _ = create_completed_ranking(db, BOCA_ID, version_number=3)
    create_socio_with_entry(
        db,
        ranking,
        club_id=BOCA_ID,
        dni=member_user.dni,
        numero_socio=member_user.member_id,
    )

    headers = bearer(member_token(client, outbox, member_user))
    data = client.get(URL, headers=headers).json()

    assert data["rules_version"] == 3


def test_breakdown_is_read_only_with_no_store(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    """FR-004: la información es de solo lectura y no se guarda en caché."""
    member_user = make_member(activated=True, club_id=BOCA_ID)
    ranking, _ = create_completed_ranking(db, BOCA_ID)
    create_socio_with_entry(
        db,
        ranking,
        club_id=BOCA_ID,
        dni=member_user.dni,
        numero_socio=member_user.member_id,
    )

    headers = bearer(member_token(client, outbox, member_user))
    response = client.get(URL, headers=headers)
    assert response.status_code == 200
    assert response.headers.get("Cache-Control") == "no-store"

    # Los métodos de modificación devuelven 405 Method Not Allowed
    assert client.post(URL, headers=headers).status_code == 405
    assert client.put(URL, headers=headers).status_code == 405
    assert client.delete(URL, headers=headers).status_code == 405


def test_breakdown_forbidden_for_admins_and_anonymous(
    client: TestClient, db: Session, outbox: Outbox, make_admin: MakeAdmin
) -> None:
    """Solo socios pueden acceder al desglose de socio."""
    # Anónimo: 401
    assert client.get(URL).status_code == 401

    # Admin: 403
    admin = make_admin(BOCA_ID)
    admin_headers = bearer(admin_token(client, outbox, admin))
    assert client.get(URL, headers=admin_headers).status_code == 403
