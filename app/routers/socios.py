from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_club
from ..models.domain import Club, Socio
from ..schemas.socios import (
    CargaCompletaRequest,
    CargaCompletaResponse,
    CargaIncrementalRequest,
    CargaIncrementalResponse,
    CargaStatusResponse,
    FreshnessResponse,
    SocioResponse,
)
from ..services.carga_service import CargaService

router = APIRouter(prefix="/socios", tags=["Socios (Padrón del Club)"])


@router.post(
    "/cargas/completa",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CargaCompletaResponse,
    summary="Enviar página de snapshot de padrón completo (HU-43)",
)
def recibir_carga_completa(
    request: CargaCompletaRequest,
    club: Club = Depends(get_current_club),
    db: Session = Depends(get_db),
) -> CargaCompletaResponse:
    """
    Recibe una página/chunk del snapshot completo de socios.
    El snapshot sólo se activa en la base de datos cuando se reciben todas las páginas
    y se valida la consistencia global (p. ej. sin DNIs duplicados entre páginas).
    """
    return CargaService.procesar_carga_completa(club, request, db)


@router.post(
    "/cargas/incremental",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CargaIncrementalResponse,
    summary="Enviar lote de cambios incrementales (HU-43)",
)
def recibir_carga_incremental(
    request: CargaIncrementalRequest,
    club: Club = Depends(get_current_club),
    db: Session = Depends(get_db),
) -> CargaIncrementalResponse:
    """
    Recibe un lote de cambios incrementales (altas, modificaciones, bajas).
    Los registros válidos son aplicados incluso si otros registros individuales
    del lote son rechazados por validación.
    """
    return CargaService.procesar_carga_incremental(club, request, db)


@router.get(
    "/cargas/{carga_id}",
    status_code=status.HTTP_200_OK,
    response_model=CargaStatusResponse,
    summary="Consultar estado y detalle de una carga (HU-43)",
)
def consultar_estado_carga(
    carga_id: str,
    club: Club = Depends(get_current_club),
    db: Session = Depends(get_db),
) -> CargaStatusResponse:
    """
    Permite consultar el estado de procesamiento de una carga completa o incremental,
    sus contadores (creados, actualizados, desactivados, rechazados) y detalles de rechazo.
    """
    return CargaService.obtener_estado_carga(club, carga_id, db)


@router.get(
    "/freshness",
    status_code=status.HTTP_200_OK,
    response_model=FreshnessResponse,
    summary="Auditar frescura del padrón de socios (HU-43 / FR-008)",
)
def auditar_frescura_padron(
    club: Club = Depends(get_current_club),
    db: Session = Depends(get_db),
) -> FreshnessResponse:
    """
    Verifica si el padrón del club se encuentra desactualizado (más de 24 horas sin carga exitosa).
    """
    return CargaService.obtener_frescura_padron(club, db)


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=list[SocioResponse],
    summary="Listar socios del club autenticado",
)
def listar_socios(
    dni: str | None = Query(None, description="Filtrar por DNI"),
    id_externo: str | None = Query(None, description="Filtrar por id_externo"),
    numero_socio: str | None = Query(None, description="Filtrar por número de socio"),
    estado_cuota: str | None = Query(
        None, description="Filtrar por estado de cuota ('al_dia' o 'moroso')"
    ),
    activo: bool | None = Query(None, description="Filtrar por estado activo"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    club: Club = Depends(get_current_club),
    db: Session = Depends(get_db),
) -> list[SocioResponse]:
    """
    Devuelve los registros del padrón local correspondientes exclusivamente al club autenticado.
    """
    query = db.query(Socio).filter(Socio.club_id == club.id)
    if dni:
        query = query.filter(Socio.dni == dni)
    if id_externo:
        query = query.filter(Socio.id_externo == id_externo)
    if numero_socio:
        query = query.filter(Socio.numero_socio == numero_socio)
    if estado_cuota:
        query = query.filter(Socio.estado_cuota == estado_cuota)
    if activo is not None:
        query = query.filter(Socio.activo == activo)

    return (
        query.order_by(Socio.fecha_alta.asc(), Socio.dni.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
