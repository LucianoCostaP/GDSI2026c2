"""HU-27: publicar la fórmula base del club, con sus escenarios de aceptación."""

import dataclasses
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    FormulaLock,
    RulesVersion,
    RulesVersionState,
    User,
)
from app.scoring import catalog
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
DEFAULTS = {p.key: str(p.default) for p in SCORING_MODEL_V1.parameters}


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


def lock(client: TestClient, headers: dict[str, str], reason: str = "Congelada"):
    return client.post("/admin/formulas/lock", json={"reason": reason}, headers=headers)


def code_of(response) -> str:
    return str(response.json()["detail"]["code"])


@pytest.fixture
def formula_v2(monkeypatch: pytest.MonkeyPatch):
    """Una segunda versión de la fórmula: alpha_t admite menos (0 a 0.5, por defecto 0.4)."""
    narrower = tuple(
        dataclasses.replace(p, default=Decimal("0.4"), maximum=Decimal("0.5"))
        if p.key == "alpha_t"
        else p
        for p in SCORING_MODEL_V1.parameters
    )
    v2 = dataclasses.replace(SCORING_MODEL_V1, version=2, parameters=narrower)
    assert catalog.descriptor_problems(v2) == []
    monkeypatch.setattr(catalog, "CATALOG", (SCORING_MODEL_V1, v2))
    return v2


# Escenario 1 -------------------------------------------------------------------------


def test_overview_without_publication(client: TestClient, boca) -> None:
    body = client.get("/admin/formulas", headers=boca).json()

    assert body["catalog"] == [
        {
            "id": "scoring-model",
            "version": 1,
            "name": SCORING_MODEL_V1.name,
            "description": SCORING_MODEL_V1.description,
        }
    ]
    assert body["in_force"] is None
    assert body["lock"]["state"] == "unlocked"


def test_overview_shows_the_formula_and_version_in_force(
    client: TestClient, boca
) -> None:
    publish(client, boca)

    in_force = client.get("/admin/formulas", headers=boca).json()["in_force"]

    assert (
        in_force["number"],
        in_force["formula_id"],
        in_force["formula_version"],
    ) == (
        1,
        "scoring-model",
        1,
    )
    assert in_force["published_by"] == "Admin"


# Escenario 2 -------------------------------------------------------------------------


def test_detail_shows_structure_and_defaults(client: TestClient, boca) -> None:
    body = client.get(FORMULA, headers=boca).json()

    assert [p["key"] for p in body["parameters"]][:3] == ["w_a", "w_p", "w_t"]
    d_sat = next(p for p in body["parameters"] if p["key"] == "d_sat")
    assert (d_sat["default"], d_sat["minimum"], d_sat["maximum"], d_sat["unit"]) == (
        "1200",
        "50",
        "3000",
        "km",
    )
    assert body["variables"] and body["constants"] and body["derived_values"]
    assert body["constraints"][0]["parameters"] == ["w_a", "w_p", "w_t"]
    assert body["values"]["w_a"] == "0.6"
    assert body["rules_version_in_force"] is None
    assert body["is_in_force"] is False


def test_unknown_formula_is_not_found(client: TestClient, boca) -> None:
    response = client.get("/admin/formulas/inventada/1", headers=boca)

    assert (response.status_code, code_of(response)) == (404, "FORMULA_NOT_FOUND")


# Escenarios 3 y 4 -----------------------------------------------------------------------


def test_preview_of_valid_values_shows_the_explanation_and_saves_nothing(
    client: TestClient, boca, db: Session
) -> None:
    values = {**DEFAULTS, "w_a": "0.5", "w_p": "0.3"}

    body = client.post(
        f"{FORMULA}/preview", json={"values": values}, headers=boca
    ).json()

    assert body["valid"] is True and body["violations"] == []
    text = str(body["explanation"])
    assert "50 % del puntaje" in text
    assert db.scalars(select(RulesVersion)).all() == []


def test_preview_of_invalid_values_shows_violations_and_no_explanation(
    client: TestClient, boca
) -> None:
    values = {**DEFAULTS, "d_sat": "10"}
    del values["gamma"]

    body = client.post(
        f"{FORMULA}/preview", json={"values": values}, headers=boca
    ).json()

    assert body["valid"] is False and body["explanation"] is None
    assert {(v["code"], v["parameter"]) for v in body["violations"]} == {
        ("PARAMETER_MISSING", "gamma"),
        ("PARAMETER_OUT_OF_LIMITS", "d_sat"),
    }


