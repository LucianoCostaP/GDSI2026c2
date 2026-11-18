"""HU-19 user story 3: generación de las notificaciones del catálogo.

Escenario 1: `event_published` al publicar un evento (HU-22), a mano o automáticamente.
Escenario 2: `wave_opened` cuando llega la hora de inicio de una ola de un cronograma
`confirmed` (HU-37), solo para los socios de esa ola.
Escenarios 3 y 4: cronogramas que no avisan y ventana de recuperación.
Escenarios 5 y 6: `ranking_completed` al completar el ranking (HU-25), nada si falla.
Escenario 7: un evento institucional se avisa como un Partido y no tiene `wave_opened`.
Escenario 8: `event_rescheduled` solo lo genera la aprobación de un cambio de HU-23
(se prueba en `tests/test_hu23_event_reprogramming.py`); ningún otro disparador.
Escenario 9: sin cuenta activada o dado de baja al generar, el Socio no recibe nada.

Las notificaciones se ven por la bandeja de HU-20, que es lo que recibe el Socio.
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.date_utils import BUENOS_AIRES_TZ
from app.models import (
    FeeStatus,
    Member,
    MemberAccountState,
    Notification,
    Ranking,
    RankingState,
    Role,
    Socio,
    User,
    WaveSchedule,
    WaveScheduleStatus,
)
from app.notifications import generators
from app.notifications.notify import notify
from app.repositories.factory import get_evento_repository
from app.schemas.eventos import EventoCreateRequest
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
from tests.hu25_helpers import RUNS, headers_for, make_socio, publish_rules
from tests.hu36_helpers import generate as generate_waves
from tests.hu36_helpers import partido
from tests.test_hu20_notification_inbox import INBOX, account_of
from tests.test_hu25_failures import fail_on_call
from tests.test_hu39_own_slot import Club

MINUTE = timedelta(minutes=1)


def inbox_of(
    client: TestClient, outbox: Outbox, member: Member
) -> list[dict[str, Any]]:
    auth = bearer(member_token(client, outbox, member))
    items: list[dict[str, Any]] = client.get(INBOX, headers=auth).json()["items"]
    return items


def inbox_with(client: TestClient, auth: dict[str, str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = client.get(INBOX, headers=auth).json()["items"]
    return items


def notifications_count(db: Session, **filters: Any) -> int:
    query = select(func.count()).select_from(Notification)
    for column, value in filters.items():
        query = query.where(getattr(Notification, column) == value)
    return db.scalar(query) or 0


# === Escenario 1: `event_published` =========================================================


def pending_event(
    db: Session,
    *,
    titulo: str = "Boca vs. San Lorenzo",
    tipo: str = "Partido",
    when: datetime | None = None,
    club_id: str = str(BOCA_ID),
) -> str:
    """Un evento recibido del club, pendiente de definir su importancia (HU-21/22)."""
    request = EventoCreateRequest(
        id_externo=f"EVT-{titulo[:10]}-{datetime.now(UTC).timestamp()}",
        titulo=titulo,
        # 21:00 en Buenos Aires, a más de 48 horas.
        fecha_hora=when or datetime(2030, 3, 15, 0, 0, tzinfo=UTC),
        lugar="La Bombonera",
        tipo=tipo,
    )
    return str(
        get_evento_repository(db).insert_pendiente(club_id=club_id, evento=request)
    )


def publish(
    client: TestClient, admin_headers: dict[str, str], event_id: str, **body: Any
) -> Any:
    return client.post(
        f"/admin/events/{event_id}/publish",
        json=body or {"clase": "A"},
        headers=admin_headers,
    )


@pytest.fixture
def admin_headers(
    client: TestClient, outbox: Outbox, make_admin: MakeAdmin
) -> dict[str, str]:
    auth = bearer(admin_token(client, outbox, make_admin(BOCA_ID)))
    outbox.clear()
    return auth


def test_al_publicar_un_evento_cada_socio_activado_del_club_recibe_el_aviso(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    make_member: MakeMember,
    admin_headers: dict[str, str],
) -> None:
    ana = make_member(activated=True)
    beto = make_member(activated=True)
    event_id = pending_event(db, titulo="Boca vs. San Lorenzo")

    assert publish(client, admin_headers, event_id).status_code == 200

    for member in (ana, beto):
        [item] = inbox_of(client, outbox, member)
        assert {
            k: item[k] for k in ("type", "title", "message", "state", "reference")
        } == {
            "type": "event_published",
            "title": "Nuevo evento publicado",
            "message": "Ya podés ver Boca vs. San Lorenzo, el 14/03/2030 a las 21:00.",
            "state": "unread",
            "reference": {"event_id": event_id},
        }


def test_la_publicacion_automatica_tambien_avisa(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    make_member: MakeMember,
    admin_headers: dict[str, str],
) -> None:
    member = make_member(activated=True)
    start = datetime.now(UTC) + timedelta(hours=80)
    event_id = pending_event(db, titulo="Partido Auto", when=start)

    response = client.post(
        "/admin/events/auto-publish",
        params={
            "reloj_simulado": (datetime.now(UTC) + timedelta(hours=25)).isoformat()
        },
        headers=admin_headers,
    )

    assert event_id in response.json()["eventos_publicados"]
    [item] = inbox_of(client, outbox, member)
    assert (item["type"], item["reference"]) == (
        "event_published",
        {"event_id": event_id},
    )


def test_un_evento_que_sigue_pendiente_no_genera_nada(
    client: TestClient,
    db: Session,
    make_member: MakeMember,
    admin_headers: dict[str, str],
) -> None:
    """Antes de su plazo, la publicación automática no lo publica: no hay aviso."""
    user = account_of(db, make_member(activated=True))
    pending_event(db, when=datetime.now(UTC) + timedelta(days=30))

    response = client.post("/admin/events/auto-publish", headers=admin_headers)

    assert response.json()["publicados"] == 0
    assert notifications_count(db, user_id=user.id) == 0


def test_una_publicacion_rechazada_no_genera_nada(
    client: TestClient,
    db: Session,
    make_member: MakeMember,
    admin_headers: dict[str, str],
) -> None:
    user = account_of(db, make_member(activated=True))
    event_id = pending_event(db, tipo="Partido")

    response = publish(client, admin_headers, event_id, puntos=10)

    assert response.status_code == 422
    assert notifications_count(db, user_id=user.id) == 0


def test_solo_reciben_las_cuentas_de_socio_activadas_del_club_del_evento(
    client: TestClient,
    db: Session,
    make_member: MakeMember,
    make_admin: MakeAdmin,
    admin_headers: dict[str, str],
) -> None:
    pending = make_member(activated=False)
    river = account_of(db, make_member(activated=True, club_id=RIVER_ID))
    admin = make_admin(BOCA_ID)
    event_id = pending_event(db)

    publish(client, admin_headers, event_id)

    assert notifications_count(db, user_id=river.id) == 0
    assert notifications_count(db, user_id=admin.id) == 0
    assert db.scalar(select(User).where(User.member_id == pending.member_id)) is None
    # No hay ninguna cuenta de socio activada en Boca: nadie recibe nada.
    assert notifications_count(db, type="event_published") == 0


def test_un_socio_con_la_cuota_en_mora_tambien_recibe_el_aviso(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    make_member: MakeMember,
    admin_headers: dict[str, str],
) -> None:
    """Puede iniciar sesión (decisión 6), así que recibe `event_published` (notificaciones §2)."""
    member = make_member(activated=True, fee_status=FeeStatus.OVERDUE)
    event_id = pending_event(db)

    publish(client, admin_headers, event_id)

    assert [i["type"] for i in inbox_of(client, outbox, member)] == ["event_published"]


def test_generar_dos_veces_el_mismo_evento_no_duplica(
    client: TestClient,
    db: Session,
    make_member: MakeMember,
    admin_headers: dict[str, str],
) -> None:
    """Reintentos y dobles corridas son seguros: la clave de ocurrencia es única por Socio."""
    user = account_of(db, make_member(activated=True))
    event_id = pending_event(db)
    publish(client, admin_headers, event_id)

    again = generators.event_published(db, event_id)

    assert again == 0
    assert notifications_count(db, user_id=user.id) == 1
    [notification] = db.scalars(
        select(Notification).where(Notification.user_id == user.id)
    )
    assert notification.occurrence_key == f"event:{event_id}:published"


def test_si_la_generacion_falla_el_evento_queda_publicado(
    client: TestClient,
    db: Session,
    make_member: MakeMember,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generar nunca bloquea ni deshace la publicación (notificaciones §1, FR-009)."""
    make_member(activated=True)
    event_id = pending_event(db)

    def broken(*_: Any, **__: Any) -> list[int]:
        raise RuntimeError("se cayó la base")

    monkeypatch.setattr(generators, "_club_members", broken)

    response = publish(client, admin_headers, event_id)

    assert response.status_code == 200
    upcoming = get_evento_repository(db).find_proximos_eventos_publicados(
        club_id=str(BOCA_ID)
    )
    assert event_id in [e["id_interno"] for e in upcoming]


