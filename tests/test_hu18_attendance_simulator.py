"""HU-18: simulador de puntaje por asistencia (`docs/contrato-api-simulador.md`)."""

import math
import uuid
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import PasioDe10Exception
from app.models import (
    AuditLog,
    Club,
    EventoPendienteDB,
    Member,
    RankingEntry,
    RulesVersion,
    Socio,
    User,
    utcnow,
)
from app.schemas.simulator import SimulationOut
from app.scoring.engine import ScoringParameters, calculate_score
from app.scoring.position import PositionRange
from app.scoring.ranking_order import RankingCandidate, ranks_above
from app.scoring.snapshot import scoring_inputs_from_snapshot
from app.services import ranking_service, simulator_service
from tests.conftest import (
    BOCA_ID,
    RIVER_ID,
    MakeMember,
    Outbox,
    bearer,
    member_token,
)
from tests.hu25_helpers import (
    RUNS,
    adjust_rules,
    headers_for,
    load_attendance,
    make_event,
    make_socio,
    publish_rules,
)

URL = "/member/scoring/simulator/{}"


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    return headers_for(client, outbox, admin)


@pytest.fixture
def account(client: TestClient, outbox: Outbox, db: Session, make_member: MakeMember):
    """Crea un socio del padrón con su cuenta activada y devuelve `(socio, headers)`."""

    def make(*, club_id: uuid.UUID = BOCA_ID, **socio_fields) -> tuple[Socio, dict]:
        dni = socio_fields.pop("dni", str(uuid.uuid4().int)[:8])
        member = make_member(activated=True, dni=dni, club_id=club_id)
        socio = make_socio(db, club_id=club_id, dni=dni, **socio_fields)
        headers = bearer(member_token(client, outbox, member))
        outbox.clear()
        return socio, headers

    return make


def run(client: TestClient, headers: dict[str, str]) -> None:
    response = client.post(RUNS, headers=headers)
    assert response.status_code == 201, response.text


def entry_of(db: Session, socio: Socio) -> RankingEntry:
    ranking = ranking_service.get_ranking_in_force(db, socio.club_id)
    assert ranking is not None
    return db.scalars(
        select(RankingEntry).where(
            RankingEntry.ranking_id == ranking.id, RankingEntry.socio_id == socio.id
        )
    ).one()


def official_total(db: Session, entry: RankingEntry, **changes) -> str:
    """El motor único sobre la instantánea de la entrada, con los cambios indicados."""
    ranking = ranking_service.get_ranking_in_force(db, BOCA_ID)
    assert ranking is not None
    rules = db.get(RulesVersion, ranking.rules_version_id)
    assert rules is not None
    inputs = replace(scoring_inputs_from_snapshot(entry.inputs), **changes)
    total = calculate_score(inputs, ScoringParameters.from_values(rules.values)).total
    return f"{total:.2f}"


def upcoming(db: Session, id_externo: str, **fields):
    return make_event(
        db, id_externo=id_externo, when=utcnow() + timedelta(days=7), **fields
    )


# --- Escenario 1: se elige un evento y se simula solo ese -----------------------------------


