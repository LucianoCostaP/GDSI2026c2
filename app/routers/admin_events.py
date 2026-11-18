from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.orm import Session

from ..audit import record
from ..auth import CurrentAdmin, CurrentAdminClub
from ..config import settings
from ..db import get_db
from ..models.enums import TipoEvento
from ..notifications import generators
from ..repositories.base import EventoRepository
from ..repositories.factory import get_evento_repository
from ..schemas.eventos import (
    AutoPublishResponse,
    ClaseInfoResponse,
    ClubCancelacionRequest,
    EventoAjustarClaseRequest,
    EventoAjustarClaseResponse,
    EventoCambioActionResponse,
    EventoCambioReviewResponse,
    EventoPendientePublicacionResponse,
    EventoRestaurarResponse,
    EventoRetiroRequest,
    EventoRetiroResponse,
    MovedWaveOut,
    PublicarEventoRequest,
    PublicarEventoResponse,
    PublishedEventOut,
    PublishedScheduleOut,
    RescheduleImpactOut,
    RescheduleNotificationsOut,
    RescheduleOut,
    ReschedulePreviewRequest,
    RescheduleRequest,
)
from ..services import published_events_service
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
    # Después del commit, y sin poder deshacer la publicación (HU-19, notificaciones §4).
    generators.event_published(db, res.id_interno)

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
    # Después del commit, y sin poder deshacer la publicación (HU-19, notificaciones §4).
    for publicado in res.detalle:
        generators.event_published(db, publicado.id_interno)

    return res


# ==============================================================================
# HU-23: REPROGRAMACIÓN, RETIRO Y RESTAURACIÓN DE EVENTOS (ADMIN)
# ==============================================================================


@router.get(
    "/admin/events/published",
    response_model=list[PublishedEventOut],
    summary="Eventos publicados que todavía no empezaron (HU-23B)",
    description=(
        "Eventos publicados del club del Admin cuyo inicio no pasó, el más cercano "
        "primero, con su cronograma de olas si lo tienen. El club sale de la cuenta del "
        "Admin (decisión 34): no se acepta `club_id`."
    ),
)
@router.get(
    "/api/admin/events/published",
    response_model=list[PublishedEventOut],
    include_in_schema=False,
)
@router.get(
    "/api/v1/admin/events/published",
    response_model=list[PublishedEventOut],
    include_in_schema=False,
)
def listar_eventos_publicados_admin(
    club_id: CurrentAdminClub,
    db: Session = Depends(get_db),
) -> list[PublishedEventOut]:
    return [
        _published_out(item)
        for item in published_events_service.list_upcoming(db, club_id)
    ]


def _published_out(item: published_events_service.PublishedEvent) -> PublishedEventOut:
    return PublishedEventOut(
        id_interno=item.event.id_interno,
        id_externo=item.event.id_externo,
        titulo=item.event.titulo,
        tipo=TipoEvento(item.event.tipo),
        fecha_hora=item.event.fecha_hora,
        lugar=item.event.lugar,
        descripcion=item.event.descripcion,
        clase=item.event.clase,
        puntos=item.event.puntos,
        cancelado_por_el_club=item.event.cancelado_por_el_club,
        version=item.event.version,
        schedule=(
            PublishedScheduleOut(
                status=item.schedule.status.value,
                opening_at=item.schedule.opening_at,
                closing_at=item.schedule.effective_closing,
                merged_into_order=item.schedule.merged_into_order,
                adjusted=item.schedule.effective_closing_at is not None,
            )
            if item.schedule is not None
            else None
        ),
    )


def _impact_out(plan: published_events_service.ReschedulePlan) -> RescheduleImpactOut:
    impact = plan.impact
    return RescheduleImpactOut(
        previous_fecha_hora=plan.previous_start,
        new_fecha_hora=plan.new_start,
        schedule_effect=impact.effect.value,
        previous_closing_at=impact.previous_closing,
        new_closing_at=impact.new_closing,
        merged_into_order=impact.merged_into_order,
        moved_waves=[
            MovedWaveOut(order=w.order, socios=w.socios) for w in plan.moved_waves
        ],
        target_wave_starts_at=plan.target_starts_at,
        target_wave_open=impact.target_open,
        notifications=RescheduleNotificationsOut(
            event_rescheduled=plan.event_rescheduled
        ),
    )