# --- El contrato `notify` --------------------------------------------------------------------


def test_notify_nunca_le_tira_el_error_a_quien_lo_llama(
    db: Session, make_member: MakeMember
) -> None:
    user = account_of(db, make_member(activated=True))

    created = notify(
        db,
        "event_published",
        "event:x:published",
        [user.id],
        club_id=BOCA_ID,
        reference={"event_id": "x"},
        params={},  # faltan titulo, fecha y hora: el texto no se puede armar
    )

    assert created == 0
    assert notifications_count(db, user_id=user.id) == 0


def test_notify_no_genera_un_tipo_inactivo(
    db: Session, make_member: MakeMember, inactive_type: str
) -> None:
    user = account_of(db, make_member(activated=True))

    created = notify(
        db,
        inactive_type,
        "event:x:rescheduled:1",
        [user.id],
        club_id=BOCA_ID,
        reference={"event_id": "x"},
        params={"titulo": "Boca vs. River", "fecha": "01/01/2030", "hora": "21:00"},
    )

    assert created == 0


# === Escenario 2: `wave_opened` =============================================================


@pytest.fixture
def club(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    make_admin: MakeAdmin,
    make_member: MakeMember,
) -> Club:
    """Un Partido de Boca con 10 socios rankeados: 5 olas de 2, una por hora."""
    admin = make_admin(BOCA_ID)
    headers = headers_for(client, outbox, admin)
    publish_rules(client, headers)
    return Club(client, db, outbox, admin, headers, make_member)


