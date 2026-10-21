from typing import Any

from pydantic import ValidationError

from ..core.date_utils import (
    validar_antelacion_48_horas,
    validar_evento_futuro,
)
from ..core.exceptions import (
    AntelacionInsuficienteError,
    EventoDuplicadoError,
)
from ..models.enums import TipoEvento
from ..repositories.base import EventoRepository
from ..schemas.eventos import (
    BatchFailedItem,
    BatchOmittedItem,
    BatchResponse,
    BatchSuccessItem,
    BatchSummary,
    EventoCreateRequest,
    EventoCreateResponse,
    EventoDetailResponse,
)


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

            if ev.tipo == TipoEvento.PARTIDO:
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

            id_interno = self.repo.insert_pendiente(
                club_id=club_id,
                evento=ev,
                estado="pendiente_definicion_importancia",
                es_historico=False,
            )
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
                        motivo="Evento ya registrado previamente (omitido de forma segura).",
                        estado="omitido",
                    )
                )
                continue

            id_interno = self.repo.insert_pendiente(
                club_id=club_id, evento=ev, estado="Historico", es_historico=True
            )
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
