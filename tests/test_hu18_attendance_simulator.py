"""HU-18: simulador de puntaje por asistencia (`docs/contrato-api-simulador.md`)."""

import uuid
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import PasioDe10Exception
from app.models import (
    EventoPendienteDB,
    Member,
    RankingEntry,
    RulesVersion,
    Socio,
    User,
    utcnow,
)
from app.scoring.engine import ScoringParameters, calculate_score
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