def test_cuando_abre_una_ola_sus_socios_reciben_el_aviso(club: Club) -> None:
    club.ready()
    first = [club.member_at(1), club.member_at(2)]

    generators.open_waves(club.db, now=club.wave_start(1) + MINUTE)

    closing = club.closing.astimezone(BUENOS_AIRES_TZ)
    for auth in first:
        [item] = inbox_with(club.client, auth)
        assert {
            k: item[k] for k in ("type", "title", "message", "state", "reference")
        } == {
            "type": "wave_opened",
            "title": "Tu turno de reserva está habilitado",
            "message": (
                f"Ya podés reservar para {club.event.titulo}. Tu acceso está habilitado "
                f"hasta el {closing:%d/%m/%Y} a las {closing:%H:%M}."
            ),
            "state": "unread",
            "reference": {"event_id": club.event.id_interno},
        }


def test_los_socios_de_otras_olas_no_reciben_nada_en_ese_momento(club: Club) -> None:
    club.ready()
    later = [club.member_at(position) for position in (3, 4, 10)]

    generators.open_waves(club.db, now=club.wave_start(1) + MINUTE)

    for auth in later:
        assert inbox_with(club.client, auth) == []


def test_cada_ola_recibe_su_aviso_cuando_llega_su_hora(club: Club) -> None:
    club.ready()
    first, second, third = club.member_at(1), club.member_at(3), club.member_at(5)

    generators.open_waves(club.db, now=club.wave_start(1) + MINUTE)
    generators.open_waves(club.db, now=club.wave_start(2) + MINUTE)

    assert [i["type"] for i in inbox_with(club.client, first)] == ["wave_opened"]
    assert [i["type"] for i in inbox_with(club.client, second)] == ["wave_opened"]
    assert inbox_with(club.client, third) == []


