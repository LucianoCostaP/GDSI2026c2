from typing import Any

from fastapi import APIRouter, Body, Depends, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_club
from ..models.domain import Club
from ..repositories.base import EventoRepository
from ..repositories.factory import get_evento_repository
from ..schemas.eventos import (
    BatchResponse,
    EventoCreateRequest,
    EventoCreateResponse,
    EventoDetailResponse,
)
from ..services.evento_service import EventoService

router = APIRouter(prefix="/eventos", tags=["Carga y Gestión de Eventos"])


def get_evento_service(
    repo: EventoRepository = Depends(get_evento_repository),
) -> EventoService:
    return EventoService(repo)


# ==============================================================================
# ENDPOINT A: Carga de un evento individual
# POST /api/v1/eventos
# ==============================================================================
@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=EventoCreateResponse,
    summary="Carga de un evento individual",
    description="Permite al club registrar un nuevo evento. Valida antelación de 48 horas para partidos, valida idempotencia del id_externo y guarda en estado 'Pendiente de definición de importancia'.",
)
def crear_evento_individual(
    payload: EventoCreateRequest,
    club: Club = Depends(get_current_club),
    service: EventoService = Depends(get_evento_service),
    db: Session = Depends(get_db),
) -> EventoCreateResponse:
    res = service.crear_evento_individual(str(club.id), payload)
    db.commit()
    return res


# ==============================================================================
# ENDPOINT B: Carga masiva de eventos (Batch)
# POST /api/v1/eventos/batch
# ==============================================================================
@router.post(
    "/batch",
    status_code=status.HTTP_207_MULTI_STATUS,
    response_model=BatchResponse,
    summary="Carga masiva de eventos futuros (Batch)",
    description="Permite registrar múltiples eventos futuros en una sola petición. Ignora duplicados de forma segura (idempotencia) y retorna 207 Multi-Status detallando creados, omitidos y fallidos.",
)
def crear_eventos_batch(
    payload: list[dict[str, Any]] = Body(
        ...,
        openapi_examples={
            "ejemplo_batch": {
                "summary": "Lote de eventos regulares",
                "value": [
                    {
                        "id_externo": "EVT-1029",
                        "titulo": "Partido vs Rivales FC",
                        "fecha_hora": "2026-11-20T17:00:00Z",
                        "lugar": "Estadio Visitante, calle ejemplo 1234",
                        "tipo": "Partido",
                        "descripcion": "Fecha 12 del torneo local",
                    }
                ],
            }
        },
    ),
    club: Club = Depends(get_current_club),
    service: EventoService = Depends(get_evento_service),
    db: Session = Depends(get_db),
) -> BatchResponse:
    res = service.crear_eventos_batch(str(club.id), payload)
    db.commit()
    return res


# ==============================================================================
# ENDPOINT C: Consulta de eventos
# GET /api/v1/eventos
# ==============================================================================
@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=list[EventoDetailResponse],
    summary="Consulta de eventos registrados por el club",
    description="Permite al club consultar sus eventos filtrando por id_externo, id_interno o título.",
)
def consultar_eventos(
    id_externo: str | None = Query(
        None, description="Busca por el ID original del club"
    ),
    id_interno: str | None = Query(
        None, description="Busca por el ID interno generado por Pasión de 10"
    ),
    titulo: str | None = Query(
        None, description="Búsqueda parcial por título del evento"
    ),
    club: Club = Depends(get_current_club),
    service: EventoService = Depends(get_evento_service),
) -> list[EventoDetailResponse]:
    return service.consultar_eventos(
        club_id=str(club.id),
        id_externo=id_externo,
        id_interno=id_interno,
        titulo=titulo,
    )


# ==============================================================================
# ENDPOINT D: Carga masiva de Eventos Históricos (Batch)
# POST /api/v1/eventos/historicos/batch
# ==============================================================================
@router.post(
    "/historicos/batch",
    status_code=status.HTTP_207_MULTI_STATUS,
    response_model=BatchResponse,
    summary="Carga masiva de Eventos Históricos (Batch)",
    description="Permite al club enviar un historial de eventos pasados para alimentar scoring. NO aplica regla de 48hs. Se guardan directamente como 'Histórico' (nunca visibles para socios). Maneja idempotencia omitiendo duplicados y responde con 207 Multi-Status.",
)
def crear_eventos_historicos_batch(
    payload: list[dict[str, Any]] = Body(
        ...,
        openapi_examples={
            "ejemplo_historicos": {
                "summary": "Lote de eventos pasados",
                "value": [
                    {
                        "id_externo": "EVT-HIST-001",
                        "titulo": "Partido vs Club Atlético Pasado",
                        "fecha_hora": "2025-05-10T15:00:00Z",
                        "lugar": "Estadio Local",
                        "tipo": "Partido",
                    }
                ],
            }
        },
    ),
    club: Club = Depends(get_current_club),
    service: EventoService = Depends(get_evento_service),
    db: Session = Depends(get_db),
) -> BatchResponse:
    res = service.crear_eventos_historicos_batch(str(club.id), payload)
    db.commit()
    return res
