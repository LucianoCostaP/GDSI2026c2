"""HU-28: Ajustar parámetros de la fórmula de puntaje en vigor."""

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    AuditLog,
    RulesVersion,
    RulesVersionState,
    User,
)
from app.scoring.catalog import SCORING_MODEL_V1
from app.services import formula_service
from tests.conftest import (
    BOCA_ID,
    RIVER_ID,
    MakeAdmin,
    MakeMember,
    Outbox,
    admin_token,
    bearer,
    member_token,
)

FORMULA = "/admin/formulas/scoring-model/1"
ADJUST = "/admin/formulas/adjust"
DEFAULTS = {p.key: str(p.default) for p in SCORING_MODEL_V1.parameters}
CHANGED_VALUES = dict(DEFAULTS, w_a="0.50", w_p="0.30", w_t="0.20")


def headers_for(client: TestClient, outbox: Outbox, user: User) -> dict[str, str]:
    headers = bearer(admin_token(client, outbox, user))
    outbox.clear()
    return headers


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, make_admin: MakeAdmin) -> dict[str, str]:
    return headers_for(client, outbox, make_admin(BOCA_ID))


@pytest.fixture
def river(client: TestClient, outbox: Outbox, make_admin: MakeAdmin) -> dict[str, str]:
    return headers_for(client, outbox, make_admin(RIVER_ID))


def publish(
    client: TestClient,
    headers: dict[str, str],
    *,
    values: dict | None = None,
    expected: int | None = None,
    confirmed: bool = True,
    path: str = FORMULA,
):
    return client.post(
        f"{path}/publish",
        json={
            "values": DEFAULTS if values is None else values,
            "expected_rules_version": expected,
            "confirmed": confirmed,
        },
        headers=headers,
    )


def adjust(
    client: TestClient,
    headers: dict[str, str],
    *,
    values: dict | None = None,
    expected: int = 1,
    confirmed: bool = True,
):
    return client.post(
        ADJUST,
        json={
            "values": CHANGED_VALUES if values is None else values,
            "expected_rules_version": expected,
            "confirmed": confirmed,
        },
        headers=headers,
    )


def lock(client: TestClient, headers: dict[str, str], reason: str = "Congelada"):
    return client.post("/admin/formulas/lock", json={"reason": reason}, headers=headers)


def code_of(response) -> str:
    return str(response.json()["detail"]["code"])


# Escenario 1 y 2: Listar parámetros vigentes y editar valores dentro de límites -------


def test_adjust_parameters_success_creates_new_version(
    client: TestClient, boca, db: Session
) -> None:
    publish(client, boca)

    # Modificamos w_a, w_p (suman 0.80) y w_t = 0.20 -> suman 1.00
    new_values = dict(DEFAULTS)
    new_values["w_a"] = "0.50"
    new_values["w_p"] = "0.30"
    new_values["w_t"] = "0.20"
    new_values["d_sat"] = "1500"

    response = adjust(client, boca, values=new_values, expected=1)
    assert response.status_code == 200
    body = response.json()
    assert body["number"] == 2
    assert "Ajustaste los parámetros" in body["message"]

    # Verifica en la base de datos
    versions = db.scalars(
        select(RulesVersion)
        .where(RulesVersion.club_id == BOCA_ID)
        .order_by(RulesVersion.number)
    ).all()
    assert len(versions) == 2
    v1, v2 = versions
    assert v1.state == RulesVersionState.SUPERSEDED
    assert v2.state == RulesVersionState.IN_FORCE
    assert v2.number == 2
    assert v2.previous_version_id == v1.id
    assert v2.values["w_a"] == "0.5"
    assert v2.values["d_sat"] == "1500"


def test_adjust_rejects_identical_values(client: TestClient, boca) -> None:
    publish(client, boca)

    # Intentar ajustar con exactamente los mismos valores vigentes
    response = adjust(client, boca, values=DEFAULTS, expected=1)
    assert response.status_code == 422
    assert code_of(response) == "NO_CHANGES_DETECTED"
    assert "No modificaste ningún parámetro" in response.json()["detail"]["message"]