@router.post(
    "/admin/events/{event_id}/reschedule/preview",
    response_model=RescheduleImpactOut,
    summary="Vista previa de una reprogramación (HU-23B)",
    description=(
        "Valida la fecha y hora nueva como la reprogramación y devuelve qué le pasaría al "
        "cronograma de olas, sin cambiar nada. El club sale de la cuenta del Admin."
    ),
)
@router.post(
    "/api/admin/events/{event_id}/reschedule/preview",
    response_model=RescheduleImpactOut,
    include_in_schema=False,
)
@router.post(
    "/api/v1/admin/events/{event_id}/reschedule/preview",
    response_model=RescheduleImpactOut,
    include_in_schema=False,
)
def previsualizar_reprogramacion(
    event_id: str,
    body: ReschedulePreviewRequest,
    club_id: CurrentAdminClub,
    db: Session = Depends(get_db),
) -> RescheduleImpactOut:
    return _impact_out(
        published_events_service.preview(
            db,
            club_id,
            event_id,
            body.fecha_hora,
            other_fields=(body.model_extra or {}).keys(),
        )
    )


@router.post(
    "/admin/events/{event_id}/reschedule",
    response_model=RescheduleOut,
    summary="Reprogramar la fecha y hora de un evento publicado (HU-23B)",
    description=(
        "Cambia solo la fecha y la hora: el evento sigue publicado con su clase o puntos "
        "y los datos del club, y el cronograma de olas se ajusta como en la vista previa. "
        "Otro campo en el cuerpo responde `FIELD_NOT_EDITABLE`; un formato inválido, "
        "`INVALID_DATETIME`; la misma fecha, `NO_CHANGES`; una fecha que no es futura, "
        "`START_NOT_IN_FUTURE`; una `expected_version` vieja, `EVENT_CHANGED`. Avisa "
        "`event_rescheduled` a los socios después de guardar. El club sale de la cuenta "
        "del Admin (decisión 34)."
    ),
)
@router.post(
    "/api/admin/events/{event_id}/reschedule",
    response_model=RescheduleOut,
    include_in_schema=False,
)
@router.post(
    "/api/v1/admin/events/{event_id}/reschedule",
    response_model=RescheduleOut,
    include_in_schema=False,
)
def reprogramar_evento(
    event_id: str,
    body: RescheduleRequest,
    admin: CurrentAdmin,
    club_id: CurrentAdminClub,
    db: Session = Depends(get_db),
) -> RescheduleOut:
    done = published_events_service.reschedule(
        db,
        admin,
        club_id,
        event_id,
        body.fecha_hora,
        expected_version=body.expected_version,
        expected_schedule_effect=body.expected_schedule_effect,
        expected_merged_into_order=body.expected_merged_into_order,
        other_fields=(body.model_extra or {}).keys(),
    )
    out = RescheduleOut(
        **_published_out(done.published).model_dump(),
        id_reprogramacion=str(done.reprogramming_id),
        impact=_impact_out(done.plan),
    )
    # Escenario 10: después del commit, sin poder deshacer la reprogramación (US4 esc. 7).
    generators.event_rescheduled(db, event_id, str(done.reprogramming_id))
    return out