def test_antes_de_la_apertura_no_se_genera_nada(club: Club) -> None:
    club.ready()
    first = club.member_at(1)

    created = generators.open_waves(club.db, now=club.opening - MINUTE)

    assert created == 0
    assert inbox_with(club.client, first) == []


def test_correr_el_trabajo_otra_vez_no_duplica(club: Club) -> None:
    club.ready()
    first = club.member_at(1)
    moment = club.wave_start(1) + MINUTE

    generators.open_waves(club.db, now=moment)
    again = generators.open_waves(club.db, now=moment + MINUTE)

    assert again == 0
    assert len(inbox_with(club.client, first)) == 1


def test_la_clave_de_ocurrencia_es_la_del_spec(club: Club) -> None:
    club.ready()
    club.member_at(1)

    generators.open_waves(club.db, now=club.wave_start(1) + MINUTE)

    keys = set(
        club.db.scalars(
            select(Notification.occurrence_key).where(
                Notification.type == "wave_opened"
            )
        )
    )
    schedule_id = club.db.scalar(select(WaveSchedule.id))
    assert keys == {f"event:{club.event.id_interno}:wave:1:schedule:{schedule_id}"}


def test_un_socio_de_la_ola_sin_cuenta_activada_no_recibe_nada(club: Club) -> None:
    """Las olas cuentan socios del padrón; solo reciben los que activaron su cuenta."""
    club.ready()
    activated = club.member_at(1)

    created = generators.open_waves(club.db, now=club.wave_start(1) + MINUTE)

    assert created == 1
    assert len(inbox_with(club.client, activated)) == 1


# === Escenario 3: cronogramas que no avisan ==================================================


def test_un_cronograma_en_borrador_no_genera_nada(club: Club) -> None:
    club.segment()
    club.schedule(confirm=False)
    first = club.member_at(1)

    created = generators.open_waves(club.db, now=club.wave_start(1) + MINUTE)

    assert created == 0
    assert inbox_with(club.client, first) == []


def test_un_cronograma_invalidado_no_genera_nada(club: Club) -> None:
    club.ready()
    first = club.member_at(1)
    schedule = club.db.scalars(select(WaveSchedule)).one()
    schedule.status = WaveScheduleStatus.INVALIDATED
    club.db.commit()

    created = generators.open_waves(club.db, now=club.wave_start(1) + MINUTE)

    assert created == 0
    assert inbox_with(club.client, first) == []


def test_con_el_cierre_general_pasado_no_se_genera_nada(club: Club) -> None:
    club.ready()
    first, last = club.member_at(1), club.member_at(10)

    created = generators.open_waves(club.db, now=club.closing + MINUTE)

    assert created == 0
    assert inbox_with(club.client, first) == inbox_with(club.client, last) == []


# === Escenario 4: ventana de recuperación ====================================================