def test_cannot_add_or_remove_parameters(client: TestClient, boca) -> None:
    publish(client, boca)

    # Parámetro desconocido
    extra = dict(DEFAULTS)
    extra["parametro_inventado"] = "1.0"
    r1 = adjust(client, boca, values=extra)
    assert r1.status_code == 422
    assert code_of(r1) == "INVALID_VALUES"
    violations = r1.json()["detail"]["violations"]
    assert any(v["code"] == "PARAMETER_UNKNOWN" for v in violations)

    # Falta un parámetro
    missing = dict(DEFAULTS)
    del missing["w_a"]
    r2 = adjust(client, boca, values=missing)
    assert r2.status_code == 422
    assert code_of(r2) == "INVALID_VALUES"
    violations2 = r2.json()["detail"]["violations"]
    assert any(v["code"] == "PARAMETER_MISSING" for v in violations2)


# Escenario 3: Pesos de pilares deben sumar 1.00 --------------------------------------


def test_pillar_weights_must_sum_to_one(client: TestClient, boca) -> None:
    publish(client, boca)

    invalid_sum = dict(DEFAULTS)
    invalid_sum["w_a"] = "0.50"
    invalid_sum["w_p"] = "0.50"
    invalid_sum["w_t"] = "0.50"  # suma 1.50

    response = adjust(client, boca, values=invalid_sum)
    assert response.status_code == 422
    assert code_of(response) == "INVALID_VALUES"
    violations = response.json()["detail"]["violations"]
    sum_violation = next(
        v for v in violations if v["code"] == "SUM_CONSTRAINT_VIOLATED"
    )
    assert "suman 1,5" in sum_violation["message"]


# Escenario 5: Valores fuera de límites -----------------------------------------------


def test_parameter_out_of_limits(client: TestClient, boca) -> None:
    publish(client, boca)

    out_of_bounds = dict(DEFAULTS)
    out_of_bounds["d_sat"] = "5000"  # max es 3000

    response = adjust(client, boca, values=out_of_bounds)
    assert response.status_code == 422
    assert code_of(response) == "INVALID_VALUES"
    violations = response.json()["detail"]["violations"]
    limit_v = next(v for v in violations if v["code"] == "PARAMETER_OUT_OF_LIMITS")
    assert limit_v["parameter"] == "d_sat"
    assert "entre 50 y 3000 km" in limit_v["message"]


# Escenario 6: Confirmación requerida -------------------------------------------------


def test_confirmation_required(client: TestClient, boca) -> None:
    publish(client, boca)

    response = adjust(client, boca, confirmed=False)
    assert response.status_code == 422
    assert code_of(response) == "CONFIRMATION_REQUIRED"


# Escenario 8: Aviso para los socios (HU-13) tras ajuste de reglas --------------------


