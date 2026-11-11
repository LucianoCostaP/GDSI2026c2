"""HU-29, escenario 26: descargar el resultado en CSV.

"Given a result shown, When the Admin asks to download it, Then a CSV file with the same figures
as the screen is generated at that moment (format in "Export"). It is not stored anywhere, and
the real data does not change."
Contrato: `docs/contrato-api-simulacion-reglas.md` §7.
"""

import csv
import io
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Ranking,
    RankingEntry,
    RankingState,
    RulesVersion,
    Socio,
    User,
)
from app.services import rules_simulation_service
from app.services.rules_simulation_export import filename
from app.services.rules_simulation_service import EMPTY_RANKING_MESSAGE
from tests.conftest import RIVER_ID, MakeAdmin, MakeMember, Outbox, bearer, member_token
from tests.hu25_helpers import (
    DEFAULTS,
    adjust_rules,
    headers_for,
    make_ranking,
    publish_rules,
)
from tests.hu29_helpers import SIMULATOR, SPREAD, make_saturation_club, run_ranking

EXPORT = f"{SIMULATOR}/export"
BREAKDOWN = f"{SIMULATOR}/breakdown"
HEADER = ["seccion", "elemento", "antes", "despues", "diferencia"]
# 22:30 UTC del 7/11 son las 19:30 en Buenos Aires.
DOWNLOADED_AT = datetime(2026, 11, 7, 22, 30, tzinfo=UTC)
SECTIONS = [
    "contexto",
    "parametros",
    "resumen",
    "histograma",
    "saturacion",
    "componentes",
    "parametro_aislado",
    "perfil",
]


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    headers = headers_for(client, outbox, admin)
    publish_rules(client, headers)
    return headers


@pytest.fixture
def ranking(db: Session, admin: User, boca: dict[str, str]) -> Ranking:
    make_saturation_club(db)
    return run_ranking(db, admin)


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rules_simulation_service, "utcnow", lambda: DOWNLOADED_AT)


def download(
    client: TestClient, headers: dict[str, str], ranking_id: int, values: dict[str, Any]
) -> Any:
    return client.post(
        EXPORT, json={"ranking_id": ranking_id, "values": values}, headers=headers
    )


def rows_of(
    client: TestClient, headers: dict[str, str], ranking_id: int, values: dict[str, Any]
) -> list[list[str]]:
    response = download(client, headers, ranking_id, values)
    assert response.status_code == 200, response.text
    assert response.content.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert rows[0] == HEADER
    return rows[1:]


def section(rows: list[list[str]], name: str) -> list[list[str]]:
    return [row[1:] for row in rows if row[0] == name]


def screen(
    client: TestClient, headers: dict[str, str], values: dict[str, Any]
) -> tuple[Any, Any]:
    body = client.post(SIMULATOR, json={"values": values}, headers=headers).json()
    factors = client.post(
        BREAKDOWN,
        json={"ranking_id": body["ranking"]["id"], "values": values},
        headers=headers,
    ).json()
    return body, factors


# --- Aceptación ----------------------------------------------------------------------------


def test_the_download_is_a_csv_file_named_with_the_buenos_aires_time(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    response = download(client, boca, ranking.id, SPREAD)

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="simulacion-reglas-20261107-1930.csv"'
    )
    assert response.headers["cache-control"] == "no-store"