def test_preview_reports_the_sum_that_fails(client: TestClient, boca) -> None:
    values = {**DEFAULTS, "w_a": "0.5"}

    body = client.post(
        f"{FORMULA}/preview", json={"values": values}, headers=boca
    ).json()

    assert [v["code"] for v in body["violations"]] == ["SUM_CONSTRAINT_VIOLATED"]
    assert "hoy suman 0,9" in body["violations"][0]["message"]


# Escenario 5 -------------------------------------------------------------------------


def test_first_publication_is_rules_version_1_and_in_force(
    client: TestClient, boca, db: Session
) -> None:
    response = publish(client, boca)

    assert response.status_code == 201
    body = response.json()
    assert body["number"] == 1
    assert body["in_force"]["number"] == 1
    rules = db.scalars(select(RulesVersion)).one()
    assert (rules.club_id, rules.state) == (BOCA_ID, RulesVersionState.IN_FORCE)


def test_publication_requires_confirmation(
    client: TestClient, boca, db: Session
) -> None:
    response = publish(client, boca, confirmed=False)

    assert (response.status_code, code_of(response)) == (422, "CONFIRMATION_REQUIRED")
    assert db.scalars(select(RulesVersion)).all() == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda v: {**v, "d_sat": "10"},
        lambda v: {**v, "w_a": "0.9"},
        lambda v: {k: x for k, x in v.items() if k != "gamma"},
        lambda v: {**v, "extra": "1"},
        lambda v: {**v, "gamma": "abc"},
    ],
)
def test_invalid_values_are_never_published(
    client: TestClient, boca, db: Session, mutate
) -> None:
    response = publish(client, boca, values=mutate(DEFAULTS))

    assert (response.status_code, code_of(response)) == (422, "INVALID_VALUES")
    assert response.json()["detail"]["violations"]
    assert db.scalars(select(RulesVersion)).all() == []


# Escenario 6 -------------------------------------------------------------------------


def test_there_is_no_way_to_create_formulas_or_change_their_structure(
    client: TestClient, boca
) -> None:
    for method, path in [
        ("post", "/admin/formulas"),
        ("put", FORMULA),
        ("patch", FORMULA),
        ("delete", FORMULA),
    ]:
        response = client.request(method.upper(), path, json={}, headers=boca)
        assert response.status_code in (404, 405)


# Escenario 7 -------------------------------------------------------------------------


def test_rules_in_force_are_required_by_other_features(
    db: Session,
) -> None:
    with pytest.raises(Exception) as error:
        formula_service.require_rules_in_force(db, BOCA_ID)

    assert error.value.status_code == 409  # type: ignore[attr-defined]
    assert error.value.detail["code"] == "FORMULA_NOT_PUBLISHED"  # type: ignore[attr-defined]


def test_rules_in_force_are_returned_once_published(
    client: TestClient, boca, db: Session
) -> None:
    publish(client, boca)

    assert formula_service.require_rules_in_force(db, BOCA_ID).number == 1


# Escenarios 8 y 9 --------------------------------------------------------------------


def test_new_version_is_prefilled_with_compatible_values_and_defaults_for_the_rest(
    client: TestClient, boca, formula_v2
) -> None:
    # alpha_t = 0.7 está en vigor, pero la versión 2 solo admite hasta 0.5: usa su default.
    publish(client, boca, values={**DEFAULTS, "w_a": "0.5", "w_p": "0.3"})

    body = client.get("/admin/formulas/scoring-model/2", headers=boca).json()

    assert body["values"]["w_a"] == "0.5"
    assert body["values"]["w_p"] == "0.3"
    assert body["values"]["alpha_t"] == "0.4"
    assert body["rules_version_in_force"] == 1
    assert body["is_in_force"] is False


def test_publishing_a_newer_version_supersedes_the_one_in_force(
    client: TestClient, boca, formula_v2, db: Session
) -> None:
    publish(client, boca)
    values = {**DEFAULTS, "alpha_t": "0.4"}

    response = publish(
        client, boca, values=values, expected=1, path="/admin/formulas/scoring-model/2"
    )

    assert response.status_code == 201 and response.json()["number"] == 2
    first, second = db.scalars(select(RulesVersion).order_by(RulesVersion.number))
    assert first.state == RulesVersionState.SUPERSEDED
    assert second.state == RulesVersionState.IN_FORCE
    assert second.previous_version_id == first.id
    assert (second.formula_version, first.formula_version) == (2, 1)


def test_publishing_the_same_formula_and_version_is_rejected(
    client: TestClient, boca, db: Session
) -> None:
    publish(client, boca)

    response = publish(client, boca, values={**DEFAULTS, "gamma": "0.8"}, expected=1)

    assert (response.status_code, code_of(response)) == (409, "SAME_FORMULA_IN_FORCE")
    assert len(db.scalars(select(RulesVersion)).all()) == 1


