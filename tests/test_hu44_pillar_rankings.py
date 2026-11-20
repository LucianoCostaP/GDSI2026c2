"""HU-44: rankings por pilar del puntaje, escenarios 1 a 12 (spec `hu-44-pillar-rankings`)."""

import re
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    EventoVisibleDB,
    Ranking,
    RankingEntry,
    RankingState,
    RulesVersion,
    Socio,
    User,
    utcnow,
)
from app.scoring.pillar_ranking import (
    SCORING_MODEL_PILLARS,
    PillarSource,
    pillar_points,
    top_by_pillar,
)
from app.scoring.ranking_order import (
    RankingCandidate,
    assign_positions,
    top_positions,
)
from app.services.pillar_ranking_service import (
    EMPTY_PILLAR_MESSAGE,
    NO_RANKING_MESSAGE,
)
from tests.conftest import (
    BOCA_ID,
    RIVER_ID,
    MakeAdmin,
    MakeMember,
    Outbox,
    bearer,
    member_token,
)
from tests.hu25_helpers import (
    adjust_rules,
    headers_for,
    load_attendance,
    make_ranking,
    make_socio,
    publish_rules,
)
from tests.hu29_helpers import (
    TO_THE_CAP,
    add_star_newcomer,
    make_varied_club,
    run_ranking,
)

PILLARS = "/admin/ranking/pillars"
TWO_DECIMALS = re.compile(r"^\d+\.\d{2}$")
COMPONENTS = {
    "attendance": ("attendance_frequency", "attendance_distance"),
    "institutional": ("institutional",),
    "seniority_age": ("seniority_age",),
}


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    return headers_for(client, outbox, admin)