def test_the_front_can_read_the_file_name_from_another_origin(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    # El front en producción está en otro origen: sin exponer el header no ve el nombre.
    response = client.post(
        EXPORT,
        json={"ranking_id": ranking.id, "values": SPREAD},
        headers={**boca, "Origin": "http://localhost:5173"},
    )

    assert response.status_code == 200, response.text
    exposed = response.headers["access-control-expose-headers"].lower()
    assert "content-disposition" in exposed


def test_the_file_has_the_sections_in_the_order_of_the_screen(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    rows = rows_of(client, boca, ranking.id, SPREAD)

    assert list(dict.fromkeys(row[0] for row in rows)) == SECTIONS
    # Cinco columnas en todas las filas, separadas por coma y con punto decimal.
    assert all(len(row) == 5 for row in rows)
    assert all("," not in cell for row in rows for cell in row[2:])


def test_the_file_has_the_same_figures_as_the_screen(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    body, factors = screen(client, boca, SPREAD)

    rows = rows_of(client, boca, ranking.id, SPREAD)

    # La diferencia de cada parámetro se prueba en su propio test.
    assert [row[:3] for row in section(rows, "parametros")] == [
        [p["symbol"], p["before"], p["after"]] for p in body["changed_parameters"]
    ]
    summary = body["summary"]
    movement = body["movement"]
    threshold = movement["relevant_threshold"]
    assert section(rows, "resumen") == [
        [label, summary["before"][k], summary["after"][k], summary["difference"][k]]
        for k, label in [
            ("mean", "media"),
            ("median", "mediana"),
            ("std_dev", "desvío estándar"),
            ("p10", "percentil 10"),
            ("p90", "percentil 90"),
        ]
    ] + [
        ["suben", "", str(movement["up"]), ""],
        ["bajan", "", str(movement["down"]), ""],
        ["sin cambios", "", str(movement["unchanged"]), ""],
        [f"suben {threshold} posiciones o más", "", str(movement["relevant_up"]), ""],
        [f"bajan {threshold} posiciones o más", "", str(movement["relevant_down"]), ""],
        [
            "cambio absoluto medio de posición",
            "",
            movement["mean_abs_position_change"],
            "",
        ],
    ]
    assert section(rows, "histograma") == [
        [
            b["label"].replace(",", ";"),
            str(b["before"]),
            str(b["after"]),
            str(b["after"] - b["before"]),
        ]
        for b in body["histogram"]
    ]
    saturation = body["saturation"]
    assert [row[1:] for row in section(rows, "saturacion")] == [
        [
            str(saturation["before"][k]),
            str(saturation["after"][k]),
            str(saturation["after"][k] - saturation["before"][k]),
        ]
        for k in ("at_cap", "needs_cap_adjustment", "tied", "largest_tie")
    ]
    assert section(rows, "componentes") == [
        [c["label"], c["before"], c["after"], c["difference"]]
        for c in body["components"]
    ]
    expected_isolated = []
    for f in factors["factors"]:
        expected_isolated += [
            [f"{f['label']}: cambio del total medio", "", "", f["mean_total_change"]],
            [f"{f['label']}: suben", "", str(f["up"]), ""],
            [f"{f['label']}: bajan", "", str(f["down"]), ""],
            [
                f"{f['label']}: cambio absoluto medio de posición",
                "",
                f["mean_abs_position_change"],
                "",
            ],
        ]
    remainder = factors["remainder"]
    expected_isolated.append(
        [remainder["label"], "", "", remainder["mean_total_change"]]
    )
    assert section(rows, "parametro_aislado") == expected_isolated


def test_the_changed_parameters_carry_the_difference(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    rows = rows_of(client, boca, ranking.id, {**DEFAULTS, "w_a": "0.65", "w_t": "0.15"})

    assert section(rows, "parametros") == [
        ["wA", "0.6", "0.65", "0.05"],
        ["wT", "0.2", "0.15", "-0.05"],
    ]


def test_the_context_has_the_ranking_date_and_both_rules_versions(
    client: TestClient, db: Session, boca: dict[str, str], ranking: Ranking
) -> None:
    ranking.completed_at = datetime(2026, 10, 29, 15, 0, 3, tzinfo=UTC)
    db.flush()
    adjust_rules(client, boca, 1, d_sat="800")

    rows = rows_of(client, boca, ranking.id, SPREAD)

    assert section(rows, "contexto") == [
        # 15:00 UTC del 29/10 (el cálculo del ranking) son las 12:00 en Buenos Aires.
        ["ranking calculado", "29/10/2026 12:00", "", ""],
        ["versión de reglas del ranking", "1", "", ""],
        ["versión de reglas vigente", "2", "", ""],
    ]


def test_the_file_is_of_the_ranking_on_the_screen_even_if_a_newer_one_completed(
    client: TestClient, db: Session, admin: User, boca: dict[str, str], ranking: Ranking
) -> None:
    body, _ = screen(client, boca, SPREAD)
    adjust_rules(client, boca, 1, d_sat="800")
    run_ranking(db, admin)

    rows = rows_of(client, boca, ranking.id, SPREAD)

    assert section(rows, "contexto")[1] == [
        "versión de reglas del ranking",
        "1",
        "",
        "",
    ]
    assert section(rows, "resumen")[0] == [
        "media",
        body["summary"]["before"]["mean"],
        body["summary"]["after"]["mean"],
        body["summary"]["difference"]["mean"],
    ]


@pytest.mark.parametrize(
    "values",
    [
        pytest.param({**DEFAULTS, "d_sat": "800"}, id="single_factor"),
        pytest.param(DEFAULTS, id="no_changes"),
    ],
)
def test_without_a_breakdown_on_the_screen_the_isolated_section_is_left_out(
    client: TestClient, boca: dict[str, str], ranking: Ranking, values: dict[str, str]
) -> None:
    rows = rows_of(client, boca, ranking.id, values)

    assert section(rows, "parametro_aislado") == []
    assert section(rows, "componentes")


def test_an_unavailable_breakdown_leaves_out_its_section(
    client: TestClient,
    boca: dict[str, str],
    ranking: Ranking,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_: Any) -> None:
        raise RuntimeError("falla de prueba")

    monkeypatch.setattr(rules_simulation_service, "_isolated_effects", fail)

    rows = rows_of(client, boca, ranking.id, SPREAD)

    assert section(rows, "parametro_aislado") == []
    assert list(dict.fromkeys(row[0] for row in rows)) == [
        s for s in SECTIONS if s != "parametro_aislado"
    ]


def test_the_file_has_no_data_of_any_socio(
    client: TestClient, db: Session, boca: dict[str, str], ranking: Ranking
) -> None:
    response = download(client, boca, ranking.id, SPREAD)

    text = response.content.decode("utf-8-sig")
    for socio in db.scalars(select(Socio)):
        assert socio.dni not in text
        assert socio.nombre not in text


def test_downloading_stores_nothing_and_changes_nothing(
    client: TestClient, db: Session, boca: dict[str, str], ranking: Ranking
) -> None:
    def state() -> tuple[int | None, ...]:
        return tuple(
            db.scalar(select(func.count()).select_from(model))
            for model in (Ranking, RankingEntry, RulesVersion, AuditLog)
        )

    before = state()

    first = download(client, boca, ranking.id, SPREAD)
    second = download(client, boca, ranking.id, SPREAD)

    db.expire_all()
    assert state() == before
    # Se genera en el momento: el mismo pedido da el mismo archivo.
    assert first.content == second.content


# --- Errores (en JSON, los mismos de los otros POST) -----------------------------------------


def test_a_ranking_that_is_not_there_is_baseline_not_found(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    response = download(client, boca, ranking.id + 1000, SPREAD)

    assert response.status_code == 409
    # Texto de la tabla "Messages and codes" de HU-29.
    assert response.json() == {
        "detail": {
            "code": "BASELINE_NOT_FOUND",
            "message": "El ranking de esta simulación ya no está disponible. "
            "Volvé a simular.",
        }
    }


def test_invalid_values_are_rejected_with_all_the_violations(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    response = download(client, boca, ranking.id, {**SPREAD, "d_sat": "abc"})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_VALUES"


def test_a_ranking_without_socios_is_rejected(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    empty = make_ranking(db, admin, RankingState.COMPLETED)

    response = download(client, boca, empty.id, SPREAD)

    assert response.status_code == 409
    assert response.json() == {
        "detail": {"code": "EMPTY_RANKING", "message": EMPTY_RANKING_MESSAGE}
    }


# --- Escenario 5: permisos y club ----------------------------------------------------------


def test_a_member_is_forbidden(
    client: TestClient, outbox: Outbox, make_member: MakeMember, ranking: Ranking
) -> None:
    headers = bearer(member_token(client, outbox, make_member(activated=True)))

    response = download(client, headers, ranking.id, SPREAD)

    assert (response.status_code, response.json()) == (403, {"detail": "FORBIDDEN"})


def test_an_admin_without_club_is_rejected(
    client: TestClient, outbox: Outbox, make_admin: MakeAdmin, ranking: Ranking
) -> None:
    headers = headers_for(client, outbox, make_admin(None))

    response = download(client, headers, ranking.id, SPREAD)

    assert response.status_code == 403
    assert response.json() == {"detail": "ADMIN_WITHOUT_CLUB"}


def test_an_unauthenticated_request_is_rejected(
    client: TestClient, ranking: Ranking
) -> None:
    response = download(client, {}, ranking.id, SPREAD)

    assert response.status_code == 401
    assert response.json() == {"detail": "NOT_AUTHENTICATED"}


def test_the_ranking_of_another_club_is_not_found_for_its_admin(
    client: TestClient, outbox: Outbox, make_admin: MakeAdmin, ranking: Ranking
) -> None:
    river = headers_for(client, outbox, make_admin(RIVER_ID))

    response = download(client, river, ranking.id, SPREAD)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "BASELINE_NOT_FOUND"


# --- Unitarias -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("now", "name"),
    [
        (DOWNLOADED_AT, "simulacion-reglas-20261107-1930.csv"),
        # 02:30 UTC del 1/11 todavía es el 31/10 en Buenos Aires.
        (
            datetime(2026, 11, 1, 2, 30, tzinfo=UTC),
            "simulacion-reglas-20261031-2330.csv",
        ),
    ],
)
def test_filename(now: datetime, name: str) -> None:
    assert filename(now) == name