def test_una_ola_que_abrio_hace_mas_que_la_ventana_se_saltea_y_se_registra(
    club: Club, caplog: pytest.LogCaptureFixture
) -> None:
    """Primera corrida 61 minutos después de abrir la ola 1 (por ejemplo, tras una caída):
    la ola 1 se saltea; la ola 2, que abrió hace 1 minuto, sí avisa."""
    club.ready()
    first, second = club.member_at(1), club.member_at(3)
    window = timedelta(minutes=settings.wave_notification_catchup_minutes)

    with caplog.at_level(logging.INFO, logger="app.notifications.generators"):
        generators.open_waves(club.db, now=club.wave_start(1) + window + MINUTE)

    assert inbox_with(club.client, first) == []
    assert [i["type"] for i in inbox_with(club.client, second)] == ["wave_opened"]
    assert any(
        "se saltea la ola 1" in record.getMessage()
        and club.event.id_interno in record.getMessage()
        for record in caplog.records
    )


def test_una_ola_dentro_de_la_ventana_todavia_avisa(club: Club) -> None:
    club.ready()
    first = club.member_at(1)
    window = timedelta(minutes=settings.wave_notification_catchup_minutes)

    generators.open_waves(club.db, now=club.wave_start(1) + window - MINUTE)

    assert [i["type"] for i in inbox_with(club.client, first)] == ["wave_opened"]