# Escenario 10 ------------------------------------------------------------------------


def test_publication_is_stored_unchanged_and_audited(
    client: TestClient, boca, db: Session
) -> None:
    values = {**DEFAULTS, "w_a": "0.5", "w_p": "0.30", "d_sat": "900.0"}
    publish(client, boca, values=values)

    rules = db.scalars(select(RulesVersion)).one()
    assert rules.values["w_a"] == "0.5"
    assert rules.values["w_p"] == "0.3"
    assert rules.values["d_sat"] == "900"
    assert (rules.formula_id, rules.formula_version, rules.number) == (
        "scoring-model",
        1,
        1,
    )
    assert rules.published_by_id and rules.published_at
    entry = db.scalars(
        select(AuditLog).where(AuditLog.action == "formula.published")
    ).one()
    assert entry.actor_user_id == rules.published_by_id
    assert entry.details["values"]["w_a"] == "0.5"
    assert entry.details["club_id"] == str(BOCA_ID)


def test_after_publishing_the_admin_sees_the_rules_and_the_explanation(
    client: TestClient, boca
) -> None:
    body = publish(client, boca).json()

    assert body["message"] == (
        "Publicaste las reglas versión 1: ya están vigentes en el club."
    )
    assert body["in_force"]["parameters"][0]["value"] == "0.6"
    assert [b["id"] for b in body["in_force"]["explanation"]["blocks"]] == [
        "formula",
        "common",
    ]


def test_the_database_allows_a_single_version_in_force_per_club(
    client: TestClient, boca, db: Session, admin
) -> None:
    publish(client, boca)

    db.add(
        RulesVersion(
            club_id=BOCA_ID,
            number=2,
            formula_id="scoring-model",
            formula_version=1,
            values={},
            state=RulesVersionState.IN_FORCE,
            published_by_id=admin.id,
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


# Escenario 11 ------------------------------------------------------------------------


def test_locking_requires_a_reason_and_is_audited(
    client: TestClient, boca, db: Session
) -> None:
    assert lock(client, boca, "  ").status_code == 422

    response = lock(client, boca, "Revisión de reglas")

    assert response.status_code == 200
    assert response.json()["state"] == "locked"
    assert response.json()["reason"] == "Revisión de reglas"
    entry = db.scalars(
        select(AuditLog).where(AuditLog.action == "formula.locked")
    ).one()
    assert entry.details["reason"] == "Revisión de reglas"
    assert entry.details["after"] == {"state": "locked"}


def test_publishing_is_rejected_while_locked_with_since_who_and_why(
    client: TestClient, boca
) -> None:
    lock(client, boca, "Congelada por la comisión")

    response = publish(client, boca)

    assert (response.status_code, code_of(response)) == (409, "FORMULA_LOCKED")
    detail = response.json()["detail"]
    assert "Admin" in detail["message"]
    assert "Congelada por la comisión" in detail["message"]
    assert detail["locked_at"]


def test_locking_without_a_published_formula_blocks_the_first_publication(
    client: TestClient, boca, db: Session
) -> None:
    lock(client, boca)

    assert code_of(publish(client, boca)) == "FORMULA_LOCKED"
    assert db.scalars(select(RulesVersion)).all() == []


def test_any_admin_of_the_club_can_unlock_and_it_is_audited(
    client: TestClient, outbox: Outbox, boca, make_admin: MakeAdmin, db: Session
) -> None:
    lock(client, boca)
    other = headers_for(client, outbox, make_admin(BOCA_ID))

    response = client.post(
        "/admin/formulas/unlock", json={"reason": "Ya se revisó"}, headers=other
    )

    assert response.status_code == 200 and response.json()["state"] == "unlocked"
    assert publish(client, other).status_code == 201
    assert db.scalars(
        select(AuditLog).where(AuditLog.action == "formula.unlocked")
    ).one()


def test_lock_state_conflicts_are_rejected(client: TestClient, boca) -> None:
    unlock = client.post("/admin/formulas/unlock", json={"reason": "x"}, headers=boca)
    assert (unlock.status_code, code_of(unlock)) == (409, "NOT_LOCKED")

    lock(client, boca)
    again = lock(client, boca)
    assert (again.status_code, code_of(again)) == (409, "ALREADY_LOCKED")


def test_the_lock_does_not_affect_viewing_or_the_rules_in_force(
    client: TestClient, boca, db: Session
) -> None:
    publish(client, boca)
    lock(client, boca)

    body = client.get("/admin/formulas", headers=boca).json()

    assert body["lock"]["state"] == "locked"
    assert body["in_force"]["number"] == 1
    assert formula_service.require_rules_in_force(db, BOCA_ID).number == 1


def test_require_unlocked_is_available_for_parameter_adjustment(
    client: TestClient, boca, db: Session
) -> None:
    formula_service.require_unlocked(db, BOCA_ID)
    lock(client, boca)

    with pytest.raises(Exception) as error:
        formula_service.require_unlocked(db, BOCA_ID)

    assert error.value.detail["code"] == "FORMULA_LOCKED"  # type: ignore[attr-defined]


# Escenario 12 ------------------------------------------------------------------------


def test_confirming_over_changed_rules_is_refused(
    client: TestClient, boca, formula_v2
) -> None:
    # Dos Admins abren el formulario sin reglas vigentes; el primero publica.
    assert publish(client, boca).status_code == 201

    response = publish(
        client, boca, expected=None, path="/admin/formulas/scoring-model/2"
    )

    assert (response.status_code, code_of(response)) == (409, "STALE_RULES")


def test_confirming_with_the_wrong_version_number_is_refused(
    client: TestClient, boca, formula_v2
) -> None:
    publish(client, boca)

    response = publish(client, boca, expected=7, path="/admin/formulas/scoring-model/2")

    assert code_of(response) == "STALE_RULES"


def test_confirming_after_the_formula_got_locked_is_refused(
    client: TestClient, boca
) -> None:
    lock(client, boca)

    assert code_of(publish(client, boca)) == "FORMULA_LOCKED"


def test_the_expected_version_is_required(client: TestClient, boca) -> None:
    response = client.post(
        f"{FORMULA}/publish", json={"values": DEFAULTS, "confirmed": True}, headers=boca
    )

    assert response.status_code == 422


# Escenario 13 ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/admin/formulas"),
        ("get", FORMULA),
        ("post", f"{FORMULA}/preview"),
        ("post", f"{FORMULA}/publish"),
        ("post", "/admin/formulas/lock"),
        ("post", "/admin/formulas/unlock"),
    ],
)
def test_members_are_forbidden_and_anonymous_requests_are_unauthenticated(
    client: TestClient, outbox: Outbox, make_member: MakeMember, method: str, path: str
) -> None:
    body = {
        "values": DEFAULTS,
        "expected_rules_version": None,
        "confirmed": True,
        "reason": "x",
    }
    request = getattr(client, method)
    kwargs = {} if method == "get" else {"json": body}

    anonymous = request(path, **kwargs)
    member = make_member(activated=True)
    forbidden = request(
        path, headers=bearer(member_token(client, outbox, member)), **kwargs
    )

    assert anonymous.status_code == 401
    assert (forbidden.status_code, forbidden.json()["detail"]) == (403, "FORBIDDEN")


