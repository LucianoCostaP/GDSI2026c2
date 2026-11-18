"""Lo que queda de HU-23 con HU-23B (decisión 62): los cambios y cancelaciones que manda el club
y el descarte de un evento pendiente (HU-21).

- Un cambio del club sobre un evento publicado se omite (HU-21 escenario 5, HU-23B edge case
  "Changes sent by the club for a published event"): no hay revisión ni aprobación; la fecha y
  la hora las reprograma el Admin (`test_hu23b_reschedule.py`).
- La cancelación del club es solo una marca informativa (HU-23B US1): el Admin decide si retira.
- El Admin descarta un evento pendiente (HU-21 escenario 10), con motivo opcional.
- No existen más la revisión de cambios, la ventana de 24 h para clase o puntos ni la
  restauración.

El retiro de un publicado (HU-23B US5) se prueba en `test_hu23b_withdraw.py`.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, FeeStatus, Member, Notification, User
from app.models.domain import EventoCambioPendienteDB, EventoVisibleDB
from tests.conftest import (
    BOCA_HEADERS,
    MakeMember,
    Outbox,
    admin_token,
    bearer,
    member_token,
)


@pytest.fixture
def socio_boca(make_member: MakeMember) -> Member:
    return make_member(activated=True, fee_status=FeeStatus.UP_TO_DATE)


@pytest.fixture
def token(client: TestClient, outbox: Outbox, admin: User) -> str:
    return admin_token(client, outbox, admin)


def recibir(
    client: TestClient,
    *,
    tipo: str = "Partido",
    titulo: str = "Partido Original",
    horas_adelante: int = 80,
) -> tuple[str, str]:
    """Un evento pendiente recibido del club: devuelve su `id_externo` y su `id_interno`."""
    id_externo = f"EVT-{uuid.uuid4().hex[:8]}"
    response = client.post(
        "/api/v1/eventos",
        json={
            "id_externo": id_externo,
            "titulo": titulo,
            "fecha_hora": (
                datetime.now(UTC) + timedelta(hours=horas_adelante)
            ).isoformat(),
            "lugar": "Estadio Principal",
            "tipo": tipo,
            "descripcion": "Descripción inicial",
        },
        headers=BOCA_HEADERS,
    )
    assert response.status_code == 201, response.text
    return id_externo, response.json()["id_interno"]


def publicado(client: TestClient, token: str, **kwargs: str) -> tuple[str, str]:
    id_externo, id_interno = recibir(client, **kwargs)
    response = client.post(
        f"/admin/events/{id_interno}/publish",
        json={"clase": "A"},
        headers=bearer(token),
    )
    assert response.status_code == 200, response.text
    return id_externo, id_interno


def notificaciones_del_evento(db: Session, id_interno: str) -> list[str]:
    return [
        n.type
        for n in db.scalars(
            select(Notification).where(
                Notification.reference["event_id"].as_string() == id_interno
            )
        )
    ]


# --- Un cambio del club sobre un evento publicado se omite ---


def test_un_cambio_del_club_sobre_un_publicado_se_omite(
    client: TestClient, db: Session, token: str, socio_boca: Member
) -> None:
    id_externo, id_interno = publicado(client, token)
    antes = db.get_one(EventoVisibleDB, id_interno)
    fecha, lugar, titulo = antes.fecha_hora, antes.lugar, antes.titulo

    response = client.put(
        f"/api/v1/eventos/{id_externo}",
        json={
            "titulo": "Otro título",
            "lugar": "Otra sede",
            "fecha_hora": (datetime.now(UTC) + timedelta(days=9)).isoformat(),
        },
        headers=BOCA_HEADERS,
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "mensaje": (
            "El evento ya está publicado: el cambio se omite. Si cambió la fecha o la "
            "hora, avisale a la administración del club."
        ),
        "omitido": True,
        "id_interno": id_interno,
    }
    db.expire_all()
    despues = db.get_one(EventoVisibleDB, id_interno)
    assert (despues.fecha_hora, despues.lugar, despues.titulo) == (fecha, lugar, titulo)
    assert despues.estado == "publicado"
    assert despues.version == 1
    # No queda nada para revisar ni se avisa a los socios.
    assert db.scalars(select(EventoCambioPendienteDB)).all() == []
    assert notificaciones_del_evento(db, id_interno) == ["event_published"]


def test_un_cambio_del_club_sobre_un_evento_desconocido_responde_404(
    client: TestClient,
) -> None:
    response = client.put(
        "/api/v1/eventos/NO-EXISTE", json={"lugar": "x"}, headers=BOCA_HEADERS
    )

    assert response.status_code == 404


# --- La cancelación del club es una marca informativa ---


def test_la_cancelacion_del_club_marca_el_evento_y_sigue_publicado(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    token: str,
    socio_boca: Member,
) -> None:
    id_externo, id_interno = publicado(client, token)

    response = client.post(
        f"/api/v1/eventos/{id_externo}/cancelacion",
        json={"motivo": "Tormenta eléctrica"},
        headers=BOCA_HEADERS,
    )

    assert response.status_code == 200, response.text
    assert response.json()["cancelado_por_el_club"] is True
    listado = client.get("/admin/events/published", headers=bearer(token)).json()
    (evento,) = [e for e in listado if e["id_interno"] == id_interno]
    assert evento["cancelado_por_el_club"] is True
    # Sigue visible para los socios hasta que el Admin lo retire, y nadie es avisado.
    socio = bearer(member_token(client, outbox, socio_boca))
    proximos = client.get("/events/upcoming", headers=socio).json()["eventos"]
    assert id_interno in {e["id_interno"] for e in proximos}
    assert notificaciones_del_evento(db, id_interno) == ["event_published"]


# --- El Admin descarta un evento pendiente (HU-21 escenario 10) ---


def pendientes(client: TestClient, token: str) -> set[str]:
    response = client.get("/admin/events/pending", headers=bearer(token))
    assert response.status_code == 200
    return {e["id_interno"] for e in response.json()}


def test_descartar_un_pendiente_lo_saca_de_los_pendientes_y_se_audita(
    client: TestClient, db: Session, token: str, admin: User
) -> None:
    _, id_interno = recibir(client)
    assert id_interno in pendientes(client, token)

    response = client.post(
        f"/admin/events/{id_interno}/discard",
        json={"motivo": "El club lo canceló"},
        headers=bearer(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["id_interno"], body["estado"]) == (id_interno, "descartado")
    assert id_interno not in pendientes(client, token)
    entry = db.scalar(
        select(AuditLog).where(
            AuditLog.action == "event.discarded", AuditLog.entity_id == id_interno
        )
    )
    assert entry is not None
    assert entry.actor_user_id == admin.id
    assert entry.details["motivo"] == "El club lo canceló"
    assert entry.details["new"] == {"estado": "descartado"}
    # Descartar no es retirar: no avisa a nadie.
    assert notificaciones_del_evento(db, id_interno) == []


@pytest.mark.parametrize("body", [None, {}, {"motivo": "   "}])
def test_el_motivo_del_descarte_es_opcional(
    client: TestClient, db: Session, token: str, body: dict | None
) -> None:
    _, id_interno = recibir(client)

    response = client.post(
        f"/admin/events/{id_interno}/discard", json=body, headers=bearer(token)
    )

    assert response.status_code == 200, response.text
    entry = db.scalar(
        select(AuditLog).where(
            AuditLog.action == "event.discarded", AuditLog.entity_id == id_interno
        )
    )
    assert entry is not None
    assert entry.details["motivo"] is None


def test_se_descarta_por_id_externo_o_por_nombre(
    client: TestClient, token: str
) -> None:
    id_externo, por_id = recibir(client)
    titulo = f"Asamblea {uuid.uuid4().hex[:6]}"
    _, por_nombre = recibir(client, tipo="Institucional", titulo=titulo)

    for referencia in (id_externo, titulo):
        response = client.post(
            f"/admin/events/{referencia}/discard", headers=bearer(token)
        )
        assert response.status_code == 200, response.text

    assert {por_id, por_nombre}.isdisjoint(pendientes(client, token))


def test_un_descartado_no_se_descarta_dos_veces(client: TestClient, token: str) -> None:
    _, id_interno = recibir(client)
    assert (
        client.post(
            f"/admin/events/{id_interno}/discard", headers=bearer(token)
        ).status_code
        == 200
    )

    otra_vez = client.post(f"/admin/events/{id_interno}/discard", headers=bearer(token))

    assert otra_vez.status_code == 409


def test_un_publicado_no_se_descarta(client: TestClient, token: str) -> None:
    """Un publicado se retira (HU-23B US5); el descarte es solo para pendientes."""
    _, id_interno = publicado(client, token)

    response = client.post(f"/admin/events/{id_interno}/discard", headers=bearer(token))

    assert response.status_code == 404


# --- Lo que HU-23B sacó ---


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/admin/events/changes"),
        ("post", "/admin/events/changes/c-1/approve"),
        ("post", "/admin/events/changes/c-1/reject"),
        ("post", "/admin/events/EVT-1/adjust-class"),
        ("post", "/admin/events/EVT-1/restore"),
    ],
)
def test_la_revision_de_cambios_la_ventana_de_24_h_y_la_restauracion_no_existen(
    client: TestClient, token: str, method: str, path: str
) -> None:
    response = getattr(client, method)(path, headers=bearer(token))

    assert response.status_code in (404, 405)


# --- Seguridad ---


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/admin/events/EVT-X/withdraw", {"confirmed": True, "expected_version": 1}),
        ("/admin/events/EVT-X/discard", {}),
    ],
)
def test_retirar_y_descartar_son_solo_para_admins(
    client: TestClient,
    outbox: Outbox,
    socio_boca: Member,
    path: str,
    body: dict,
) -> None:
    socio = bearer(member_token(client, outbox, socio_boca))

    assert client.post(path, json=body).status_code == 401
    assert client.post(path, json=body, headers=socio).status_code == 403
