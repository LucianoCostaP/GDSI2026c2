"""HU-29, escenario 5: permisos y club.

"Given a user who is not an Admin, When they try to open or run the simulator, Then they are
rejected with `FORBIDDEN`; an Admin without club is rejected with `ADMIN_WITHOUT_CLUB`; an
unauthenticated request with `NOT_AUTHENTICATED`. The club is taken from the account and the
ranking read is the club's own (cross-cutting section 9); a club sent in the request is
ignored." Contrato: `docs/contrato-api-simulacion-reglas.md` §1 (errores comunes).
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import RankingState, User
from app.services.rules_simulation_service import NO_BASELINE_MESSAGE
from tests.conftest import RIVER_ID, MakeAdmin, MakeMember, Outbox, bearer, member_token
from tests.hu25_helpers import (
    DEFAULTS,
    RUNS,
    headers_for,
    make_ranking,
    make_socio,
    publish_rules,
)

SIMULATOR = "/admin/rules-simulation"


def open_simulator(client: TestClient, **kwargs: object) -> Any:
    return client.get(SIMULATOR, **kwargs)


def run_simulation(client: TestClient, **kwargs: object) -> Any:
    json = kwargs.pop("json", {"values": DEFAULTS})
    return client.post(SIMULATOR, json=json, **kwargs)


# Abrir (`GET`) y simular (`POST`) tienen las mismas reglas de acceso.
ENDPOINTS = pytest.mark.parametrize(
    "call", [open_simulator, run_simulation], ids=["open", "run"]
)


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    return headers_for(client, outbox, admin)


@pytest.fixture
def boca_ranking(client: TestClient, db: Session, boca: dict[str, str]) -> int:
    """Boca con reglas publicadas y un ranking completado de un socio."""
    publish_rules(client, boca)
    make_socio(db)
    response = client.post(RUNS, headers=boca)
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


# --- Aceptación ----------------------------------------------------------------------------


@ENDPOINTS
def test_a_member_is_forbidden(
    call: Callable[..., Any],
    client: TestClient,
    outbox: Outbox,
    make_member: MakeMember,
    boca_ranking: int,
) -> None:
    member = make_member(activated=True)
    headers = bearer(member_token(client, outbox, member))

    response = call(client, headers=headers)

    assert response.status_code == 403
    assert response.json() == {"detail": "FORBIDDEN"}


@ENDPOINTS
def test_an_admin_without_club_is_rejected(
    call: Callable[..., Any],
    client: TestClient,
    outbox: Outbox,
    make_admin: MakeAdmin,
    boca_ranking: int,
) -> None:
    headers = headers_for(client, outbox, make_admin(None))

    response = call(client, headers=headers)

    assert response.status_code == 403
    assert response.json() == {"detail": "ADMIN_WITHOUT_CLUB"}


@ENDPOINTS
def test_an_unauthenticated_request_is_rejected(
    call: Callable[..., Any], client: TestClient, boca_ranking: int
) -> None:
    response = call(client)

    assert response.status_code == 401
    assert response.json() == {"detail": "NOT_AUTHENTICATED"}


@ENDPOINTS
def test_the_club_comes_from_the_account_and_a_club_in_the_request_is_ignored(
    call: Callable[..., Any],
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    boca_ranking: int,
) -> None:
    # River tiene un ranking más nuevo: si se leyera el club del pedido, sería la base.
    river = make_ranking(
        db,
        admin,
        RankingState.COMPLETED,
        club_id=RIVER_ID,
        completed_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    kwargs: dict[str, object] = {
        "params": {"club_id": str(RIVER_ID)},
        "headers": {**boca, "X-Club-ID": str(RIVER_ID)},
    }
    if call is run_simulation:
        kwargs["json"] = {"values": DEFAULTS, "club_id": str(RIVER_ID)}

    response = call(client, **kwargs)

    assert response.status_code == 200, response.text
    assert response.json()["ranking"]["id"] == boca_ranking != river.id
    assert response.json()["ranking"]["population_size"] == 1


@ENDPOINTS
def test_the_ranking_of_another_club_is_never_the_baseline(
    call: Callable[..., Any],
    client: TestClient,
    outbox: Outbox,
    make_admin: MakeAdmin,
    boca_ranking: int,
) -> None:
    # Boca tiene un ranking completado; River no tiene ninguno.
    river = headers_for(client, outbox, make_admin(RIVER_ID))

    response = call(client, headers=river)

    assert response.status_code == 409
    assert response.json() == {
        "detail": {"code": "NO_BASELINE", "message": NO_BASELINE_MESSAGE}
    }
