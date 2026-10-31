"""HU-25, Ciclo 2: población elegible del ranking (edge case "Ranking population").

Entran los socios del club con la cuota al día y sin baja, tengan o no la cuenta activada.
Los morosos quedan fuera, pero conservan su historial.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AsistenciaDB,
    CargaParticipacionDB,
    EstadoCuota,
    Ranking,
    Socio,
    User,
)
from app.services import ranking_run_service
from app.services.ranking_population import select_population
from tests.conftest import BOCA_ID, RIVER_ID, MakeMember, Outbox
from tests.hu25_helpers import (
    RUNS,
    entries_of,
    headers_for,
    make_socio,
    publish_rules,
    rankings_of,
)

MOROSO = EstadoCuota.MOROSO.value
AL_DIA = EstadoCuota.AL_DIA.value


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    return headers_for(client, outbox, admin)


def add_attendance(db: Session, socio: Socio, evento_id: str) -> AsistenciaDB:
    """Guarda una asistencia definitiva del socio (con la carga de la que viene)."""
    carga = CargaParticipacionDB(
        club_id=socio.club_id,
        tipo="asistencia",
        origen="club",
        carga_id_externo=f"carga-{uuid.uuid4().hex[:8]}",
        evento_id_externo=evento_id,
    )
    db.add(carga)
    db.flush()
    asistencia = AsistenciaDB(
        club_id=socio.club_id,
        evento_id_externo=evento_id,
        dni=socio.dni,
        numero_socio=socio.numero_socio,
        carga_id=carga.id,
    )
    db.add(asistencia)
    db.commit()
    return asistencia


def attendance_event_ids(db: Session, socio: Socio) -> set[str]:
    return set(
        db.scalars(
            select(AsistenciaDB.evento_id_externo).where(
                AsistenciaDB.club_id == socio.club_id, AsistenciaDB.dni == socio.dni
            )
        )
    )


def ranked_socio_ids(db: Session, ranking_id: int) -> set[uuid.UUID]:
    ranking = db.get_one(Ranking, ranking_id)
    return {entry.socio_id for entry in entries_of(db, ranking)}


def population_ids(db: Session, club_id: uuid.UUID = BOCA_ID) -> list[uuid.UUID]:
    return [socio.id for socio in select_population(db, club_id)]


# --- Aceptación: "Los morosos quedan fuera pero conservan su historial" --------------------


def test_overdue_socio_is_left_out_but_keeps_history_and_returns_after_paying(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    al_dia = make_socio(db)
    moroso = make_socio(db, estado_cuota=MOROSO)
    add_attendance(db, moroso, "EVT-001")
    add_attendance(db, moroso, "EVT-002")

    first = client.post(RUNS, headers=boca)

    assert first.status_code == 201
    assert first.json()["population_size"] == 1
    assert ranked_socio_ids(db, first.json()["id"]) == {al_dia.id}
    assert attendance_event_ids(db, moroso) == {"EVT-001", "EVT-002"}

    moroso.estado_cuota = AL_DIA
    db.commit()
    second = client.post(RUNS, headers=boca)

    assert second.status_code == 201
    assert second.json()["population_size"] == 2
    assert ranked_socio_ids(db, second.json()["id"]) == {al_dia.id, moroso.id}
    assert attendance_event_ids(db, moroso) == {"EVT-001", "EVT-002"}


# --- Aceptación: "Socios sin cuenta activada también se rankean" ---------------------------


def test_socio_with_up_to_date_fees_and_unactivated_account_is_ranked(
    client: TestClient, db: Session, boca: dict[str, str], make_member: MakeMember
) -> None:
    publish_rules(client, boca)
    member = make_member(activated=False)
    socio = make_socio(db, dni=member.dni)

    response = client.post(RUNS, headers=boca)

    assert response.status_code == 201
    assert response.json()["population_size"] == 1
    assert ranked_socio_ids(db, response.json()["id"]) == {socio.id}


# --- Unitarias: quién entra a la población -------------------------------------------------


def test_excludes_moroso(db: Session) -> None:
    al_dia = make_socio(db)
    make_socio(db, estado_cuota=MOROSO)

    assert population_ids(db) == [al_dia.id]


def test_includes_unactivated_account(db: Session, make_member: MakeMember) -> None:
    member = make_member(activated=False)
    socio = make_socio(db, dni=member.dni)

    assert population_ids(db) == [socio.id]


def test_includes_socio_without_any_account(db: Session) -> None:
    socio = make_socio(db)

    assert population_ids(db) == [socio.id]


def test_includes_socio_with_activated_account(
    db: Session, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    socio = make_socio(db, dni=member.dni)

    assert population_ids(db) == [socio.id]


def test_excludes_socio_with_baja(db: Session) -> None:
    # HU-43, escenario 9: una baja sale de la población del próximo ranking.
    activo = make_socio(db)
    make_socio(db, activo=False)

    assert population_ids(db) == [activo.id]


def test_population_scoped_to_club(db: Session) -> None:
    boca = make_socio(db, club_id=BOCA_ID)
    river = make_socio(db, club_id=RIVER_ID)
    make_socio(db, club_id=RIVER_ID, estado_cuota=MOROSO)

    assert population_ids(db, BOCA_ID) == [boca.id]
    assert population_ids(db, RIVER_ID) == [river.id]


def test_population_is_ordered_by_dni(db: Session) -> None:
    socios = [make_socio(db, dni=dni) for dni in ("30000003", "10000001", "20000002")]

    expected = [s.id for s in sorted(socios, key=lambda s: s.dni)]
    assert population_ids(db) == expected


def test_population_size_recorded(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    make_socio(db)
    make_socio(db)
    make_socio(db, estado_cuota=MOROSO)
    make_socio(db, activo=False)
    make_socio(db, club_id=RIVER_ID)

    ranking = ranking_run_service.start_run(db, admin, BOCA_ID)

    assert ranking.population_size == 2
    assert len(entries_of(db, ranking)) == 2


def test_returning_member_keeps_history_inside_window(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    socio = make_socio(db, estado_cuota=MOROSO)
    add_attendance(db, socio, "EVT-001")
    history_before = attendance_event_ids(db, socio)

    ranking_run_service.start_run(db, admin, BOCA_ID)

    # Mientras debe la cuota no está en el ranking, y su historial sigue intacto.
    assert population_ids(db) == []
    assert attendance_event_ids(db, socio) == history_before

    socio.estado_cuota = AL_DIA
    db.commit()

    # Al ponerse al día vuelve a la población, con las mismas asistencias.
    assert population_ids(db) == [socio.id]
    assert attendance_event_ids(db, socio) == history_before
    assert [r.population_size for r in rankings_of(db)] == [0]
