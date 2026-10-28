import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Path,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from ..auth import CurrentAdmin
from ..database import get_db
from ..models.domain import Club
from ..schemas.participacion import (
    AprobacionAccionResponse,
    CargaPendienteAprobacionResponse,
    EventoElegibleAsistenciaResponse,
    UploadCSVResponse,
)
from ..services.participacion_service import ParticipacionService

router = APIRouter(
    prefix="/admin", tags=["Administración de Asistencias y Actividades (HU-24)"]
)


def _resolver_club_id(db: Session, club_id_raw: str | None = None) -> uuid.UUID:
    if club_id_raw:
        try:
            return uuid.UUID(club_id_raw)
        except ValueError:
            pass
    primer_club = db.query(Club).first()
    if primer_club:
        return primer_club.id
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "error": {
                "code": "NO_CLUB",
                "message": "No se encontraron clubes registrados en el sistema.",
            }
        },
    )


@router.get(
    "/events/eligible-for-attendance",
    status_code=status.HTTP_200_OK,
    response_model=list[EventoElegibleAsistenciaResponse],
    summary="Listar eventos elegibles para carga de asistencia (HU-24)",
)
def listar_eventos_elegibles(
    admin: CurrentAdmin,
    db: Annotated[Session, Depends(get_db)],
    x_club_id: str | None = Header(None, alias="X-Club-ID"),
    club_id: str | None = Query(None, description="Filtrar por ID de club"),
) -> list[EventoElegibleAsistenciaResponse]:
    """
    Retorna la lista de eventos ya ocurridos que admiten carga de asistencia,
    indicando si ya poseen una carga previa.
    """
    cid = _resolver_club_id(db, club_id or x_club_id)
    return ParticipacionService.listar_eventos_elegibles_para_asistencia(cid, db)


@router.post(
    "/events/{id_externo}/attendance/upload-csv",
    status_code=status.HTTP_200_OK,
    response_model=UploadCSVResponse,
    summary="Cargar asistencia de un evento mediante archivo CSV (HU-24)",
)
async def cargar_asistencia_csv(
    id_externo: str,
    admin: CurrentAdmin,
    file: UploadFile = File(
        ..., description="Archivo CSV con asistencias (máx. 10 MB)"
    ),
    confirm_replace: bool = Form(
        False, description="Confirmar reemplazo si el evento ya posee asistencia"
    ),
    db: Session = Depends(get_db),
    x_club_id: str | None = Header(None, alias="X-Club-ID"),
    club_id: str | None = Query(None, description="ID del club"),
) -> UploadCSVResponse:
    """
    Permite al Administrador subir un archivo CSV con las asistencias a un evento puntual.
    Aplica regla del 5% de tolerancia de error y validación cruzada con 'fecha_evento'.
    """
    cid = _resolver_club_id(db, club_id or x_club_id)
    content_bytes = await file.read()
    try:
        content_str = content_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "INVALID_ENCODING",
                    "message": "El archivo debe estar codificado en UTF-8 o UTF-8 con BOM.",
                }
            },
        )

    return ParticipacionService.procesar_csv_asistencia(
        club_id=cid,
        evento_id_externo=id_externo,
        contenido_csv=content_str,
        admin=admin,
        confirm_replace=confirm_replace,
        db=db,
    )


@router.post(
    "/activities/upload-csv",
    status_code=status.HTTP_200_OK,
    response_model=UploadCSVResponse,
    summary="Cargar actividades recurrentes mediante archivo CSV (HU-24)",
)
async def cargar_actividades_csv(
    admin: CurrentAdmin,
    file: UploadFile = File(
        ..., description="Archivo CSV con actividades recurrentes (máx. 10 MB)"
    ),
    db: Session = Depends(get_db),
    x_club_id: str | None = Header(None, alias="X-Club-ID"),
    club_id: str | None = Query(None, description="ID del club"),
) -> UploadCSVResponse:
    """
    Permite al Administrador subir un archivo CSV con actividades recurrentes (deporte federado y subcomisiones).
    Aplica la regla de tolerancia del 5% de error.
    """
    cid = _resolver_club_id(db, club_id or x_club_id)
    content_bytes = await file.read()
    try:
        content_str = content_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "INVALID_ENCODING",
                    "message": "El archivo debe estar codificado en UTF-8 o UTF-8 con BOM.",
                }
            },
        )

    return ParticipacionService.procesar_csv_actividades(
        club_id=cid,
        contenido_csv=content_str,
        admin=admin,
        db=db,
    )


