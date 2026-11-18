"""HU-20: notificaciones de demo del seed, para mostrar la bandeja antes de HU-19."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Notification, RankingState, User
from app.models.domain import EventoVisibleDB
from app.seed import DEMO_INSTITUCIONAL, DEMO_PARTIDO, seed_demo_notifications
from tests.conftest import BOCA_ID, RIVER_ID, MakeAdmin, MakeMember, Outbox
from tests.hu25_helpers import headers_for, make_ranking, publish_rules
from tests.test_hu20_notification_inbox import INBOX, account_of, headers

NOW = datetime(2026, 11, 15, 15, 0, tzinfo=UTC)


def demo_events(db: Session) -> None:
    db.add_all(
        [
            EventoVisibleDB(
                id_interno=DEMO_PARTIDO,
                club_id=BOCA_ID,
                id_externo="EVT-BOCA-FUT-PUB-01",
                titulo="Boca Juniors vs. Vélez Sarsfield - Fecha 14",
                # 21:00 en Buenos Aires.
                fecha_hora=datetime(2026, 11, 20, 0, 0, tzinfo=UTC),
                lugar="La Bombonera",
                tipo="Partido",
                clase="B",
            ),
            EventoVisibleDB(
                id_interno=DEMO_INSTITUCIONAL,
                club_id=BOCA_ID,
                id_externo="EVT-BOCA-FUT-PUB-02",
                titulo="Clínica Abierta de Básquetbol",
                fecha_hora=datetime(2026, 11, 23, 21, 30, tzinfo=UTC),
                lugar="Polideportivo",
                tipo="Institucional",
                puntos=15,
            ),
        ]
    )
    db.commit()


def notifications_of(db: Session, user: User) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.created_at.desc())
        )
    )


def test_cada_socio_activado_recibe_una_notificacion_por_tipo_activo(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    make_member: MakeMember,
    make_admin: MakeAdmin,
) -> None:
    admin = make_admin(BOCA_ID)
    publish_rules(client, headers_for(client, outbox, admin))
    ranking = make_ranking(
        db, admin, RankingState.COMPLETED, completed_at=NOW - timedelta(days=1)
    )
    demo_events(db)
    member = make_member(activated=True)

    seed_demo_notifications(db, BOCA_ID, now=NOW)
    db.commit()

    body = client.get(INBOX, headers=headers(client, outbox, member)).json()
    assert [
        (i["type"], i["state"], i["reference"], i["title"], i["message"])
        for i in body["items"]
    ] == [
        (
            "wave_opened",
            "unread",
            {"event_id": DEMO_PARTIDO},
            "Tu turno de reserva está habilitado",
            (
                "Ya podés reservar para Boca Juniors vs. Vélez Sarsfield - Fecha 14. "
                "Tu acceso está habilitado hasta el 18/11/2026 a las 21:00."
            ),
        ),
        (
            "ranking_completed",
            "unread",
            {"ranking_id": ranking.id},
            "Se actualizó el ranking",
            "Se calculó un nuevo ranking. Consultá tu puntaje y tu posición.",
        ),
        (
            "event_published",
            "read",
            {"event_id": DEMO_INSTITUCIONAL},
            "Nuevo evento publicado",
            "Ya podés ver Clínica Abierta de Básquetbol, el 23/11/2026 a las 18:30.",
        ),
    ]
    assert body["unread_count"] == 2


def test_volver_a_correr_el_seed_no_duplica(
    db: Session, make_member: MakeMember
) -> None:
    demo_events(db)
    user = account_of(db, make_member(activated=True))

    first = seed_demo_notifications(db, BOCA_ID, now=NOW)
    second = seed_demo_notifications(db, BOCA_ID, now=NOW + timedelta(hours=1))

    assert (first, second) == (2, 0)
    assert len(notifications_of(db, user)) == 2


def test_sin_ranking_completado_se_saltea_esa_notificacion(
    db: Session, make_member: MakeMember
) -> None:
    demo_events(db)
    user = account_of(db, make_member(activated=True))

    seed_demo_notifications(db, BOCA_ID, now=NOW)

    assert {n.type for n in notifications_of(db, user)} == {
        "event_published",
        "wave_opened",
    }


def test_solo_reciben_las_cuentas_de_socio_activadas_del_club(
    db: Session, make_member: MakeMember, make_admin: MakeAdmin
) -> None:
    demo_events(db)
    pending = make_member(activated=False)
    river = account_of(db, make_member(activated=True, club_id=RIVER_ID))
    admin = make_admin(BOCA_ID)

    created = seed_demo_notifications(db, BOCA_ID, now=NOW)

    assert created == 0
    assert notifications_of(db, river) == notifications_of(db, admin) == []
    assert db.scalar(select(User).where(User.member_id == pending.member_id)) is None


def test_las_claves_de_demo_no_chocan_con_las_que_generara_hu19(
    db: Session, make_member: MakeMember
) -> None:
    demo_events(db)
    user = account_of(db, make_member(activated=True))

    seed_demo_notifications(db, BOCA_ID, now=NOW)

    assert all(n.occurrence_key.startswith("demo:") for n in notifications_of(db, user))
