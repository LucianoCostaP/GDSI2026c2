import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import settings
from ..core.date_utils import (
    a_hora_buenos_aires,
    asegurar_utc,
    formatear_tipo_evento,
    validar_antelacion_48_horas,
    validar_evento_futuro,
)
from ..core.exceptions import (
    AntelacionInsuficienteError,
    EventoDuplicadoError,
    EventoNoEncontradoError,
    EventoYaPublicadoError,
    PublicacionInvalidaError,
)
from ..models.domain import EventoPendienteDB, EventoVisibleDB
from ..models.enums import (
    DEMANDA_CLASE_PARTIDO,
    FACTORES_CLASE_PARTIDO,
    ClasePartido,
    TipoEvento,
)
from ..models.wave_schedule import WaveSchedule, WaveScheduleStatus
from ..repositories.base import EventoRepository
from ..schemas.eventos import (
    AutoPublishResponse,
    BatchFailedItem,
    BatchOmittedItem,
    BatchResponse,
    BatchSuccessItem,
    BatchSummary,
    ClaseInfoResponse,
    ClubEventoUpdateRequest,
    ComparacionValores,
    EventoAjustarClaseResponse,
    EventoCambioActionResponse,
    EventoCambioReviewResponse,
    EventoCreateRequest,
    EventoCreateResponse,
    EventoDetailResponse,
    EventoPendientePublicacionResponse,
    EventoRestaurarResponse,
    EventoRetiroResponse,
    ProximoEventoItem,
    ProximosEventosResponse,
    PublicarEventoRequest,
    PublicarEventoResponse,
)

# HU-17 FR-004 y decisión 24: texto exacto, los tests lo comparan por igualdad.
MENSAJE_SIN_EVENTOS_PROXIMOS = "No hay eventos próximos publicados."
logger = logging.getLogger(__name__)


