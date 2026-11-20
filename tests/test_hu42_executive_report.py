"""Tests de integración y aceptación para HU-42: Reporte Ejecutivo de Scoring y Equidad."""

import csv
import io
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Ranking, RankingEntry, RankingState, RulesVersion, Socio, User
from app.services.executive_report_service import (
    EMPTY_RANKING_MESSAGE,
    NO_BASELINE_MESSAGE,
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
from tests.hu25_helpers import headers_for, make_socio, publish_rules
from tests.hu29_helpers import make_saturation_club, run_ranking

ENDPOINT = "/admin/reports/executive-scoring"
CSV_ENDPOINT = "/admin/reports/executive-scoring/csv"


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    headers = headers_for(client, outbox, admin)
    publish_rules(client, headers)
    return headers


@pytest.fixture
def ranking(db: Session, admin: User, boca: dict[str, str]) -> Ranking:
    make_saturation_club(db)
    return run_ranking(db, admin)


# ==============================================================================
# 1. Permisos y Control de Acceso
# ==============================================================================


def test_access_unauthenticated(client: TestClient) -> None:
    """Sin token de autenticación se rechaza con 401 NOT_AUTHENTICATED."""
    res_json = client.get(ENDPOINT)
    assert res_json.status_code == 401
    assert res_json.json()["detail"] == "NOT_AUTHENTICATED"

    res_csv = client.get(CSV_ENDPOINT)
    assert res_csv.status_code == 401
    assert res_csv.json()["detail"] == "NOT_AUTHENTICATED"


def test_access_socio_forbidden(
    client: TestClient, outbox: Outbox, make_member: MakeMember
) -> None:
    """Un usuario con rol Socio se rechaza con 403 FORBIDDEN."""
    member = make_member(activated=True)
    headers = bearer(member_token(client, outbox, member))

    res_json = client.get(ENDPOINT, headers=headers)
    assert res_json.status_code == 403
    assert res_json.json()["detail"] == "FORBIDDEN"

    res_csv = client.get(CSV_ENDPOINT, headers=headers)
    assert res_csv.status_code == 403
    assert res_csv.json()["detail"] == "FORBIDDEN"


def test_access_admin_without_club(
    client: TestClient, outbox: Outbox, make_admin: MakeAdmin
) -> None:
    """Un Administrador sin club asignado se rechaza con 403 ADMIN_WITHOUT_CLUB."""
    admin_no_club = make_admin(None)
    headers = headers_for(client, outbox, admin_no_club)

    res_json = client.get(ENDPOINT, headers=headers)
    assert res_json.status_code == 403
    assert res_json.json()["detail"] == "ADMIN_WITHOUT_CLUB"


def test_multitenancy_isolation(
    client: TestClient,
    outbox: Outbox,
    make_admin: MakeAdmin,
    ranking: Ranking,
) -> None:
    """Un admin de River no accede al reporte de Boca (aislamiento multi-tenant)."""
    river_admin = make_admin(RIVER_ID)
    river_headers = headers_for(client, outbox, river_admin)

    # River no tiene ranking calculado todavía -> 404 NO_BASELINE
    res = client.get(ENDPOINT, headers=river_headers)
    assert res.status_code == 404
    assert res.json()["detail"]["code"] == "NO_BASELINE"


# ==============================================================================
# 2. Precondiciones y Errores de Negocio
# ==============================================================================


def test_no_baseline_returns_404(client: TestClient, boca: dict[str, str]) -> None:
    """Si el club no tiene ningún ranking completado, devuelve 404 NO_BASELINE."""
    res = client.get(ENDPOINT, headers=boca)
    assert res.status_code == 404
    body = res.json()["detail"]
    assert body["code"] == "NO_BASELINE"
    assert body["message"] == NO_BASELINE_MESSAGE

    res_csv = client.get(CSV_ENDPOINT, headers=boca)
    assert res_csv.status_code == 404
    assert res_csv.json()["detail"]["code"] == "NO_BASELINE"


def test_empty_ranking_returns_422(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    """Si el ranking vigente tiene 0 socios (population_size = 0), responde 422 EMPTY_RANKING."""
    # Creamos un ranking completado pero sin socios
    rules = db.scalar(select(RulesVersion).where(RulesVersion.club_id == BOCA_ID))
    assert rules is not None
    r = Ranking(
        club_id=BOCA_ID,
        rules_version_id=rules.id,
        status=RankingState.COMPLETED,
        calculation_date=date(2026, 10, 29),
        population_size=0,
        requested_by_id=admin.id,
    )
    db.add(r)
    db.commit()

    res = client.get(ENDPOINT, headers=boca)
    assert res.status_code == 422
    body = res.json()["detail"]
    assert body["code"] == "EMPTY_RANKING"
    assert body["message"] == EMPTY_RANKING_MESSAGE

    res_csv = client.get(CSV_ENDPOINT, headers=boca)
    assert res_csv.status_code == 422


# ==============================================================================
# 3. Reporte Ejecutivo JSON (Aceptación y Métricas)
# ==============================================================================


def test_executive_report_json_success(
    client: TestClient, admin: User, boca: dict[str, str], ranking: Ranking
) -> None:
    """El reporte JSON devuelve metadatos, resumen estadístico, histograma, pilares y equidad."""
    res = client.get(ENDPOINT, headers=boca)
    assert res.status_code == 200, res.text
    assert res.headers["Cache-Control"] == "no-store"

    data = res.json()

    # 1. Metadatos
    meta = data["metadata"]
    assert meta["club_id"] == str(BOCA_ID)
    assert meta["generated_by"] == admin.email
    assert meta["ranking_id"] == ranking.id
    assert "generated_at" in meta
    assert "ranking_calculated_at" in meta
    assert meta["rules_version"]["formula_id"] == "scoring-model"
    assert meta["rules_version"]["version"] >= 1
    assert "w_a" in meta["rules_version"]["parameters"]

    # 2. Resumen
    summ = data["summary"]
    assert summ["total_socios"] == ranking.population_size
    assert float(summ["mean_score"]) >= 0.0
    assert float(summ["median_score"]) >= 0.0
    assert float(summ["std_dev"]) >= 0.0
    assert "p10" in summ["percentiles"]
    assert "p25" in summ["percentiles"]
    assert "p75" in summ["percentiles"]
    assert "p90" in summ["percentiles"]
    assert summ["socios_at_cap"] >= 0
    assert summ["ties"]["tied_socios_count"] >= 0
    assert summ["ties"]["largest_tie_size"] >= 0

    # 3. Histograma
    hist = data["histogram"]
    assert len(hist) == 20
    total_in_bins = sum(b["count"] for b in hist)
    assert total_in_bins == summ["total_socios"]
    assert hist[0]["lower"] == 0 and hist[0]["upper"] == 5
    assert hist[-1]["lower"] == 95 and hist[-1]["upper"] == 100

    # 4. Pilares
    pil = data["pillars_average"]
    assert float(pil["asistencia"]) >= 0.0
    assert float(pil["institucional"]) >= 0.0
    assert float(pil["antiguedad"]) >= 0.0
    assert float(pil["bonus_nuevo"]) >= 0.0

    # 5. Equidad demográfica
    demo = data["demographic_equity"]
    assert "seniority" in demo
    assert "distance" in demo
    assert "age" in demo


def test_demographic_equity_privacy_rule_and_merge(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    """Con 11 socios (saturation_club), los segmentos con menos de 10 socios se fusionan."""
    res = client.get(ENDPOINT, headers=boca)
    assert res.status_code == 200
    demo = res.json()["demographic_equity"]

    # Con 11 socios, al fusionar no se pueden formar al menos 2 segmentos de >= 10 socios,
    # por lo que debe devolver SEGMENTATION_NOT_AVAILABLE
    for attr in ("seniority", "distance", "age"):
        eq = demo[attr]
        assert eq["available"] is False
        assert eq["code"] == "SEGMENTATION_NOT_AVAILABLE"
        assert "No hay suficientes socios" in eq["message"]
        assert len(eq["segments"]) == 0


def test_demographic_equity_available_with_many_socios(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    """Con población suficiente distribuida (ej: 40 socios), la segmentación queda disponible."""
    # Creamos 20 socios con baja antigüedad y 20 con alta antigüedad
    for i in range(20):
        make_socio(
            db,
            dni=f"410000{i:02d}",
            fecha_alta=date(2025, 1, 1),
            fecha_nacimiento=date(1995, 1, 1),
            distancia_km=Decimal("5.0"),
        )
    for i in range(20):
        make_socio(
            db,
            dni=f"420000{i:02d}",
            fecha_alta=date(2005, 1, 1),
            fecha_nacimiento=date(1960, 1, 1),
            distancia_km=Decimal("500.0"),
        )
    run_ranking(db, admin)

    res = client.get(ENDPOINT, headers=boca)
    assert res.status_code == 200
    demo = res.json()["demographic_equity"]

    sen = demo["seniority"]
    assert sen["available"] is True
    assert len(sen["segments"]) >= 2
    total_sen_socios = sum(s["socio_count"] for s in sen["segments"])
    assert total_sen_socios == 40
    for s in sen["segments"]:
        assert s["socio_count"] >= 10
        assert float(s["share_percent"]) > 0.0
        assert float(s["average_score"]) >= 0.0
        assert float(s["average_position"]) >= 1.0


# ==============================================================================
# 4. Exportación CSV
# ==============================================================================


def test_executive_report_csv_export(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    """Descarga el reporte en CSV con codificación UTF-8 BOM y estructura por secciones."""
    res = client.get(CSV_ENDPOINT, headers=boca)
    assert res.status_code == 200
    assert res.headers["content-type"] == "text/csv; charset=utf-8"
    assert res.headers["cache-control"] == "no-store"
    assert res.headers["content-disposition"].startswith(
        'attachment; filename="reporte-ejecutivo-scoring-'
    )
    assert res.headers["content-disposition"].endswith('.csv"')

    assert res.content.startswith(b"\xef\xbb\xbf")

    reader = list(csv.reader(io.StringIO(res.content.decode("utf-8-sig"))))
    header = reader[0]
    assert header == ["seccion", "categoria", "metrica", "valor", "unidad_o_detalle"]

    rows = reader[1:]
    sections = {r[0] for r in rows}
    assert "1. Metadatos" in sections
    assert "2. Resumen Global" in sections
    assert "3. Pilares de Scoring" in sections
    assert "4. Histograma" in sections
    assert "5. Equidad Demográfica" in sections


# ==============================================================================
# 5. Privacidad / PII y Lectura Pura (Idempotencia)
# ==============================================================================


def test_no_pii_exposed(
    client: TestClient, db: Session, boca: dict[str, str], ranking: Ranking
) -> None:
    """Verifica que ningún DNI, nombre ni número de socio se exponga en el reporte ni en el CSV."""
    socios = list(db.scalars(select(Socio).where(Socio.club_id == BOCA_ID)))
    assert len(socios) > 0

    json_text = client.get(ENDPOINT, headers=boca).text
    csv_text = client.get(CSV_ENDPOINT, headers=boca).content.decode("utf-8-sig")

    for s in socios:
        assert s.dni not in json_text
        assert s.dni not in csv_text
        if s.nombre:
            assert s.nombre not in json_text
            assert s.nombre not in csv_text
        if s.numero_socio:
            assert s.numero_socio not in json_text
            assert s.numero_socio not in csv_text


def test_report_is_read_only_idempotent(
    client: TestClient, db: Session, boca: dict[str, str], ranking: Ranking
) -> None:
    """El reporte no muta ningún estado ni crea nuevas corridas."""
    entries_count_before = len(list(db.scalars(select(RankingEntry))))
    rankings_count_before = len(list(db.scalars(select(Ranking))))

    client.get(ENDPOINT, headers=boca)
    client.get(CSV_ENDPOINT, headers=boca)

    entries_count_after = len(list(db.scalars(select(RankingEntry))))
    rankings_count_after = len(list(db.scalars(select(Ranking))))

    assert entries_count_after == entries_count_before
    assert rankings_count_after == rankings_count_before
