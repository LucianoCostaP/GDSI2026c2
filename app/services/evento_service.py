from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError

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
from ..models.enums import (
    DEMANDA_CLASE_PARTIDO,
    FACTORES_CLASE_PARTIDO,
    ClasePartido,
    TipoEvento,
)
from ..repositories.base import EventoRepository
from ..schemas.eventos import (
    AutoPublishResponse,
    BatchFailedItem,
    BatchOmittedItem,
    BatchResponse,
    BatchSuccessItem,
    BatchSummary,
    ClaseInfoResponse,
    EventoCreateRequest,
    EventoCreateResponse,
    EventoDetailResponse,
    EventoPendientePublicacionResponse,
    ProximoEventoItem,
    ProximosEventosResponse,
    PublicarEventoRequest,
    PublicarEventoResponse,
)

# HU-17 FR-004 y decisión 24: texto exacto, los tests lo comparan por igualdad.
MENSAJE_SIN_EVENTOS_PROXIMOS = "No hay eventos próximos publicados."


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
            lead_minimo = ahora_utc + timedelta(
                hours=settings.min_publication_lead_hours
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
