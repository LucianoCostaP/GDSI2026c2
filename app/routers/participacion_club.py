from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_club
from ..models.domain import Club
from ..schemas.participacion import (
    CargaActividadesBatchRequest,
    CargaActividadesResponse,
    CargaAsistenciaPageRequest,
    CargaAsistenciaResponse,
    CargaParticipacionStatusResponse,
)
from ..services.participacion_service import ParticipacionService

router = APIRouter(tags=["Asistencias y Actividades del Club (HU-24)"])


@router.post(
    "/eventos/{id_externo}/asistencia",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CargaAsistenciaResponse,
    summary="Enviar página de asistencia de un evento (HU-24)",
)
def recibir_asistencia_evento(
    id_externo: str,
    request: CargaAsistenciaPageRequest,
    club: Club = Depends(get_current_club),
    db: Session = Depends(get_db),
) -> CargaAsistenciaResponse:
    """
    Recibe una página numerada de la asistencia de un evento que ya ocurrió.
    Los registros válidos quedan en staging y se aplican al recibir la última página.
    Si el evento ya posee asistencia previa, la carga queda pendiente de aprobación por el Admin.
    """
    return ParticipacionService.procesar_pagina_asistencia(
        club, id_externo, request, db
    )


@router.post(
    "/actividades/lotes",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CargaActividadesResponse,
    summary="Enviar lote de actividades recurrentes modificadas (HU-24)",
)
def recibir_actividades_recurrentes(
    request: CargaActividadesBatchRequest,
    club: Club = Depends(get_current_club),
    db: Session = Depends(get_db),
) -> CargaActividadesResponse:
    """
    Recibe un lote incremental de actividades recurrentes (deporte federado y subcomisiones).
    Se aplican inmediatamente los registros válidos de forma idempotente con control de marca de agua.
    """
    return ParticipacionService.procesar_lote_actividades(club, request, db)


@router.get(
    "/participacion/cargas/{carga_id}",
    status_code=status.HTTP_200_OK,
    response_model=CargaParticipacionStatusResponse,
    summary="Consultar estado de una carga de asistencia o actividades (HU-24)",
)
@router.get(
    "/asistencias/cargas/{carga_id}",
    status_code=status.HTTP_200_OK,
    response_model=CargaParticipacionStatusResponse,
    include_in_schema=False,
)
@router.get(
    "/actividades/lotes/{carga_id}",
    status_code=status.HTTP_200_OK,
    response_model=CargaParticipacionStatusResponse,
    include_in_schema=False,
)
def consultar_estado_carga(
    carga_id: str,
    club: Club = Depends(get_current_club),
    db: Session = Depends(get_db),
) -> CargaParticipacionStatusResponse:
    """
    Permite consultar el estado de una carga de participación, métricas y detalles de rechazo.
    """
    return ParticipacionService.obtener_estado_carga(club, carga_id, db)