def test_member_explanation_shows_notice_after_adjustment_when_ranking_behind(
    client: TestClient,
    boca,
    make_member: MakeMember,
    outbox: Outbox,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish(client, boca)
    member = make_member(club_id=BOCA_ID, activated=True)
    member_headers = bearer(member_token(client, outbox, member))
    outbox.clear()

    # Simulamos que hubo un ranking previo completado con la versión 1
    monkeypatch.setattr(
        formula_service,
        "latest_completed_ranking_rules_number",
        lambda db, club_id: 1,
    )

    # Antes del ajuste: versión 1, notice es None
    before = client.get("/member/scoring/explanation", headers=member_headers).json()
    assert before["rules_version"] == 1
    assert before["notice"] is None

    # Ajustamos parámetros a la versión 2
    new_values = dict(DEFAULTS)
    new_values["w_a"] = "0.50"
    new_values["w_p"] = "0.30"
    new_values["w_t"] = "0.20"
    adjust(client, boca, values=new_values, expected=1)

    # Después del ajuste: versión 2, ranking sigue en versión 1 -> notice presente
    after = client.get("/member/scoring/explanation", headers=member_headers).json()
    assert after["rules_version"] == 2
    assert after["notice"] == {
        "code": "RULES_AHEAD_OF_RANKING",
        "message": "Estas reglas se van a reflejar en el ranking después del próximo cálculo.",
    }


# Escenario 9: Auditoría --------------------------------------------------------------


def test_audit_records_previous_and_new_values(
    client: TestClient, boca, db: Session
) -> None:
    publish(client, boca)

    new_values = dict(DEFAULTS)
    new_values["w_a"] = "0.50"
    new_values["w_p"] = "0.30"
    new_values["w_t"] = "0.20"
    adjust(client, boca, values=new_values, expected=1)

    audit = db.scalar(
        select(AuditLog)
        .where(AuditLog.action == "formula.parameters_adjusted")
        .order_by(AuditLog.occurred_at.desc())
    )
    assert audit is not None
    assert audit.details["number"] == 2
    assert audit.details["previous_number"] == 1
    assert audit.details["previous_values"]["w_a"] == "0.6"
    assert audit.details["values"]["w_a"] == "0.5"


# Escenario 10: Corte de temporada (14 días antes del inicio) -------------------------


def test_season_cutoff_blocks_adjustment(
    client: TestClient, boca, monkeypatch: pytest.MonkeyPatch
) -> None:
    publish(client, boca)

    # Configuramos inicio de temporada para el 15/03/2027 (el corte de 14 días es el 01/03/2027)
    season_start = date(2027, 3, 15)
    monkeypatch.setattr(settings, "season_start_date", season_start)

    # Simular fecha antes del corte: 28 de febrero de 2027
    monkeypatch.setattr(
        formula_service,
        "utcnow",
        lambda: datetime(2027, 2, 28, 12, 0, tzinfo=UTC),
    )
    r_before = adjust(client, boca, expected=1)
    assert r_before.status_code == 200

    # Simular fecha en el corte: 1 de marzo de 2027 (Buenos Aires)
    monkeypatch.setattr(
        formula_service,
        "utcnow",
        lambda: datetime(2027, 3, 1, 10, 0, tzinfo=UTC),
    )
    r_cutoff = adjust(client, boca, expected=2)
    assert r_cutoff.status_code == 409
    assert code_of(r_cutoff) == "SEASON_CUTOFF_REACHED"
    detail = r_cutoff.json()["detail"]
    assert "El plazo para modificar parámetros cerró el 01/03/2027" in detail["message"]
    assert detail["cutoff_date"] == "2027-03-01"
    assert detail["season_start_date"] == "2027-03-15"

    # Simular fecha posterior al inicio de temporada
    monkeypatch.setattr(
        formula_service,
        "utcnow",
        lambda: datetime(2027, 3, 20, 10, 0, tzinfo=UTC),
    )
    r_after = adjust(client, boca, expected=2)
    assert r_after.status_code == 409
    assert code_of(r_after) == "SEASON_CUTOFF_REACHED"


def test_no_season_cutoff_when_season_start_is_none(
    client: TestClient, boca, monkeypatch: pytest.MonkeyPatch
) -> None:
    publish(client, boca)
    monkeypatch.setattr(settings, "season_start_date", None)

    response = adjust(client, boca, expected=1)
    assert response.status_code == 200


# Escenario 11: Control de concurrencia optimista (versión desactualizada) ------------


def test_concurrency_conflict_stale_rules(client: TestClient, boca) -> None:
    publish(client, boca)

    # Admin 1 ajusta a versión 2
    r1 = adjust(client, boca, expected=1)
    assert r1.status_code == 200

    # Admin 2 intenta ajustar basándose en versión 1
    r2 = adjust(client, boca, expected=1)
    assert r2.status_code == 409
    assert code_of(r2) == "STALE_RULES"


# Escenario 12: Sin fórmula publicada o fórmula bloqueada -----------------------------


def test_cannot_adjust_without_published_formula(client: TestClient, boca) -> None:
    response = adjust(client, boca, expected=0)
    assert response.status_code == 409
    assert code_of(response) == "FORMULA_NOT_PUBLISHED"


def test_cannot_adjust_when_formula_is_locked(client: TestClient, boca) -> None:
    publish(client, boca)
    lock(client, boca, reason="Revisión de comisión directiva")

    response = adjust(client, boca, expected=1)
    assert response.status_code == 409
    assert code_of(response) == "FORMULA_LOCKED"
    assert "Revisión de comisión directiva" in response.json()["detail"]["message"]


# Per club isolation ------------------------------------------------------------------


def test_adjustments_are_isolated_per_club(client: TestClient, boca, river) -> None:
    publish(client, boca)
    publish(client, river)

    new_boca = dict(DEFAULTS)
    new_boca["w_a"] = "0.50"
    new_boca["w_p"] = "0.30"
    new_boca["w_t"] = "0.20"
    adjust(client, boca, values=new_boca, expected=1)

    # Boca está en versión 2
    boca_overview = client.get("/admin/formulas", headers=boca).json()
    assert boca_overview["in_force"]["number"] == 2
    assert boca_overview["in_force"]["parameters"][0]["value"] == "0.5"

    # River sigue en versión 1
    river_overview = client.get("/admin/formulas", headers=river).json()
    assert river_overview["in_force"]["number"] == 1
    assert river_overview["in_force"]["parameters"][0]["value"] == "0.6"