def test_la_ventana_de_recuperacion_es_un_ajuste(
    club: Club, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert settings.wave_notification_catchup_minutes == 60  # valor por defecto
    monkeypatch.setattr(settings, "wave_notification_catchup_minutes", 5)
    club.ready()
    first = club.member_at(1)

    generators.open_waves(club.db, now=club.wave_start(1) + 6 * MINUTE)

    assert inbox_with(club.client, first) == []


# --- El trabajo de olas, a pedido de un Admin -------------------------------------------------
#
# No hay scheduler (Render corre un solo servicio `web`): como `POST /admin/events/auto-publish`
# de HU-22, el Admin puede correr el trabajo a mano. Solo procesa los cronogramas de su club.

RUN_WAVES = "/admin/notifications/wave-openings/run"


def test_un_admin_corre_el_trabajo_de_olas(club: Club) -> None:
    club.ready()
    first = club.member_at(1)

    response = club.client.post(
        RUN_WAVES,
        params={"reloj_simulado": (club.wave_start(1) + MINUTE).isoformat()},
        headers=club.headers,
    )

    assert (response.status_code, response.json()) == (200, {"created": 1})
    assert [i["type"] for i in inbox_with(club.client, first)] == ["wave_opened"]


def test_el_trabajo_solo_procesa_los_cronogramas_del_club_pedido(club: Club) -> None:
    club.ready()
    first = club.member_at(1)

    created = generators.open_waves(
        club.db, now=club.wave_start(1) + MINUTE, club_id=RIVER_ID
    )

    assert created == 0
    assert inbox_with(club.client, first) == []


def test_correr_el_trabajo_de_olas_es_solo_para_admins(
    client: TestClient, outbox: Outbox, make_member: MakeMember
) -> None:
    anonymous = client.post(RUN_WAVES)
    as_member = client.post(
        RUN_WAVES,
        headers=bearer(member_token(client, outbox, make_member(activated=True))),
    )

    assert (anonymous.status_code, anonymous.json()["detail"]) == (
        401,
        "NOT_AUTHENTICATED",
    )
    assert (as_member.status_code, as_member.json()["detail"]) == (403, "FORBIDDEN")


# === Escenarios 5 y 6: `ranking_completed` ===================================================


def account_for(db: Session, socio: Socio) -> User:
    """Activa la cuenta del socio del padrón (en Postgres el trigger ya creó su `Member`)."""
    member = db.scalar(
        select(Member).where(Member.dni == socio.dni, Member.club_id == socio.club_id)
    )
    if member is None:
        member = Member(
            member_id=f"M-{socio.dni}",
            dni=socio.dni,
            email=socio.email,
            name=socio.nombre,
            club_id=socio.club_id,
        )
        db.add(member)
    member.account_state = MemberAccountState.ACTIVATED
    user = User(
        member_id=member.member_id,
        name=member.name or "Socio",
        email=member.email or "socio@example.com",
        role=Role.MEMBER,
        club_id=socio.club_id,
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def boca_admin(
    client: TestClient, outbox: Outbox, make_admin: MakeAdmin
) -> dict[str, str]:
    headers = headers_for(client, outbox, make_admin(BOCA_ID))
    publish_rules(client, headers)
    return headers


def test_al_completar_el_ranking_sus_socios_activados_reciben_el_aviso(
    client: TestClient, db: Session, boca_admin: dict[str, str]
) -> None:
    ranked = [account_for(db, make_socio(db)) for _ in range(2)]
    make_socio(db)  # en el ranking, sin cuenta activada

    response = client.post(RUNS, headers=boca_admin)

    assert response.status_code == 201
    ranking_id = response.json()["id"]
    for user in ranked:
        [notification] = db.scalars(
            select(Notification).where(Notification.user_id == user.id)
        )
        assert (
            notification.type,
            notification.title,
            notification.message,
            notification.reference,
            notification.occurrence_key,
        ) == (
            "ranking_completed",
            "Se actualizó el ranking",
            "Se calculó un nuevo ranking. Consultá tu puntaje y tu posición.",
            {"ranking_id": ranking_id},
            f"ranking:{ranking_id}",
        )
    assert notifications_count(db, type="ranking_completed") == 2


def test_un_socio_que_no_esta_en_el_ranking_no_recibe_el_aviso(
    client: TestClient,
    db: Session,
    make_member: MakeMember,
    boca_admin: dict[str, str],
) -> None:
    """Un moroso no entra en el ranking (HU-25), y una cuenta sin socio en el padrón tampoco."""
    account_for(db, make_socio(db))
    overdue = account_for(db, make_socio(db, estado_cuota="moroso"))
    without_socio = account_of(db, make_member(activated=True))

    client.post(RUNS, headers=boca_admin)

    assert notifications_count(db, user_id=overdue.id) == 0
    assert notifications_count(db, user_id=without_socio.id) == 0


def test_cada_ranking_completado_avisa_una_vez(
    client: TestClient, db: Session, boca_admin: dict[str, str]
) -> None:
    user = account_for(db, make_socio(db))

    first = client.post(RUNS, headers=boca_admin).json()["id"]
    second = client.post(RUNS, headers=boca_admin).json()["id"]
    again = generators.ranking_completed(db, second)

    assert again == 0
    references = [
        n.reference
        for n in db.scalars(select(Notification).where(Notification.user_id == user.id))
    ]
    assert sorted(r["ranking_id"] for r in references) == [first, second]


def test_si_el_aviso_falla_el_ranking_queda_completado_y_vigente(
    client: TestClient,
    db: Session,
    boca_admin: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account_for(db, make_socio(db))

    def broken(*_: Any, **__: Any) -> list[int]:
        raise RuntimeError("se cayó la base")

    monkeypatch.setattr(generators, "_ranked_members", broken)

    response = client.post(RUNS, headers=boca_admin)

    assert response.status_code == 201
    ranking = db.get_one(Ranking, response.json()["id"])
    assert ranking.status == RankingState.COMPLETED
    assert notifications_count(db, type="ranking_completed") == 0


def test_un_ranking_fallido_no_genera_nada(
    client: TestClient,
    db: Session,
    boca_admin: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account_for(db, make_socio(db))
    fail_on_call(monkeypatch, "build_membership_inputs", 1)

    response = client.post(RUNS, headers=boca_admin)

    assert response.status_code == 500
    assert notifications_count(db, type="ranking_completed") == 0


# === Escenario 7: eventos institucionales ====================================================


def test_un_evento_institucional_se_avisa_igual_que_un_partido(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    make_member: MakeMember,
    admin_headers: dict[str, str],
) -> None:
    member = make_member(activated=True)
    event_id = pending_event(db, titulo="Asamblea General", tipo="Institucional")

    assert publish(client, admin_headers, event_id, puntos=50).status_code == 200

    [item] = inbox_of(client, outbox, member)
    assert {k: item[k] for k in ("type", "title", "message", "reference")} == {
        "type": "event_published",
        "title": "Nuevo evento publicado",
        "message": "Ya podés ver Asamblea General, el 14/03/2030 a las 21:00.",
        "reference": {"event_id": event_id},
    }


def test_un_evento_institucional_no_tiene_avisos_de_ola(club: Club) -> None:
    """Las olas son solo para Partidos (HU-36): un institucional no puede tener cronograma, así
    que el trabajo de olas nunca le genera `wave_opened`, aunque el Partido del club sí avise."""
    institucional = partido(club.db, tipo="Institucional")
    rejected = generate_waves(club.client, club.headers, institucional)
    assert rejected.status_code != 201
    assert "NOT_A_PARTIDO" in rejected.text
    club.ready()
    for position in (1, 3, 5, 7, 9):  # un socio con cuenta activada por ola
        club.member_at(position)

    for order in range(1, 6):
        generators.open_waves(club.db, now=club.wave_start(order) + MINUTE)

    references = [
        n.reference["event_id"]
        for n in club.db.scalars(
            select(Notification).where(Notification.type == "wave_opened")
        )
    ]
    assert references and set(references) == {club.event.id_interno}
    assert institucional.id_interno not in references


# === Escenario 8: `event_rescheduled` ======================================================
#
# Desde HU-23 el tipo está activo y lo genera la aprobación de un cambio (tests de HU-23). Que un
# tipo inactivo no se genera ni aparece en la bandeja lo siguen probando
# `test_notify_no_genera_un_tipo_inactivo` y los de inactivos de HU-20, con `inactive_type`.


HU23_TYPES = ("event_rescheduled", "event_withdrawn", "event_restored")


def test_ningun_disparador_genera_los_tipos_de_hu23(club: Club) -> None:
    """Publicar, abrir las olas y completar el ranking: nada genera los tipos de HU-23
    (decisión 61)."""
    club.ready()
    club.member_at(1)
    generators.event_published(club.db, club.event.id_interno)
    for order in range(1, 6):
        generators.open_waves(club.db, now=club.wave_start(order) + MINUTE)
    generators.ranking_completed(club.db, club.ranking.id)

    assert notifications_count(club.db, type="event_published") > 0
    assert notifications_count(club.db, type="wave_opened") > 0
    assert notifications_count(club.db, type="ranking_completed") > 0
    for type in HU23_TYPES:
        assert notifications_count(club.db, type=type) == 0, type


# === Escenario 9: sin cuenta activada o dado de baja =========================================
#
# "Sin cuenta activada" se prueba en cada generador (`..._sin_cuenta_activada_...` y los socios
# del padrón sin cuenta de los escenarios 1 y 5). Acá, la baja: la marca el padrón de HU-43
# (`Socio.activo = False`) y se mira al generar, no al publicar el ranking ni el cronograma.


def dar_de_baja(db: Session, socio: Socio, *, activo: bool = False) -> None:
    socio.activo = activo
    db.commit()


def test_un_socio_dado_de_baja_no_recibe_el_aviso_de_un_evento(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    make_member: MakeMember,
    admin_headers: dict[str, str],
) -> None:
    activo, de_baja = make_socio(db), make_socio(db)
    activo_user, de_baja_user = account_for(db, activo), account_for(db, de_baja)
    sin_padron = account_of(db, make_member(activated=True))
    dar_de_baja(db, de_baja)
    event_id = pending_event(db)

    assert publish(client, admin_headers, event_id).status_code == 200

    assert notifications_count(db, user_id=activo_user.id) == 1
    assert notifications_count(db, user_id=sin_padron.id) == 1
    assert notifications_count(db, user_id=de_baja_user.id) == 0


def test_con_una_nueva_alta_vuelve_a_recibir_los_avisos(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> None:
    socio = make_socio(db)
    user = account_for(db, socio)
    dar_de_baja(db, socio)
    publish(client, admin_headers, pending_event(db, titulo="Durante la baja"))

    dar_de_baja(db, socio, activo=True)
    later = pending_event(db, titulo="Después del alta")
    publish(client, admin_headers, later)

    references = [
        n.reference
        for n in db.scalars(select(Notification).where(Notification.user_id == user.id))
    ]
    assert references == [{"event_id": later}]


def test_un_socio_de_la_ola_dado_de_baja_no_recibe_el_aviso(club: Club) -> None:
    """Estaba en el ranking y en la ola, pero se dio de baja antes de que la ola abriera."""
    club.ready()
    de_baja, activo = club.member_at(1), club.member_at(2)
    dar_de_baja(club.db, club.socio_at(1))

    generators.open_waves(club.db, now=club.wave_start(1) + MINUTE)

    assert inbox_with(club.client, activo) != []
    assert notifications_count(club.db, type="wave_opened") == 1
    # La sesión se abrió antes de la baja (revocarla es una brecha de HU-43, decisión 31).
    assert inbox_with(club.client, de_baja) == []


def test_un_socio_del_ranking_dado_de_baja_no_recibe_el_aviso(club: Club) -> None:
    """Un ranking guarda a quien estaba de alta al calcularlo; la baja posterior se mira al
    generar el aviso."""
    de_baja, activo = club.member_at(1), club.member_at(2)
    dar_de_baja(club.db, club.socio_at(1))

    created = generators.ranking_completed(club.db, club.ranking.id)

    assert created == 1
    assert [i["type"] for i in inbox_with(club.client, activo)] == ["ranking_completed"]
    assert inbox_with(club.client, de_baja) == []


# --- Escenario 9 con los tipos de HU-23 -------------------------------------------------------


def hu23_generator(type: str) -> Callable[[Session, str], int]:
    """El generador de HU-23 de `type`, como lo llama el router después del commit."""
    moment = datetime(2030, 3, 10, 15, 0, tzinfo=UTC)
    generator: Callable[[Session, str], int] = {
        "event_rescheduled": lambda db, event_id: generators.event_rescheduled(
            db, event_id, "c-1"
        ),
        "event_withdrawn": lambda db, event_id: generators.event_withdrawn(
            db, event_id, "Suspendido", moment
        ),
        "event_restored": lambda db, event_id: generators.event_restored(
            db, event_id, moment
        ),
    }[type]
    return generator


@pytest.mark.parametrize("type", HU23_TYPES)
def test_los_tipos_de_hu23_solo_llegan_a_los_socios_activados_y_de_alta_del_club(
    client: TestClient,
    db: Session,
    make_member: MakeMember,
    make_admin: MakeAdmin,
    admin_headers: dict[str, str],
    type: str,
) -> None:
    """Como `event_published`: cada socio del club con cuenta activada, salvo el dado de baja;
    nada para una cuenta sin activar, otro club ni un Admin (notificaciones §2)."""
    activo, de_baja = make_socio(db), make_socio(db)
    activo_user, de_baja_user = account_for(db, activo), account_for(db, de_baja)
    pending = make_member(activated=False)
    river = account_of(db, make_member(activated=True, club_id=RIVER_ID))
    admin = make_admin(BOCA_ID)
    event_id = pending_event(db)
    assert publish(client, admin_headers, event_id).status_code == 200
    dar_de_baja(db, de_baja)

    created = hu23_generator(type)(db, event_id)

    assert created == 1
    assert notifications_count(db, user_id=activo_user.id, type=type) == 1
    assert notifications_count(db, user_id=de_baja_user.id, type=type) == 0
    assert notifications_count(db, user_id=river.id) == 0
    assert notifications_count(db, user_id=admin.id) == 0
    assert db.scalar(select(User).where(User.member_id == pending.member_id)) is None
