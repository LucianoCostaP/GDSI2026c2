import csv
import hashlib
import io
import json
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..audit import record
from ..models.auth import User
from ..models.domain import (
    ActividadRecurrenteDB,
    AsistenciaDB,
    AsistenciaStagingDB,
    CargaParticipacionDB,
    CargaParticipacionRechazoDB,
    Club,
    EventoPendienteDB,
    EventoVisibleDB,
    Socio,
)
from ..models.enums import EstadoCargaParticipacion, OrigenCarga, TipoParticipacion
from ..schemas.participacion import (
    AprobacionAccionResponse,
    CargaActividadesBatchRequest,
    CargaActividadesResponse,
    CargaAsistenciaPageRequest,
    CargaAsistenciaResponse,
    CargaParticipacionStatusResponse,
    CargaPendienteAprobacionResponse,
    CargaPreviaInfo,
    EventoElegibleAsistenciaResponse,
    RechazoParticipacionDetail,
    UploadCSVResponse,
)


class ParticipacionService:
    @staticmethod
    def _calcular_hash(payload: Any) -> str:
        serialized = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _verificar_evento_elegible(
        club_id: uuid.UUID, id_externo: str, db: Session
    ) -> EventoVisibleDB | EventoPendienteDB:
        """
        Valida que el evento exista para el club, esté publicado o sea un histórico confirmado,
        y que su fecha_hora de inicio ya haya transcurrido.
        """
        ahora = datetime.now(UTC)

        # 1. Buscar en eventos visibles (publicados)
        evento_vis = (
            db.query(EventoVisibleDB)
            .filter(
                EventoVisibleDB.club_id == club_id,
                EventoVisibleDB.id_externo == id_externo,
            )
            .first()
        )
        if evento_vis:
            fh = (
                evento_vis.fecha_hora
                if evento_vis.fecha_hora.tzinfo
                else evento_vis.fecha_hora.replace(tzinfo=UTC)
            )
            if fh > ahora:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "error": {
                            "code": "EVENT_NOT_ELIGIBLE",
                            "message": "El evento aún no ha comenzado. Solo se admite asistencia para eventos ya ocurridos.",
                            "field": "id_externo",
                        }
                    },
                )
            return evento_vis

        # 2. Buscar en eventos pendientes/históricos confirmados
        evento_pend = (
            db.query(EventoPendienteDB)
            .filter(
                EventoPendienteDB.club_id == club_id,
                EventoPendienteDB.id_externo == id_externo,
            )
            .first()
        )
        if evento_pend and evento_pend.es_historico:
            fh = (
                evento_pend.fecha_hora
                if evento_pend.fecha_hora.tzinfo
                else evento_pend.fecha_hora.replace(tzinfo=UTC)
            )
            if fh > ahora:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "error": {
                            "code": "EVENT_NOT_ELIGIBLE",
                            "message": "El evento histórico tiene fecha futura.",
                            "field": "id_externo",
                        }
                    },
                )
            return evento_pend

        # Si no existe o está en estado pendiente de publicar no histórico
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "error": {
                    "code": "EVENT_NOT_ELIGIBLE",
                    "message": "El evento no existe o no se encuentra publicado ni confirmado como histórico.",
                    "field": "id_externo",
                }
            },
        )

    # ==========================================================================
    # ASISTENCIA A EVENTOS (PUSH DEL CLUB)
    # ==========================================================================

    @classmethod
    def procesar_pagina_asistencia(
        cls,
        club: Club,
        id_externo: str,
        request: CargaAsistenciaPageRequest,
        db: Session,
    ) -> CargaAsistenciaResponse:
        # 1. Validar elegibilidad del evento
        cls._verificar_evento_elegible(club.id, id_externo, db)

        # 2. Control de idempotencia
        payload_hash = cls._calcular_hash([r.model_dump() for r in request.registros])

        carga = (
            db.query(CargaParticipacionDB)
            .filter(
                CargaParticipacionDB.club_id == club.id,
                CargaParticipacionDB.tipo == TipoParticipacion.ASISTENCIA,
                CargaParticipacionDB.carga_id_externo == request.carga_id,
            )
            .first()
        )

        ahora = datetime.now(UTC)

        if carga:
            # Si el evento asociado difiere o el total de páginas difiere -> 409
            if (
                carga.evento_id_externo != id_externo
                or carga.total_paginas != request.total_paginas
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": {
                            "code": "CONFLICT",
                            "message": "La carga ya existe pero los parámetros generales difieren.",
                            "field": "carga_id",
                        }
                    },
                )

            # Verificar expiración (60 minutos desde su inicio)
            creado = (
                carga.creado_en
                if carga.creado_en.tzinfo
                else carga.creado_en.replace(tzinfo=UTC)
            )
            if ahora - creado > timedelta(minutes=60):
                carga.estado = EstadoCargaParticipacion.FAILED
                carga.motivo_fallo = "LOAD_EXPIRED"
                db.commit()
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "error": {
                            "code": "LOAD_EXPIRED",
                            "message": "La carga de asistencia expiró porque transcurrieron más de 60 minutos desde la primera página.",
                            "field": "carga_id",
                        }
                    },
                )

            # Verificar si la página ya fue recibida
            stagings_pag = (
                db.query(AsistenciaStagingDB)
                .filter(
                    AsistenciaStagingDB.carga_id == carga.id,
                    AsistenciaStagingDB.pagina == request.pagina,
                )
                .all()
            )
            rechazos_pag = (
                db.query(CargaParticipacionRechazoDB)
                .filter(
                    CargaParticipacionRechazoDB.carga_id == carga.id,
                    CargaParticipacionRechazoDB.fila == request.pagina,
                )
                .all()
            )

            if stagings_pag or rechazos_pag:
                # Comprobar si el contenido es idéntico o fue alterado
                dnis_almacenados = [s.dni for s in stagings_pag] + [
                    r.dni for r in rechazos_pag if r.dni
                ]
                dnis_entrantes = [r.dni.strip() for r in request.registros]

                if sorted(dnis_almacenados) != sorted(dnis_entrantes):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "error": {
                                "code": "CONFLICT",
                                "message": "La página ya fue recibida previamente con contenido diferente.",
                                "field": "pagina",
                            }
                        },
                    )

                return CargaAsistenciaResponse(
                    carga_id=request.carga_id,
                    evento_id_externo=id_externo,
                    pagina=request.pagina,
                    total_paginas=request.total_paginas,
                    estado=carga.estado,
                    total_registros_pagina=len(request.registros),
                    registros_validos_pagina=len(stagings_pag),
                    registros_rechazados_pagina=len(rechazos_pag),
                    rechazos=[
                        RechazoParticipacionDetail(
                            dni=r.dni, field=r.campo, codigo=r.codigo, motivo=r.motivo
                        )
                        for r in rechazos_pag
                    ],
                    mensaje="Página ya recibida previamente (respuesta idempotente).",
                )
        else:
            # Crear nueva carga en base de datos
            carga = CargaParticipacionDB(
                id=uuid.uuid4(),
                club_id=club.id,
                tipo=TipoParticipacion.ASISTENCIA,
                origen=OrigenCarga.CLUB,
                carga_id_externo=request.carga_id,
                evento_id_externo=id_externo,
                estado=EstadoCargaParticipacion.RECEIVING,
                total_paginas=request.total_paginas,
                paginas_recibidas=0,
                total_registros=0,
                registros_incorporados=0,
                registros_actualizados=0,
                registros_rechazados=0,
                payload_hash=payload_hash,
                creado_en=ahora,
                actualizado_en=ahora,
            )
            db.add(carga)
            db.flush()

        # 3. Validación de registros de la página
        dnis_en_pagina = [r.dni.strip() for r in request.registros]
        # Consultar socios del club para estos DNIs
        socios_db = (
            db.query(Socio)
            .filter(
                Socio.club_id == club.id,
                Socio.dni.in_(dnis_en_pagina),
            )
            .all()
        )
        socios_map = {s.dni: s for s in socios_db}

        dnis_vistos_en_pagina = set()
        validos_para_staging: list[AsistenciaStagingDB] = []
        rechazos_pagina: list[CargaParticipacionRechazoDB] = []

        for reg in request.registros:
            dni_clean = reg.dni.strip()
            # Validar duplicado en la misma página
            if dni_clean in dnis_vistos_en_pagina:
                rechazos_pagina.append(
                    CargaParticipacionRechazoDB(
                        id=uuid.uuid4(),
                        carga_id=carga.id,
                        dni=dni_clean,
                        campo="dni",
                        codigo="DUPLICATE_DNI_PAGE",
                        motivo="DNI duplicado dentro de la misma página.",
                        fila=request.pagina,
                    )
                )
                continue

            dnis_vistos_en_pagina.add(dni_clean)

            # Validar existencia del socio
            socio = socios_map.get(dni_clean)
            if not socio:
                rechazos_pagina.append(
                    CargaParticipacionRechazoDB(
                        id=uuid.uuid4(),
                        carga_id=carga.id,
                        dni=dni_clean,
                        campo="dni",
                        codigo="SOCIO_NOT_FOUND",
                        motivo="El socio no existe en el padrón del club.",
                        fila=request.pagina,
                    )
                )
                continue

            # Validar número de socio si fue provisto
            if reg.numero_socio:
                num_clean = reg.numero_socio.strip()
                if socio.numero_socio and socio.numero_socio != num_clean:
                    rechazos_pagina.append(
                        CargaParticipacionRechazoDB(
                            id=uuid.uuid4(),
                            carga_id=carga.id,
                            dni=dni_clean,
                            campo="numero_socio",
                            codigo="NUMERO_SOCIO_MISMATCH",
                            motivo="El número de socio provisto no coincide con el DNI registrado.",
                            fila=request.pagina,
                        )
                    )
                    continue

            # Registro válido
            validos_para_staging.append(
                AsistenciaStagingDB(
                    id=uuid.uuid4(),
                    carga_id=carga.id,
                    pagina=request.pagina,
                    dni=dni_clean,
                    numero_socio=reg.numero_socio.strip() if reg.numero_socio else None,
                )
            )

        # 4. Guardar en BD
        db.add_all(rechazos_pagina)
        db.add_all(validos_para_staging)

        carga.paginas_recibidas += 1
        carga.total_registros += len(request.registros)
        carga.registros_rechazados += len(rechazos_pagina)
        carga.actualizado_en = ahora

        # 5. Si es la última página -> Validaciones cruzadas y Cierre
        if (
            request.pagina == request.total_paginas
            or carga.paginas_recibidas >= request.total_paginas
        ):
            # Control DNI duplicado entre páginas
            duplicados_inter = (
                db.query(AsistenciaStagingDB.dni)
                .filter(AsistenciaStagingDB.carga_id == carga.id)
                .group_by(AsistenciaStagingDB.dni)
                .having(func.count(AsistenciaStagingDB.dni) > 1)
                .all()
            )

            if duplicados_inter:
                carga.estado = EstadoCargaParticipacion.FAILED
                carga.motivo_fallo = "DUPLICATE_DNI_ACROSS_PAGES"
                db.commit()
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "error": {
                            "code": "DUPLICATE_DNI_ACROSS_PAGES",
                            "message": f"Se detectaron DNIs repetidos entre distintas páginas de la carga ({len(duplicados_inter)} duplicados). La carga completa fue abortada.",
                            "field": "dni",
                        }
                    },
                )

            total_validos_acumulados = (
                db.query(AsistenciaStagingDB)
                .filter(AsistenciaStagingDB.carga_id == carga.id)
                .count()
            )

            # Si no hay ningún registro válido en toda la carga
            if total_validos_acumulados == 0:
                carga.estado = EstadoCargaParticipacion.FAILED
                carga.motivo_fallo = "EMPTY_LOAD"
                db.commit()
                return CargaAsistenciaResponse(
                    carga_id=request.carga_id,
                    evento_id_externo=id_externo,
                    pagina=request.pagina,
                    total_paginas=request.total_paginas,
                    estado=EstadoCargaParticipacion.FAILED,
                    total_registros_pagina=len(request.registros),
                    registros_validos_pagina=len(validos_para_staging),
                    registros_rechazados_pagina=len(rechazos_pagina),
                    rechazos=[
                        RechazoParticipacionDetail(
                            dni=r.dni, field=r.campo, codigo=r.codigo, motivo=r.motivo
                        )
                        for r in rechazos_pagina
                    ],
                    mensaje="La carga no contiene registros válidos. Nada fue aplicado.",
                )

            # Verificar si el evento ya tenía asistencia previa
            asistencia_previa_count = (
                db.query(AsistenciaDB)
                .filter(
                    AsistenciaDB.club_id == club.id,
                    AsistenciaDB.evento_id_externo == id_externo,
                )
                .count()
            )

            if asistencia_previa_count > 0:
                # Se mantiene en pending_approval hasta que el Admin confirme
                carga.estado = EstadoCargaParticipacion.PENDING_APPROVAL
                db.commit()
                return CargaAsistenciaResponse(
                    carga_id=request.carga_id,
                    evento_id_externo=id_externo,
                    pagina=request.pagina,
                    total_paginas=request.total_paginas,
                    estado=EstadoCargaParticipacion.PENDING_APPROVAL,
                    total_registros_pagina=len(request.registros),
                    registros_validos_pagina=len(validos_para_staging),
                    registros_rechazados_pagina=len(rechazos_pagina),
                    rechazos=[
                        RechazoParticipacionDetail(
                            dni=r.dni, field=r.campo, codigo=r.codigo, motivo=r.motivo
                        )
                        for r in rechazos_pagina
                    ],
                    mensaje="La carga de asistencia requiere aprobación del Administrador porque el evento ya posee asistencia cargada.",
                )

            # Si no tenía asistencia previa -> Aplicar atómicamente
            carga.estado = EstadoCargaParticipacion.SUCCESSFUL
            carga.registros_incorporados = total_validos_acumulados

            # Traspaso atómico de staging a tabla definitiva
            stagings = (
                db.query(AsistenciaStagingDB)
                .filter(AsistenciaStagingDB.carga_id == carga.id)
                .all()
            )
            nuevas_asistencias = [
                AsistenciaDB(
                    id=uuid.uuid4(),
                    club_id=club.id,
                    evento_id_externo=id_externo,
                    dni=st.dni,
                    numero_socio=st.numero_socio,
                    carga_id=carga.id,
                    creado_en=ahora,
                )
                for st in stagings
            ]
            db.add_all(nuevas_asistencias)

            # Limpiar staging
            db.query(AsistenciaStagingDB).filter(
                AsistenciaStagingDB.carga_id == carga.id
            ).delete()

            db.commit()

            return CargaAsistenciaResponse(
                carga_id=request.carga_id,
                evento_id_externo=id_externo,
                pagina=request.pagina,
                total_paginas=request.total_paginas,
                estado=EstadoCargaParticipacion.SUCCESSFUL,
                total_registros_pagina=len(request.registros),
                registros_validos_pagina=len(validos_para_staging),
                registros_rechazados_pagina=len(rechazos_pagina),
                rechazos=[
                    RechazoParticipacionDetail(
                        dni=r.dni, field=r.campo, codigo=r.codigo, motivo=r.motivo
                    )
                    for r in rechazos_pagina
                ],
                mensaje="Carga de asistencia procesada y aplicada con éxito.",
            )

        db.commit()

        return CargaAsistenciaResponse(
            carga_id=request.carga_id,
            evento_id_externo=id_externo,
            pagina=request.pagina,
            total_paginas=request.total_paginas,
            estado=carga.estado,
            total_registros_pagina=len(request.registros),
            registros_validos_pagina=len(validos_para_staging),
            registros_rechazados_pagina=len(rechazos_pagina),
            rechazos=[
                RechazoParticipacionDetail(
                    dni=r.dni, field=r.campo, codigo=r.codigo, motivo=r.motivo
                )
                for r in rechazos_pagina
            ],
            mensaje="Página recibida y almacenada en staging.",
        )

    # ==========================================================================
    # ACTIVIDADES RECURRENTES (PUSH DEL CLUB)
    # ==========================================================================

    @classmethod
    def procesar_lote_actividades(
        cls,
        club: Club,
        request: CargaActividadesBatchRequest,
        db: Session,
    ) -> CargaActividadesResponse:
        hoy = date.today()

        # 1. Validar fechas de cabecera
        if request.hasta < request.desde:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "error": {
                        "code": "INVALID_DATE_RANGE",
                        "message": "La fecha 'hasta' del lote no puede ser anterior a 'desde'.",
                        "field": "hasta",
                    }
                },
            )

        # 2. Control de Marca de Agua (WATERMARK_GAP)
        ultimo_hasta = (
            db.query(func.max(CargaParticipacionDB.hasta))
            .filter(
                CargaParticipacionDB.club_id == club.id,
                CargaParticipacionDB.tipo == TipoParticipacion.ACTIVIDADES,
                CargaParticipacionDB.estado == EstadoCargaParticipacion.SUCCESSFUL,
            )
            .scalar()
        )

        if ultimo_hasta:
            if request.desde > ultimo_hasta:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "error": {
                            "code": "WATERMARK_GAP",
                            "message": f"El período enviado (desde {request.desde}) deja un vacío respecto al último lote exitoso (hasta {ultimo_hasta}).",
                            "field": "desde",
                        }
                    },
                )
        else:
            # Primer lote: desde debe ser como máximo 365 días hacia atrás
            limite_primer_lote = hoy - timedelta(days=365)
            if request.desde < limite_primer_lote:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "error": {
                            "code": "WATERMARK_GAP",
                            "message": f"El primer lote de actividades no puede iniciar con más de 365 días de antigüedad (mínimo permitido: {limite_primer_lote}).",
                            "field": "desde",
                        }
                    },
                )

        # 3. Control de Idempotencia
        payload_hash = cls._calcular_hash([r.model_dump() for r in request.registros])

        carga_existente = (
            db.query(CargaParticipacionDB)
            .filter(
                CargaParticipacionDB.club_id == club.id,
                CargaParticipacionDB.tipo == TipoParticipacion.ACTIVIDADES,
                CargaParticipacionDB.carga_id_externo == request.lote_id,
            )
            .first()
        )

        if carga_existente:
            if carga_existente.payload_hash == payload_hash:
                # Idempotente
                rechazos_prev = (
                    db.query(CargaParticipacionRechazoDB)
                    .filter(CargaParticipacionRechazoDB.carga_id == carga_existente.id)
                    .all()
                )
                return CargaActividadesResponse(
                    lote_id=request.lote_id,
                    estado=carga_existente.estado,
                    total_registros=carga_existente.total_registros,
                    registros_incorporados=carga_existente.registros_incorporados,
                    registros_actualizados=carga_existente.registros_actualizados,
                    registros_rechazados=carga_existente.registros_rechazados,
                    rechazos=[
                        RechazoParticipacionDetail(
                            dni=r.dni, field=r.campo, codigo=r.codigo, motivo=r.motivo
                        )
                        for r in rechazos_prev
                    ],
                    mensaje="Lote ya recibido previamente con idéntico contenido (respuesta idempotente).",
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "CONFLICT",
                        "message": "Ya existe un lote con ese lote_id pero con contenido diferente.",
                        "field": "lote_id",
                    }
                },
            )

        ahora = datetime.now(UTC)
        carga = CargaParticipacionDB(
            id=uuid.uuid4(),
            club_id=club.id,
            tipo=TipoParticipacion.ACTIVIDADES,
            origen=OrigenCarga.CLUB,
            carga_id_externo=request.lote_id,
            estado=EstadoCargaParticipacion.PROCESSING,
            total_paginas=1,
            paginas_recibidas=1,
            total_registros=len(request.registros),
            registros_incorporados=0,
            registros_actualizados=0,
            registros_rechazados=0,
            payload_hash=payload_hash,
            desde=request.desde,
            hasta=request.hasta,
            creado_en=ahora,
            actualizado_en=ahora,
        )
        db.add(carga)
        db.flush()

        # 4. Validar registros y aplicar
        dnis_lote = [r.dni.strip() for r in request.registros]
        socios_db = (
            db.query(Socio)
            .filter(
                Socio.club_id == club.id,
                Socio.dni.in_(dnis_lote),
            )
            .all()
        )
        socios_validos = {s.dni for s in socios_db}

        rechazos: list[CargaParticipacionRechazoDB] = []
        incorporados = 0
        actualizados = 0

        for idx, reg in enumerate(request.registros, start=1):
            dni_clean = reg.dni.strip()

            # Tipo válido
            if reg.tipo not in ("deporte_federado", "subcomision"):
                rechazos.append(
                    CargaParticipacionRechazoDB(
                        id=uuid.uuid4(),
                        carga_id=carga.id,
                        dni=dni_clean,
                        campo="tipo",
                        codigo="INVALID_TIPO",
                        motivo="El tipo debe ser 'deporte_federado' o 'subcomision'.",
                        fila=idx,
                    )
                )
                continue

            # Rango de fechas
            if reg.fecha_hasta < reg.fecha_desde:
                rechazos.append(
                    CargaParticipacionRechazoDB(
                        id=uuid.uuid4(),
                        carga_id=carga.id,
                        dni=dni_clean,
                        campo="fecha_hasta",
                        codigo="INVALID_DATE_RANGE",
                        motivo="La fecha de fin no puede ser anterior a la de inicio.",
                        fila=idx,
                    )
                )
                continue

            # Fechas no futuras
            if reg.fecha_desde > hoy or reg.fecha_hasta > hoy:
                rechazos.append(
                    CargaParticipacionRechazoDB(
                        id=uuid.uuid4(),
                        carga_id=carga.id,
                        dni=dni_clean,
                        campo="fecha_desde",
                        codigo="FUTURE_DATE",
                        motivo="Las fechas de actividad no pueden situarse en el futuro.",
                        fila=idx,
                    )
                )
                continue

            # Existencia de socio
            if dni_clean not in socios_validos:
                rechazos.append(
                    CargaParticipacionRechazoDB(
                        id=uuid.uuid4(),
                        carga_id=carga.id,
                        dni=dni_clean,
                        campo="dni",
                        codigo="SOCIO_NOT_FOUND",
                        motivo="El socio no existe en el padrón del club.",
                        fila=idx,
                    )
                )
                continue

            # Upsert idempotente por (club_id, dni, tipo, fecha_desde)
            actividad_existente = (
                db.query(ActividadRecurrenteDB)
                .filter(
                    ActividadRecurrenteDB.club_id == club.id,
                    ActividadRecurrenteDB.dni == dni_clean,
                    ActividadRecurrenteDB.tipo == reg.tipo,
                    ActividadRecurrenteDB.fecha_desde == reg.fecha_desde,
                )
                .first()
            )

            if actividad_existente:
                actividad_existente.fecha_hasta = reg.fecha_hasta
                actividad_existente.carga_id = carga.id
                actividad_existente.actualizado_en = ahora
                actualizados += 1
            else:
                nueva_act = ActividadRecurrenteDB(
                    id=uuid.uuid4(),
                    club_id=club.id,
                    dni=dni_clean,
                    tipo=reg.tipo,
                    fecha_desde=reg.fecha_desde,
                    fecha_hasta=reg.fecha_hasta,
                    carga_id=carga.id,
                    creado_en=ahora,
                    actualizado_en=ahora,
                )
                db.add(nueva_act)
                incorporados += 1

        db.add_all(rechazos)

        carga.registros_incorporados = incorporados
        carga.registros_actualizados = actualizados
        carga.registros_rechazados = len(rechazos)
        carga.estado = EstadoCargaParticipacion.SUCCESSFUL
        carga.actualizado_en = ahora

        db.commit()

        return CargaActividadesResponse(
            lote_id=request.lote_id,
            estado=EstadoCargaParticipacion.SUCCESSFUL,
            total_registros=len(request.registros),
            registros_incorporados=incorporados,
            registros_actualizados=actualizados,
            registros_rechazados=len(rechazos),
            rechazos=[
                RechazoParticipacionDetail(
                    dni=r.dni, field=r.campo, codigo=r.codigo, motivo=r.motivo
                )
                for r in rechazos
            ],
            mensaje="Lote de actividades procesado y aplicado con éxito.",
        )

    # ==========================================================================
    # CONSULTA DE ESTADO DE CARGAS
    # ==========================================================================

    @classmethod
    def obtener_estado_carga(
        cls, club: Club, carga_id: str, db: Session
    ) -> CargaParticipacionStatusResponse:
        carga = (
            db.query(CargaParticipacionDB)
            .filter(
                CargaParticipacionDB.club_id == club.id,
                CargaParticipacionDB.carga_id_externo == carga_id,
            )
            .first()
        )
        if not carga:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "NOT_FOUND",
                        "message": f"No se encontró la carga de participación con ID '{carga_id}'.",
                        "field": "carga_id",
                    }
                },
            )

        rechazos = (
            db.query(CargaParticipacionRechazoDB)
            .filter(CargaParticipacionRechazoDB.carga_id == carga.id)
            .all()
        )

        return CargaParticipacionStatusResponse(
            carga_id=carga.carga_id_externo,
            tipo=carga.tipo,
            origen=carga.origen,
            evento_id_externo=carga.evento_id_externo,
            estado=carga.estado,
            total_paginas=carga.total_paginas,
            paginas_recibidas=carga.paginas_recibidas,
            total_registros=carga.total_registros,
            registros_incorporados=carga.registros_incorporados,
            registros_actualizados=carga.registros_actualizados,
            registros_rechazados=carga.registros_rechazados,
            desde=carga.desde,
            hasta=carga.hasta,
            creado_en=carga.creado_en,
            actualizado_en=carga.actualizado_en,
            rechazos=[
                RechazoParticipacionDetail(
                    dni=r.dni,
                    field=r.campo,
                    codigo=r.codigo,
                    motivo=r.motivo,
                    fila=r.fila,
                )
                for r in rechazos
            ],
            motivo_fallo=carga.motivo_fallo,
        )

    # ==========================================================================
    # ADMINISTRACIÓN (CSV FALLBACK, APROBACIONES, EVENTOS ELEGIBLES)
    # ==========================================================================

    @classmethod
    def listar_eventos_elegibles_para_asistencia(
        cls, club_id: uuid.UUID, db: Session
    ) -> list[EventoElegibleAsistenciaResponse]:
        ahora = datetime.now(UTC)
        eventos_visibles = (
            db.query(EventoVisibleDB).filter(EventoVisibleDB.club_id == club_id).all()
        )
        eventos_historicos = (
            db.query(EventoPendienteDB)
            .filter(
                EventoPendienteDB.club_id == club_id,
                EventoPendienteDB.es_historico == True,
            )
            .all()
        )
        todos = sorted(
            list(eventos_visibles) + list(eventos_historicos),
            key=lambda e: (
                e.fecha_hora
                if e.fecha_hora.tzinfo
                else e.fecha_hora.replace(tzinfo=UTC)
            ),
            reverse=True,
        )

        resultado: list[EventoElegibleAsistenciaResponse] = []
        for ev in todos:
            fh = (
                ev.fecha_hora
                if ev.fecha_hora.tzinfo
                else ev.fecha_hora.replace(tzinfo=UTC)
            )
            if fh <= ahora:
                # Comprobar si tiene asistencia previa
                carga_previa = (
                    db.query(CargaParticipacionDB)
                    .filter(
                        CargaParticipacionDB.club_id == club_id,
                        CargaParticipacionDB.tipo == TipoParticipacion.ASISTENCIA,
                        CargaParticipacionDB.evento_id_externo == ev.id_externo,
                        CargaParticipacionDB.estado
                        == EstadoCargaParticipacion.SUCCESSFUL,
                    )
                    .order_by(CargaParticipacionDB.actualizado_en.desc())
                    .first()
                )

                info_previa = None
                if carga_previa:
                    info_previa = {
                        "carga_id": carga_previa.carga_id_externo,
                        "fecha": carga_previa.actualizado_en.isoformat(),
                        "origen": carga_previa.origen,
                        "total_registros": carga_previa.registros_incorporados,
                    }

                resultado.append(
                    EventoElegibleAsistenciaResponse(
                        id_interno=ev.id_interno,
                        id_externo=ev.id_externo,
                        titulo=ev.titulo,
                        tipo=ev.tipo.value
                        if hasattr(ev.tipo, "value")
                        else str(ev.tipo),
                        fecha_hora=ev.fecha_hora,
                        lugar=ev.lugar,
                        tiene_asistencia_previa=carga_previa is not None,
                        asistencia_previa_info=info_previa,
                    )
                )

        return resultado

    @classmethod
    def procesar_csv_asistencia(
        cls,
        club_id: uuid.UUID,
        evento_id_externo: str,
        contenido_csv: str,
        admin: User,
        confirm_replace: bool,
        db: Session,
    ) -> UploadCSVResponse:
        # 1. Validar evento
        evento = cls._verificar_evento_elegible(club_id, evento_id_externo, db)
        fecha_evento_esperada = (
            evento.fecha_hora.date()
            if hasattr(evento.fecha_hora, "date")
            else datetime.fromisoformat(str(evento.fecha_hora)).date()
        )

        # 2. Parsear CSV
        reader = csv.DictReader(io.StringIO(contenido_csv))
        if not reader.fieldnames:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "EMPTY_FILE",
                        "message": "El archivo CSV está vacío.",
                    }
                },
            )

        headers = [h.strip().lower() for h in reader.fieldnames]
        if "dni" not in headers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "INVALID_CSV_HEADER",
                        "message": "Falta la columna obligatoria 'dni' en la cabecera del CSV.",
                        "field": "file",
                    }
                },
            )

        filas = list(reader)
        if not filas:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "EMPTY_FILE",
                        "message": "El archivo CSV no contiene filas de datos.",
                    }
                },
            )

        if len(filas) > 100000:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={
                    "error": {
                        "code": "FILE_TOO_LARGE",
                        "message": "El archivo supera el límite de 100.000 filas.",
                        "field": "file",
                    }
                },
            )

        # 3. Validar consistencia de fecha_evento si está presente en el CSV
        has_fecha_col = "fecha_evento" in headers
        for idx, fila in enumerate(filas, start=2):
            if has_fecha_col and fila.get("fecha_evento"):
                fecha_str = fila["fecha_evento"].strip()
                try:
                    fecha_fila = datetime.strptime(fecha_str, "%Y-%m-%d").date()
                    if fecha_fila != fecha_evento_esperada:
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail={
                                "error": {
                                    "code": "EVENT_DATE_MISMATCH",
                                    "message": f"La fecha en el archivo ({fecha_fila}) no coincide con la fecha del evento seleccionado ({fecha_evento_esperada}).",
                                    "field": "fecha_evento",
                                }
                            },
                        )
                except ValueError:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail={
                            "error": {
                                "code": "INVALID_DATE_FORMAT",
                                "message": f"Formato inválido de fecha en fila {idx}: debe ser YYYY-MM-DD.",
                                "field": "fecha_evento",
                            }
                        },
                    )

        # 4. Comprobar si ya existe asistencia previa para requerir confirmación
        asistencia_previa = (
            db.query(CargaParticipacionDB)
            .filter(
                CargaParticipacionDB.club_id == club_id,
                CargaParticipacionDB.tipo == TipoParticipacion.ASISTENCIA,
                CargaParticipacionDB.evento_id_externo == evento_id_externo,
                CargaParticipacionDB.estado == EstadoCargaParticipacion.SUCCESSFUL,
            )
            .order_by(CargaParticipacionDB.actualizado_en.desc())
            .first()
        )

        if asistencia_previa and not confirm_replace:
            # Retornar advertencia con metadata para que el Admin confirme
            prev_info = CargaPreviaInfo(
                carga_id=asistencia_previa.carga_id_externo,
                fecha=asistencia_previa.actualizado_en,
                origen=asistencia_previa.origen,
                total_registros=asistencia_previa.registros_incorporados,
            )
            return UploadCSVResponse(
                carga_id="",
                tipo=TipoParticipacion.ASISTENCIA,
                evento_id_externo=evento_id_externo,
                estado="requires_confirmation",
                total_registros=len(filas),
                registros_incorporados=0,
                registros_actualizados=0,
                registros_rechazados=0,
                requiere_confirmacion_reemplazo=True,
                carga_previa=prev_info,
                mensaje="El evento ya posee asistencia previa. Debe confirmar el reemplazo explícitamente.",
            )

        # 5. Validar filas una a una
        dnis_csv = [f["dni"].strip() for f in filas if f.get("dni")]
        socios_db = (
            db.query(Socio)
            .filter(Socio.club_id == club_id, Socio.dni.in_(dnis_csv))
            .all()
        )
        socios_map = {s.dni: s for s in socios_db}

        dnis_vistos = set()
        rechazos: list[dict[str, Any]] = []
        validos: list[dict[str, str | None]] = []

        for idx, f in enumerate(filas, start=2):
            dni = f.get("dni", "").strip()
            num_socio = (
                f.get("numero_socio", "").strip() if f.get("numero_socio") else None
            )

            if not dni:
                rechazos.append(
                    {
                        "dni": None,
                        "campo": "dni",
                        "codigo": "INVALID_RECORD_FORMAT",
                        "motivo": "DNI vacío.",
                        "fila": idx,
                    }
                )
                continue

            if dni in dnis_vistos:
                rechazos.append(
                    {
                        "dni": dni,
                        "campo": "dni",
                        "codigo": "DUPLICATE_DNI_PAGE",
                        "motivo": "DNI repetido en el archivo.",
                        "fila": idx,
                    }
                )
                continue
            dnis_vistos.add(dni)

            socio = socios_map.get(dni)
            if not socio:
                rechazos.append(
                    {
                        "dni": dni,
                        "campo": "dni",
                        "codigo": "SOCIO_NOT_FOUND",
                        "motivo": "El socio no pertenece al club.",
                        "fila": idx,
                    }
                )
                continue

            if num_socio and socio.numero_socio and socio.numero_socio != num_socio:
                rechazos.append(
                    {
                        "dni": dni,
                        "campo": "numero_socio",
                        "codigo": "NUMERO_SOCIO_MISMATCH",
                        "motivo": "El número de socio no coincide con el DNI.",
                        "fila": idx,
                    }
                )
                continue

            validos.append({"dni": dni, "numero_socio": num_socio})

        # 6. Regla del 5% de tolerancia
        tasa_error = len(rechazos) / len(filas)
        if tasa_error > 0.05:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "error": {
                        "code": "TOLERANCE_EXCEEDED",
                        "message": f"El archivo supera la tolerancia máxima de error del 5% ({tasa_error * 100:.1f}% de rechazos). Nada fue aplicado.",
                        "field": "file",
                    }
                },
            )

        # 7. Crear carga y aplicar atómicamente
        ahora = datetime.now(UTC)
        carga_uuid = uuid.uuid4()
        carga_id_ext = (
            f"csv-att-{ahora.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        )

        carga = CargaParticipacionDB(
            id=carga_uuid,
            club_id=club_id,
            tipo=TipoParticipacion.ASISTENCIA,
            origen=OrigenCarga.FILE,
            carga_id_externo=carga_id_ext,
            evento_id_externo=evento_id_externo,
            estado=EstadoCargaParticipacion.SUCCESSFUL,
            total_paginas=1,
            paginas_recibidas=1,
            total_registros=len(filas),
            registros_incorporados=len(validos),
            registros_actualizados=0,
            registros_rechazados=len(rechazos),
            usuario_id=admin.id,
            creado_en=ahora,
            actualizado_en=ahora,
        )
        db.add(carga)
        db.flush()

        # Si reemplaza carga previa
        if asistencia_previa:
            asistencia_previa.estado = EstadoCargaParticipacion.REPLACED
            # Borrar asistencias anteriores
            db.query(AsistenciaDB).filter(
                AsistenciaDB.club_id == club_id,
                AsistenciaDB.evento_id_externo == evento_id_externo,
            ).delete()

        # Insertar asistencias nuevas
        nuevas_asistencias = [
            AsistenciaDB(
                id=uuid.uuid4(),
                club_id=club_id,
                evento_id_externo=evento_id_externo,
                dni=v["dni"],
                numero_socio=v["numero_socio"],
                carga_id=carga_uuid,
                creado_en=ahora,
            )
            for v in validos
        ]
        db.add_all(nuevas_asistencias)

        # Guardar rechazos
        rechazos_db = [
            CargaParticipacionRechazoDB(
                id=uuid.uuid4(),
                carga_id=carga_uuid,
                dni=r["dni"],
                campo=r["campo"],
                codigo=r["codigo"],
                motivo=r["motivo"],
                fila=r["fila"],
            )
            for r in rechazos
        ]
        db.add_all(rechazos_db)

        # Auditoría
        record(
            db,
            "attendance.uploaded_csv",
            actor_id=admin.id,
            entity="event",
            entity_id=evento_id_externo,
            carga_id=carga_id_ext,
            incorporated=len(validos),
            rejected=len(rechazos),
            replaced=asistencia_previa is not None,
        )

        db.commit()

        return UploadCSVResponse(
            carga_id=carga_id_ext,
            tipo=TipoParticipacion.ASISTENCIA,
            evento_id_externo=evento_id_externo,
            estado=EstadoCargaParticipacion.SUCCESSFUL,
            total_registros=len(filas),
            registros_incorporados=len(validos),
            registros_actualizados=0,
            registros_rechazados=len(rechazos),
            rechazos=[
                RechazoParticipacionDetail(
                    dni=r["dni"],
                    field=r["campo"],
                    codigo=r["codigo"],
                    motivo=r["motivo"],
                    fila=r["fila"],
                )
                for r in rechazos
            ],
            mensaje="Archivo CSV de asistencia procesado y aplicado con éxito.",
        )

    @classmethod
    def procesar_csv_actividades(
        cls,
        club_id: uuid.UUID,
        contenido_csv: str,
        admin: User,
        db: Session,
    ) -> UploadCSVResponse:
        hoy = date.today()
        ahora = datetime.now(UTC)

        reader = csv.DictReader(io.StringIO(contenido_csv))
        if not reader.fieldnames:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "EMPTY_FILE",
                        "message": "El archivo CSV está vacío.",
                    }
                },
            )

        headers = [h.strip().lower() for h in reader.fieldnames]
        required = {"dni", "tipo", "fecha_desde", "fecha_hasta"}
        if not required.issubset(set(headers)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "INVALID_CSV_HEADER",
                        "message": f"Faltan columnas obligatorias en el CSV: {required - set(headers)}",
                        "field": "file",
                    }
                },
            )

        filas = list(reader)
        if not filas:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "EMPTY_FILE",
                        "message": "El archivo CSV no contiene filas de datos.",
                    }
                },
            )

        if len(filas) > 100000:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={
                    "error": {
                        "code": "FILE_TOO_LARGE",
                        "message": "El archivo supera el límite de 100.000 filas.",
                        "field": "file",
                    }
                },
            )

        dnis_csv = [f["dni"].strip() for f in filas if f.get("dni")]
        socios_db = (
            db.query(Socio)
            .filter(Socio.club_id == club_id, Socio.dni.in_(dnis_csv))
            .all()
        )
        socios_validos = {s.dni for s in socios_db}

        rechazos: list[dict[str, Any]] = []
        validos: list[dict[str, Any]] = []

        for idx, f in enumerate(filas, start=2):
            dni = f.get("dni", "").strip()
            tipo = f.get("tipo", "").strip()
            fd_str = f.get("fecha_desde", "").strip()
            fh_str = f.get("fecha_hasta", "").strip()

            if not dni or not tipo or not fd_str or not fh_str:
                rechazos.append(
                    {
                        "dni": dni,
                        "campo": None,
                        "codigo": "INVALID_RECORD_FORMAT",
                        "motivo": "Faltan campos obligatorios.",
                        "fila": idx,
                    }
                )
                continue

            if tipo not in ("deporte_federado", "subcomision"):
                rechazos.append(
                    {
                        "dni": dni,
                        "campo": "tipo",
                        "codigo": "INVALID_TIPO",
                        "motivo": "El tipo debe ser 'deporte_federado' o 'subcomision'.",
                        "fila": idx,
                    }
                )
                continue

            try:
                fd = datetime.strptime(fd_str, "%Y-%m-%d").date()
                fh = datetime.strptime(fh_str, "%Y-%m-%d").date()
            except ValueError:
                rechazos.append(
                    {
                        "dni": dni,
                        "campo": "fecha_desde",
                        "codigo": "INVALID_DATE_FORMAT",
                        "motivo": "Formato de fecha inválido (debe ser YYYY-MM-DD).",
                        "fila": idx,
                    }
                )
                continue

            if fh < fd:
                rechazos.append(
                    {
                        "dni": dni,
                        "campo": "fecha_hasta",
                        "codigo": "INVALID_DATE_RANGE",
                        "motivo": "fecha_hasta no puede ser anterior a fecha_desde.",
                        "fila": idx,
                    }
                )
                continue

            if fd > hoy or fh > hoy:
                rechazos.append(
                    {
                        "dni": dni,
                        "campo": "fecha_desde",
                        "codigo": "FUTURE_DATE",
                        "motivo": "Las fechas no pueden ser futuras.",
                        "fila": idx,
                    }
                )
                continue

            if dni not in socios_validos:
                rechazos.append(
                    {
                        "dni": dni,
                        "campo": "dni",
                        "codigo": "SOCIO_NOT_FOUND",
                        "motivo": "El socio no pertenece al club.",
                        "fila": idx,
                    }
                )
                continue

            validos.append(
                {"dni": dni, "tipo": tipo, "fecha_desde": fd, "fecha_hasta": fh}
            )

        # Regla del 5%
        tasa_error = len(rechazos) / len(filas)
        if tasa_error > 0.05:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "error": {
                        "code": "TOLERANCE_EXCEEDED",
                        "message": f"El archivo supera la tolerancia máxima de error del 5% ({tasa_error * 100:.1f}% de rechazos). Nada fue aplicado.",
                        "field": "file",
                    }
                },
            )

        carga_uuid = uuid.uuid4()
        carga_id_ext = (
            f"csv-act-{ahora.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        )

        carga = CargaParticipacionDB(
            id=carga_uuid,
            club_id=club_id,
            tipo=TipoParticipacion.ACTIVIDADES,
            origen=OrigenCarga.FILE,
            carga_id_externo=carga_id_ext,
            estado=EstadoCargaParticipacion.SUCCESSFUL,
            total_paginas=1,
            paginas_recibidas=1,
            total_registros=len(filas),
            registros_incorporados=0,
            registros_actualizados=0,
            registros_rechazados=len(rechazos),
            usuario_id=admin.id,
            creado_en=ahora,
            actualizado_en=ahora,
        )
        db.add(carga)
        db.flush()

        incorporados = 0
        actualizados = 0

        for v in validos:
            act_db = (
                db.query(ActividadRecurrenteDB)
                .filter(
                    ActividadRecurrenteDB.club_id == club_id,
                    ActividadRecurrenteDB.dni == v["dni"],
                    ActividadRecurrenteDB.tipo == v["tipo"],
                    ActividadRecurrenteDB.fecha_desde == v["fecha_desde"],
                )
                .first()
            )
            if act_db:
                act_db.fecha_hasta = v["fecha_hasta"]
                act_db.carga_id = carga_uuid
                act_db.actualizado_en = ahora
                actualizados += 1
            else:
                nueva = ActividadRecurrenteDB(
                    id=uuid.uuid4(),
                    club_id=club_id,
                    dni=v["dni"],
                    tipo=v["tipo"],
                    fecha_desde=v["fecha_desde"],
                    fecha_hasta=v["fecha_hasta"],
                    carga_id=carga_uuid,
                    creado_en=ahora,
                    actualizado_en=ahora,
                )
                db.add(nueva)
                incorporados += 1

        carga.registros_incorporados = incorporados
        carga.registros_actualizados = actualizados

        rechazos_db = [
            CargaParticipacionRechazoDB(
                id=uuid.uuid4(),
                carga_id=carga_uuid,
                dni=r["dni"],
                campo=r["campo"],
                codigo=r["codigo"],
                motivo=r["motivo"],
                fila=r["fila"],
            )
            for r in rechazos
        ]
        db.add_all(rechazos_db)

        record(
            db,
            "activities.uploaded_csv",
            actor_id=admin.id,
            entity="club",
            entity_id=str(club_id),
            carga_id=carga_id_ext,
            incorporated=incorporados,
            updated=actualizados,
            rejected=len(rechazos),
        )

        db.commit()

        return UploadCSVResponse(
            carga_id=carga_id_ext,
            tipo=TipoParticipacion.ACTIVIDADES,
            estado=EstadoCargaParticipacion.SUCCESSFUL,
            total_registros=len(filas),
            registros_incorporados=incorporados,
            registros_actualizados=actualizados,
            registros_rechazados=len(rechazos),
            rechazos=[
                RechazoParticipacionDetail(
                    dni=r["dni"],
                    field=r["campo"],
                    codigo=r["codigo"],
                    motivo=r["motivo"],
                    fila=r["fila"],
                )
                for r in rechazos
            ],
            mensaje="Archivo CSV de actividades procesado y aplicado con éxito.",
        )

    # ==========================================================================
    # APROBACIÓN O RECHAZO DE REEMPLAZOS POR EL ADMIN
    # ==========================================================================

    @classmethod
    def listar_cargas_pendientes_aprobacion(
        cls, club_id: uuid.UUID, db: Session
    ) -> list[CargaPendienteAprobacionResponse]:
        pendientes = (
            db.query(CargaParticipacionDB)
            .filter(
                CargaParticipacionDB.club_id == club_id,
                CargaParticipacionDB.estado
                == EstadoCargaParticipacion.PENDING_APPROVAL,
            )
            .order_by(CargaParticipacionDB.creado_en.asc())
            .all()
        )

        res: list[CargaPendienteAprobacionResponse] = []
        for p in pendientes:
            evento = (
                db.query(EventoVisibleDB)
                .filter(
                    EventoVisibleDB.club_id == club_id,
                    EventoVisibleDB.id_externo == p.evento_id_externo,
                )
                .first()
            )

            # Contar válidos en staging
            validos_staging = (
                db.query(AsistenciaStagingDB)
                .filter(AsistenciaStagingDB.carga_id == p.id)
                .count()
            )

            # Carga previa activa
            previa = (
                db.query(CargaParticipacionDB)
                .filter(
                    CargaParticipacionDB.club_id == club_id,
                    CargaParticipacionDB.tipo == TipoParticipacion.ASISTENCIA,
                    CargaParticipacionDB.evento_id_externo == p.evento_id_externo,
                    CargaParticipacionDB.estado == EstadoCargaParticipacion.SUCCESSFUL,
                )
                .order_by(CargaParticipacionDB.actualizado_en.desc())
                .first()
            )

            previa_info = None
            if previa:
                previa_info = CargaPreviaInfo(
                    carga_id=previa.carga_id_externo,
                    fecha=previa.actualizado_en,
                    origen=previa.origen,
                    total_registros=previa.registros_incorporados,
                )

            res.append(
                CargaPendienteAprobacionResponse(
                    carga_id=p.carga_id_externo,
                    evento_id_externo=p.evento_id_externo or "",
                    evento_titulo=evento.titulo if evento else None,
                    fecha_evento=evento.fecha_hora if evento else None,
                    origen=p.origen,
                    registros_a_incorporar=validos_staging,
                    creado_en=p.creado_en,
                    carga_previa=previa_info,
                )
            )

        return res

    @classmethod
    def aprobar_reemplazo(
        cls, carga_id: str, admin: User, club_id: uuid.UUID, db: Session
    ) -> AprobacionAccionResponse:
        carga = (
            db.query(CargaParticipacionDB)
            .filter(
                CargaParticipacionDB.club_id == club_id,
                CargaParticipacionDB.carga_id_externo == carga_id,
                CargaParticipacionDB.estado
                == EstadoCargaParticipacion.PENDING_APPROVAL,
            )
            .first()
        )
        if not carga:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "NOT_FOUND",
                        "message": "No se encontró carga pendiente de aprobación con ese ID.",
                    }
                },
            )

        ahora = datetime.now(UTC)

        # 1. Marcar cargas anteriores como 'replaced'
        previas = (
            db.query(CargaParticipacionDB)
            .filter(
                CargaParticipacionDB.club_id == club_id,
                CargaParticipacionDB.tipo == TipoParticipacion.ASISTENCIA,
                CargaParticipacionDB.evento_id_externo == carga.evento_id_externo,
                CargaParticipacionDB.estado == EstadoCargaParticipacion.SUCCESSFUL,
            )
            .all()
        )
        for prev in previas:
            prev.estado = EstadoCargaParticipacion.REPLACED
            prev.actualizado_en = ahora

        # 2. Borrar asistencias anteriores
        db.query(AsistenciaDB).filter(
            AsistenciaDB.club_id == club_id,
            AsistenciaDB.evento_id_externo == carga.evento_id_externo,
        ).delete()

        # 3. Traspasar de staging a asistencias
        stagings = (
            db.query(AsistenciaStagingDB)
            .filter(AsistenciaStagingDB.carga_id == carga.id)
            .all()
        )
        nuevas_asistencias = [
            AsistenciaDB(
                id=uuid.uuid4(),
                club_id=club_id,
                evento_id_externo=carga.evento_id_externo or "",
                dni=st.dni,
                numero_socio=st.numero_socio,
                carga_id=carga.id,
                creado_en=ahora,
            )
            for st in stagings
        ]
        db.add_all(nuevas_asistencias)
        total_incorporados = len(nuevas_asistencias)

        # 4. Limpiar staging
        db.query(AsistenciaStagingDB).filter(
            AsistenciaStagingDB.carga_id == carga.id
        ).delete()

        # 5. Marcar nueva carga como successful
        carga.estado = EstadoCargaParticipacion.SUCCESSFUL
        carga.registros_incorporados = total_incorporados
        carga.aprobado_por_id = admin.id
        carga.actualizado_en = ahora

        record(
            db,
            "attendance.replacement_approved",
            actor_id=admin.id,
            entity="event",
            entity_id=carga.evento_id_externo or "",
            carga_id=carga.carga_id_externo,
            incorporated=total_incorporados,
        )

        db.commit()

        return AprobacionAccionResponse(
            carga_id=carga.carga_id_externo,
            evento_id_externo=carga.evento_id_externo,
            estado=EstadoCargaParticipacion.SUCCESSFUL,
            mensaje="Reemplazo de asistencia aprobado y aplicado con éxito.",
        )

    @classmethod
    def rechazar_reemplazo(
        cls,
        carga_id: str,
        admin: User,
        club_id: uuid.UUID,
        motivo: str | None,
        db: Session,
    ) -> AprobacionAccionResponse:
        carga = (
            db.query(CargaParticipacionDB)
            .filter(
                CargaParticipacionDB.club_id == club_id,
                CargaParticipacionDB.carga_id_externo == carga_id,
                CargaParticipacionDB.estado
                == EstadoCargaParticipacion.PENDING_APPROVAL,
            )
            .first()
        )
        if not carga:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "NOT_FOUND",
                        "message": "No se encontró carga pendiente de aprobación con ese ID.",
                    }
                },
            )

        ahora = datetime.now(UTC)

        # 1. Limpiar staging
        db.query(AsistenciaStagingDB).filter(
            AsistenciaStagingDB.carga_id == carga.id
        ).delete()

        # 2. Marcar carga como rejected
        carga.estado = EstadoCargaParticipacion.REJECTED
        carga.motivo_fallo = motivo or "Rechazado por el Administrador"
        carga.aprobado_por_id = admin.id
        carga.actualizado_en = ahora

        record(
            db,
            "attendance.replacement_rejected",
            actor_id=admin.id,
            entity="event",
            entity_id=carga.evento_id_externo or "",
            carga_id=carga.carga_id_externo,
            reason=motivo,
        )

        db.commit()

        return AprobacionAccionResponse(
            carga_id=carga.carga_id_externo,
            evento_id_externo=carga.evento_id_externo,
            estado=EstadoCargaParticipacion.REJECTED,
            mensaje="Carga de reemplazo rechazada. La asistencia previa se mantiene intacta.",
        )

    @classmethod
    def generar_csv_rechazos(
        cls, carga_id_externo: str, club_id: uuid.UUID, db: Session
    ) -> str:
        carga = (
            db.query(CargaParticipacionDB)
            .filter(
                CargaParticipacionDB.club_id == club_id,
                CargaParticipacionDB.carga_id_externo == carga_id_externo,
            )
            .first()
        )
        if not carga:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "NOT_FOUND",
                        "message": "No se encontró la carga especificada.",
                    }
                },
            )

        rechazos = (
            db.query(CargaParticipacionRechazoDB)
            .filter(CargaParticipacionRechazoDB.carga_id == carga.id)
            .order_by(CargaParticipacionRechazoDB.fila.asc().nulls_last())
            .all()
        )

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["fila", "dni", "campo", "codigo", "motivo"])
        for r in rechazos:
            writer.writerow(
                [r.fila or "", r.dni or "", r.campo or "", r.codigo, r.motivo]
            )

        return output.getvalue()
