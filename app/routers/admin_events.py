from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.orm import Session

from ..audit import record
from ..auth import CurrentAdmin
from ..config import settings
from ..db import get_db
from ..repositories.base import EventoRepository
from ..repositories.factory import get_evento_repository
from ..schemas.eventos import (
    AutoPublishResponse,
    ClaseInfoResponse,
    EventoPendientePublicacionResponse,
    PublicarEventoRequest,
    PublicarEventoResponse,
)
from ..services.evento_service import EventoService

router = APIRouter(tags=["Gestión y Publicación de Eventos (Admin - HU-22)"])


def get_evento_service(
    repo: EventoRepository = Depends(get_evento_repository),
) -> EventoService:
    return EventoService(repo)


def _parse_clock(raw: str | None) -> datetime | None:
    # El reloj simulado es solo para pruebas: en producción manda el reloj del servidor.
    if not raw or settings.app_env == "production":
        return None
    raw_clean = raw.strip().replace(" ", "+")
    try:
        dt = datetime.fromisoformat(raw_clean)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return None


def _auditar_publicacion(
    db: Session, publicado: PublicarEventoResponse, *, actor_id: int | None
) -> None:
    """Registra quién publicó (Admin o sistema) y los valores aplicados."""
    record(
        db,
        "event.published",
        actor_id=actor_id,
        entity="event",
        entity_id=publicado.id_interno,
        published_by=publicado.publicado_por,
        es_default=publicado.es_default,
        tipo=publicado.tipo,
        before={"estado": "pendiente_definicion_importancia"},
        after={
            "estado": "publicado",
            "clase": publicado.clase,
            "puntos": publicado.puntos,
        },
    )


# ==============================================================================
# ENDPOINT: Selector de Clases de Partidos (HU-22 - Escenario 3)
# ==============================================================================
@router.get(
    "/admin/events/classes",
    response_model=list[ClaseInfoResponse],
    summary="Selector de clases de partidos",
    description="Retorna las clases A, B y C disponibles con sus factores de asistencia, demanda y descripción.",
)
@router.get(
    "/api/admin/events/classes",
    response_model=list[ClaseInfoResponse],
    include_in_schema=False,
)
@router.get(
    "/api/v1/admin/events/classes",
    response_model=list[ClaseInfoResponse],
    include_in_schema=False,
)
def obtener_clases_partido(
    admin: CurrentAdmin,
    service: EventoService = Depends(get_evento_service),
) -> list[ClaseInfoResponse]:
    return service.obtener_clases_disponibles()


# ==============================================================================
# ENDPOINT: Listado de Eventos Pendientes de Definición (HU-22 - Escenario 1)
# ==============================================================================
@router.get(
    "/admin/events/pending",
    response_model=list[EventoPendientePublicacionResponse],
    summary="Listado de eventos pendientes de publicación",
    description="Lista todos los eventos pendientes con el tiempo restante para su deadline de publicación automática.",
)
@router.get(
    "/api/admin/events/pending",
    response_model=list[EventoPendientePublicacionResponse],
    include_in_schema=False,
)
@router.get(
    "/api/v1/admin/events/pending",
    response_model=list[EventoPendientePublicacionResponse],
    include_in_schema=False,
)
def listar_eventos_pendientes(
    admin: CurrentAdmin,
    response: Response,
    club_id: str | None = Query(None, description="Filtrar por club específico"),
    tipo: str | None = Query(
        None, description="Filtrar por tipo de evento (Partido/Institucional)"
    ),
    titulo: str | None = Query(None, description="Búsqueda por título del evento"),
    reloj_simulado: str | None = Query(
        None, description="Reloj simulado para pruebas (formato ISO)"
    ),
    limit: int = Query(50, ge=1, le=500, description="Tamaño de página"),
    offset: int = Query(0, ge=0, description="Cantidad de eventos a saltear"),
    service: EventoService = Depends(get_evento_service),
) -> list[EventoPendientePublicacionResponse]:
    # Listas del Admin paginadas (cross-cutting §6): el total va en X-Total-Count.
    sim_now = _parse_clock(reloj_simulado)
    pendientes = service.listar_eventos_pendientes_publicacion(
        club_id=club_id, now=sim_now, tipo=tipo, titulo=titulo
    )
    response.headers["X-Total-Count"] = str(len(pendientes))
    return pendientes[offset : offset + limit]


# ==============================================================================
# ENDPOINT: Publicación Manual de Evento (HU-22 - Escenarios 2, 4, 5, 8, 9)
# ==============================================================================
@router.post(
    "/admin/events/{id_externo_o_interno}/publish",
    response_model=PublicarEventoResponse,
    status_code=status.HTTP_200_OK,
    summary="Publicar evento definiendo clase o puntos",
    description="Permite al Admin definir la clase (Partido) o puntos (Institucional) y publicar el evento de forma atómica e irreversible.",
)
@router.post(
    "/api/admin/events/{id_externo_o_interno}/publish",
    response_model=PublicarEventoResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
@router.post(
    "/api/v1/admin/events/{id_externo_o_interno}/publish",
    response_model=PublicarEventoResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def publicar_evento_manual(
    id_externo_o_interno: str,
    payload: PublicarEventoRequest,
    admin: CurrentAdmin,
    db: Annotated[Session, Depends(get_db)],
    x_club_id: str | None = Header(None, alias="X-Club-ID"),
    reloj_simulado: str | None = Query(
        None, description="Reloj simulado para pruebas (formato ISO)"
    ),
    service: EventoService = Depends(get_evento_service),
) -> PublicarEventoResponse:
    sim_now = _parse_clock(reloj_simulado)
    res = service.publicar_evento_manual(
        club_id=x_club_id,
        id_externo_o_interno=id_externo_o_interno,
        request=payload,
        actor_id=admin.id,
        now=sim_now,
    )

    # La publicación y su auditoría se confirman juntas (FR-007, cross-cutting §6).
    _auditar_publicacion(db, res, actor_id=admin.id)
    db.commit()

    return res


# ==============================================================================
# ENDPOINT: Publicación Automática por Scheduler (HU-22 - Escenarios 6, 7, 8)
# ==============================================================================
@router.post(
    "/admin/events/auto-publish",
    response_model=AutoPublishResponse,
    status_code=status.HTTP_200_OK,
    summary="Ejecutar publicación automática de eventos vencidos",
    description="Ejecuta la publicación automática de todos los eventos cuyo deadline haya sido alcanzado, aplicando valores por defecto.",
)
@router.post(
    "/api/admin/events/auto-publish",
    response_model=AutoPublishResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
@router.post(
    "/api/v1/admin/events/auto-publish",
    response_model=AutoPublishResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def ejecutar_publicacion_automatica(
    admin: CurrentAdmin,
    db: Annotated[Session, Depends(get_db)],
    club_id: str | None = Query(None, description="Filtrar por club específico"),
    reloj_simulado: str | None = Query(
        None, description="Reloj simulado para pruebas (formato ISO)"
    ),
    service: EventoService = Depends(get_evento_service),
) -> AutoPublishResponse:
    sim_now = _parse_clock(reloj_simulado)
    res = service.publicar_eventos_automaticos(club_id=club_id, now=sim_now)

    for publicado in res.detalle:
        _auditar_publicacion(db, publicado, actor_id=None)
    db.commit()

    return res
