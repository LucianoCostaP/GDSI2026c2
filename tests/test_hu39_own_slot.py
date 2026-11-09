"""HU-39: el Socio consulta la ola que le tocó y cuándo se le habilita la reserva."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.date_utils import asegurar_utc
from app.models import (
    EventoVisibleDB,
    FeeStatus,
    Member,
    MemberAccountState,
    Ranking,
    RankingEntry,
    Role,
    Socio,
    User,
    utcnow,
)
from tests.conftest import (
    BOCA_ID,
    RIVER_ID,
    MakeMember,
    Outbox,
    admin_token,
    bearer,
    last_code,
    member_token,
)
from tests.hu25_helpers import headers_for, publish_rules
from tests.hu36_helpers import DAY, HOUR, partido, ranking_with
from tests.hu36_helpers import generate as generate_waves

MINUTE = timedelta(minutes=1)
SECOND = timedelta(seconds=1)


def slot_url(event: EventoVisibleDB | str) -> str:
    event_id = event if isinstance(event, str) else event.id_interno
    return f"/member/events/{event_id}/slot"


def at(moment: datetime) -> dict[str, str]:
    return {"X-Test-Clock": moment.isoformat()}


def login(client: TestClient, outbox: Outbox, identifier: str) -> str:
    sent = client.post("/auth/member/login/request", json={"identifier": identifier})
    assert sent.status_code == 202, sent.text
    verified = client.post(
        "/auth/member/login/verify",
        json={"challenge": sent.json()["challenge"], "code": last_code(outbox)},
    )
    assert verified.status_code == 200, verified.text
    return str(verified.json()["token"])


def as_utc(value: str) -> datetime:
    return asegurar_utc(datetime.fromisoformat(value))


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    headers = headers_for(client, outbox, admin)
    publish_rules(client, headers)
    return headers


class Club:
    """Un Partido de Boca con 10 socios rankeados: 5 olas de 2 socios cada una."""

    def __init__(
        self,
        client: TestClient,
        db: Session,
        outbox: Outbox,
        admin: User,
        headers: dict[str, str],
        make_member: MakeMember,
    ) -> None:
        self.client = client
        self.db = db
        self.outbox = outbox
        self.headers = headers
        self.make_member = make_member
        self.ranking: Ranking = ranking_with(db, admin, 10)
        self.event = partido(db)
        self.opening = utcnow() + 2 * DAY
        # Paso de una hora: la ola k abre en opening + (k − 1) h.
        self.closing = self.opening + 5 * HOUR

    def segment(self) -> None:
        assert generate_waves(self.client, self.headers, self.event).status_code == 201

    def schedule(self, *, confirm: bool = True) -> None:
        response = self.client.post(
            f"/admin/events/{self.event.id_interno}/schedule",
            json={
                "opening_at": self.opening.isoformat(),
                "closing_at": self.closing.isoformat(),
            },
            headers=self.headers,
        )
        assert response.status_code == 201
        if confirm:
            confirmed = self.client.post(
                f"/admin/events/{self.event.id_interno}/schedule/confirm",
                headers=self.headers,
            )
            assert confirmed.status_code == 200

    def socio_at(self, position: int) -> Socio:
        return self.db.scalars(
            select(Socio)
            .join(RankingEntry, RankingEntry.socio_id == Socio.id)
            .where(
                RankingEntry.ranking_id == self.ranking.id,
                RankingEntry.position == position,
            )
        ).one()

    def member(self, dni: str | None = None) -> dict[str, str]:
        """Cuenta activada del socio con ese DNI. En Postgres el padrón ya creó su `Member`
        (trigger de sincronización) y solo falta activarlo."""
        member = (
            self.db.scalar(select(Member).where(Member.dni == dni)) if dni else None
        )
        if member is None:
            member = self.make_member(activated=True, dni=dni)
        else:
            member.account_state = MemberAccountState.ACTIVATED
            member.club_id = member.club_id or BOCA_ID
            self.db.add(
                User(
                    member_id=member.member_id,
                    name=member.name,
                    email=member.email,
                    role=Role.MEMBER,
                    club_id=member.club_id,
                )
            )
            self.db.commit()
            # Su member_id es el id_externo del padrón, que no es un número de socio
            # válido para el login: entra por DNI.
            return bearer(login(self.client, self.outbox, member.dni))
        return bearer(member_token(self.client, self.outbox, member))

    def member_at(self, position: int) -> dict[str, str]:
        return self.member(self.socio_at(position).dni)

    def ready(self) -> None:
        self.segment()
        self.schedule()

    def wave_start(self, order: int) -> datetime:
        return self.opening + (order - 1) * HOUR

    def slot(self, headers: dict[str, str], moment: datetime | None = None) -> dict:
        response = self.client.get(
            slot_url(self.event),
            headers={**headers, **(at(moment) if moment else {})},
        )
        assert response.status_code == 200, response.text
        return response.json()


@pytest.fixture
def club(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    admin: User,
    boca: dict[str, str],
    make_member: MakeMember,
) -> Club:
    return Club(client, db, outbox, admin, boca, make_member)


# Acceso: solo el Socio, y solo a eventos publicados de su club.


def test_without_a_session_it_is_rejected(client: TestClient, db: Session) -> None:
    assert client.get(slot_url(partido(db))).status_code == 401


def test_an_admin_cannot_see_it(
    client: TestClient, db: Session, outbox: Outbox, admin: User
) -> None:
    response = client.get(
        slot_url(partido(db)), headers=bearer(admin_token(client, outbox, admin))
    )

    assert response.status_code == 403


def test_an_unknown_event_is_not_found(club: Club) -> None:
    response = club.client.get(slot_url("no-existe"), headers=club.member())

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "EVENT_NOT_FOUND"


def test_an_event_of_another_club_is_not_found(club: Club) -> None:
    river = partido(club.db, club_id=RIVER_ID)

    response = club.client.get(slot_url(river), headers=club.member())

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "EVENT_NOT_FOUND"


def test_a_historical_event_is_not_found(club: Club) -> None:
    historical = partido(club.db, when=utcnow() - DAY, tipo="Historico")

    response = club.client.get(slot_url(historical), headers=club.member())

    assert response.status_code == 404


def test_the_club_comes_from_the_account_not_from_the_query(club: Club) -> None:
    river = partido(club.db, club_id=RIVER_ID)

    response = club.client.get(
        f"{slot_url(river)}?club_id={RIVER_ID}", headers=club.member()
    )

    assert response.status_code == 404


def test_the_answer_is_not_cached(club: Club) -> None:
    response = club.client.get(slot_url(club.event), headers=club.member())

    assert response.headers["Cache-Control"] == "no-store"


# Escenario 8: los eventos institucionales no tienen turnos.


def test_an_institutional_event_has_no_turns(club: Club) -> None:
    event = partido(club.db, tipo="Institucional")

    response = club.client.get(slot_url(event), headers=club.member_at(1))

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "no_turns"
    assert body["message"] == "Este evento no tiene turnos de reserva."
    assert body["event"]["tipo"] == "Evento institucional/amateur"
    assert body["wave"] is None


# Escenario 6: sin cronograma confirmado.

NO_SCHEDULE = "El cronograma de reservas de este evento todavía no está definido."


def test_a_partido_without_segmentation_has_no_schedule(club: Club) -> None:
    body = club.slot(club.member_at(1))

    assert body["status"] == "no_schedule"
    assert body["message"] == NO_SCHEDULE
    assert body["wave"] is None
    assert body["closing_at"] is None


def test_a_segmentation_without_schedule_has_no_schedule(club: Club) -> None:
    club.segment()

    assert club.slot(club.member_at(1))["status"] == "no_schedule"


def test_a_draft_schedule_is_not_shown(club: Club) -> None:
    club.segment()
    club.schedule(confirm=False)

    assert club.slot(club.member_at(1))["status"] == "no_schedule"


def test_an_invalidated_schedule_is_not_shown(club: Club) -> None:
    club.ready()
    regenerated = club.client.post(
        f"/admin/events/{club.event.id_interno}/segmentation",
        json={"confirmed": True},
        headers=club.headers,
    )
    assert regenerated.status_code == 200

    assert club.slot(club.member_at(1))["status"] == "no_schedule"


def test_the_event_is_described(club: Club) -> None:
    body = club.slot(club.member_at(1))

    assert body["event"]["id_interno"] == club.event.id_interno
    assert body["event"]["titulo"] == club.event.titulo
    assert body["event"]["lugar"] == "La Bombonera"
    assert body["event"]["tipo"] == "Partido"
    assert as_utc(body["event"]["fecha_hora"]) == asegurar_utc(club.event.fecha_hora)


# Escenarios 5 y 7: sin ola asignada.

NO_WAVE = "No tenés un turno asignado para este evento. Contactá al club."


def test_a_socio_outside_the_ranking_has_no_wave(club: Club) -> None:
    club.ready()
    socio = Socio(
        club_id=club.event.club_id,
        id_externo="ext-nuevo",
        dni="99887766",
        numero_socio="N-nuevo",
        nombre="Socio Nuevo",
        fecha_nacimiento=utcnow().date() - 30 * 365 * DAY,
        fecha_alta=utcnow().date(),
        estado_cuota="al_dia",
        email="nuevo@example.com",
        distancia_km=10,
    )
    club.db.add(socio)
    club.db.commit()

    body = club.slot(club.member(socio.dni), club.opening + MINUTE)

    assert body["status"] == "no_wave"
    assert body["message"] == NO_WAVE
    assert body["wave"] is None
    assert body["starts_at"] is None
    assert as_utc(body["closing_at"]) == club.closing


def test_an_account_without_a_roster_socio_has_no_wave(club: Club) -> None:
    club.ready()

    assert club.slot(club.member(), club.opening + MINUTE)["status"] == "no_wave"


def test_a_later_ranking_does_not_move_the_socio(
    club: Club, db: Session, admin: User
) -> None:
    club.ready()
    headers = club.member_at(1)
    # Un ranking posterior al de la segmentación, en el que el socio no está.
    ranking_with(db, admin, 3, at=utcnow())

    body = club.slot(headers, club.opening + MINUTE)

    assert body["status"] == "open"
    assert body["wave"] == {"order": 1, "total": 5}


def test_a_socio_who_became_overdue_after_the_ranking_keeps_the_wave(
    club: Club, db: Session
) -> None:
    club.ready()
    socio = club.socio_at(3)
    headers = club.member(socio.dni)
    socio.estado_cuota = "moroso"
    member = db.scalars(select(Member).where(Member.dni == socio.dni)).one()
    member.fee_status = FeeStatus.OVERDUE
    db.commit()

    body = club.slot(headers, club.opening + MINUTE)

    assert body["wave"] == {"order": 2, "total": 5}
    assert body["status"] == "pending"


# Escenarios 1 y 3: la ola todavía no abrió.


def test_before_its_start_the_wave_is_pending(club: Club) -> None:
    club.ready()
    now = club.wave_start(3) - 90 * MINUTE

    body = club.slot(club.member_at(5), now)

    assert body["status"] == "pending"
    assert body["message"] is None
    assert body["wave"] == {"order": 3, "total": 5}
    assert as_utc(body["starts_at"]) == club.wave_start(3)
    assert as_utc(body["closing_at"]) == club.closing
    assert body["seconds_until_start"] == 90 * 60
    assert body["seconds_until_closing"] == int((club.closing - now).total_seconds())
    assert as_utc(body["now"]) == now


def test_the_countdown_comes_from_the_server_clock(club: Club) -> None:
    club.ready()
    headers = club.member_at(10)

    first = club.slot(headers, club.wave_start(5) - HOUR)
    later = club.slot(headers, club.wave_start(5) - MINUTE)

    assert first["seconds_until_start"] == 3600
    assert later["seconds_until_start"] == 60


def test_a_fraction_of_second_left_rounds_up(club: Club) -> None:
    club.ready()

    body = club.slot(club.member_at(1), club.opening - SECOND / 2)

    assert body["status"] == "pending"
    assert body["seconds_until_start"] == 1


# Escenario 2: la ola ya abrió y el cierre general no pasó.


def test_from_its_start_the_wave_is_open_until_the_closing(club: Club) -> None:
    club.ready()

    body = club.slot(club.member_at(5), club.wave_start(3))

    assert body["status"] == "open"
    assert body["message"] is None
    assert body["seconds_until_start"] is None
    assert body["seconds_until_closing"] == 3 * 3600
    assert as_utc(body["closing_at"]) == club.closing


def test_an_earlier_wave_stays_open_when_a_later_one_opens(club: Club) -> None:
    club.ready()

    body = club.slot(club.member_at(1), club.wave_start(5))

    assert body["status"] == "open"
    assert body["wave"] == {"order": 1, "total": 5}


# Escenario 4: después del cierre general.

CLOSED = "El período de reserva de este evento terminó."


def test_after_the_closing_the_period_is_closed(club: Club) -> None:
    club.ready()

    body = club.slot(club.member_at(5), club.closing)

    assert body["status"] == "closed"
    assert body["message"] == CLOSED
    assert body["wave"] == {"order": 3, "total": 5}
    assert body["seconds_until_start"] is None
    assert body["seconds_until_closing"] is None


def test_after_the_closing_a_socio_without_wave_also_sees_it_closed(
    club: Club,
) -> None:
    club.ready()

    body = club.slot(club.member(), club.closing + DAY)

    assert body["status"] == "closed"
    assert body["wave"] is None


# Reloj de prueba: en producción manda siempre el reloj del servidor.


def test_the_test_clock_is_ignored_in_production(
    club: Club, monkeypatch: pytest.MonkeyPatch
) -> None:
    club.ready()
    headers = club.member_at(1)
    monkeypatch.setattr("app.routers.member_events.settings.app_env", "production")

    body = club.slot(headers, club.closing + DAY)

    assert body["status"] == "pending"


def test_without_a_test_clock_the_server_clock_is_used(club: Club) -> None:
    club.ready()

    body = club.slot(club.member_at(1))

    assert body["status"] == "pending"
    assert abs(as_utc(body["now"]) - utcnow()) < MINUTE
