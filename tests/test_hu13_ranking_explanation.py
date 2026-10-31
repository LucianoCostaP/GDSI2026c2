"""HU-13: explicación del ranking para el Socio, con sus escenarios de aceptación."""

import json
import re

import pytest
from fastapi.testclient import TestClient

from app.models import FeeStatus, RulesVersion, RulesVersionState, User, utcnow
from app.scoring.catalog import SCORING_MODEL_V1
from app.scoring.explanation import render_explanation
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

URL = "/member/scoring/explanation"
FORMULA = "/admin/formulas/scoring-model/1"
DEFAULTS = {p.key: str(p.default) for p in SCORING_MODEL_V1.parameters}


def admin_headers(client: TestClient, outbox: Outbox, user: User) -> dict[str, str]:
    headers = bearer(admin_token(client, outbox, user))
    outbox.clear()
    return headers


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, make_admin: MakeAdmin) -> dict[str, str]:
    return admin_headers(client, outbox, make_admin(BOCA_ID))


@pytest.fixture
def river(client: TestClient, outbox: Outbox, make_admin: MakeAdmin) -> dict[str, str]:
    return admin_headers(client, outbox, make_admin(RIVER_ID))


@pytest.fixture
def socio(client: TestClient, outbox: Outbox, make_member: MakeMember):
    """Headers de un Socio activado de Boca."""
    headers = bearer(member_token(client, outbox, make_member(activated=True)))
    outbox.clear()
    return headers