def test_a_forbidden_member_cannot_publish_anything(
    client: TestClient, outbox: Outbox, make_member: MakeMember, db: Session
) -> None:
    member = make_member(activated=True)
    publish(client, bearer(member_token(client, outbox, member)))

    assert db.scalars(select(RulesVersion)).all() == []


# Escenario 14 ------------------------------------------------------------------------


def test_each_club_has_its_own_rules(client: TestClient, boca, river) -> None:
    publish(client, boca)

    assert client.get("/admin/formulas", headers=river).json()["in_force"] is None
    assert publish(client, river).json()["number"] == 1
    assert client.get("/admin/formulas", headers=boca).json()["in_force"]["number"] == 1


def test_each_club_has_its_own_lock(client: TestClient, boca, river) -> None:
    lock(client, boca)

    assert client.get("/admin/formulas", headers=river).json()["lock"]["state"] == (
        "unlocked"
    )
    assert publish(client, river).status_code == 201
    assert code_of(publish(client, boca)) == "FORMULA_LOCKED"


def test_the_club_is_never_taken_from_the_request(
    client: TestClient, boca, db: Session
) -> None:
    other = str(uuid.UUID(str(RIVER_ID)))
    response = client.post(
        f"{FORMULA}/publish?club_id={other}",
        json={
            "values": DEFAULTS,
            "expected_rules_version": None,
            "confirmed": True,
            "club_id": other,
        },
        headers={**boca, "X-Club-ID": other},
    )

    assert response.status_code == 201
    assert db.scalars(select(RulesVersion)).one().club_id == BOCA_ID
    assert db.scalars(select(FormulaLock)).all() == []


def test_an_admin_without_club_cannot_use_the_section(
    client: TestClient, outbox: Outbox, make_admin: MakeAdmin
) -> None:
    headers = headers_for(client, outbox, make_admin(None))

    response = client.get("/admin/formulas", headers=headers)

    assert (response.status_code, response.json()["detail"]) == (
        403,
        "ADMIN_WITHOUT_CLUB",
    )