def get_pillars(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.get(PILLARS, headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    return response.json()


def pillar(body: dict, key: str) -> dict:
    return next(p for p in body["pillars"] if p["key"] == key)


def entries_by_numero(db: Session, ranking: Ranking) -> dict[str, RankingEntry]:
    rows = db.execute(
        select(Socio.numero_socio, RankingEntry)
        .join(Socio, Socio.id == RankingEntry.socio_id)
        .where(RankingEntry.ranking_id == ranking.id)
    )
    return {numero: entry for numero, entry in rows}


def stored_points(entry: RankingEntry, key: str) -> Decimal:
    return sum((getattr(entry, name) for name in COMPONENTS[key]), Decimal(0))


# --- Escenario 1: tres tablas con el top 10 ------------------------------------------------


def test_admin_sees_the_top_10_of_each_of_the_three_pillars(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    # 12 socios sin asistencias, cada uno un año más antiguo que el anterior: en Antigüedad y
    # edad quedan 12 con puntos distintos (nadie llega al tope) y se muestran los 10 primeros.
    socios = [
        make_socio(
            db,
            dni=f"3000000{i:02d}",
            fecha_alta=date(2014 + i, 3, 1),
            fecha_nacimiento=date(1995, 1, 1),
        )
        for i in range(12)
    ]
    run_ranking(db, admin)

    body = get_pillars(client, boca)

    assert body["has_ranking"] is True
    assert body["message"] is None
    assert [(p["key"], p["name"]) for p in body["pillars"]] == [
        ("attendance", "Asistencia"),
        ("institutional", "Participación institucional"),
        ("seniority_age", "Antigüedad y edad"),
    ]
    assert all(len(p["rows"]) <= 10 for p in body["pillars"])
    seniority = pillar(body, "seniority_age")["rows"]
    # Los más antiguos primero: el de alta 2014 encabeza; los de 2024 y 2025 quedan afuera.
    assert [r["numero_socio"] for r in seniority] == [
        s.numero_socio for s in socios[:10]
    ]


def test_each_pillar_follows_the_order_of_its_points_over_the_whole_ranking(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    make_varied_club(db)
    ranking = run_ranking(db, admin)
    entries = entries_by_numero(db, ranking)

    body = get_pillars(client, boca)

    for key in COMPONENTS:
        rows = pillar(body, key)["rows"]
        with_points = [e for e in entries.values() if stored_points(e, key) > 0]
        assert len(rows) == min(10, len(with_points))
        points = [Decimal(r["points"]) for r in rows]
        assert points == sorted(points, reverse=True)
        # Nadie fuera de la tabla supera al último que entró.
        shown = {r["numero_socio"] for r in rows}
        left_out = [stored_points(e, key) for n, e in entries.items() if n not in shown]
        assert all(p <= points[-1] for p in left_out)


# --- Escenario 2: posición, nombre, número de socio y puntos -------------------------------


def test_each_row_shows_position_name_membership_number_and_points_with_two_decimals(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    club = make_varied_club(db)
    run_ranking(db, admin)
    by_numero = {s.numero_socio: s for s in club.socios}

    body = get_pillars(client, boca)

    for p in body["pillars"]:
        assert [r["position"] for r in p["rows"]] == list(range(1, len(p["rows"]) + 1))
        for row in p["rows"]:
            # Ni DNI, ni email, ni distancia, ni total o posición general.
            assert set(row) == {"position", "numero_socio", "nombre", "points"}
            assert TWO_DECIMALS.match(row["points"])
            assert row["nombre"] == by_numero[row["numero_socio"]].nombre


def test_name_and_membership_number_come_from_the_current_roster(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    socio = make_socio(db, nombre="Nombre Viejo")
    run_ranking(db, admin)
    socio.nombre = "Nombre Nuevo"
    db.commit()

    rows = pillar(get_pillars(client, boca), "seniority_age")["rows"]

    assert rows[0]["nombre"] == "Nombre Nuevo"


# --- Escenario 3: versión de reglas y fecha del cálculo ------------------------------------


def test_tables_show_the_rules_version_and_completion_time_of_their_ranking(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    make_varied_club(db)
    ranking = run_ranking(db, admin)
    rules = db.get_one(RulesVersion, ranking.rules_version_id)
    assert ranking.completed_at is not None

    source = get_pillars(client, boca)["ranking"]

    assert source["id"] == ranking.id
    assert source["rules_version"] == rules.number
    assert source["calculation_date"] == ranking.calculation_date.isoformat()
    assert source["completed_at"].replace("Z", "+00:00") == (
        ranking.completed_at.isoformat()
    )


def test_rules_published_after_the_ranking_do_not_change_the_version_shown(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    make_varied_club(db)
    run_ranking(db, admin)
    adjust_rules(client, boca, expected_rules_version=1, w_a="0.5", w_p="0.3")

    assert get_pillars(client, boca)["ranking"]["rules_version"] == 1


def test_tables_come_from_the_latest_completed_ranking(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    make_varied_club(db)
    run_ranking(db, admin)
    latest = run_ranking(db, admin)

    assert get_pillars(client, boca)["ranking"]["id"] == latest.id


# --- Escenario 4: los puntos coinciden con el desglose (HU-16) -----------------------------


def test_pillar_points_equal_the_stored_breakdown_components(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    make_varied_club(db)
    ranking = run_ranking(db, admin)
    entries = entries_by_numero(db, ranking)

    body = get_pillars(client, boca)

    for key in COMPONENTS:
        for row in pillar(body, key)["rows"]:
            entry = entries[row["numero_socio"]]
            assert Decimal(row["points"]) == stored_points(entry, key)
    # Asistencia es frecuencia más distancia: hay socios con los dos componentes en la tabla.
    both = [
        entries[r["numero_socio"]]
        for r in pillar(body, "attendance")["rows"]
        if entries[r["numero_socio"]].attendance_frequency > 0
        and entries[r["numero_socio"]].attendance_distance > 0
    ]
    assert both


def test_pillar_points_equal_what_the_member_breakdown_shows(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    admin: User,
    boca: dict[str, str],
    make_member: MakeMember,
) -> None:
    """Mismos valores que el socio ve en su desglose (`GET /member/scoring/breakdown`)."""
    publish_rules(client, boca)
    make_varied_club(db)
    member = make_member(activated=True, club_id=BOCA_ID)
    socio = make_socio(db, dni=member.dni, distancia_km=Decimal("350.00"))
    match = db.scalars(
        select(EventoVisibleDB).where(EventoVisibleDB.id_externo == "EVT-A")
    ).one()
    load_attendance(db, match, [socio])
    run_ranking(db, admin)

    body = get_pillars(client, boca)
    member_headers = bearer(member_token(client, outbox, member))
    breakdown = client.get("/member/scoring/breakdown", headers=member_headers).json()
    by_key = {c["key"]: Decimal(c["points"]) for c in breakdown["components"]}

    shown = 0
    for key, names in COMPONENTS.items():
        expected = sum((by_key[n] for n in names), Decimal(0))
        row = next(
            (
                r
                for r in pillar(body, key)["rows"]
                if r["numero_socio"] == socio.numero_socio
            ),
            None,
        )
        if row is None:
            # Fuera de la tabla solo si no sumó nada en ese pilar (escenario 7).
            assert expected == 0
        else:
            assert Decimal(row["points"]) == expected
            shown += 1
    # Asistencia y Antigüedad y edad: el socio fue a un partido y tiene antigüedad.
    assert shown >= 2


# --- Escenario 5: sin bonus de socio nuevo ni ajuste por tope ------------------------------


def test_new_member_bonus_and_cap_adjustment_count_in_no_pillar(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca, **TO_THE_CAP)
    make_varied_club(db)
    star = add_star_newcomer(db)
    ranking = run_ranking(db, admin)
    entry = entries_by_numero(db, ranking)[star.numero_socio]
    # El socio estrella tiene bonus y, con estas reglas, pasa de 100: hay ajuste por tope.
    assert entry.new_member_bonus > 0
    assert entry.cap_adjustment < 0

    body = get_pillars(client, boca)

    star_points = {
        key: Decimal(
            next(
                r["points"]
                for r in pillar(body, key)["rows"]
                if r["numero_socio"] == star.numero_socio
            )
        )
        for key in COMPONENTS
    }
    assert star_points["attendance"] == (
        entry.attendance_frequency + entry.attendance_distance
    )
    assert star_points["institutional"] == entry.institutional
    assert star_points["seniority_age"] == entry.seniority_age
    # La suma de los tres pilares no es el total (HU-14).
    assert sum(star_points.values()) != entry.total


# --- Escenario 6: desempate dentro de un pilar ---------------------------------------------


def test_ties_in_a_pillar_are_broken_by_seniority_then_age_then_lower_document(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    # Todos superan los valores de referencia: 20,00 puntos en Antigüedad y edad.
    higher_dni = make_socio(
        db,
        fecha_alta=date(1960, 1, 1),
        fecha_nacimiento=date(1940, 1, 1),
        dni="5000000",
    )
    lower_dni = make_socio(
        db,
        fecha_alta=date(1960, 1, 1),
        fecha_nacimiento=date(1940, 1, 1),
        dni="4000000",
    )
    older_person = make_socio(
        db,
        fecha_alta=date(1960, 1, 1),
        fecha_nacimiento=date(1930, 1, 1),
        dni="1000000",
    )
    oldest_member = make_socio(
        db,
        fecha_alta=date(1950, 1, 1),
        fecha_nacimiento=date(1950, 1, 1),
        dni="9000000",
    )
    run_ranking(db, admin)

    rows = pillar(get_pillars(client, boca), "seniority_age")["rows"]

    assert {r["points"] for r in rows} == {"20.00"}
    # El documento se compara como número: "4000000" va antes que "5000000".
    assert [r["numero_socio"] for r in rows] == [
        oldest_member.numero_socio,
        older_person.numero_socio,
        lower_dni.numero_socio,
        higher_dni.numero_socio,
    ]
    assert [r["position"] for r in rows] == [1, 2, 3, 4]


# --- Escenario 7: solo socios con puntos, sin relleno --------------------------------------


def test_a_pillar_with_fewer_than_10_socios_with_points_lists_only_those(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    club = make_varied_club(db)
    run_ranking(db, admin)

    body = get_pillars(client, boca)

    # De los 7 socios, solo dos sumaron participación institucional (la asamblea y el deporte).
    institutional = pillar(body, "institutional")
    assert {r["numero_socio"] for r in institutional["rows"]} == {
        club.institutional.numero_socio,
        club.veteran.numero_socio,
    }
    assert institutional["empty_message"] is None
    assert all(Decimal(r["points"]) > 0 for p in body["pillars"] for r in p["rows"])


# --- Escenario 8: pilar sin ningún socio con puntos ----------------------------------------


def test_a_pillar_where_nobody_has_points_shows_the_empty_message(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    # Sin eventos ni actividades: nadie suma asistencia ni participación institucional.
    make_socio(db)
    make_socio(db)
    run_ranking(db, admin)

    body = get_pillars(client, boca)

    for key in ("attendance", "institutional"):
        assert pillar(body, key)["rows"] == []
        assert pillar(body, key)["empty_message"] == (
            "Ningún socio sumó puntos en este pilar en el último cálculo."
        )
    seniority = pillar(body, "seniority_age")
    assert len(seniority["rows"]) == 2
    assert seniority["empty_message"] is None


def test_a_pillar_weighted_zero_shows_the_empty_message(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca, w_a="0.80", w_p="0.00", w_t="0.20")
    make_varied_club(db)
    run_ranking(db, admin)

    institutional = pillar(get_pillars(client, boca), "institutional")

    assert institutional["rows"] == []
    assert institutional["empty_message"] == EMPTY_PILLAR_MESSAGE


def test_a_formula_without_pillars_shows_no_tables(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    """Caso borde: hoy el catálogo solo tiene `scoring-model`; otra fórmula tendría que
    declarar sus pilares (modelo de scoring, regla 9)."""
    publish_rules(client, boca)
    make_varied_club(db)
    ranking = run_ranking(db, admin)
    db.get_one(RulesVersion, ranking.rules_version_id).formula_id = "otra-formula"
    db.commit()

    body = get_pillars(client, boca)

    assert body["has_ranking"] is True
    assert body["ranking"]["id"] == ranking.id
    assert body["pillars"] == []
    assert body["message"] == "La fórmula de este ranking no define rankings por pilar."


# --- Escenario 9: nunca se calculó un ranking ----------------------------------------------


def test_without_a_completed_ranking_the_message_replaces_the_tables(
    client: TestClient, boca: dict[str, str]
) -> None:
    body = get_pillars(client, boca)

    assert body == {
        "has_ranking": False,
        "message": "Todavía no hay un ranking calculado.",
        "updating": False,
        "ranking": None,
        "pillars": [],
    }


# --- Escenario 10: cálculo en curso --------------------------------------------------------


def test_while_a_calculation_runs_the_last_completed_tables_are_shown_as_updating(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    make_varied_club(db)
    completed = run_ranking(db, admin)
    before = get_pillars(client, boca)
    make_ranking(db, admin, RankingState.RUNNING)

    during = get_pillars(client, boca)

    assert during["updating"] is True
    assert during["ranking"]["id"] == completed.id
    assert during["pillars"] == before["pillars"]


def test_the_first_calculation_running_shows_the_no_ranking_message_as_updating(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    make_ranking(db, admin, RankingState.RUNNING)

    body = get_pillars(client, boca)

    assert body["has_ranking"] is False
    assert body["message"] == NO_RANKING_MESSAGE
    assert body["updating"] is True


def test_a_run_older_than_15_minutes_counts_as_abandoned_and_is_not_updating(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    make_varied_club(db)
    run_ranking(db, admin)
    stale = make_ranking(
        db,
        admin,
        RankingState.RUNNING,
        calculated_at=utcnow() - timedelta(minutes=20),
    )

    body = get_pillars(client, boca)

    assert body["updating"] is False
    # Solo se lee: la corrida no se marca `failed` desde esta pantalla.
    db.refresh(stale)
    assert stale.status == RankingState.RUNNING


# --- Escenario 11: cálculo fallido ---------------------------------------------------------


def test_after_a_failed_calculation_the_last_completed_tables_stay_unchanged(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    make_varied_club(db)
    completed = run_ranking(db, admin)
    before = get_pillars(client, boca)
    make_ranking(db, admin, RankingState.FAILED)

    after = get_pillars(client, boca)

    assert after == before
    assert after["ranking"]["id"] == completed.id
    assert after["updating"] is False


# --- Escenario 12: acceso y aislamiento ----------------------------------------------------


def test_without_a_session_the_request_is_rejected_with_401(
    client: TestClient,
) -> None:
    response = client.get(PILLARS)

    assert response.status_code == 401
    assert response.json()["detail"] == "NOT_AUTHENTICATED"


def test_a_socio_is_rejected_with_403(
    client: TestClient, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    headers = bearer(member_token(client, outbox, member))

    response = client.get(PILLARS, headers=headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "FORBIDDEN"


def test_an_admin_without_club_is_rejected_with_403(
    client: TestClient, outbox: Outbox, make_admin: MakeAdmin
) -> None:
    headers = headers_for(client, outbox, make_admin(None))

    response = client.get(PILLARS, headers=headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "ADMIN_WITHOUT_CLUB"


def test_an_admin_only_sees_the_rankings_of_their_own_club(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    admin: User,
    boca: dict[str, str],
    make_admin: MakeAdmin,
) -> None:
    publish_rules(client, boca)
    make_varied_club(db)
    run_ranking(db, admin)
    river = headers_for(client, outbox, make_admin(RIVER_ID))

    # El club sale de la cuenta: un `club_id` o `X-Club-ID` en el pedido se ignora.
    response = client.get(
        PILLARS,
        params={"club_id": str(BOCA_ID)},
        headers={**river, "X-Club-ID": str(BOCA_ID)},
    )

    assert response.status_code == 200
    assert response.json()["has_ranking"] is False


# --- Código puro ---------------------------------------------------------------------------


def test_socios_without_points_in_a_pillar_are_left_out() -> None:
    def source(attendance: str) -> PillarSource:
        return PillarSource(
            socio_id=uuid.uuid4(),
            components={
                "attendance_frequency": Decimal(attendance),
                "attendance_distance": Decimal(0),
                "institutional": Decimal(0),
                "seniority_age": Decimal(0),
            },
            seniority_start=date(2000, 1, 1),
            birth_date=date(1980, 1, 1),
            dni=str(uuid.uuid4().int)[:8],
        )

    sources = [source("3.10"), source("0.00"), source("0.01")]

    tops = top_by_pillar(SCORING_MODEL_PILLARS, sources)

    assert [r.points for r in tops[0].rows] == [Decimal("3.10"), Decimal("0.01")]
    assert tops[1].rows == [] and tops[2].rows == []


def candidate(total: str, dni: str, alta: date = date(2000, 1, 1)) -> RankingCandidate:
    return RankingCandidate(
        socio_id=uuid.uuid4(),
        total=Decimal(total),
        seniority_start=alta,
        birth_date=date(1980, 1, 1),
        dni=dni,
    )


def test_top_positions_are_the_first_positions_of_the_full_order() -> None:
    candidates = [
        candidate(str(t), dni=str(1000 + i), alta=date(1990 + i % 7, 1, 1))
        for i, t in enumerate([5, 7, 7, 3, 9, 7, 1, 9, 0, 4, 7, 2])
    ]

    assert top_positions(candidates, 5) == assign_positions(candidates)[:5]
    assert top_positions(candidates, 50) == assign_positions(candidates)


def test_pillar_points_sum_only_the_components_of_the_pillar() -> None:
    components = {
        "attendance_frequency": Decimal("30.10"),
        "attendance_distance": Decimal("4.05"),
        "institutional": Decimal("12.00"),
        "seniority_age": Decimal("8.33"),
    }
    attendance, institutional, seniority = SCORING_MODEL_PILLARS

    assert pillar_points(attendance, components) == Decimal("34.15")
    assert pillar_points(institutional, components) == Decimal("12.00")
    assert pillar_points(seniority, components) == Decimal("8.33")


def test_top_by_pillar_keeps_the_pillar_order_and_limit() -> None:
    sources = [
        PillarSource(
            socio_id=uuid.uuid4(),
            components={
                "attendance_frequency": Decimal(i),
                "attendance_distance": Decimal(0),
                "institutional": Decimal(20 - i),
                "seniority_age": Decimal(5),
            },
            seniority_start=date(2000, 1, 1),
            birth_date=date(1980, 1, 1),
            dni=str(100 + i),
        )
        for i in range(15)
    ]

    tops = top_by_pillar(SCORING_MODEL_PILLARS, sources)

    assert [t.pillar.key for t in tops] == [
        "attendance",
        "institutional",
        "seniority_age",
    ]
    assert all(len(t.rows) == 10 for t in tops)
    assert [r.points for r in tops[0].rows][:2] == [Decimal(14), Decimal(13)]
    assert [r.points for r in tops[1].rows][:2] == [Decimal(20), Decimal(19)]
    # Todos empatados en 5: decide el documento, de menor a mayor.
    assert [r.socio_id for r in tops[2].rows] == [s.socio_id for s in sources[:10]]