def publish(client, headers, values=None, expected=None, path=FORMULA):
    response = client.post(
        f"{path}/publish",
        json={
            "values": DEFAULTS if values is None else values,
            "expected_rules_version": expected,
            "confirmed": True,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response


def text_of(explanation: dict) -> str:
    return " ".join(
        [explanation["title"]]
        + [
            part
            for block in explanation["blocks"]
            for section in block["sections"]
            for part in (section["heading"], *section["paragraphs"])
        ]
    )


def block(explanation: dict, block_id: str) -> str:
    return text_of(
        {
            "title": "",
            "blocks": [b for b in explanation["blocks"] if b["id"] == block_id],
        }
    )


# Escenario 1 ---------------------------------------------------------------------------


def test_socio_reads_the_explanation_in_spanish_with_current_values(
    client: TestClient, boca, socio
) -> None:
    publish(client, boca, {**DEFAULTS, "d_sat": "800"})

    body = client.get(URL, headers=socio).json()

    assert body["status"] == "published"
    assert body["message"] is None
    assert body["rules_version"] == 1
    assert body["formula"]["id"] == "scoring-model"
    explanation = body["explanation"]
    assert explanation["title"] == "¿Cómo se calcula mi puntaje?"
    formula_text = block(explanation, "formula")
    assert "0 a 100" in formula_text
    assert "60 %" in formula_text and "20 %" in formula_text
    assert "800 km" in formula_text
    assert "1200" not in formula_text


# Escenario 2 ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_the_explanation_is_read_only(client: TestClient, boca, socio, method) -> None:
    publish(client, boca)

    assert getattr(client, method)(URL, headers=socio).status_code == 405


# Escenario 3 ---------------------------------------------------------------------------


def test_after_a_rules_change_the_old_values_are_gone(
    client: TestClient, boca, socio, db
) -> None:
    # HU-27 no deja republicar la misma fórmula; el cambio de reglas (HU-28) se simula
    # guardando directamente una versión nueva.
    publish(client, boca)
    old = db.query(RulesVersion).one()
    old.state = RulesVersionState.SUPERSEDED
    db.flush()
    db.add(
        RulesVersion(
            club_id=BOCA_ID,
            number=2,
            formula_id="scoring-model",
            formula_version=1,
            values={**old.values, "w_a": "0.50", "w_p": "0.30", "w_t": "0.20"},
            state=RulesVersionState.IN_FORCE,
            published_by_id=old.published_by_id,
            published_at=utcnow(),
            previous_version_id=old.id,
        )
    )
    db.commit()

    response = client.get(URL, headers=socio)
    body = response.json()

    assert response.headers["Cache-Control"] == "no-store"
    assert body["rules_version"] == 2
    assert "50 %" in block(body["explanation"], "formula")
    assert "60 %" not in block(body["explanation"], "formula")


# Escenario 4 ---------------------------------------------------------------------------


def test_every_socio_of_a_club_sees_the_same_and_other_clubs_see_their_own(
    client: TestClient, outbox: Outbox, make_member: MakeMember, boca, river
) -> None:
    publish(client, boca)
    publish(client, river, {**DEFAULTS, "w_a": "0.40", "w_p": "0.30", "w_t": "0.30"})
    first = bearer(member_token(client, outbox, make_member(activated=True)))
    second = bearer(member_token(client, outbox, make_member(activated=True)))
    other = bearer(
        member_token(client, outbox, make_member(activated=True, club_id=RIVER_ID))
    )

    a = client.get(URL, headers=first).json()
    b = client.get(URL, headers=second).json()
    c = client.get(URL, headers=other).json()

    assert a == b
    assert "60 %" in block(a["explanation"], "formula")
    assert "40 %" in block(c["explanation"], "formula")


def test_the_club_is_never_taken_from_the_request(
    client: TestClient, boca, river, socio
) -> None:
    publish(client, boca)
    publish(client, river, {**DEFAULTS, "w_a": "0.40", "w_p": "0.30", "w_t": "0.30"})
    other = str(RIVER_ID)

    response = client.get(
        f"{URL}?club_id={other}", headers={**socio, "X-Club-ID": other}
    )

    assert "60 %" in block(response.json()["explanation"], "formula")


def test_a_socio_account_without_club_is_rejected(
    client: TestClient, outbox: Outbox, make_member: MakeMember
) -> None:
    headers = bearer(
        member_token(client, outbox, make_member(activated=True, club_id=None))
    )

    response = client.get(URL, headers=headers)

    assert (response.status_code, response.json()["detail"]) == (
        403,
        "MEMBER_WITHOUT_CLUB",
    )


# Escenarios 5 y 7 ----------------------------------------------------------------------
# HU-25 todavía no existe: se simula la consulta del último ranking completado.
# Estos tests fijan la versión del último ranking con un reemplazo (monkeypatch). La
# integración sin mocks, con rankings reales de HU-25, está en tests/test_hu25_ranking_in_force.py.


def test_notice_when_the_rules_in_force_differ_from_the_latest_ranking(
    client: TestClient, boca, socio, monkeypatch
) -> None:
    publish(client, boca)
    monkeypatch.setattr(
        formula_service, "latest_completed_ranking_rules_number", lambda db, club: 0
    )

    notice = client.get(URL, headers=socio).json()["notice"]

    assert notice == {
        "code": "RULES_AHEAD_OF_RANKING",
        "message": formula_service.RULES_AHEAD_OF_RANKING_NOTICE,
    }
    assert "próximo cálculo" in notice["message"]


def test_no_notice_when_the_latest_ranking_used_the_rules_in_force(
    client: TestClient, boca, socio, monkeypatch
) -> None:
    publish(client, boca)
    monkeypatch.setattr(
        formula_service, "latest_completed_ranking_rules_number", lambda db, club: 1
    )

    assert client.get(URL, headers=socio).json()["notice"] is None


def test_no_notice_and_normal_explanation_without_a_completed_ranking(
    client: TestClient, boca, socio
) -> None:
    publish(client, boca)

    body = client.get(URL, headers=socio).json()

    assert body["notice"] is None
    assert body["explanation"] is not None


# Escenario 6 ---------------------------------------------------------------------------


def test_a_club_without_published_formula_gets_a_friendly_message_not_an_error(
    client: TestClient, socio
) -> None:
    response = client.get(URL, headers=socio)

    assert response.status_code == 200
    assert response.json() == {
        "status": "none",
        "message": (
            "Todavía no hay reglas de puntaje publicadas. "
            "Cuando el club las publique, vas a poder verlas acá."
        ),
        "rules_version": None,
        "formula": None,
        "explanation": None,
        "notice": None,
    }


def test_the_no_rules_message_is_not_the_admin_error(client: TestClient, socio) -> None:
    assert "sección Fórmula" not in client.get(URL, headers=socio).text


# Escenario 8 ---------------------------------------------------------------------------


def test_the_common_block_states_eligibility_history_and_tiebreak(
    client: TestClient, boca, socio
) -> None:
    publish(client, boca)

    common = block(client.get(URL, headers=socio).json()["explanation"], "common")

    assert "0 a 100" in common
    assert "cuota al día" in common
    assert "historial" in common and "volvés al ranking" in common
    assert "mayor antigüedad" in common
    assert "mayor edad" in common
    assert "menor número de documento" in common
    assert "no muestra datos de otros socios" in common


# Escenario 9 ---------------------------------------------------------------------------


def test_the_scoring_model_text_covers_every_part_with_current_values(
    client: TestClient, boca, socio
) -> None:
    values = {
        **DEFAULTS,
        "alpha_a": "0.30",
        "p_inst_max": "80",
        "alpha_t": "0.60",
        "t_ref": "40",
        "e_ref": "90",
        "gamma": "0.8",
        "b_max": "10",
        "t_max": "90",
        "t_carencia": "200",
    }
    publish(client, boca, values)

    text = block(client.get(URL, headers=socio).json()["explanation"], "formula")

    assert "los de menor demanda pesan más" in text
    assert "año anterior" in text  # ventana de asistencia
    assert "30 % de tu puntaje de asistencia" in text  # distancia
    assert "365 días" in text and "tope de 80 puntos" in text  # participación
    assert (
        "60 %" in text and "40 años" in text and "90 años" in text
    )  # antigüedad y edad
    assert "curvatura vale 0,8" in text
    assert "hasta 10 puntos extra" in text and "90 días" in text and "200 días" in text


def test_the_template_texts_match_the_constants_of_the_formula() -> None:
    """Los números fijos que la plantilla escribe a mano tienen que ser los de las constantes
    del descriptor: si cambia uno sin el otro, la explicación se desfasa de las reglas."""
    values = {p.key: p.default for p in SCORING_MODEL_V1.parameters}
    text = text_of(render_explanation(SCORING_MODEL_V1, values).to_dict())
    constants = {c.symbol: c.value for c in SCORING_MODEL_V1.constants}

    for clazz in ("A", "B", "C"):
        assert f"Clase {clazz}" in text
    assert f"vale {constants['C(Clase A)']}" in text
    assert f"vale {constants['C(Clase B)']}" in text
    assert f"vale {constants['C(Clase C)']}" in text
    assert f"({constants['Deporte Federado']} puntos por mes)" in text
    assert f"({constants['Subcomisiones']} puntos por mes" in text
    assert f"{constants['Vigencia']} días" in text


# Escenario 10 --------------------------------------------------------------------------


def test_a_socio_with_overdue_fees_also_sees_the_explanation(
    client: TestClient, outbox: Outbox, make_member: MakeMember, boca
) -> None:
    publish(client, boca)
    member = make_member(activated=True, fee_status=FeeStatus.OVERDUE)
    headers = bearer(member_token(client, outbox, member))

    response = client.get(URL, headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "published"


def test_the_formula_lock_does_not_affect_the_explanation(
    client: TestClient, boca, socio
) -> None:
    publish(client, boca)
    client.post("/admin/formulas/lock", json={"reason": "Congelada"}, headers=boca)

    assert client.get(URL, headers=socio).json()["status"] == "published"


def test_the_socio_does_not_get_admin_data(client: TestClient, boca, socio) -> None:
    publish(client, boca)

    body = client.get(URL, headers=socio).json()

    assert set(body) == {
        "status",
        "message",
        "rules_version",
        "formula",
        "explanation",
        "notice",
    }
    assert "Admin" not in json.dumps(body)


# Escenario 11 --------------------------------------------------------------------------


def test_admins_are_forbidden_and_anonymous_requests_are_unauthenticated(
    client: TestClient, boca
) -> None:
    forbidden = client.get(URL, headers=boca)
    anonymous = client.get(URL)

    assert (forbidden.status_code, forbidden.json()["detail"]) == (403, "FORBIDDEN")
    assert (anonymous.status_code, anonymous.json()["detail"]) == (
        401,
        "NOT_AUTHENTICATED",
    )


# FR-008 y SC-003 -----------------------------------------------------------------------


def test_the_admin_preview_and_the_socio_view_are_identical(
    client: TestClient, boca, socio
) -> None:
    typed = {**DEFAULTS, "w_a": "0.6", "d_sat": "1200.0", "b_max": "15"}
    preview = client.post(f"{FORMULA}/preview", json={"values": typed}, headers=boca)
    publish(client, boca, typed)

    seen = client.get(URL, headers=socio).json()["explanation"]

    assert preview.json()["valid"] is True
    assert preview.json()["explanation"] == seen
    assert (
        client.get("/admin/formulas", headers=boca).json()["in_force"]["explanation"]
        == seen
    )


def test_no_placeholder_is_left_unfilled(client: TestClient, boca, socio) -> None:
    publish(client, boca)

    text = text_of(client.get(URL, headers=socio).json()["explanation"])

    assert not re.search(r"[{}]", text)