class EventoService:
    def __init__(self, repo: EventoRepository):
        self.repo = repo

    def crear_evento_individual(
        self, club_id: str, evento: EventoCreateRequest
    ) -> EventoCreateResponse:
        """
        Carga de un evento individual (POST /api/v1/eventos).
        - Idempotencia: Si ya existe un evento registrado con ese id_externo, retorna 409 Conflict.
        - Regla de 48 horas: Valida antelación mínima para eventos futuros (422).
        - Flujo de estado: Se guarda estrictamente en 'pendiente_definicion_importancia' (o 'Historico').
        """
        if self.repo.exists_externo(club_id, evento.id_externo):
            raise EventoDuplicadoError(
                "Ya existe un evento registrado con ese id_externo."
            )

        validar_antelacion_48_horas(
            fecha_hora=evento.fecha_hora,
            tipo=evento.tipo,
            es_historico=bool(evento.es_historico),
        )

        estado_inicial = (
            "Historico"
            if (evento.es_historico or evento.tipo == TipoEvento.HISTORICO)
            else "pendiente_definicion_importancia"
        )
        id_interno = self.repo.insert_pendiente(
            club_id=club_id,
            evento=evento,
            estado=estado_inicial,
            es_historico=bool(
                evento.es_historico or evento.tipo == TipoEvento.HISTORICO
            ),
        )

        return EventoCreateResponse(
            mensaje="Evento creado exitosamente.", id_interno=id_interno
        )

    def crear_eventos_batch(
        self, club_id: str, eventos_raw: list[Any]
    ) -> BatchResponse:
        """
        Carga masiva de eventos futuros (POST /api/v1/eventos/batch).
        - Solo admite eventos con fecha de inicio posterior a la actual.
        - Validación estricta de 48 horas para partidos.
        - Idempotencia obligatoria: Si el id_externo ya existe, se omite de forma segura.
        - Retorna 207 Multi-Status.
        """
        creados: list[BatchSuccessItem] = []
        omitidos: list[BatchOmittedItem] = []
        fallidos: list[BatchFailedItem] = []
        ids_externos_en_lote = set()

        for item in eventos_raw:
            id_ext_declarado = (
                item.get("id_externo")
                if isinstance(item, dict)
                else getattr(item, "id_externo", None)
            )
            try:
                if isinstance(item, dict):
                    ev = EventoCreateRequest(**item)
                elif isinstance(item, EventoCreateRequest):
                    ev = item
                else:
                    raise TypeError("Formato de payload no reconocido.")
            except (ValidationError, Exception) as err:  # noqa: BLE001
                fallidos.append(
                    BatchFailedItem(
                        id_externo=id_ext_declarado,
                        error=f"Faltan campos obligatorios o el formato es incorrecto: {err!s}",
                        codigo=400,
                    )
                )
                continue

            if not validar_evento_futuro(ev.fecha_hora):
                fallidos.append(
                    BatchFailedItem(
                        id_externo=ev.id_externo,
                        error="La fecha de inicio debe ser posterior a la actual (no se admite historial en este endpoint).",
                        codigo=422,
                    )
                )
                continue

            try:
                validar_antelacion_48_horas(
                    fecha_hora=ev.fecha_hora, tipo=ev.tipo, es_historico=False
                )
            except AntelacionInsuficienteError as err:
                fallidos.append(
                    BatchFailedItem(
                        id_externo=ev.id_externo, error=err.message, codigo=422
                    )
                )
                continue

            if ev.id_externo in ids_externos_en_lote or self.repo.exists_externo(
                club_id, ev.id_externo
            ):
                omitidos.append(
                    BatchOmittedItem(
                        id_externo=ev.id_externo,
                        motivo="Ya existe un evento registrado con ese id_externo (omitido de forma segura).",
                        estado="omitido",
                    )
                )
                continue

            try:
                id_interno = self.repo.insert_pendiente(
                    club_id=club_id,
                    evento=ev,
                    estado="pendiente_definicion_importancia",
                    es_historico=False,
                )
            except EventoDuplicadoError:
                # Registrado por otro request entre el chequeo y el insert
                omitidos.append(
                    BatchOmittedItem(
                        id_externo=ev.id_externo,
                        motivo="Ya existe un evento registrado con ese id_externo (omitido de forma segura).",
                        estado="omitido",
                    )
                )
                continue
            ids_externos_en_lote.add(ev.id_externo)
            creados.append(
                BatchSuccessItem(
                    id_externo=ev.id_externo, id_interno=id_interno, estado="creado"
                )
            )

        resumen = BatchSummary(
            total=len(eventos_raw),
            creados=len(creados),
            omitidos=len(omitidos),
            fallidos=len(fallidos),
        )
        return BatchResponse(
            resumen=resumen,
            creados=creados,
            exitosos=creados,
            omitidos=omitidos,
            fallidos=fallidos,
        )

    def crear_eventos_historicos_batch(
        self, club_id: str, eventos_raw: list[Any]
    ) -> BatchResponse:
        """
        Carga masiva de Eventos Históricos (POST /api/v1/eventos/historicos/batch).
        - Recibe un historial de eventos pasados.
        - NO se les aplica la regla de las 48 horas de antelación.
        - Ingresan directamente bajo el estado 'Historico'.
        - Idempotencia: omisión segura de duplicados.
        - Retorna 207 Multi-Status.
        """
        creados: list[BatchSuccessItem] = []
        omitidos: list[BatchOmittedItem] = []
        fallidos: list[BatchFailedItem] = []
        ids_externos_en_lote = set()

        for item in eventos_raw:
            id_ext_declarado = (
                item.get("id_externo")
                if isinstance(item, dict)
                else getattr(item, "id_externo", None)
            )
            try:
                if isinstance(item, dict):
                    item_dict = dict(item)
                    item_dict["es_historico"] = True
                    ev = EventoCreateRequest(**item_dict)
                elif isinstance(item, EventoCreateRequest):
                    ev = item
                    ev.es_historico = True
                else:
                    raise TypeError("Formato de payload no reconocido.")
            except (ValidationError, Exception) as err:  # noqa: BLE001
                fallidos.append(
                    BatchFailedItem(
                        id_externo=id_ext_declarado,
                        error=f"Faltan campos obligatorios o el formato es incorrecto: {err!s}",
                        codigo=400,
                    )
                )
                continue

            if ev.id_externo in ids_externos_en_lote or self.repo.exists_externo(
                club_id, ev.id_externo
            ):
                omitidos.append(
                    BatchOmittedItem(
                        id_externo=ev.id_externo,
                        motivo="Evento histórico ya registrado previamente (omitido de forma segura).",
                        estado="omitido",
                    )
                )
                continue

            try:
                id_interno = self.repo.insert_pendiente(
                    club_id=club_id, evento=ev, estado="Historico", es_historico=True
                )
            except EventoDuplicadoError:
                # Registrado por otro request entre el chequeo y el insert
                omitidos.append(
                    BatchOmittedItem(
                        id_externo=ev.id_externo,
                        motivo="Evento histórico ya registrado previamente (omitido de forma segura).",
                        estado="omitido",
                    )
                )
                continue
            ids_externos_en_lote.add(ev.id_externo)
            creados.append(
                BatchSuccessItem(
                    id_externo=ev.id_externo, id_interno=id_interno, estado="creado"
                )
            )

        resumen = BatchSummary(
            total=len(eventos_raw),
            creados=len(creados),
            omitidos=len(omitidos),
            fallidos=len(fallidos),
        )
        return BatchResponse(
            resumen=resumen,
            creados=creados,
            exitosos=creados,
            omitidos=omitidos,
            fallidos=fallidos,
        )

    def consultar_eventos(
        self,
        club_id: str,
        id_externo: str | None = None,
        id_interno: str | None = None,
        titulo: str | None = None,
    ) -> list[EventoDetailResponse]:
        """
        Consulta de eventos (GET /api/v1/eventos).
        Consulta la vista filtrada del club actual.
        """
        rows = self.repo.find_eventos(
            club_id=club_id, id_externo=id_externo, id_interno=id_interno, titulo=titulo
        )
        return [EventoDetailResponse(**row) for row in rows]

    def obtener_clases_disponibles(self) -> list[ClaseInfoResponse]:
        """
        Retorna las clases disponibles para Partidos (HU-22).
        Cada clase muestra su significado, su factor de ponderación y el nivel de demanda.
        """
        return [
            ClaseInfoResponse(
                clase=ClasePartido.A,
                factor=FACTORES_CLASE_PARTIDO[ClasePartido.A],
                demanda=DEMANDA_CLASE_PARTIDO[ClasePartido.A],
                es_default=(settings.default_partido_clase == "A"),
                descripcion=(
                    "Demanda alta (factor 1.0). Un factor mayor premia la asistencia a partidos de menor convocatoria."
                ),
            ),
            ClaseInfoResponse(
                clase=ClasePartido.B,
                factor=FACTORES_CLASE_PARTIDO[ClasePartido.B],
                demanda=DEMANDA_CLASE_PARTIDO[ClasePartido.B],
                es_default=(settings.default_partido_clase == "B"),
                descripcion=(
                    "Demanda regular (factor 1.3, predeterminada). Un factor mayor premia la asistencia a partidos de menor convocatoria."
                ),
            ),
            ClaseInfoResponse(
                clase=ClasePartido.C,
                factor=FACTORES_CLASE_PARTIDO[ClasePartido.C],
                demanda=DEMANDA_CLASE_PARTIDO[ClasePartido.C],
                es_default=(settings.default_partido_clase == "C"),
                descripcion=(
                    "Demanda baja (factor 1.8). Un factor mayor premia la asistencia a partidos de menor convocatoria."
                ),
            ),
        ]

    def listar_eventos_pendientes_publicacion(
        self,
        club_id: str | None = None,
        now: datetime | None = None,
        tipo: str | None = None,
        titulo: str | None = None,
    ) -> list[EventoPendientePublicacionResponse]:
        """
        Lista los eventos en estado 'pendiente_definicion_importancia' para el Admin (HU-22).
        Incluye el cálculo del deadline de publicación y el tiempo restante.
        """
        ahora_utc = asegurar_utc(now or datetime.now(UTC))
        pendientes = self.repo.find_eventos_pendientes(club_id=club_id)

        items: list[EventoPendientePublicacionResponse] = []
        for p in pendientes:
            if tipo and str(p.get("tipo", "")).lower() != tipo.lower():
                continue
            if titulo and titulo.lower() not in str(p.get("titulo", "")).lower():
                continue

            creado_en_utc = asegurar_utc(p.get("creado_en") or ahora_utc)
            fecha_hora_utc = asegurar_utc(p["fecha_hora"])

            # Deadline: el menor entre 24h tras importación y 48h antes del inicio
            d1 = creado_en_utc + timedelta(hours=settings.publication_window_hours)
            d2 = fecha_hora_utc - timedelta(hours=settings.min_publication_lead_hours)
            deadline = min(d1, d2)

            diff_segundos = (deadline - ahora_utc).total_seconds()
            segundos_restantes = max(0, int(diff_segundos))
            plazo_expirado = ahora_utc >= deadline

            item = EventoPendientePublicacionResponse(
                id_interno=str(p["id_interno"]),
                id_externo=str(p["id_externo"]),
                titulo=str(p["titulo"]),
                fecha_hora=fecha_hora_utc,
                lugar=str(p["lugar"]),
                tipo=str(p["tipo"]),
                descripcion=p.get("descripcion"),
                creado_en=creado_en_utc,
                deadline_publicacion=deadline,
                segundos_restantes_deadline=segundos_restantes,
                plazo_expirado=plazo_expirado,
            )
            items.append(item)

        items.sort(key=lambda x: x.deadline_publicacion)
        return items

    def publicar_evento_manual(
        self,
        club_id: str | None,
        id_externo_o_interno: str,
        request: PublicarEventoRequest,
        actor_id: int | None = None,
        now: datetime | None = None,
    ) -> PublicarEventoResponse:
        """
        Publica un evento manualmente por parte de un Administrador (HU-22).
        Reglas de validación:
        - Si el evento ya fue publicado, lanza EventoYaPublicadoError (409 Conflict).
        - Si el evento no existe en pendientes, lanza EventoNoEncontradoError (404 Not Found).
        - Antelación mínima: Debe faltar al menos 48 horas para el inicio del evento (422).
        - Exclusividad de importancia:
          - Partido: Requiere obligatoriamente clase ('A', 'B' o 'C'). No admite puntos.
          - Institucional: Requiere obligatoriamente puntos (1 a 100). No admite clase.
        """
        # 1. Verificar si ya fue publicado previamente
        if self.repo.is_already_published(club_id, id_externo_o_interno):
            raise EventoYaPublicadoError(
                "El evento ya ha sido publicado previamente y no se puede modificar su importancia."
            )

        # 2. Obtener evento pendiente
        evento = self.repo.get_evento_pendiente(club_id, id_externo_o_interno)
        if not evento:
            if self.repo.is_already_published(club_id, id_externo_o_interno):
                raise EventoYaPublicadoError(
                    "El evento ya ha sido publicado previamente y no se puede modificar su importancia."
                )
            raise EventoNoEncontradoError(
                f"No se encontró un evento pendiente con identificador '{id_externo_o_interno}'."
            )

        target_club_id = str(evento["club_id"])

        # 3. Validar antelación mínima de 48 horas (FR-004, SC-004)
        ahora_utc = asegurar_utc(now or datetime.now(UTC))
        fecha_utc = asegurar_utc(evento["fecha_hora"])
        lead_minimo = ahora_utc + timedelta(hours=settings.min_publication_lead_hours)
        if fecha_utc < lead_minimo:
            raise PublicacionInvalidaError(
                "No se puede publicar manualmente el evento porque faltan menos de 48 horas para su inicio."
            )

        # 4. Validar reglas de clase y puntos según tipo de evento
        tipo_str = str(evento["tipo"]).strip()
        is_partido = (
            tipo_str.lower() == "partido" or evento["tipo"] == TipoEvento.PARTIDO
        )

        clase_val: str | None = None
        puntos_val: int | None = None

        if is_partido:
            if request.puntos is not None:
                raise PublicacionInvalidaError(
                    "Los puntos no aplican a eventos de tipo Partido. Debe especificar una clase (A, B o C)."
                )
            if request.clase is None:
                raise PublicacionInvalidaError(
                    "Debe especificar una clase (A, B o C) para publicar un Partido manualmente."
                )
            raw_clase = (
                request.clase.value
                if hasattr(request.clase, "value")
                else str(request.clase)
            )
            if raw_clase not in ("A", "B", "C"):
                raise PublicacionInvalidaError(
                    f"Clase '{raw_clase}' inválida. Debe ser A, B o C."
                )
            clase_val = raw_clase
        else:
            if request.clase is not None:
                raise PublicacionInvalidaError(
                    "La clase solo aplica a eventos de tipo Partido. Para eventos institucionales debe indicar los puntos (1 a 100)."
                )
            if request.puntos is None:
                raise PublicacionInvalidaError(
                    "Debe especificar los puntos asignados (1 a 100) para un evento institucional."
                )
            if not (1 <= request.puntos <= 100):
                raise PublicacionInvalidaError(
                    "Los puntos para un evento institucional deben ser un número entero entre 1 y 100."
                )
            puntos_val = request.puntos

        # 5. Publicación atómica en repositorio (compare-and-set, FR-006)
        id_interno = self.repo.publish_evento(
            club_id=target_club_id,
            id_externo_o_interno=str(evento["id_interno"]),
            clase=clase_val,
            puntos=puntos_val,
            publicado_por="admin",
            es_default=False,
        )

        return PublicarEventoResponse(
            mensaje="Evento publicado exitosamente.",
            id_interno=id_interno,
            tipo=tipo_str,
            clase=clase_val,
            puntos=puntos_val,
            publicado_en=ahora_utc,
            publicado_por="admin",
            es_default=False,
        )

    def publicar_eventos_automaticos(
        self,
        club_id: str | None = None,
        now: datetime | None = None,
    ) -> AutoPublishResponse:
        """
        Publicación automática periódica por scheduler o ejecución manual (HU-22).
        - Publica al llegar al deadline: min(creado_en + 24h, fecha_hora - 48h).
        - Aplica valores predeterminados: Clase B para partidos y 20 puntos para institucionales.
        - Registrado como realizado por el sistema ('system', es_default=True).
        - Si se perdió la antelación de 48h, se omite y se advierte.
        """
        ahora_utc = asegurar_utc(now or datetime.now(UTC))
        pendientes = self.repo.find_eventos_pendientes(club_id=club_id)

        procesados = 0
        publicados: list[PublicarEventoResponse] = []
        omitidos = 0

        for p in pendientes:
            procesados += 1
            creado_en_utc = asegurar_utc(p.get("creado_en") or ahora_utc)
            fecha_hora_utc = asegurar_utc(p["fecha_hora"])

            d1 = creado_en_utc + timedelta(hours=settings.publication_window_hours)
            d2 = fecha_hora_utc - timedelta(hours=settings.min_publication_lead_hours)
            deadline = min(d1, d2)

            # Verificar si ya llegó al deadline
            if ahora_utc < deadline:
                # Aún no venció el plazo de definición manual
                continue

            # Verificar si se perdió la antelación mínima de 48 horas
            # Según SC-001, las publicaciones automáticas ocurren dentro de los 2 minutos
            # de su deadline. Para un evento con deadline = fecha_hora - 48h (ej. evento a 60h),
            # una tolerancia de 2 minutos evita omitir erróneamente eventos cuyo deadline recién venció.
            tolerancia_scheduler = timedelta(minutes=2)
            lead_minimo = (
                ahora_utc
                + timedelta(hours=settings.min_publication_lead_hours)
                - tolerancia_scheduler
            )
            if fecha_hora_utc < lead_minimo:
                # Se perdió la antelación mínima: no se puede publicar automáticamente
                omitidos += 1
                continue

            tipo_str = str(p["tipo"]).strip()
            is_partido = (
                tipo_str.lower() == "partido" or p["tipo"] == TipoEvento.PARTIDO
            )

            if is_partido:
                clase_val = settings.default_partido_clase  # "B"
                puntos_val = None
            else:
                clase_val = None
                puntos_val = settings.default_institucional_puntos  # 20

            try:
                id_pub = self.repo.publish_evento(
                    club_id=str(p["club_id"]),
                    id_externo_o_interno=str(p["id_interno"]),
                    clase=clase_val,
                    puntos=puntos_val,
                    publicado_por="system",
                    es_default=True,
                )
            except (EventoYaPublicadoError, EventoNoEncontradoError):
                # Publicado concurrentemente por un admin u otro proceso
                omitidos += 1
                continue
            publicados.append(
                PublicarEventoResponse(
                    id_interno=id_pub,
                    tipo=tipo_str,
                    clase=clase_val,
                    puntos=puntos_val,
                    publicado_en=ahora_utc,
                    publicado_por="system",
                    es_default=True,
                )
            )

        return AutoPublishResponse(
            mensaje="Proceso de publicación automática completado.",
            procesados=procesados,
            publicados=len(publicados),
            omitidos=omitidos,
            eventos_publicados=[p.id_interno for p in publicados],
            detalle=publicados,
        )

    def publicar_evento(
        self,
        club_id: str,
        id_externo_o_interno: str,
        clase: str | None = None,
        puntos: int | None = None,
    ) -> str:
        """
        Publica un evento para que pase al estado 'visible'/'published' (HU-22).
        Retorna el id_interno del evento publicado.
        """
        return self.repo.publish_evento(
            club_id=club_id,
            id_externo_o_interno=id_externo_o_interno,
            clase=clase,
            puntos=puntos,
        )

    def obtener_proximos_eventos_publicados(
        self,
        club_id: str | None = None,
        now: datetime | None = None,
        tipo: str | None = None,
        titulo: str | None = None,
    ) -> ProximosEventosResponse:
        """
        Consulta de próximos eventos publicados para el socio (HU-17).
        - Solo eventos en estado 'published' / 'visible'.
        - Solo eventos cuyo inicio no haya pasado (start > now).
        - Ordenados cronológicamente (el más próximo primero).
        - Datos: fecha, hora, lugar y tipo ('Partido' o 'Evento institucional/amateur').
        - NO incluye clase de partido.
        - Incluye enlace de navegación al turno del socio (HU-39).
        - Si no hay eventos, incluye mensaje informativo.
        """
        rows = self.repo.find_proximos_eventos_publicados(club_id=club_id, now=now)

        items: list[ProximoEventoItem] = []
        for r in rows:
            if tipo and str(r.get("tipo", "")).lower() != tipo.lower():
                continue
            if titulo and titulo.lower() not in str(r.get("titulo", "")).lower():
                continue

            fh = r["fecha_hora"]
            if isinstance(fh, str):
                fh = datetime.fromisoformat(fh)
            fh_utc = asegurar_utc(fh)
            fh_ba = a_hora_buenos_aires(fh_utc)

            fecha_str = fh_ba.strftime("%Y-%m-%d")
            hora_str = fh_ba.strftime("%H:%M")
            tipo_socio = formatear_tipo_evento(r["tipo"])
            id_interno = str(r["id_interno"])

            item = ProximoEventoItem(
                id=id_interno,
                id_interno=id_interno,
                id_externo=str(r["id_externo"]),
                titulo=str(r["titulo"]),
                fecha_hora=fh_utc,
                fecha=fecha_str,
                hora=hora_str,
                lugar=str(r["lugar"]),
                tipo=tipo_socio,
                descripcion=r.get("descripcion"),
                slot_url=f"/member/events/{id_interno}/slot",
            )
            items.append(item)

        mensaje = None
        if not items:
            mensaje = MENSAJE_SIN_EVENTOS_PROXIMOS

        return ProximosEventosResponse(
            total=len(items),
            eventos=items,
            mensaje=mensaje,
        )

    # ==========================================================================
    # HU-23: REPROGRAMACIÓN, RETIRO Y RESTAURACIÓN DE EVENTOS
    # ==========================================================================

    def recibir_actualizacion_club(
        self,
        club_id: str,
        id_externo_o_interno: str,
        payload: ClubEventoUpdateRequest,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Recibe una actualización enviada por el club (PUT /api/v1/eventos/{id}).
        - Si el evento está publicado: almacena como 'pendiente_revision' sin aplicarlo (FR-001).
        - Si los valores son idénticos: no almacena cambio y responde que está actualizado (FR-001/Esc. 4).
        - Rechaza cambios de tipo o si ya comenzó/está retirado (FR-004).
        - Si ya había un cambio pendiente de revisión, lo reemplaza (Esc. 7).
        """
        ahora = asegurar_utc(now or datetime.now(UTC))

        # 1. Buscar en eventos visibles (publicados / retirados)
        evento_vis = self.repo.get_evento_visible(
            id_externo_o_interno=id_externo_o_interno, club_id=club_id
        )

        if evento_vis:
            # Validar que no esté retirado (FR-004 / Esc. 6)
            if evento_vis.get("estado") in ("withdrawn", "retirado"):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "error": {
                            "code": "EVENT_WITHDRAWN",
                            "message": "El evento fue retirado y no admite actualizaciones.",
                            "field": "id_externo",
                        }
                    },
                )

            # Validar que no haya comenzado (FR-004 / Esc. 6)
            fh_actual = asegurar_utc(
                evento_vis["fecha_hora"]
                if isinstance(evento_vis["fecha_hora"], datetime)
                else datetime.fromisoformat(str(evento_vis["fecha_hora"]))
            )
            if fh_actual <= ahora:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "error": {
                            "code": "EVENT_ALREADY_STARTED",
                            "message": "El evento ya comenzó o finalizó y no puede ser modificado.",
                            "field": "id_externo",
                        }
                    },
                )

            # Validar que no cambie el tipo (FR-004 / Esc. 5)
            if (
                payload.tipo
                and payload.tipo.strip().lower()
                != str(evento_vis["tipo"]).strip().lower()
            ):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "error": {
                            "code": "EVENT_TYPE_CHANGE_NOT_ALLOWED",
                            "message": "No se permite cambiar el tipo de evento (Partido vs Institucional) ya que define el modelo de puntuación.",
                            "field": "tipo",
                        }
                    },
                )

            # Validar si los valores son idénticos a los actuales (Esc. 4)
            cambio_titulo = (
                payload.titulo is not None
                and payload.titulo.strip() != str(evento_vis.get("titulo", "")).strip()
            )
            cambio_lugar = (
                payload.lugar is not None
                and payload.lugar.strip() != str(evento_vis.get("lugar", "")).strip()
            )
            desc_actual = (
                str(evento_vis.get("descripcion", "")).strip()
                if evento_vis.get("descripcion")
                else ""
            )
            desc_nueva = (
                payload.descripcion.strip()
                if payload.descripcion is not None
                else desc_actual
            )
            cambio_desc = payload.descripcion is not None and desc_nueva != desc_actual

            cambio_fecha = False
            if payload.fecha_hora is not None:
                nueva_fh = asegurar_utc(payload.fecha_hora)
                cambio_fecha = nueva_fh != fh_actual

            if not (cambio_titulo or cambio_lugar or cambio_desc or cambio_fecha):
                return {
                    "mensaje": "El evento ya se encuentra actualizado con los datos provistos.",
                    "cambio_creado": False,
                    "id_interno": evento_vis["id_interno"],
                }

            # Construir valores nuevos y previos
            nueva_fh_val = (
                asegurar_utc(payload.fecha_hora)
                if payload.fecha_hora is not None
                else fh_actual
            )
            valores_nuevos = {
                "titulo": (
                    payload.titulo.strip()
                    if payload.titulo is not None
                    else evento_vis["titulo"]
                ),
                "fecha_hora": nueva_fh_val,
                "lugar": (
                    payload.lugar.strip()
                    if payload.lugar is not None
                    else evento_vis["lugar"]
                ),
                "descripcion": (
                    payload.descripcion.strip()
                    if payload.descripcion is not None
                    else evento_vis.get("descripcion")
                ),
                "tipo": evento_vis["tipo"],
            }
            valores_previos = {
                "titulo": evento_vis["titulo"],
                "fecha_hora": fh_actual.isoformat(),
                "lugar": evento_vis["lugar"],
                "descripcion": evento_vis.get("descripcion"),
                "tipo": evento_vis["tipo"],
            }

            id_cambio = self.repo.insert_o_reemplazar_cambio_pendiente(
                club_id=club_id,
                id_interno=evento_vis["id_interno"],
                valores_nuevos=valores_nuevos,
                valores_previos=valores_previos,
            )

            return {
                "mensaje": "Actualización recibida. Pendiente de revisión por administración.",
                "cambio_creado": True,
                "id_cambio": str(id_cambio),
                "id_interno": evento_vis["id_interno"],
            }

        # 2. Si no es visible, buscar en pendientes
        matching_pend = self.repo.get_evento_pendiente(
            club_id=club_id, id_externo_o_interno=id_externo_o_interno
        )

        if matching_pend:
            if (
                matching_pend.get("es_historico")
                or matching_pend.get("estado") == "Historico"
            ):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "error": {
                            "code": "EVENT_NOT_ELIGIBLE",
                            "message": "No se pueden actualizar eventos históricos.",
                            "field": "id_externo",
                        }
                    },
                )
            if matching_pend.get("estado") == "descartado":
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "error": {
                            "code": "EVENT_DISCARDED",
                            "message": "No se pueden actualizar eventos descartados.",
                            "field": "id_externo",
                        }
                    },
                )

            fh_pend = asegurar_utc(
                matching_pend["fecha_hora"]
                if isinstance(matching_pend["fecha_hora"], datetime)
                else datetime.fromisoformat(str(matching_pend["fecha_hora"]))
            )
            if fh_pend <= ahora:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "error": {
                            "code": "EVENT_ALREADY_STARTED",
                            "message": "El evento ya comenzó o finalizó y no puede ser modificado.",
                            "field": "id_externo",
                        }
                    },
                )

            if (
                payload.tipo
                and payload.tipo.strip().lower()
                != str(matching_pend["tipo"]).strip().lower()
            ):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "error": {
                            "code": "EVENT_TYPE_CHANGE_NOT_ALLOWED",
                            "message": "No se permite cambiar el tipo de evento ya que define el modelo de puntuación.",
                            "field": "tipo",
                        }
                    },
                )

            return {
                "mensaje": "Evento pendiente actualizado.",
                "cambio_creado": False,
                "id_interno": matching_pend["id_interno"],
            }

        raise EventoNoEncontradoError("No se encontró el evento especificado.")

    def recibir_cancelacion_club(
        self,
        club_id: str,
        id_externo_o_interno: str,
        motivo: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Registra la notificación de cancelación enviada por el club (HU-23 User Story 2 / Esc. 1).
        Marca el evento con la bandera 'cancelado_por_el_club'.
        """
        res = self.repo.marcar_cancelado_club(club_id, id_externo_o_interno)
        if not res:
            raise EventoNoEncontradoError(
                "No se encontró el evento especificado para marcar cancelación."
            )
        return {
            "mensaje": "Cancelación registrada por el club.",
            "cancelado_por_el_club": True,
            "id_interno": res["id_interno"],
        }

    def listar_cambios_pendientes(
        self,
        club_id: str | None = None,
    ) -> list[EventoCambioReviewResponse]:
        """
        Lista todas las solicitudes de reprogramación pendientes de revisión (HU-23 Esc. 1 y FR-002).
        Retorna la comparativa antes/después para que el Administrador evalúe.
        """
        rows = self.repo.find_cambios_pendientes(club_id=club_id)
        resultado: list[EventoCambioReviewResponse] = []

        for r in rows:
            fh_act = asegurar_utc(
                r["fecha_hora_actual"]
                if isinstance(r["fecha_hora_actual"], datetime)
                else datetime.fromisoformat(str(r["fecha_hora_actual"]))
            )
            fh_nueva = None
            if r.get("fecha_hora"):
                fh_nueva = asegurar_utc(
                    r["fecha_hora"]
                    if isinstance(r["fecha_hora"], datetime)
                    else datetime.fromisoformat(str(r["fecha_hora"]))
                )

            solicitado_en = asegurar_utc(
                r["solicitado_en"]
                if isinstance(r["solicitado_en"], datetime)
                else datetime.fromisoformat(str(r["solicitado_en"]))
            )

            comparacion = ComparacionValores(
                fecha_hora_actual=fh_act,
                fecha_hora_nueva=fh_nueva,
                lugar_actual=r.get("lugar_actual") or "",
                lugar_nuevo=r.get("lugar"),
                titulo_actual=r.get("titulo_actual") or "",
                titulo_nuevo=r.get("titulo"),
                descripcion_actual=r.get("descripcion_actual"),
                descripcion_nueva=r.get("descripcion"),
            )

            raw_vp = r.get("valores_previos")
            if isinstance(raw_vp, str):
                try:
                    valores_previos = json.loads(raw_vp)
                except (json.JSONDecodeError, TypeError, ValueError):
                    valores_previos = {}
            elif isinstance(raw_vp, dict):
                valores_previos = raw_vp
            else:
                valores_previos = {}
            valores_nuevos = {
                "titulo": r.get("titulo"),
                "fecha_hora": fh_nueva.isoformat() if fh_nueva else None,
                "lugar": r.get("lugar"),
                "descripcion": r.get("descripcion"),
            }

            item = EventoCambioReviewResponse(
                id_cambio=str(r["id_cambio"]),
                id_interno=str(r["id_interno"]),
                id_externo=str(r.get("id_externo") or ""),
                club_id=str(r["club_id"]),
                titulo=str(r.get("titulo") or r.get("titulo_actual") or ""),
                tipo=str(r.get("tipo") or r.get("tipo_actual") or "Partido"),
                estado=str(r.get("estado_revision") or "pendiente_revision"),
                solicitado_en=solicitado_en,
                valores_previos=valores_previos,
                valores_nuevos=valores_nuevos,
                comparacion=comparacion,
            )
            resultado.append(item)

        return resultado

    def aprobar_cambio_evento(
        self,
        db: Session,
        cambio_id: str,
        admin_id: int,
        now: datetime | None = None,
    ) -> EventoCambioActionResponse:
        """
        Aprueba una solicitud de cambio (HU-23 Escenarios 2, 8, 10, 11, 12, 13 y FR-003, FR-005, FR-006).
        - Aplica inmediatamente los valores al evento visible (mantiene estado 'publicado').
        - Fija la ventana de 24h para ajuste de clase/puntos.
        - Evalúa la regla de invalidación/ajuste del cronograma de olas.
        - Audita el cambio registrando quién, cuándo, valores previos y nuevos.
        - Encola la notificación del evento para el sistema de notificaciones.
        """
        cambio = self.repo.get_cambio_pendiente(cambio_id)
        if not cambio:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Solicitud de cambio no encontrada.",
            )
        if cambio.get("estado_revision") != "pendiente_revision":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"La solicitud de cambio ya se encuentra {cambio.get('estado_revision')}.",
            )

        evento_vis = self.repo.get_evento_visible(cambio["id_interno"])
        if not evento_vis:
            raise EventoNoEncontradoError("Evento visible no encontrado.")

        if evento_vis.get("estado") in ("withdrawn", "retirado"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="El evento fue retirado y no se pueden aplicar cambios.",
            )

        ahora = asegurar_utc(now or datetime.now(UTC))
        fin_ajuste = ahora + timedelta(hours=24)

        valores_a_aplicar: dict[str, Any] = {}
        for k in ["titulo", "fecha_hora", "lugar", "descripcion"]:
            if cambio.get(k) is not None:
                val = cambio[k]
                if k == "fecha_hora":
                    val = asegurar_utc(
                        val
                        if isinstance(val, datetime)
                        else datetime.fromisoformat(str(val))
                    )
                valores_a_aplicar[k] = val

        # Aplicar cambio en el repositorio
        self.repo.aplicar_cambio_evento(
            id_interno=cambio["id_interno"],
            valores=valores_a_aplicar,
            fin_ajuste_clase_puntos=fin_ajuste,
        )

        # Sincronizar entidad SQLAlchemy si existe
        ev_db = db.get(EventoVisibleDB, cambio["id_interno"])
        if ev_db:
            for k, v in valores_a_aplicar.items():
                setattr(ev_db, k, v)
            ev_db.fin_ajuste_clase_puntos = fin_ajuste

        # Actualizar estado del cambio a aprobado
        self.repo.update_cambio_estado(
            id_cambio=cambio_id,
            estado_revision="aprobado",
            revisado_por_id=admin_id,
        )

        # Reglas de Cronograma de Olas (FR-006 & Escenarios 10, 11, 12)
        advertencia_cronograma = None
        new_start = valores_a_aplicar.get("fecha_hora")
        if new_start is None:
            new_start = asegurar_utc(
                evento_vis["fecha_hora"]
                if isinstance(evento_vis["fecha_hora"], datetime)
                else datetime.fromisoformat(str(evento_vis["fecha_hora"]))
            )

        schedule = db.scalar(
            select(WaveSchedule).where(
                WaveSchedule.event_id == cambio["id_interno"],
                WaveSchedule.status == WaveScheduleStatus.CONFIRMED,
            )
        )
        if schedule:
            closing_at = asegurar_utc(schedule.closing_at)
            opening_at = asegurar_utc(schedule.opening_at)

            if new_start >= closing_at:
                # Escenario 10: el nuevo inicio no es antes del cierre -> se deja como está
                pass
            elif ahora < opening_at:
                # Escenario 11: nuevo inicio antes del cierre y ninguna ola abrió -> invalidar
                prev_status = schedule.status.value
                schedule.status = WaveScheduleStatus.INVALIDATED
                audit.record(
                    db,
                    "wave_schedule.invalidated",
                    actor_id=admin_id,
                    entity="wave_schedule",
                    entity_id=schedule.id,
                    event_id=cambio["id_interno"],
                    previous={"status": prev_status},
                    new={"status": WaveScheduleStatus.INVALIDATED.value},
                    motivo="reprogramacion_previa_apertura",
                )
                advertencia_cronograma = "El cronograma fue invalidado porque el nuevo inicio es anterior al cierre general. Debe regenerarse."
            else:
                # Escenario 12: nuevo inicio antes del cierre y ya abrieron olas -> fijar closing = new_start
                prev_closing = schedule.closing_at
                schedule.closing_at = new_start
                audit.record(
                    db,
                    "wave_schedule.adjusted",
                    actor_id=admin_id,
                    entity="wave_schedule",
                    entity_id=schedule.id,
                    event_id=cambio["id_interno"],
                    previous={"closing_at": prev_closing.isoformat()},
                    new={"closing_at": new_start.isoformat()},
                    motivo="reprogramacion_con_olas_abiertas",
                )
                advertencia_cronograma = "El cierre general del cronograma se ajustó al nuevo inicio del evento debido a que ya se habían abierto olas."

        # Auditoría del cambio (Escenario 13 & FR-011)
        audit.record(
            db,
            "event.reprogrammed",
            actor_id=admin_id,
            entity="event",
            entity_id=cambio["id_interno"],
            cambio_id=cambio_id,
            previous=cambio.get("valores_previos") or {},
            new={
                k: (v.isoformat() if isinstance(v, datetime) else v)
                for k, v in valores_a_aplicar.items()
            },
        )

        return EventoCambioActionResponse(
            mensaje="Cambio aprobado y aplicado exitosamente.",
            id_cambio=str(cambio_id),
            id_interno=cambio["id_interno"],
            estado="aprobado",
            fin_ajuste_clase_puntos=fin_ajuste,
            advertencia_cronograma=advertencia_cronograma,
        )

    def rechazar_cambio_evento(
        self,
        db: Session,
        cambio_id: str,
        admin_id: int,
        motivo: str | None = None,
        now: datetime | None = None,
    ) -> EventoCambioActionResponse:
        """
        Rechaza una solicitud de cambio (HU-23 Escenario 3 y 13).
        El evento permanece intacto con sus valores originales.
        """
        cambio = self.repo.get_cambio_pendiente(cambio_id)
        if not cambio:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Solicitud de cambio no encontrada.",
            )
        if cambio.get("estado_revision") != "pendiente_revision":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"La solicitud de cambio ya se encuentra {cambio.get('estado_revision')}.",
            )

        self.repo.update_cambio_estado(
            id_cambio=cambio_id,
            estado_revision="rechazado",
            revisado_por_id=admin_id,
        )

        audit.record(
            db,
            "event.reprogramming_rejected",
            actor_id=admin_id,
            entity="event",
            entity_id=cambio["id_interno"],
            cambio_id=cambio_id,
            motivo=motivo,
        )

        return EventoCambioActionResponse(
            mensaje="Cambio rechazado.",
            id_cambio=str(cambio_id),
            id_interno=cambio["id_interno"],
            estado="rechazado",
        )

    def retirar_evento(
        self,
        db: Session,
        club_id: str | None,
        id_externo_o_interno: str,
        admin_id: int,
        motivo: str,
        now: datetime | None = None,
    ) -> EventoRetiroResponse:
        """
        Retira un evento publicado (HU-23 User Story 2 / Esc. 2, 3, 4, 9 y FR-008, FR-009)
        o descarta un evento pendiente (HU-21 / HU-23).
        - Requiere motivo obligatorio.
        - Para eventos publicados: pasa a 'withdrawn', anula segmentación/cronograma, audita y notifica.
        - Para eventos pendientes: pasa a 'descartado' y audita.
        """
        if not motivo or not motivo.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="El motivo de retiro es obligatorio.",
            )

        ahora = asegurar_utc(now or datetime.now(UTC))

        # 1. Buscar en eventos visibles (publicados / retirados)
        evento_vis = self.repo.get_evento_visible(
            id_externo_o_interno=id_externo_o_interno, club_id=club_id
        )
        if evento_vis:
            if evento_vis.get("estado") in ("withdrawn", "retirado"):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="El evento ya fue retirado previamente.",
                )

            fh_utc = asegurar_utc(
                evento_vis["fecha_hora"]
                if isinstance(evento_vis["fecha_hora"], datetime)
                else datetime.fromisoformat(str(evento_vis["fecha_hora"]))
            )
            if fh_utc <= ahora:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="No se puede retirar un evento que ya comenzó o finalizó.",
                )

            self.repo.retirar_evento(
                id_interno=evento_vis["id_interno"],
                admin_id=admin_id,
                motivo=motivo.strip(),
            )

            ev_db = db.get(EventoVisibleDB, evento_vis["id_interno"])
            if ev_db:
                ev_db.estado = "withdrawn"
                ev_db.retirado_en = ahora
                ev_db.retirado_por_id = admin_id
                ev_db.motivo_retiro = motivo.strip()

            # Anular cronograma de olas si existía (Esc. 4 & FR-009)
            schedule = db.scalar(
                select(WaveSchedule).where(
                    WaveSchedule.event_id == evento_vis["id_interno"]
                )
            )
            if schedule:
                prev_status = schedule.status.value
                schedule.status = WaveScheduleStatus.INVALIDATED
                audit.record(
                    db,
                    "wave_schedule.voided",
                    actor_id=admin_id,
                    entity="wave_schedule",
                    entity_id=schedule.id,
                    event_id=evento_vis["id_interno"],
                    previous={"status": prev_status},
                    new={"status": "voided"},
                )

            audit.record(
                db,
                "event.withdrawn",
                actor_id=admin_id,
                entity="event",
                entity_id=evento_vis["id_interno"],
                motivo=motivo.strip(),
                previous={"estado": "publicado"},
                new={"estado": "withdrawn"},
            )

            return EventoRetiroResponse(
                mensaje="Evento retirado exitosamente.",
                id_interno=evento_vis["id_interno"],
                estado="withdrawn",
                retirado_en=ahora,
                motivo=motivo.strip(),
            )

        # 2. Fallback a eventos pendientes
        evento_pend = self.repo.get_evento_pendiente(
            club_id=club_id, id_externo_o_interno=id_externo_o_interno
        )
        if not evento_pend:
            raise EventoNoEncontradoError("No se encontró el evento para retirar.")

        if evento_pend.get("estado") == "descartado":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El evento ya fue descartado previamente.",
            )

        self.repo.descartar_evento_pendiente(id_interno=evento_pend["id_interno"])

        ev_pend_db = db.get(EventoPendienteDB, evento_pend["id_interno"])
        if ev_pend_db:
            ev_pend_db.estado = "descartado"
            ev_pend_db.actualizado_en = ahora

        audit.record(
            db,
            "event.discarded",
            actor_id=admin_id,
            entity="event",
            entity_id=evento_pend["id_interno"],
            motivo=motivo.strip(),
            previous={
                "estado": evento_pend.get("estado", "pendiente_definicion_importancia")
            },
            new={"estado": "descartado"},
        )

        return EventoRetiroResponse(
            mensaje="Evento pendiente retirado/descartado exitosamente.",
            id_interno=evento_pend["id_interno"],
            estado="descartado",
            retirado_en=ahora,
            motivo=motivo.strip(),
        )

    def restaurar_evento(
        self,
        db: Session,
        club_id: str | None,
        id_externo_o_interno: str,
        admin_id: int,
        now: datetime | None = None,
    ) -> EventoRestaurarResponse:
        """
        Restaura un evento retirado o descartado (HU-23 User Story 2 / Esc. 7, 9 y FR-010).
        - Solo si su fecha de inicio no ha pasado.
        - Para eventos visibles: vuelve al estado 'publicado', su cronograma de olas se mantiene anulado.
        - Para eventos pendientes: vuelve al estado 'pendiente_definicion_importancia'.
        """
        ahora = asegurar_utc(now or datetime.now(UTC))

        # 1. Buscar en eventos visibles (publicados / retirados)
        evento_vis = self.repo.get_evento_visible(
            id_externo_o_interno=id_externo_o_interno, club_id=club_id
        )
        if evento_vis:
            if evento_vis.get("estado") not in ("withdrawn", "retirado"):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="El evento no se encuentra en estado retirado.",
                )

            fh_utc = asegurar_utc(
                evento_vis["fecha_hora"]
                if isinstance(evento_vis["fecha_hora"], datetime)
                else datetime.fromisoformat(str(evento_vis["fecha_hora"]))
            )
            if fh_utc <= ahora:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="No se puede restaurar un evento cuya fecha de inicio ya pasó.",
                )

            self.repo.restaurar_evento(
                id_interno=evento_vis["id_interno"],
                admin_id=admin_id,
            )

            ev_db = db.get(EventoVisibleDB, evento_vis["id_interno"])
            if ev_db:
                ev_db.estado = "publicado"
                ev_db.restaurado_en = ahora
                ev_db.restaurado_por_id = admin_id

            audit.record(
                db,
                "event.restored",
                actor_id=admin_id,
                entity="event",
                entity_id=evento_vis["id_interno"],
                previous={"estado": "withdrawn"},
                new={"estado": "publicado"},
            )

            return EventoRestaurarResponse(
                mensaje="Evento restaurado exitosamente.",
                id_interno=evento_vis["id_interno"],
                estado="publicado",
                restaurado_en=ahora,
            )

        # 2. Fallback a eventos pendientes descartados
        evento_pend = self.repo.get_evento_pendiente(
            club_id=club_id, id_externo_o_interno=id_externo_o_interno
        )
        if not evento_pend:
            raise EventoNoEncontradoError("No se encontró el evento para restaurar.")

        if evento_pend.get("estado") != "descartado":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El evento pendiente no se encuentra en estado descartado.",
            )

        fh_utc = asegurar_utc(
            evento_pend["fecha_hora"]
            if isinstance(evento_pend["fecha_hora"], datetime)
            else datetime.fromisoformat(str(evento_pend["fecha_hora"]))
        )
        if fh_utc <= ahora:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="No se puede restaurar un evento cuya fecha de inicio ya pasó.",
            )

        self.repo.restaurar_evento_pendiente(id_interno=evento_pend["id_interno"])

        ev_pend_db = db.get(EventoPendienteDB, evento_pend["id_interno"])
        if ev_pend_db:
            ev_pend_db.estado = "pendiente_definicion_importancia"
            ev_pend_db.actualizado_en = ahora

        audit.record(
            db,
            "event.restored",
            actor_id=admin_id,
            entity="event",
            entity_id=evento_pend["id_interno"],
            previous={"estado": "descartado"},
            new={"estado": "pendiente_definicion_importancia"},
        )

        return EventoRestaurarResponse(
            mensaje="Evento pendiente restaurado exitosamente.",
            id_interno=evento_pend["id_interno"],
            estado="pendiente_definicion_importancia",
            restaurado_en=ahora,
        )

    def ajustar_clase_o_puntos_reprogramacion(
        self,
        db: Session,
        club_id: str | None,
        id_externo_o_interno: str,
        clase: str | None,
        puntos: int | None,
        admin_id: int,
        now: datetime | None = None,
    ) -> EventoAjustarClaseResponse:
        """
        Permite al Admin ajustar la clase (Partido) o puntos (Institucional) dentro de las 24hs
        posteriores a la aprobación de una reprogramación (HU-23 Escenarios 8, 9 y FR-005).
        """
        evento_vis = self.repo.get_evento_visible(
            id_externo_o_interno=id_externo_o_interno, club_id=club_id
        )
        if not evento_vis:
            # Check si es un evento pendiente
            evento_pend = self.repo.get_evento_pendiente(
                club_id=club_id, id_externo_o_interno=id_externo_o_interno
            )
            if evento_pend:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="El evento aún no ha sido publicado. La clase o puntos se asignan desde 'Eventos pendientes de publicar' al momento de publicarlo.",
                )
            raise EventoNoEncontradoError("No se encontró el evento.")

        ahora = asegurar_utc(now or datetime.now(UTC))
        fin_ajuste = evento_vis.get("fin_ajuste_clase_puntos")
        if not fin_ajuste:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="El evento no se encuentra dentro de la ventana de 24 horas habilitada para ajuste posterior a reprogramación.",
            )

        fin_ajuste_utc = asegurar_utc(
            fin_ajuste
            if isinstance(fin_ajuste, datetime)
            else datetime.fromisoformat(str(fin_ajuste))
        )
        if ahora > fin_ajuste_utc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="La ventana de 24 horas para ajustar la clase o puntos del evento ha expirado.",
            )

        tipo_ev = str(evento_vis.get("tipo", "")).strip().lower()
        if tipo_ev == "partido":
            if not clase or str(clase).upper() not in ["A", "B", "C"]:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Debe especificar una clase válida ('A', 'B' o 'C') para un Partido.",
                )
            clase_val = str(clase).upper()
            puntos_val = None
        else:
            if puntos is None or puntos < 1 or puntos > 100:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Debe especificar un puntaje entre 1 y 100 para un evento Institucional.",
                )
            clase_val = None
            puntos_val = puntos

        self.repo.ajustar_clase_o_puntos(
            id_interno=evento_vis["id_interno"],
            clase=clase_val,
            puntos=puntos_val,
        )

        ev_db = db.get(EventoVisibleDB, evento_vis["id_interno"])
        if ev_db:
            ev_db.clase = clase_val
            ev_db.puntos = puntos_val

        audit.record(
            db,
            "event.class_adjusted",
            actor_id=admin_id,
            entity="event",
            entity_id=evento_vis["id_interno"],
            previous={
                "clase": evento_vis.get("clase"),
                "puntos": evento_vis.get("puntos"),
            },
            new={"clase": clase_val, "puntos": puntos_val},
        )

        return EventoAjustarClaseResponse(
            mensaje="Clase/puntos ajustados exitosamente.",
            id_interno=evento_vis["id_interno"],
            clase=clase_val,
            puntos=puntos_val,
            actualizado_en=ahora,
        )
