from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from ..auth import CurrentMember
from ..config import settings
from ..core.date_utils import asegurar_utc
from ..db import get_db
from ..models import Member, User
from ..models.domain import Club, Socio
from ..repositories.base import EventoRepository
from ..repositories.factory import get_evento_repository
from ..schemas.eventos import ProximosEventosResponse
from ..services.evento_service import EventoService

router = APIRouter(tags=["Próximos Eventos (Socio - HU-17)"])


def get_evento_service(
    repo: EventoRepository = Depends(get_evento_repository),
) -> EventoService:
    return EventoService(repo)


def get_member_club_id(db: Session, member_user: User) -> str | None:
    """
    Identifica el club al que pertenece el socio logueado.
    Si no hay datos en base (o en entorno de tests en memoria), retorna None o primer club.
    """
    try:
        if member_user.member_id:
            socio = (
                db.query(Socio)
                .filter(
                    (Socio.id_externo == member_user.member_id)
                    | (Socio.numero_socio == member_user.member_id)
                )
                .first()
            )
            if socio:
                return str(socio.club_id)

            member = (
                db.query(Member)
                .filter(Member.member_id == member_user.member_id)
                .first()
            )
            if member and member.dni:
                socio_dni = db.query(Socio).filter(Socio.dni == member.dni).first()
                if socio_dni:
                    return str(socio_dni.club_id)

        primer_club = db.query(Club).first()
        if primer_club:
            return str(primer_club.id)
    except Exception:  # noqa: BLE001, S110
        pass
    return None


def _parse_clock(val: str | None) -> datetime | None:
    # El reloj simulado es solo para pruebas: en producción manda el reloj del servidor.
    if not val or settings.app_env == "production":
        return None
    val_str = str(val).strip().replace(" ", "+")
    return asegurar_utc(datetime.fromisoformat(val_str))


# ==============================================================================
# ENDPOINT HU-17: Consulta de próximos eventos para socios
# ==============================================================================
@router.get(
    "/events/upcoming",
    response_model=ProximosEventosResponse,
    summary="Consulta de próximos eventos (HU-17)",
    description=(
        "Permite a un socio autenticado consultar la lista de eventos publicados y futuros. "
        "Los eventos se ordenan cronológicamente (el más próximo primero), en formato de hora de Buenos Aires. "
        "No expone la clase interna de los partidos y ofrece enlaces para consultar el turno propio (HU-39)."
    ),
)
@router.get(
    "/member/events/upcoming",
    response_model=ProximosEventosResponse,
    include_in_schema=False,
)
@router.get(
    "/member/events",
    response_model=ProximosEventosResponse,
    include_in_schema=False,
)
@router.get(
    "/api/events/upcoming",
    response_model=ProximosEventosResponse,
    include_in_schema=False,
)
@router.get(
    "/api/member/events/upcoming",
    response_model=ProximosEventosResponse,
    include_in_schema=False,
)
@router.get(
    "/api/member/events",
    response_model=ProximosEventosResponse,
    include_in_schema=False,
)
@router.get(
    "/api/v1/events/upcoming",
    response_model=ProximosEventosResponse,
    include_in_schema=False,
)
def consultar_proximos_eventos(
    member: CurrentMember,
    db: Annotated[Session, Depends(get_db)],
    service: EventoService = Depends(get_evento_service),
    club_id: str | None = Query(None, description="Filtro opcional por ID de club"),
    tipo: str | None = Query(
        None, description="Filtro opcional por tipo ('Partido' o 'Institucional')"
    ),
    titulo: str | None = Query(
        None, description="Búsqueda opcional por título del evento"
    ),
    x_test_clock: str | None = Header(
        None,
        alias="X-Test-Clock",
        description="Reloj inyectable para pruebas (UTC / ISO 8601)",
    ),
    reloj_simulado: str | None = Query(
        None, description="Fecha y hora simulada para pruebas (ISO 8601)"
    ),
) -> ProximosEventosResponse:
    effective_club_id = club_id or get_member_club_id(db, member)
    ahora_reloj = (
        _parse_clock(reloj_simulado) or _parse_clock(x_test_clock) or datetime.now(UTC)
    )

    return service.obtener_proximos_eventos_publicados(
        club_id=effective_club_id,
        now=ahora_reloj,
        tipo=tipo,
        titulo=titulo,
    )