@router.get(
    "/admin/events/changes",
    response_model=list[EventoCambioReviewResponse],
    summary="Listado de solicitudes de cambios de eventos enviadas por clubes",
    description="Lista los cambios pendientes de revisión con comparativa antes/después (HU-23).",
)
@router.get(
    "/api/admin/events/changes",
    response_model=list[EventoCambioReviewResponse],
    include_in_schema=False,
)
@router.get(
    "/api/v1/admin/events/changes",
    response_model=list[EventoCambioReviewResponse],
    include_in_schema=False,
)
def listar_cambios_pendientes_admin(
    admin: CurrentAdmin,
    response: Response,
    club_id: str | None = Query(None, description="Filtrar por club específico"),
    service: EventoService = Depends(get_evento_service),
) -> list[EventoCambioReviewResponse]:
    cambios = service.listar_cambios_pendientes(club_id=club_id)
    response.headers["X-Total-Count"] = str(len(cambios))
    return cambios


@router.post(
    "/admin/events/changes/{id_cambio}/approve",
    response_model=EventoCambioActionResponse,
    status_code=status.HTTP_200_OK,
    summary="Aprobar reprogramación de evento enviada por el club",
    description="Aplica los cambios al evento publicado y activa la ventana de 24h para ajuste de clase/puntos (HU-23).",
)
@router.post(
    "/api/admin/events/changes/{id_cambio}/approve",
    response_model=EventoCambioActionResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
@router.post(
    "/api/v1/admin/events/changes/{id_cambio}/approve",
    response_model=EventoCambioActionResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def aprobar_cambio_evento(
    id_cambio: str,
    admin: CurrentAdmin,
    db: Annotated[Session, Depends(get_db)],
    reloj_simulado: str | None = Query(
        None, description="Reloj simulado para pruebas (formato ISO)"
    ),
    service: EventoService = Depends(get_evento_service),
) -> EventoCambioActionResponse:
    sim_now = _parse_clock(reloj_simulado)
    res = service.aprobar_cambio_evento(
        db=db,
        cambio_id=id_cambio,
        admin_id=admin.id,
        now=sim_now,
    )
    db.commit()
    # Después del commit, y sin poder deshacer la aprobación (HU-23, notificaciones §4).
    generators.event_rescheduled(db, res.id_interno, res.id_cambio, now=sim_now)
    return res


@router.post(
    "/admin/events/changes/{id_cambio}/reject",
    response_model=EventoCambioActionResponse,
    status_code=status.HTTP_200_OK,
    summary="Rechazar reprogramación de evento enviada por el club",
    description="Rechaza la solicitud de reprogramación dejando el evento sin alteraciones (HU-23).",
)
@router.post(
    "/api/admin/events/changes/{id_cambio}/reject",
    response_model=EventoCambioActionResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
@router.post(
    "/api/v1/admin/events/changes/{id_cambio}/reject",
    response_model=EventoCambioActionResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def rechazar_cambio_evento(
    id_cambio: str,
    admin: CurrentAdmin,
    db: Annotated[Session, Depends(get_db)],
    payload: ClubCancelacionRequest | None = None,
    reloj_simulado: str | None = Query(
        None, description="Reloj simulado para pruebas (formato ISO)"
    ),
    service: EventoService = Depends(get_evento_service),
) -> EventoCambioActionResponse:
    sim_now = _parse_clock(reloj_simulado)
    motivo = payload.motivo if payload else None
    res = service.rechazar_cambio_evento(
        db=db,
        cambio_id=id_cambio,
        admin_id=admin.id,
        motivo=motivo,
        now=sim_now,
    )
    db.commit()
    return res


@router.post(
    "/admin/events/{id_externo_o_interno}/withdraw",
    response_model=EventoRetiroResponse,
    status_code=status.HTTP_200_OK,
    summary="Retirar un evento publicado",
    description="Pasa el evento publicado a 'withdrawn', anulando su segmentación y cronograma de olas (HU-23).",
)
@router.post(
    "/api/admin/events/{id_externo_o_interno}/withdraw",
    response_model=EventoRetiroResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
@router.post(
    "/api/v1/admin/events/{id_externo_o_interno}/withdraw",
    response_model=EventoRetiroResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def retirar_evento(
    id_externo_o_interno: str,
    payload: EventoRetiroRequest,
    admin: CurrentAdmin,
    db: Annotated[Session, Depends(get_db)],
    x_club_id: str | None = Header(None, alias="X-Club-ID"),
    reloj_simulado: str | None = Query(
        None, description="Reloj simulado para pruebas (formato ISO)"
    ),
    service: EventoService = Depends(get_evento_service),
) -> EventoRetiroResponse:
    sim_now = _parse_clock(reloj_simulado)
    res = service.retirar_evento(
        db=db,
        club_id=x_club_id,
        id_externo_o_interno=id_externo_o_interno,
        admin_id=admin.id,
        motivo=payload.motivo,
        now=sim_now,
    )
    db.commit()
    # Solo el retiro de un publicado avisa; descartar un pendiente (HU-21) no.
    if res.estado == "withdrawn":
        generators.event_withdrawn(db, res.id_interno, res.motivo, res.retirado_en)
    return res


@router.post(
    "/admin/events/{id_externo_o_interno}/restore",
    response_model=EventoRestaurarResponse,
    status_code=status.HTTP_200_OK,
    summary="Restaurar un evento retirado",
    description="Devuelve el evento al estado 'publicado'. Su cronograma de olas permanece anulado hasta generarse uno nuevo (HU-23).",
)
@router.post(
    "/api/admin/events/{id_externo_o_interno}/restore",
    response_model=EventoRestaurarResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
@router.post(
    "/api/v1/admin/events/{id_externo_o_interno}/restore",
    response_model=EventoRestaurarResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def restaurar_evento(
    id_externo_o_interno: str,
    admin: CurrentAdmin,
    db: Annotated[Session, Depends(get_db)],
    x_club_id: str | None = Header(None, alias="X-Club-ID"),
    reloj_simulado: str | None = Query(
        None, description="Reloj simulado para pruebas (formato ISO)"
    ),
    service: EventoService = Depends(get_evento_service),
) -> EventoRestaurarResponse:
    sim_now = _parse_clock(reloj_simulado)
    res = service.restaurar_evento(
        db=db,
        club_id=x_club_id,
        id_externo_o_interno=id_externo_o_interno,
        admin_id=admin.id,
        now=sim_now,
    )
    db.commit()
    # Solo vuelve a avisar un evento que vuelve a `publicado`, no un pendiente restaurado.
    if res.estado == "publicado":
        generators.event_restored(db, res.id_interno, res.restaurado_en)
    return res


@router.post(
    "/admin/events/{id_externo_o_interno}/adjust-class",
    response_model=EventoAjustarClaseResponse,
    status_code=status.HTTP_200_OK,
    summary="Ajustar clase o puntos de un evento reprogramado",
    description="Permite modificar la clase (Partido) o puntos (Institucional) dentro de las 24 horas de aprobada la reprogramación (HU-23).",
)
@router.post(
    "/api/admin/events/{id_externo_o_interno}/adjust-class",
    response_model=EventoAjustarClaseResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
@router.post(
    "/api/v1/admin/events/{id_externo_o_interno}/adjust-class",
    response_model=EventoAjustarClaseResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def ajustar_clase_o_puntos(
    id_externo_o_interno: str,
    payload: EventoAjustarClaseRequest,
    admin: CurrentAdmin,
    db: Annotated[Session, Depends(get_db)],
    x_club_id: str | None = Header(None, alias="X-Club-ID"),
    reloj_simulado: str | None = Query(
        None, description="Reloj simulado para pruebas (formato ISO)"
    ),
    service: EventoService = Depends(get_evento_service),
) -> EventoAjustarClaseResponse:
    sim_now = _parse_clock(reloj_simulado)
    res = service.ajustar_clase_o_puntos_reprogramacion(
        db=db,
        club_id=x_club_id,
        id_externo_o_interno=id_externo_o_interno,
        clase=str(payload.clase.value) if payload.clase else None,
        puntos=payload.puntos,
        admin_id=admin.id,
        now=sim_now,
    )
    db.commit()
    return res