def test_selecting_a_partido_starts_its_simulation(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    socio, headers = account()
    run(client, boca)
    event = upcoming(db, "P-1", clase="B")

    response = client.get(URL.format(event.id_interno), headers=headers)

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    entry = entry_of(db, socio)
    assert body["event"]["id"] == event.id_interno
    assert body["event"]["tipo"] == "Partido"
    assert body["event"]["puntos"] is None
    assert "clase" not in body["event"]
    assert body["ranking"]["rules_version"] == 1
    assert body["current"] == {
        "score": f"{entry.total:.2f}",
        "position": entry.position,
        "ranked_total": 1,
    }
    assert body["attend"]["score"] == official_total(
        db,
        entry,
        matches_by_class={"A": 0, "B": 1, "C": 0},
        attended_by_class={"A": 0, "B": 1, "C": 0},
    )
    assert body["not_attend"]["score"] == official_total(
        db,
        entry,
        matches_by_class={"A": 0, "B": 1, "C": 0},
    )
    for hypothesis in ("attend", "not_attend"):
        expected = Decimal(body[hypothesis]["score"]) - entry.total
        assert body[hypothesis]["difference"] == f"{expected:.2f}"
        assert body[hypothesis]["position"] is None
    assert body["position_estimate"]["code"] == "POSITION_NOT_AVAILABLE"


def test_the_simulation_covers_only_the_selected_event(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    socio, headers = account()
    run(client, boca)
    selected = upcoming(db, "P-1", clase="C")
    upcoming(db, "P-2", clase="A")
    upcoming(db, "I-1", tipo="Institucional", clase=None, puntos=40)

    body = client.get(URL.format(selected.id_interno), headers=headers).json()

    # Solo el Partido elegido (clase C): ni el otro Partido ni los puntos institucionales.
    entry = entry_of(db, socio)
    assert body["attend"]["score"] == official_total(
        db,
        entry,
        matches_by_class={"A": 0, "B": 0, "C": 1},
        attended_by_class={"A": 0, "B": 0, "C": 1},
    )
    assert body["not_attend"]["score"] == official_total(
        db, entry, matches_by_class={"A": 0, "B": 0, "C": 1}
    )


def test_selecting_an_institutional_event_adds_only_its_points(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    socio, headers = account()
    run(client, boca)
    event = upcoming(db, "I-1", tipo="Institucional", clase=None, puntos=40)

    body = client.get(URL.format(event.id_interno), headers=headers).json()

    entry = entry_of(db, socio)
    assert body["event"]["tipo"] == "Evento institucional/amateur"
    assert body["event"]["puntos"] == 40
    base = scoring_inputs_from_snapshot(entry.inputs)
    assert body["attend"]["score"] == official_total(
        db, entry, institutional_points=base.institutional_points + 40
    )
    assert body["not_attend"] == {
        "score": f"{entry.total:.2f}",
        "difference": "0.00",
        "position": None,
    }
    assert body["position_estimate"]["reason"] == "INSTITUTIONAL_NOT_ESTIMATED"


def test_simulating_does_not_change_the_real_score(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    socio, headers = account()
    run(client, boca)
    event = upcoming(db, "P-1")
    before = entry_of(db, socio)
    total, inputs = before.total, dict(before.inputs)

    for _ in range(3):
        assert (
            client.get(URL.format(event.id_interno), headers=headers).status_code == 200
        )

    db.expire_all()
    after = entry_of(db, socio)
    assert (after.total, after.inputs) == (total, inputs)


def test_an_event_of_another_club_is_not_found(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    _, headers = account()
    run(client, boca)
    foreign = upcoming(db, "P-1", club_id=RIVER_ID)

    for event_id in (foreign.id_interno, "no-existe"):
        response = client.get(URL.format(event_id), headers=headers)
        assert response.status_code == 404
        assert response.json()["detail"] == {
            "code": "EVENT_NOT_FOUND",
            "message": "No encontramos el evento.",
        }


# --- Escenario 2: un socio fuera del ranking no puede simular -------------------------------

STATUS_URL = "/member/scoring/simulator"
NOT_IN_RANKING = {
    "code": "NOT_IN_RANKING",
    "message": "Para simular necesitás un puntaje calculado. "
    "Todavía no estás en el ranking.",
}


@pytest.fixture
def outside_ranking(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    boca: dict[str, str],
    account,
    make_member: MakeMember,
):
    """Arma cada caso del escenario 2 y devuelve los headers del socio que consulta."""

    def make(case: str) -> dict[str, str]:
        publish_rules(client, boca)
        if case == "no_ranking":
            return account()[1]
        account()  # alguien del club, para que el ranking tenga población
        if case == "joined_after":
            run(client, boca)
            return account()[1]
        if case == "fees_overdue":
            socio, headers = account()
            run(client, boca)
            socio.estado_cuota = "moroso"
            db.commit()
            return headers
        assert case == "not_in_roster"
        run(client, boca)
        member = make_member(activated=True, dni="99999999", club_id=BOCA_ID)
        headers = bearer(member_token(client, outbox, member))
        outbox.clear()
        return headers

    return make


CASES = ("no_ranking", "joined_after", "fees_overdue", "not_in_roster")


@pytest.mark.parametrize("case", CASES)
def test_opening_the_simulator_outside_the_ranking_shows_the_message(
    client: TestClient, outside_ranking, case: str
) -> None:
    headers = outside_ranking(case)

    response = client.get(STATUS_URL, headers=headers)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "status": "unavailable",
        "reason": NOT_IN_RANKING["code"],
        "message": NOT_IN_RANKING["message"],
        "ranking": None,
    }


@pytest.mark.parametrize("case", CASES)
def test_simulating_an_event_outside_the_ranking_is_rejected(
    client: TestClient, db: Session, outside_ranking, case: str
) -> None:
    headers = outside_ranking(case)
    event = upcoming(db, "P-1")

    response = client.get(URL.format(event.id_interno), headers=headers)

    assert response.status_code == 409
    assert response.json()["detail"] == NOT_IN_RANKING


def test_a_ranked_socio_can_open_the_simulator(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    socio, headers = account()
    run(client, boca)

    body = client.get(STATUS_URL, headers=headers).json()

    ranking = ranking_service.get_ranking_in_force(db, socio.club_id)
    assert ranking is not None and ranking.completed_at is not None
    assert body["status"] == "available"
    assert body["reason"] is None and body["message"] is None
    assert body["ranking"]["rules_version"] == 1
    assert body["ranking"]["calculation_date"] == ranking.calculation_date.isoformat()


def test_an_admin_cannot_open_the_simulator(
    client: TestClient, boca: dict[str, str]
) -> None:
    assert client.get(STATUS_URL, headers=boca).status_code == 403


# --- Escenario 3: un evento no publicado o ya empezado no se simula -------------------------

NOT_SIMULABLE = {
    "code": "EVENT_NOT_SIMULABLE",
    "message": "Este evento ya no está disponible para simular.",
}


@pytest.fixture
def no_calculation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Falla si el simulador llega a calcular un puntaje ("nothing is calculated")."""

    def fail(*_args, **_kwargs):
        raise AssertionError("No se tenía que calcular nada.")

    monkeypatch.setattr(simulator_service, "calculate_score", fail)


def user_of(db: Session, socio: Socio) -> User:
    return db.scalars(
        select(User)
        .join(Member, Member.member_id == User.member_id)
        .where(Member.dni == socio.dni)
    ).one()


def test_an_event_that_already_started_is_not_simulable(
    client: TestClient, db: Session, boca: dict[str, str], account, no_calculation
) -> None:
    publish_rules(client, boca)
    _, headers = account()
    run(client, boca)
    started = make_event(db, id_externo="P-1", when=utcnow() - timedelta(minutes=1))

    response = client.get(URL.format(started.id_interno), headers=headers)

    assert response.status_code == 409
    assert response.json()["detail"] == NOT_SIMULABLE


def test_an_unpublished_event_is_not_simulable(
    client: TestClient, db: Session, boca: dict[str, str], account, no_calculation
) -> None:
    publish_rules(client, boca)
    _, headers = account()
    run(client, boca)
    pending = EventoPendienteDB(
        id_interno="INT-pendiente",
        club_id=BOCA_ID,
        id_externo="P-pendiente",
        titulo="Partido sin publicar",
        fecha_hora=utcnow() + timedelta(days=7),
        lugar="La Bombonera",
        tipo="Partido",
    )
    db.add(pending)
    db.commit()

    response = client.get(URL.format(pending.id_interno), headers=headers)

    assert response.status_code == 409
    assert response.json()["detail"] == NOT_SIMULABLE


def test_an_unpublished_event_of_another_club_is_not_found(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    _, headers = account()
    run(client, boca)
    db.add(
        EventoPendienteDB(
            id_interno="INT-river",
            club_id=RIVER_ID,
            id_externo="P-river",
            titulo="Partido de otro club",
            fecha_hora=utcnow() + timedelta(days=7),
            lugar="Monumental",
            tipo="Partido",
        )
    )
    db.commit()

    response = client.get(URL.format("INT-river"), headers=headers)

    assert response.status_code == 404


def test_the_start_of_the_event_is_the_limit(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    """Con el reloj inyectado: se simula hasta antes del inicio, no desde el inicio."""
    publish_rules(client, boca)
    socio, _ = account()
    run(client, boca)
    event = upcoming(db, "P-1")
    user = user_of(db, socio)
    start = event.fecha_hora

    before = simulator_service.simulate_event(
        db, user, BOCA_ID, event.id_interno, now=start - timedelta(seconds=1)
    )
    assert before.event.id == event.id_interno
    for moment in (start, start + timedelta(seconds=1)):
        with pytest.raises(PasioDe10Exception) as error:
            simulator_service.simulate_event(
                db, user, BOCA_ID, event.id_interno, now=moment
            )
        assert error.value.code == "EVENT_NOT_SIMULABLE"
        assert error.value.status_code == 409


# --- Ayudas de los escenarios 4 a 7: historial real cargado antes del cálculo ---------------


def past_match(db: Session, id_externo: str, attendees: list[Socio], clase: str = "B"):
    """Partido ya jugado del club, con su asistencia cargada (cuenta para el ranking)."""
    event = make_event(
        db, id_externo=id_externo, when=utcnow() - timedelta(days=3), clase=clase
    )
    load_attendance(db, event, attendees)


def past_assembly(db: Session, id_externo: str, attendees: list[Socio], puntos: int):
    """Evento institucional ya realizado, con su asistencia cargada."""
    event = make_event(
        db,
        id_externo=id_externo,
        when=utcnow() - timedelta(days=3),
        tipo="Institucional",
        clase=None,
        puntos=puntos,
    )
    load_attendance(db, event, attendees)


def simulate(client: TestClient, headers: dict[str, str], event) -> dict:
    response = client.get(URL.format(event.id_interno), headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def components_of(db: Session, entry: RankingEntry, **changes) -> dict[str, Decimal]:
    """Componentes del motor único sobre la instantánea, con los cambios indicados."""
    ranking = ranking_service.get_ranking_in_force(db, BOCA_ID)
    assert ranking is not None
    rules = db.get(RulesVersion, ranking.rules_version_id)
    assert rules is not None
    inputs = replace(scoring_inputs_from_snapshot(entry.inputs), **changes)
    params = ScoringParameters.from_values(rules.values)
    return calculate_score(inputs, params).components


# --- Escenario 4: un Partido al que asiste suma a asistidos y totales, con su factor --------


def test_attending_a_partido_adds_it_to_attended_and_total_of_its_class(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    socio, headers = account()
    past_match(db, "H-1", [socio])
    past_match(db, "H-2", [])
    run(client, boca)
    entry = entry_of(db, socio)
    attendance = entry.inputs["attendance"]
    assert attendance["matches_by_class"] == {"A": 0, "B": 2, "C": 0}
    assert attendance["attended_by_class"] == {"A": 0, "B": 1, "C": 0}

    body = simulate(client, headers, upcoming(db, "P-1", clase="B"))

    assert body["attend"]["score"] == official_total(
        db,
        entry,
        matches_by_class={"A": 0, "B": 3, "C": 0},
        attended_by_class={"A": 0, "B": 2, "C": 0},
    )
    # De 1 de 2 a 2 de 3: la frecuencia sube y el puntaje también.
    assert Decimal(body["attend"]["score"]) > entry.total
    assert Decimal(body["attend"]["difference"]) > 0


def test_the_class_factor_of_the_partido_changes_the_projection(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    socio, headers = account()
    past_match(db, "H-1", [socio], clase="B")
    past_match(db, "H-2", [], clase="B")
    run(client, boca)
    entry = entry_of(db, socio)

    scores = {
        clase: simulate(client, headers, upcoming(db, f"P-{clase}", clase=clase))
        for clase in ("A", "C")
    }

    for clase, body in scores.items():
        matches = {"A": 0, "B": 2, "C": 0}
        attended = {"A": 0, "B": 1, "C": 0}
        matches[clase] += 1
        attended[clase] += 1
        assert body["attend"]["score"] == official_total(
            db, entry, matches_by_class=matches, attended_by_class=attended
        )
        # La clase se usa en el cálculo pero no viaja en la respuesta.
        assert "clase" not in body["event"] and "factor" not in body["event"]
    # C pesa 1,8 y A 1,0: asistir a un partido de clase C sube más la frecuencia.
    assert Decimal(scores["C"]["attend"]["score"]) > Decimal(
        scores["A"]["attend"]["score"]
    )


def test_the_first_attended_partido_turns_on_the_distance_term(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    """Sin partidos asistidos el término de distancia es 0; asistir lo recalcula."""
    publish_rules(client, boca)
    socio, headers = account(distancia_km=Decimal("1500.00"))
    past_match(db, "H-1", [])
    run(client, boca)
    entry = entry_of(db, socio)
    assert entry.attendance_distance == 0

    body = simulate(client, headers, upcoming(db, "P-1", clase="B"))

    matches = {"A": 0, "B": 2, "C": 0}
    attend = components_of(
        db, entry, matches_by_class=matches, attended_by_class={"A": 0, "B": 1, "C": 0}
    )
    assert attend["attendance_distance"] > 0
    assert body["attend"]["score"] == f"{sum(attend.values()):.2f}"


# --- Escenario 5: si no asiste, el Partido suma solo a los totales y la frecuencia baja -----


def test_not_attending_a_partido_adds_it_only_to_the_total(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    socio, headers = account()
    past_match(db, "H-1", [socio])
    past_match(db, "H-2", [])
    run(client, boca)
    entry = entry_of(db, socio)

    body = simulate(client, headers, upcoming(db, "P-1", clase="B"))

    assert body["not_attend"]["score"] == official_total(
        db, entry, matches_by_class={"A": 0, "B": 3, "C": 0}
    )
    # De 1 de 2 a 1 de 3: la frecuencia cae y el puntaje queda por debajo del actual.
    not_attend = components_of(db, entry, matches_by_class={"A": 0, "B": 3, "C": 0})
    assert not_attend["attendance_frequency"] < entry.attendance_frequency
    assert Decimal(body["not_attend"]["score"]) < entry.total
    assert body["not_attend"]["difference"].startswith("-")
    assert Decimal(body["attend"]["score"]) >= Decimal(body["not_attend"]["score"])


# --- Escenario 6: un institucional suma sus puntos antes del tope Pinst_max -----------------


def test_institutional_points_are_added_before_the_cap(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca, p_inst_max="50")
    socio, headers = account()
    past_assembly(db, "H-1", [socio], puntos=40)
    run(client, boca)
    entry = entry_of(db, socio)
    assert entry.inputs["institutional"]["points"] == 40

    body = simulate(
        client,
        headers,
        upcoming(db, "I-1", tipo="Institucional", clase=None, puntos=40),
    )

    # 40 + 40 = 80 puntos crudos, pero el tope es 50: gana 10 puntos, no 40 (wP = 0,20).
    assert body["attend"]["score"] == official_total(
        db, entry, institutional_points=Decimal(80)
    )
    assert body["attend"]["difference"] == "2.00"
    assert body["not_attend"]["difference"] == "0.00"


def test_at_the_cap_attending_an_institutional_event_adds_nothing(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca, p_inst_max="50")
    socio, headers = account()
    past_assembly(db, "H-1", [socio], puntos=40)
    past_assembly(db, "H-2", [socio], puntos=40)
    run(client, boca)
    entry = entry_of(db, socio)

    body = simulate(
        client,
        headers,
        upcoming(db, "I-1", tipo="Institucional", clase=None, puntos=40),
    )

    current = f"{entry.total:.2f}"
    assert body["attend"] == {"score": current, "difference": "0.00", "position": None}
    assert body["not_attend"] == body["attend"]


# --- Escenario 7: actual, proyecciones y diferencias, topeadas en 100 -----------------------


def test_the_projection_is_capped_at_100(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    """Un socio nuevo con bono, edad al máximo y lejos del estadio: asistir pasaría de 100."""
    publish_rules(client, boca, alpha_t="0", e_ref="40", b_max="25.0")
    socio, headers = account(
        fecha_alta=date.today() - timedelta(days=10),
        distancia_km=Decimal("3000.00"),
    )
    run(client, boca)
    entry = entry_of(db, socio)
    assert entry.total < 100

    body = simulate(client, headers, upcoming(db, "P-1", clase="B"))

    attend = components_of(
        db,
        entry,
        matches_by_class={"A": 0, "B": 1, "C": 0},
        attended_by_class={"A": 0, "B": 1, "C": 0},
    )
    assert attend["cap_adjustment"] < 0  # sin el tope pasaría de 100
    assert body["attend"]["score"] == "100.00"
    assert body["attend"]["difference"] == f"{100 - entry.total:.2f}"


def test_the_simulation_shows_current_projections_and_differences(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    socio, headers = account()
    past_match(db, "H-1", [socio])
    past_match(db, "H-2", [])
    run(client, boca)
    entry = entry_of(db, socio)

    body = simulate(client, headers, upcoming(db, "P-1"))

    assert Decimal(body["current"]["score"]) == entry.total
    for hypothesis in ("attend", "not_attend"):
        score = Decimal(body[hypothesis]["score"])
        assert Decimal(0) <= score <= Decimal(100)
        assert body[hypothesis]["difference"] == f"{score - entry.total:.2f}"


# --- Escenario 8: versión de reglas del ranking y aviso si las vigentes son otras -----------

RULES_AHEAD = {
    "code": "RULES_AHEAD_OF_RANKING",
    "message": "Esta simulación usa las reglas del último ranking (versión 1). Las reglas "
    "vigentes se aplicarán desde el próximo cálculo.",
}


def test_the_simulation_shows_the_rules_version_and_date_of_the_ranking(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    socio, headers = account()
    run(client, boca)

    body = simulate(client, headers, upcoming(db, "P-1"))

    ranking = ranking_service.get_ranking_in_force(db, socio.club_id)
    assert ranking is not None and ranking.completed_at is not None
    assert body["ranking"]["rules_version"] == 1
    assert body["ranking"]["calculation_date"] == ranking.calculation_date.isoformat()
    assert body["ranking"]["completed_at"] is not None
    # Mismas reglas vigentes que las del ranking: no hay aviso.
    assert body["rules_notice"] is None


def test_new_rules_in_force_are_announced_and_not_used(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    socio, headers = account()
    run(client, boca)
    adjust_rules(client, boca, expected_rules_version=1, alpha_a="0.50")
    entry = entry_of(db, socio)
    event = upcoming(db, "P-1", clase="B")

    body = simulate(client, headers, event)

    assert body["ranking"]["rules_version"] == 1
    assert body["rules_notice"] == RULES_AHEAD
    # Los puntajes salen de las reglas del ranking (versión 1), no de las vigentes.
    one_match = {"A": 0, "B": 1, "C": 0}
    assert body["attend"]["score"] == official_total(
        db, entry, matches_by_class=one_match, attended_by_class=one_match
    )
    in_force = db.scalars(
        select(RulesVersion).where(
            RulesVersion.club_id == BOCA_ID, RulesVersion.number == 2
        )
    ).one()
    with_new_rules = calculate_score(
        replace(
            scoring_inputs_from_snapshot(entry.inputs),
            matches_by_class=one_match,
            attended_by_class=one_match,
        ),
        ScoringParameters.from_values(in_force.values),
    ).total
    assert body["attend"]["score"] != f"{with_new_rules:.2f}"


def test_the_notice_disappears_after_a_ranking_with_the_new_rules(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    _, headers = account()
    run(client, boca)
    adjust_rules(client, boca, expected_rules_version=1, alpha_a="0.50")
    run(client, boca)

    body = simulate(client, headers, upcoming(db, "P-1"))

    assert body["ranking"]["rules_version"] == 2
    assert body["rules_notice"] is None


# --- Escenario 9: las proyecciones usan la distancia actual del padrón ----------------------


def move_home(db: Session, socio: Socio, km: str) -> None:
    """El club manda una distancia nueva para el socio (HU-43) después del ranking."""
    socio.distancia_km = Decimal(km)
    db.commit()


def test_the_projections_use_the_current_distance(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    socio, headers = account(distancia_km=Decimal("1200.00"))
    past_match(db, "H-1", [socio])
    run(client, boca)
    move_home(db, socio, "850.00")
    entry = entry_of(db, socio)

    body = simulate(client, headers, upcoming(db, "P-1", clase="B"))

    assert body["distance"] == {
        "used_km": "850.00",
        "ranking_km": "1200.00",
        "changed": True,
        "notice": "Tu distancia al estadio cambió desde el último ranking: la simulación "
        "usa 850 km y tu puntaje de hoy usa 1200 km.",
    }
    near = Decimal("850.00")
    assert body["attend"]["score"] == official_total(
        db,
        entry,
        distance_km=near,
        matches_by_class={"A": 0, "B": 2, "C": 0},
        attended_by_class={"A": 0, "B": 2, "C": 0},
    )
    assert body["not_attend"]["score"] == official_total(
        db,
        entry,
        distance_km=near,
        matches_by_class={"A": 0, "B": 2, "C": 0},
        attended_by_class={"A": 0, "B": 1, "C": 0},
    )


def test_the_current_score_and_position_keep_the_ranking_distance(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    socio, headers = account(distancia_km=Decimal("1200.00"))
    past_match(db, "H-1", [socio])
    run(client, boca)
    entry = entry_of(db, socio)
    total, position = entry.total, entry.position
    move_home(db, socio, "850.00")

    body = simulate(client, headers, upcoming(db, "P-1"))

    assert body["current"]["score"] == f"{total:.2f}"
    assert body["current"]["position"] == position
    # La diferencia se toma contra el puntaje del ranking: incluye el cambio de distancia.
    for hypothesis in ("attend", "not_attend"):
        expected = Decimal(body[hypothesis]["score"]) - total
        assert body[hypothesis]["difference"] == f"{expected:.2f}"
    # Nada se guarda: la instantánea del ranking sigue con la distancia anterior.
    db.expire_all()
    assert entry_of(db, socio).inputs["attendance"]["distance_km"] == "1200.00"


def test_without_a_change_of_home_there_is_no_notice(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    _, headers = account(distancia_km=Decimal("1200.00"))
    run(client, boca)

    body = simulate(client, headers, upcoming(db, "P-1"))

    assert body["distance"] == {
        "used_km": "1200.00",
        "ranking_km": "1200.00",
        "changed": False,
        "notice": None,
    }


def test_a_distance_with_decimals_is_shown_with_a_decimal_comma(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    socio, headers = account(distancia_km=Decimal("12.00"))
    run(client, boca)
    move_home(db, socio, "7.50")

    body = simulate(client, headers, upcoming(db, "P-1"))

    assert body["distance"]["notice"] == (
        "Tu distancia al estadio cambió desde el último ranking: la simulación usa "
        "7,5 km y tu puntaje de hoy usa 12 km."
    )


# --- Escenario 10: posición estimada de un Partido, con rango y etiqueta --------------------

ESTIMATE_LABEL = (
    "Estimación: supone que cada socio asiste según su propio historial. Puede diferir "
    "después del próximo cálculo."
)


def projection_on(db: Session, **settings) -> None:
    """El equipo enciende la proyección del club (después de la validación offline)."""
    club = db.get(Club, BOCA_ID)
    assert club is not None
    club.position_projection_enabled = True
    for field, value in settings.items():
        setattr(club, field, value)
    db.commit()


def expected_positions(
    db: Session, me: Socio, match_class: str, hypotheses: dict[str, str]
) -> dict[str, tuple[int, int, int]]:
    """Oráculo del "Position model" del spec, escrito a partir de sus fórmulas."""
    ranking = ranking_service.get_ranking_in_force(db, BOCA_ID)
    assert ranking is not None
    rows = db.execute(
        select(RankingEntry, Socio)
        .join(Socio, Socio.id == RankingEntry.socio_id)
        .where(RankingEntry.ranking_id == ranking.id)
    ).all()
    attended = sum(
        e.inputs["attendance"]["attended_by_class"][match_class] for e, _ in rows
    )
    counted = sum(
        e.inputs["attendance"]["matches_by_class"][match_class] for e, _ in rows
    )
    rate = Fraction(attended, counted)

    def candidate(entry: RankingEntry, socio: Socio, total: str) -> RankingCandidate:
        membership = entry.inputs["membership"]
        return RankingCandidate(
            socio_id=socio.id,
            total=Decimal(total),
            seniority_start=date.fromisoformat(membership["seniority_start"]),
            birth_date=date.fromisoformat(membership["birth_date"]),
            dni=socio.dni,
        )

    my_entry = entry_of(db, me)
    result = {}
    for name, my_total in hypotheses.items():
        own = candidate(my_entry, me, my_total)
        mu, variance = Fraction(0), Fraction(0)
        for entry, socio in rows:
            if socio.id == me.id:
                continue
            history = entry.inputs["attendance"]
            matches = dict(history["matches_by_class"])
            matches[match_class] += 1
            went = dict(history["attended_by_class"])
            went[match_class] += 1
            a_total = official_total(
                db, entry, matches_by_class=matches, attended_by_class=went
            )
            b_total = official_total(db, entry, matches_by_class=matches)
            a_above = ranks_above(candidate(entry, socio, a_total), own)
            b_above = ranks_above(candidate(entry, socio, b_total), own)
            p = (history["attended_by_class"][match_class] + 5 * rate) / (
                history["matches_by_class"][match_class] + 5
            )
            mu += p * a_above + (1 - p) * b_above
            if a_above and not b_above:
                variance += p * (1 - p)
        center = 1 + mu
        spread = 1.2815515655446004 * math.sqrt(variance)
        result[name] = (
            math.floor(center + Fraction(1, 2)),
            max(1, math.floor(float(center) - spread)),
            min(ranking.population_size, math.ceil(float(center) + spread)),
        )
    return result


@pytest.fixture
def club_with_history(db: Session, account):
    """Ocho socios con historiales distintos en 4 Partidos Clase B; devuelve el que consulta."""
    me, headers = account(fecha_alta=date(2015, 3, 1))
    others = [
        make_socio(db, fecha_alta=date(2010 + i, 1, 1), dni=f"{20000000 + i}")
        for i in range(7)
    ]
    went = {
        "H-1": [me, *others[:6]],
        "H-2": [me, *others[:4]],
        "H-3": [*others[:3], others[5]],
        "H-4": [others[0], others[6]],
    }
    for id_externo, attendees in went.items():
        past_match(db, id_externo, attendees)
    return me, headers


def test_a_partido_shows_an_estimated_position_with_range_and_label(
    client: TestClient, db: Session, boca: dict[str, str], club_with_history
) -> None:
    publish_rules(client, boca)
    me, headers = club_with_history
    run(client, boca)
    projection_on(db, position_min_population=2)
    entry = entry_of(db, me)

    body = simulate(client, headers, upcoming(db, "P-1", clase="B"))

    assert body["current"] == {
        "score": f"{entry.total:.2f}",
        "position": entry.position,
        "ranked_total": 8,
    }
    assert body["position_estimate"] == {
        "status": "estimated",
        "code": None,
        "reason": None,
        "message": None,
        "label": ESTIMATE_LABEL,
        "range_level": "0.80",
    }
    expected = expected_positions(
        db,
        me,
        "B",
        {"attend": body["attend"]["score"], "not_attend": body["not_attend"]["score"]},
    )
    for hypothesis in ("attend", "not_attend"):
        estimate, lower, upper = expected[hypothesis]
        position = body[hypothesis]["position"]
        assert (position["estimate"], position["lower"], position["upper"]) == (
            estimate,
            lower,
            upper,
        )
        assert 1 <= lower <= estimate <= upper <= 8
        if lower == upper:
            assert position["text"] == f"puesto estimado {estimate}"
        else:
            assert position["text"] == (
                f"puesto estimado {estimate} (probable entre {lower} y {upper})"
            )
    # Asistir nunca da una posición peor que no asistir (SC-004).
    assert (
        body["attend"]["position"]["estimate"]
        <= body["not_attend"]["position"]["estimate"]
    )
    # Nada de otros socios en la respuesta (FR-009).
    assert "others" not in body and "probability" not in str(body)


def test_some_rival_makes_the_range_wider_than_one_place(
    client: TestClient, db: Session, boca: dict[str, str], club_with_history
) -> None:
    """Con socios cerca del puntaje, la posición es un rango y no un número exacto (escenario 13)."""
    publish_rules(client, boca)
    _, headers = club_with_history
    run(client, boca)
    projection_on(db, position_min_population=2)

    body = simulate(client, headers, upcoming(db, "P-1", clase="B"))

    positions = [body[h]["position"] for h in ("attend", "not_attend")]
    assert any(p["lower"] < p["upper"] for p in positions)
    assert all(
        "probable entre" in p["text"] for p in positions if p["lower"] < p["upper"]
    )


def test_a_socio_clearly_ahead_is_estimated_first_in_both_hypotheses(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    me, headers = account()
    others = [make_socio(db) for _ in range(3)]
    for i in range(4):
        past_match(db, f"H-{i}", [me])
    past_match(db, "H-9", [me, others[0]])
    run(client, boca)
    projection_on(db, position_min_population=2)

    body = simulate(client, headers, upcoming(db, "P-1", clase="B"))

    assert body["position_estimate"]["label"] == ESTIMATE_LABEL
    for hypothesis in ("attend", "not_attend"):
        assert body[hypothesis]["position"] == {
            "estimate": 1,
            "lower": 1,
            "upper": 1,
            "text": "puesto estimado 1",
        }


def test_the_range_level_comes_from_the_club_settings(
    client: TestClient, db: Session, boca: dict[str, str], club_with_history
) -> None:
    publish_rules(client, boca)
    _, headers = club_with_history
    run(client, boca)
    projection_on(db, position_min_population=2)
    narrow = simulate(client, headers, upcoming(db, "P-1", clase="B"))
    projection_on(db, position_range_level=Decimal("0.95"))

    wide = simulate(client, headers, upcoming(db, "P-2", clase="B"))

    assert wide["position_estimate"]["range_level"] == "0.95"
    for hypothesis in ("attend", "not_attend"):
        before, after = narrow[hypothesis]["position"], wide[hypothesis]["position"]
        assert after["estimate"] == before["estimate"]
        assert after["lower"] <= before["lower"] and after["upper"] >= before["upper"]


def test_the_range_line_uses_the_es_ar_thousands_separator() -> None:
    position = simulator_service._position_out(PositionRange(3150, 3136, 3164))

    assert position.text == "puesto estimado 3.150 (probable entre 3.136 y 3.164)"


# --- Escenario 11: un institucional muestra puntajes, posición actual y aviso, sin estimar ---

INSTITUTIONAL_NOTICE = (
    "No asistir no cambia tu puntaje, pero tu posición puede bajar si otros socios "
    "suman puntos."
)


def test_an_institutional_event_shows_scores_current_position_and_notice(
    client: TestClient, db: Session, boca: dict[str, str], club_with_history
) -> None:
    publish_rules(client, boca)
    me, headers = club_with_history
    run(client, boca)
    # Con la proyección encendida y un ranking que alcanza: un Partido sí se estimaría.
    projection_on(db, position_min_population=2)
    entry = entry_of(db, me)
    partido = simulate(client, headers, upcoming(db, "P-1"))
    assert partido["position_estimate"]["status"] == "estimated"

    body = simulate(
        client,
        headers,
        upcoming(db, "I-1", tipo="Institucional", clase=None, puntos=40),
    )

    assert body["current"] == {
        "score": f"{entry.total:.2f}",
        "position": entry.position,
        "ranked_total": 8,
    }
    assert body["position_estimate"] == {
        "status": "not_estimated",
        "code": None,
        "reason": "INSTITUTIONAL_NOT_ESTIMATED",
        "message": INSTITUTIONAL_NOTICE,
        "label": None,
        "range_level": None,
    }
    assert body["attend"]["position"] is None
    assert body["not_attend"]["position"] is None
    # Los dos puntajes: asistir suma los puntos y no asistir deja el actual (SC-004).
    base = scoring_inputs_from_snapshot(entry.inputs)
    assert body["attend"]["score"] == official_total(
        db, entry, institutional_points=base.institutional_points + 40
    )
    assert body["not_attend"]["score"] == f"{entry.total:.2f}"
    assert body["not_attend"]["difference"] == "0.00"


def test_an_institutional_event_is_not_an_error_with_the_projection_off(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    _, headers = account()
    run(client, boca)
    response = client.patch(
        "/admin/simulator/settings",
        json={"position_projection_enabled": False},
        headers=boca,
    )
    assert response.status_code == 200, response.text

    body = simulate(
        client,
        headers,
        upcoming(db, "I-1", tipo="Institucional", clase=None, puntos=20),
    )

    # El motivo es el del institucional, nunca POSITION_NOT_AVAILABLE ni su mensaje.
    assert body["position_estimate"]["code"] is None
    assert body["position_estimate"]["reason"] == "INSTITUTIONAL_NOT_ESTIMATED"
    assert body["position_estimate"]["message"] == INSTITUTIONAL_NOTICE


def test_an_institutional_event_never_reads_the_other_socios(
    client: TestClient,
    db: Session,
    boca: dict[str, str],
    club_with_history,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_rules(client, boca)
    _, headers = club_with_history
    run(client, boca)
    projection_on(db, position_min_population=2)

    def fail(*args, **kwargs):
        raise AssertionError("no se estima la posición de un institucional")

    monkeypatch.setattr(simulator_service, "_estimated_positions", fail)

    body = simulate(
        client,
        headers,
        upcoming(db, "I-1", tipo="Institucional", clase=None, puntos=40),
    )

    assert body["position_estimate"]["reason"] == "INSTITUTIONAL_NOT_ESTIMATED"


# --- Escenario 12: un Partido sin posición estimada muestra solo los puntajes ---------------

POSITION_NOT_AVAILABLE = (
    "No podemos estimar tu posición en este momento. Te mostramos solo tu puntaje."
)


def assert_only_scores(db: Session, me: Socio, body: dict, reason: str) -> None:
    """Mismo mensaje para todos los motivos; el motivo viaja solo como código."""
    assert body["position_estimate"] == {
        "status": "unavailable",
        "code": "POSITION_NOT_AVAILABLE",
        "reason": reason,
        "message": POSITION_NOT_AVAILABLE,
        "label": None,
        "range_level": None,
    }
    entry = entry_of(db, me)
    assert body["current"]["position"] == entry.position
    for hypothesis in ("attend", "not_attend"):
        assert body[hypothesis]["position"] is None
        expected = Decimal(body[hypothesis]["score"]) - entry.total
        assert body[hypothesis]["difference"] == f"{expected:.2f}"


def test_with_the_projection_off_only_the_scores_are_shown(
    client: TestClient, db: Session, boca: dict[str, str], club_with_history
) -> None:
    publish_rules(client, boca)
    me, headers = club_with_history
    run(client, boca)
    projection_on(db, position_min_population=2)
    club = db.get(Club, BOCA_ID)
    assert club is not None
    club.position_projection_enabled = False
    db.commit()

    body = simulate(client, headers, upcoming(db, "P-1"))

    assert_only_scores(db, me, body, "PROJECTION_DISABLED")


def test_without_any_counted_match_in_the_club_only_the_scores_are_shown(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    me, headers = account()
    make_socio(db)
    run(client, boca)
    projection_on(db, position_min_population=1)

    body = simulate(client, headers, upcoming(db, "P-1"))

    assert_only_scores(db, me, body, "INSUFFICIENT_HISTORY")


def test_without_matches_of_the_class_the_club_rate_of_all_classes_is_used(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    """Sin partidos de la clase hay historial igual: no es INSUFFICIENT_HISTORY."""
    publish_rules(client, boca)
    me, headers = account()
    other = make_socio(db)
    past_match(db, "H-1", [me, other], clase="A")
    run(client, boca)
    projection_on(db, position_min_population=2)

    body = simulate(client, headers, upcoming(db, "P-1", clase="C"))

    assert body["position_estimate"]["status"] == "estimated"


def test_a_ranking_smaller_than_the_minimum_shows_only_the_scores(
    client: TestClient, db: Session, boca: dict[str, str], club_with_history
) -> None:
    publish_rules(client, boca)
    me, headers = club_with_history
    run(client, boca)
    # 8 socios en el ranking: con el mínimo en 9 no alcanza, con 8 sí.
    projection_on(db, position_min_population=9)

    body = simulate(client, headers, upcoming(db, "P-1"))

    assert_only_scores(db, me, body, "SMALL_POPULATION")
    projection_on(db, position_min_population=8)
    assert (
        simulate(client, headers, upcoming(db, "P-2"))["position_estimate"]["status"]
        == "estimated"
    )


def test_a_failure_while_estimating_shows_only_the_scores(
    client: TestClient,
    db: Session,
    boca: dict[str, str],
    club_with_history,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_rules(client, boca)
    me, headers = club_with_history
    run(client, boca)
    projection_on(db, position_min_population=2)

    def broken(*args, **kwargs):
        raise RuntimeError("falla del cálculo")

    monkeypatch.setattr(simulator_service, "ranks_above", broken)

    body = simulate(client, headers, upcoming(db, "P-1"))

    assert_only_scores(db, me, body, "POSITION_ERROR")
    assert Decimal(body["attend"]["score"]) >= Decimal(body["not_attend"]["score"])


def test_an_estimate_that_does_not_finish_in_time_shows_only_the_scores(
    client: TestClient,
    db: Session,
    boca: dict[str, str],
    club_with_history,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_rules(client, boca)
    me, headers = club_with_history
    run(client, boca)
    projection_on(db, position_min_population=2)
    monkeypatch.setattr(simulator_service, "POSITION_TIME_BUDGET_SECONDS", 0)

    body = simulate(client, headers, upcoming(db, "P-1"))

    assert_only_scores(db, me, body, "POSITION_ERROR")


# --- Escenario 13: una posición estimada nunca sale sin etiqueta ni como número exacto ------


def assert_labeled_ranges(body: dict) -> None:
    """Toda posición estimada es un rango con la etiqueta y el texto de estimación."""
    assert body["position_estimate"]["status"] == "estimated"
    assert body["position_estimate"]["label"] == ESTIMATE_LABEL
    assert body["position_estimate"]["range_level"] is not None
    for hypothesis in ("attend", "not_attend"):
        position = body[hypothesis]["position"]
        assert set(position) == {"estimate", "lower", "upper", "text"}
        assert position["lower"] <= position["estimate"] <= position["upper"]
        assert position["text"].startswith("puesto estimado ")


def test_every_estimated_position_is_a_labeled_range(
    client: TestClient, db: Session, boca: dict[str, str], club_with_history
) -> None:
    publish_rules(client, boca)
    _, headers = club_with_history
    run(client, boca)
    projection_on(db, position_min_population=2)

    for clase in ("A", "B", "C"):
        body = simulate(client, headers, upcoming(db, f"P-{clase}", clase=clase))
        assert_labeled_ranges(body)


def test_a_range_of_a_single_place_is_still_labeled_as_an_estimate(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    me, headers = account()
    others = [make_socio(db) for _ in range(2)]
    for i in range(4):
        past_match(db, f"H-{i}", [me])
    past_match(db, "H-9", [me, others[0]])
    run(client, boca)
    projection_on(db, position_min_population=2)

    body = simulate(client, headers, upcoming(db, "P-1"))

    assert_labeled_ranges(body)
    position = body["attend"]["position"]
    assert position["lower"] == position["upper"] == 1
    # Un solo puesto se muestra como "puesto estimado 1", nunca como "1" a secas.
    assert position["text"] == "puesto estimado 1"


def simulation_with(*, position_estimate: dict, attend_position, not_attend_position):
    """Una respuesta armada a mano, para probar lo que el esquema deja salir."""
    return SimulationOut.model_validate(
        {
            "event": {
                "id": "e",
                "titulo": "t",
                "tipo": "Partido",
                "fecha_hora": "2026-11-08T20:00:00Z",
                "puntos": None,
            },
            "ranking": {
                "completed_at": None,
                "calculation_date": "2026-10-29",
                "rules_version": 1,
            },
            "rules_notice": None,
            "distance": {
                "used_km": "1.00",
                "ranking_km": "1.00",
                "changed": False,
                "notice": None,
            },
            "current": {"score": "50.00", "position": 3, "ranked_total": 10},
            "attend": {
                "score": "51.00",
                "difference": "1.00",
                "position": attend_position,
            },
            "not_attend": {
                "score": "49.00",
                "difference": "-1.00",
                "position": not_attend_position,
            },
            "position_estimate": position_estimate,
        }
    )


RANGE = {
    "estimate": 3,
    "lower": 2,
    "upper": 4,
    "text": "puesto estimado 3 (probable entre 2 y 4)",
}
ESTIMATED = {
    "status": "estimated",
    "code": None,
    "reason": None,
    "message": None,
    "label": ESTIMATE_LABEL,
    "range_level": "0.80",
}
UNAVAILABLE = {
    "status": "unavailable",
    "code": "POSITION_NOT_AVAILABLE",
    "reason": "POSITION_ERROR",
    "message": "No podemos estimar tu posición en este momento. Te mostramos solo tu puntaje.",
}


def test_a_well_formed_estimate_is_accepted() -> None:
    simulation_with(
        position_estimate=ESTIMATED, attend_position=RANGE, not_attend_position=RANGE
    )


@pytest.mark.parametrize(
    ("position_estimate", "attend_position", "not_attend_position"),
    [
        # Sin etiqueta.
        ({**ESTIMATED, "label": None}, RANGE, RANGE),
        ({**ESTIMATED, "label": ""}, RANGE, RANGE),
        ({**ESTIMATED, "range_level": None}, RANGE, RANGE),
        # Una posición estimada fuera de una estimación.
        (UNAVAILABLE, RANGE, None),
        # Una estimación a la que le falta una hipótesis.
        (ESTIMATED, RANGE, None),
        # Un número exacto disfrazado: sin texto de estimación o fuera de su rango.
        (ESTIMATED, {**RANGE, "text": "puesto 3"}, RANGE),
        (ESTIMATED, {**RANGE, "estimate": 5}, RANGE),
    ],
)
def test_an_estimated_position_without_its_label_is_never_returned(
    position_estimate, attend_position, not_attend_position
) -> None:
    with pytest.raises(ValidationError):
        simulation_with(
            position_estimate=position_estimate,
            attend_position=attend_position,
            not_attend_position=not_attend_position,
        )


# --- Escenario 14: el Admin configura el simulador de su club (FR-010, FR-013) -------------

SETTINGS = "/admin/simulator/settings"


def test_the_projection_is_enabled_by_default(
    client: TestClient, boca: dict[str, str]
) -> None:
    response = client.get(SETTINGS, headers=boca)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "position_projection_enabled": True,
        "position_range_level": "0.80",
        "position_prior_strength": "5.00",
        "position_min_population": 100,
    }


def test_by_default_a_partido_tries_to_estimate_the_position(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    """Encendida por defecto: un ranking chico no se estima por tamaño, no por estar apagada."""
    publish_rules(client, boca)
    socio, headers = account()
    past_match(db, "H-1", [socio])
    run(client, boca)

    body = simulate(client, headers, upcoming(db, "P-1"))

    assert body["position_estimate"]["code"] == "POSITION_NOT_AVAILABLE"
    assert body["position_estimate"]["reason"] == "SMALL_POPULATION"


def test_the_admin_turns_the_projection_off_and_on(
    client: TestClient, db: Session, boca: dict[str, str], club_with_history
) -> None:
    publish_rules(client, boca)
    _, headers = club_with_history
    run(client, boca)
    response = client.patch(SETTINGS, json={"position_min_population": 2}, headers=boca)
    assert response.status_code == 200, response.text
    assert (
        simulate(client, headers, upcoming(db, "P-1"))["position_estimate"]["status"]
        == "estimated"
    )

    response = client.patch(
        SETTINGS, json={"position_projection_enabled": False}, headers=boca
    )

    assert response.status_code == 200, response.text
    assert response.json()["position_projection_enabled"] is False
    body = simulate(client, headers, upcoming(db, "P-2"))
    assert body["position_estimate"]["reason"] == "PROJECTION_DISABLED"
    assert body["attend"]["position"] is None and body["not_attend"]["position"] is None
    client.patch(SETTINGS, json={"position_projection_enabled": True}, headers=boca)
    assert (
        simulate(client, headers, upcoming(db, "P-3"))["position_estimate"]["status"]
        == "estimated"
    )


def test_only_the_sent_fields_change_and_the_change_is_audited(
    client: TestClient, db: Session, boca: dict[str, str], admin: User
) -> None:
    response = client.patch(
        SETTINGS,
        json={"position_range_level": "0.90", "position_min_population": 50},
        headers=boca,
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "position_projection_enabled": True,
        "position_range_level": "0.90",
        "position_prior_strength": "5.00",
        "position_min_population": 50,
    }
    log = db.scalars(
        select(AuditLog).where(AuditLog.action == "simulator_settings.updated")
    ).one()
    assert log.actor_user_id == admin.id
    assert log.entity_id == str(BOCA_ID)
    assert log.details["before"] == {
        "position_range_level": "0.80",
        "position_min_population": 100,
    }
    assert log.details["after"] == {
        "position_range_level": "0.90",
        "position_min_population": 50,
    }


def test_a_patch_without_changes_is_not_audited(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    response = client.patch(
        SETTINGS, json={"position_projection_enabled": True}, headers=boca
    )

    assert response.status_code == 200, response.text
    assert (
        db.scalars(
            select(AuditLog).where(AuditLog.action == "simulator_settings.updated")
        ).first()
        is None
    )


@pytest.mark.parametrize(
    "body",
    [
        {"position_range_level": "1"},
        {"position_range_level": "0"},
        {"position_range_level": "0.805"},
        {"position_prior_strength": "0"},
        {"position_min_population": 0},
        {"club_id": str(RIVER_ID)},
    ],
)
def test_invalid_settings_are_rejected(
    client: TestClient, boca: dict[str, str], body: dict
) -> None:
    response = client.patch(SETTINGS, json=body, headers=boca)

    assert response.status_code == 422
    assert client.get(SETTINGS, headers=boca).json()["position_range_level"] == "0.80"


def test_the_settings_belong_to_the_admin_club(
    client: TestClient, outbox: Outbox, boca: dict[str, str], make_admin
) -> None:
    river = headers_for(client, outbox, make_admin(RIVER_ID))

    client.patch(SETTINGS, json={"position_projection_enabled": False}, headers=river)

    assert (
        client.get(SETTINGS, headers=river).json()["position_projection_enabled"]
        is False
    )
    assert (
        client.get(SETTINGS, headers=boca).json()["position_projection_enabled"] is True
    )


def test_a_socio_cannot_change_the_settings(client: TestClient, account) -> None:
    _, headers = account()

    assert client.get(SETTINGS, headers=headers).status_code == 403
    response = client.patch(
        SETTINGS, json={"position_projection_enabled": False}, headers=headers
    )
    assert response.status_code == 403
    assert client.patch(SETTINGS, json={}).status_code == 401