@router.get(
    "/attendance/pending-approvals",
    status_code=status.HTTP_200_OK,
    response_model=list[CargaPendienteAprobacionResponse],
    summary="Listar cargas de asistencia pendientes de aprobación (HU-24)",
)
def listar_cargas_pendientes_aprobacion(
    admin: CurrentAdmin,
    db: Annotated[Session, Depends(get_db)],
    x_club_id: str | None = Header(None, alias="X-Club-ID"),
    club_id: str | None = Query(None, description="ID del club"),
) -> list[CargaPendienteAprobacionResponse]:
    """
    Retorna los reemplazos de asistencia enviados por el club que aguardan confirmación del Administrador.
    """
    cid = _resolver_club_id(db, club_id or x_club_id)
    return ParticipacionService.listar_cargas_pendientes_aprobacion(cid, db)


@router.post(
    "/attendance/{carga_id}/approve",
    status_code=status.HTTP_200_OK,
    response_model=AprobacionAccionResponse,
    summary="Aprobar reemplazo de asistencia pendiente (HU-24)",
)
def aprobar_reemplazo(
    admin: CurrentAdmin,
    carga_id: str = Path(..., description="ID de la carga a aprobar"),
    db: Session = Depends(get_db),
    x_club_id: str | None = Header(None, alias="X-Club-ID"),
    club_id: str | None = Query(None, description="ID del club"),
) -> AprobacionAccionResponse:
    """
    Confirma el reemplazo atómico de la asistencia de un evento, archivando la anterior como 'reemplazada'.
    """
    cid = _resolver_club_id(db, club_id or x_club_id)
    return ParticipacionService.aprobar_reemplazo(carga_id, admin, cid, db)


@router.post(
    "/attendance/{carga_id}/reject",
    status_code=status.HTTP_200_OK,
    response_model=AprobacionAccionResponse,
    summary="Rechazar reemplazo de asistencia pendiente (HU-24)",
)
def rechazar_reemplazo(
    admin: CurrentAdmin,
    carga_id: str = Path(..., description="ID de la carga a rechazar"),
    motivo: str | None = Query(None, description="Motivo del rechazo"),
    db: Session = Depends(get_db),
    x_club_id: str | None = Header(None, alias="X-Club-ID"),
    club_id: str | None = Query(None, description="ID del club"),
) -> AprobacionAccionResponse:
    """
    Rechaza la carga de reemplazo, purgando su staging y manteniendo intacta la asistencia previa.
    """
    cid = _resolver_club_id(db, club_id or x_club_id)
    return ParticipacionService.rechazar_reemplazo(carga_id, admin, cid, motivo, db)


@router.get(
    "/attendance/cargas/{carga_id}/rejections/csv",
    status_code=status.HTTP_200_OK,
    summary="Descargar archivo CSV con los registros rechazados y sus motivos (HU-24 / FR-008)",
)
def descargar_rechazos_csv(
    admin: CurrentAdmin,
    carga_id: str = Path(..., description="ID de la carga"),
    db: Session = Depends(get_db),
    x_club_id: str | None = Header(None, alias="X-Club-ID"),
    club_id: str | None = Query(None, description="ID del club"),
) -> Response:
    """
    Genera y descarga un archivo CSV con el detalle de registros rechazados de la carga.
    """
    cid = _resolver_club_id(db, club_id or x_club_id)
    csv_content = ParticipacionService.generar_csv_rechazos(carga_id, cid, db)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="rechazos_{carga_id}.csv"'
        },
    )
