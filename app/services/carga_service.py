import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    Club,
    Socio,
    SocioCarga,
    SocioCargaPagina,
    SocioCargaRechazo,
    SocioStagingCompleta,
)
from ..schemas import (
    CargaCompletaRequest,
    CargaCompletaResponse,
    CargaIncrementalRequest,
    CargaIncrementalResponse,
    CargaStatusResponse,
    FreshnessResponse,
    RechazoDetail,
    SocioPayload,
)


def _compute_hash(data: Any) -> str:
    """Calcula hash SHA-256 canónico para verificar idempotencia."""
    serialized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class CargaService:
    @staticmethod
    def procesar_carga_completa(
        club: Club, request: CargaCompletaRequest, db: Session
    ) -> CargaCompletaResponse:
        """
        Procesa una página de un snapshot completo.
        - Idempotencia: reenvío de misma página con igual contenido no duplica.
        - Si el contenido difiere para misma página/carga, retorna 409 Conflict.
        - Valida cada socio individualmente: los válidos van a staging, los inválidos a rechazos.
        - Si es la última página, ejecuta control de integridad (ej: DNIs duplicados entre páginas)
          y activa atómicamente el snapshot en la tabla de socios.
        """
        if request.pagina > request.total_paginas:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "BAD_REQUEST",
                        "message": f"La página {request.pagina} excede el total declarado de {request.total_paginas}.",
                        "field": "pagina",
                    }
                },
            )

        page_hash = _compute_hash(request.socios)

        # 1. Obtener o crear la entidad de carga
        carga = (
            db.query(SocioCarga)
            .filter(
                SocioCarga.club_id == club.id, SocioCarga.carga_id == request.carga_id
            )
            .first()
        )

        if not carga:
            carga = SocioCarga(
                id=uuid4(),
                club_id=club.id,
                carga_id=request.carga_id,
                tipo="completa",
                estado="recibiendo",
                total_paginas=request.total_paginas,
                paginas_recibidas=0,
                iniciado_en=datetime.now(UTC),
            )
            db.add(carga)
            db.flush()
        else:
            # Validar consistencia con la carga previa
            if carga.tipo != "completa" or carga.total_paginas != request.total_paginas:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": {
                            "code": "CONFLICT",
                            "message": "Inconsistencia de configuración estructural con la carga existente.",
                        }
                    },
                )

            if carga.estado == "exitosa":
                # Ya finalizó. Verificar si esta página fue recibida con el mismo hash
                pagina_existente = (
                    db.query(SocioCargaPagina)
                    .filter_by(carga_id_uuid=carga.id, pagina=request.pagina)
                    .first()
                )
                if pagina_existente and pagina_existente.payload_hash == page_hash:
                    return CargaCompletaResponse(
                        carga_id=carga.carga_id,
                        pagina=request.pagina,
                        total_paginas=carga.total_paginas,
                        estado="exitosa",
                        mensaje="Página ya recibida y snapshot activado previamente (idempotente).",
                        rechazos=[],
                    )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": {
                            "code": "CONFLICT",
                            "message": "La carga ya fue completada exitosamente; no se admiten páginas distintas.",
                        }
                    },
                )

            if carga.estado == "fallida":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": {
                            "code": "CONFLICT",
                            "message": f"La carga falló previamente ({carga.error_mensaje}) y no admite más páginas.",
                        }
                    },
                )

        # 2. Verificar si la página ya fue registrada en esta carga
        pagina_existente = (
            db.query(SocioCargaPagina)
            .filter_by(carga_id_uuid=carga.id, pagina=request.pagina)
            .first()
        )
        if pagina_existente:
            if pagina_existente.payload_hash == page_hash:
                # Idempotente
                return CargaCompletaResponse(
                    carga_id=carga.carga_id,
                    pagina=request.pagina,
                    total_paginas=carga.total_paginas,
                    estado=carga.estado,
                    mensaje=f"Página {request.pagina} ya registrada previamente (idempotente).",
                    rechazos=[],
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": {
                            "code": "CONFLICT",
                            "message": f"Conflicto de contenido: la página {request.pagina} ya fue enviada con otro contenido.",
                        }
                    },
                )

        # 3. Validar registros individuales de la página
        page_rechazos: list[RechazoDetail] = []
        valid_staged: list[SocioStagingCompleta] = []
        staged_dnis_in_page = set()
        staged_ids_in_page = set()

        for idx, item in enumerate(request.socios):
            try:
                socio_parsed = SocioPayload.model_validate(item)
            except ValidationError as e:
                # Error de validación en este registro
                err = e.errors()[0]
                field_name = str(err["loc"][0]) if err.get("loc") else "general"
                msg = err.get("msg", "Error de validación")
                rechazo = RechazoDetail(
                    id_externo=item.get("id_externo")
                    if isinstance(item, dict)
                    else None,
                    field=field_name,
                    codigo="INVALID_RECORD_FORMAT",
                    motivo=msg,
                )
                page_rechazos.append(rechazo)
                db.add(
                    SocioCargaRechazo(
                        id=uuid4(),
                        carga_id_uuid=carga.id,
                        id_externo=rechazo.id_externo,
                        field=rechazo.field,
                        codigo=rechazo.codigo,
                        motivo=rechazo.motivo,
                    )
                )
                continue

            # Chequeo de duplicados dentro de la misma página
            if socio_parsed.dni in staged_dnis_in_page:
                rechazo = RechazoDetail(
                    id_externo=socio_parsed.id_externo,
                    field="dni",
                    codigo="DUPLICATE_DNI_PAGE",
                    motivo=f"El DNI {socio_parsed.dni} se encuentra duplicado en la misma página.",
                )
                page_rechazos.append(rechazo)
                db.add(
                    SocioCargaRechazo(
                        id=uuid4(),
                        carga_id_uuid=carga.id,
                        id_externo=rechazo.id_externo,
                        field=rechazo.field,
                        codigo=rechazo.codigo,
                        motivo=rechazo.motivo,
                    )
                )
                continue

            if socio_parsed.id_externo in staged_ids_in_page:
                rechazo = RechazoDetail(
                    id_externo=socio_parsed.id_externo,
                    field="id_externo",
                    codigo="DUPLICATE_ID_EXTERNO_PAGE",
                    motivo=f"El id_externo {socio_parsed.id_externo} se encuentra duplicado en la misma página.",
                )
                page_rechazos.append(rechazo)
                db.add(
                    SocioCargaRechazo(
                        id=uuid4(),
                        carga_id_uuid=carga.id,
                        id_externo=rechazo.id_externo,
                        field=rechazo.field,
                        codigo=rechazo.codigo,
                        motivo=rechazo.motivo,
                    )
                )
                continue

            staged_dnis_in_page.add(socio_parsed.dni)
            staged_ids_in_page.add(socio_parsed.id_externo)

            # Preparar fila para staging
            staged_row = SocioStagingCompleta(
                id=uuid4(),
                carga_id_uuid=carga.id,
                club_id=club.id,
                pagina=request.pagina,
                id_externo=socio_parsed.id_externo,
                dni=socio_parsed.dni,
                numero_socio=socio_parsed.numero_socio,
                nombre=socio_parsed.nombre,
                fecha_nacimiento=socio_parsed.fecha_nacimiento,
                fecha_alta=socio_parsed.fecha_alta,
                fecha_baja_previa=socio_parsed.fecha_baja_previa,
                estado_cuota=socio_parsed.estado_cuota,
                email=socio_parsed.email,
                distancia_km=socio_parsed.distancia_km,
                localidad=socio_parsed.localidad,
                fecha_modificacion=socio_parsed.fecha_modificacion or datetime.now(UTC),
            )
            valid_staged.append(staged_row)

        # 4. Guardar registros válidos en staging
        if valid_staged:
            db.bulk_save_objects(valid_staged)

        # 5. Registrar la página recibida
        db.add(
            SocioCargaPagina(
                id=uuid4(),
                carga_id_uuid=carga.id,
                pagina=request.pagina,
                payload_hash=page_hash,
                recibido_en=datetime.now(UTC),
            )
        )

        carga.paginas_recibidas += 1
        carga.total_registros += len(request.socios)
        carga.rechazados += len(page_rechazos)
        db.flush()

        # 6. Evaluar si se han recibido todas las páginas
        if carga.paginas_recibidas == carga.total_paginas:
            # Transición a 'procesando' y validaciones finales entre páginas
            carga.estado = "procesando"
            db.flush()

            # Verificación de DNIs duplicados a lo largo de todas las páginas de staging
            dup_dnis = (
                db.query(SocioStagingCompleta.dni, func.count(SocioStagingCompleta.id))
                .filter(SocioStagingCompleta.carga_id_uuid == carga.id)
                .group_by(SocioStagingCompleta.dni)
                .having(func.count(SocioStagingCompleta.id) > 1)
                .all()
            )

            dup_ids = (
                db.query(
                    SocioStagingCompleta.id_externo, func.count(SocioStagingCompleta.id)
                )
                .filter(SocioStagingCompleta.carga_id_uuid == carga.id)
                .group_by(SocioStagingCompleta.id_externo)
                .having(func.count(SocioStagingCompleta.id) > 1)
                .all()
            )

            if dup_dnis or dup_ids:
                # Falla de consistencia final: se rechaza la carga completa
                # manteniendo intacta la última copia válida del padrón.
                carga.estado = "fallida"
                motivos = []
                if dup_dnis:
                    dnis_str = ", ".join([d[0] for d in dup_dnis[:5]])
                    motivos.append(f"DNIs duplicados entre páginas: {dnis_str}")
                    for d in dup_dnis:
                        db.add(
                            SocioCargaRechazo(
                                id=uuid4(),
                                carga_id_uuid=carga.id,
                                field="dni",
                                codigo="DUPLICATE_DNI_ACROSS_PAGES",
                                motivo=f"DNI duplicado entre páginas del snapshot: {d[0]}",
                            )
                        )
                if dup_ids:
                    ids_str = ", ".join([i[0] for i in dup_ids[:5]])
                    motivos.append(f"IDs externos duplicados entre páginas: {ids_str}")

                carga.error_mensaje = "; ".join(motivos)
                carga.completado_en = datetime.now(UTC)
                db.commit()

                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "error": {
                            "code": "CONSISTENCY_CHECK_FAILED",
                            "message": f"El snapshot no superó el control de consistencia final: {carga.error_mensaje}. Se conserva la última versión válida del padrón.",
                        }
                    },
                )

            # 7. Activación atómica del snapshot en una única transacción
            # Obtener registros existentes del club
            existentes = {
                s.id_externo: s
                for s in db.query(Socio).filter(Socio.club_id == club.id).all()
            }

            staged_all = (
                db.query(SocioStagingCompleta)
                .filter(SocioStagingCompleta.carga_id_uuid == carga.id)
                .all()
            )

            staged_externo_ids = set()
            creados_count = 0
            actualizados_count = 0

            for st in staged_all:
                staged_externo_ids.add(st.id_externo)
                if st.id_externo in existentes:
                    # Actualizar socio existente
                    socio = existentes[st.id_externo]
                    socio.dni = st.dni
                    socio.numero_socio = st.numero_socio
                    socio.nombre = st.nombre
                    socio.fecha_nacimiento = st.fecha_nacimiento
                    socio.fecha_alta = st.fecha_alta
                    socio.fecha_baja_previa = st.fecha_baja_previa
                    socio.estado_cuota = st.estado_cuota
                    socio.email = st.email
                    socio.distancia_km = st.distancia_km
                    socio.localidad = st.localidad
                    socio.activo = True
                    socio.fecha_modificacion = st.fecha_modificacion
                    socio.actualizado_en = datetime.now(UTC)
                    actualizados_count += 1
                else:
                    # Crear nuevo socio
                    nuevo_socio = Socio(
                        id=uuid4(),
                        club_id=club.id,
                        id_externo=st.id_externo,
                        dni=st.dni,
                        numero_socio=st.numero_socio,
                        nombre=st.nombre,
                        fecha_nacimiento=st.fecha_nacimiento,
                        fecha_alta=st.fecha_alta,
                        fecha_baja_previa=st.fecha_baja_previa,
                        estado_cuota=st.estado_cuota,
                        email=st.email,
                        distancia_km=st.distancia_km,
                        localidad=st.localidad,
                        activo=True,
                        fecha_modificacion=st.fecha_modificacion,
                        creado_en=datetime.now(UTC),
                        actualizado_en=datetime.now(UTC),
                    )
                    db.add(nuevo_socio)
                    creados_count += 1

            # Desactivar socios no incluidos en el snapshot completo
            desactivados_count = 0
            for ext_id, socio in existentes.items():
                if ext_id not in staged_externo_ids and socio.activo:
                    socio.activo = False
                    socio.actualizado_en = datetime.now(UTC)
                    desactivados_count += 1

            # Limpiar staging de esta carga
            db.query(SocioStagingCompleta).filter(
                SocioStagingCompleta.carga_id_uuid == carga.id
            ).delete()

            # Actualizar contadores y estado final de la carga
            carga.creados = creados_count
            carga.actualizados = actualizados_count
            carga.desactivados = desactivados_count
            carga.estado = "exitosa"
            carga.completado_en = datetime.now(UTC)
            db.commit()

            return CargaCompletaResponse(
                carga_id=carga.carga_id,
                pagina=request.pagina,
                total_paginas=carga.total_paginas,
                estado="exitosa",
                mensaje="Snapshot completo recibido y activado atómicamente con éxito.",
                rechazos=page_rechazos,
            )

        db.commit()
        return CargaCompletaResponse(
            carga_id=carga.carga_id,
            pagina=request.pagina,
            total_paginas=carga.total_paginas,
            estado="recibiendo",
            mensaje=f"Página {request.pagina} de {carga.total_paginas} recibida y alojada en staging.",
            rechazos=page_rechazos,
        )

    @staticmethod
    def procesar_carga_incremental(
        club: Club, request: CargaIncrementalRequest, db: Session
    ) -> CargaIncrementalResponse:
        """
        Aplica cambios incrementales (alta, modificación, baja).
        - Idempotente por lote_id.
        - Los registros válidos se aplican aunque otros fallen en validación.
        - Registros con baja quedan marcados como inactivos, preservando historial.
        """
        payload_hash = _compute_hash(
            {
                "desde": str(request.desde),
                "hasta": str(request.hasta),
                "cambios": [c.model_dump() for c in request.cambios],
            }
        )

        carga_existente = (
            db.query(SocioCarga)
            .filter(
                SocioCarga.club_id == club.id, SocioCarga.carga_id == request.lote_id
            )
            .first()
        )

        if carga_existente:
            if carga_existente.payload_hash == payload_hash:
                # Idempotente: retornar resultado original
                rechazos = (
                    db.query(SocioCargaRechazo)
                    .filter_by(carga_id_uuid=carga_existente.id)
                    .all()
                )
                return CargaIncrementalResponse(
                    lote_id=carga_existente.carga_id,
                    estado=carga_existente.estado,
                    creados=carga_existente.creados,
                    actualizados=carga_existente.actualizados,
                    desactivados=carga_existente.desactivados,
                    rechazados=carga_existente.rechazados,
                    detalles_rechazos=[
                        RechazoDetail(
                            id_externo=r.id_externo,
                            field=r.field,
                            codigo=r.codigo,
                            motivo=r.motivo,
                        )
                        for r in rechazos
                    ],
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": {
                            "code": "CONFLICT",
                            "message": f"El lote '{request.lote_id}' ya fue recibido con contenido diferente.",
                        }
                    },
                )

        # Crear nueva carga incremental
        carga = SocioCarga(
            id=uuid4(),
            club_id=club.id,
            carga_id=request.lote_id,
            tipo="incremental",
            estado="procesando",
            total_paginas=1,
            paginas_recibidas=1,
            desde=request.desde,
            hasta=request.hasta,
            total_registros=len(request.cambios),
            payload_hash=payload_hash,
            iniciado_en=datetime.now(UTC),
        )
        db.add(carga)
        db.flush()

        creados = 0
        actualizados = 0
        desactivados = 0
        rechazos_list: list[RechazoDetail] = []

        for cambio in request.cambios:
            accion = cambio.accion

            if accion in ("alta", "modificacion"):
                if not cambio.socio:
                    rechazo = RechazoDetail(
                        field="socio",
                        codigo="MISSING_SOCIO_DATA",
                        motivo=f"La acción '{accion}' requiere el objeto 'socio'.",
                    )
                    rechazos_list.append(rechazo)
                    db.add(
                        SocioCargaRechazo(
                            id=uuid4(),
                            carga_id_uuid=carga.id,
                            field=rechazo.field,
                            codigo=rechazo.codigo,
                            motivo=rechazo.motivo,
                        )
                    )
                    continue

                try:
                    socio_data = SocioPayload.model_validate(cambio.socio)
                except ValidationError as ve:
                    err = ve.errors()[0]
                    field_name = str(err["loc"][0]) if err.get("loc") else "socio"
                    rechazo = RechazoDetail(
                        id_externo=cambio.socio.get("id_externo")
                        if isinstance(cambio.socio, dict)
                        else None,
                        field=field_name,
                        codigo="INVALID_SOCIO_DATA",
                        motivo=err.get("msg", "Error de validación"),
                    )
                    rechazos_list.append(rechazo)
                    db.add(
                        SocioCargaRechazo(
                            id=uuid4(),
                            carga_id_uuid=carga.id,
                            id_externo=rechazo.id_externo,
                            field=rechazo.field,
                            codigo=rechazo.codigo,
                            motivo=rechazo.motivo,
                        )
                    )
                    continue

                socio_existente = (
                    db.query(Socio)
                    .filter(
                        Socio.club_id == club.id,
                        Socio.id_externo == socio_data.id_externo,
                    )
                    .first()
                )

                if accion == "alta":
                    if socio_existente:
                        # Si ya existe, se actualiza o reporta según contrato
                        socio_existente.dni = socio_data.dni
                        socio_existente.numero_socio = socio_data.numero_socio
                        socio_existente.nombre = socio_data.nombre
                        socio_existente.fecha_nacimiento = socio_data.fecha_nacimiento
                        socio_existente.fecha_alta = socio_data.fecha_alta
                        socio_existente.fecha_baja_previa = socio_data.fecha_baja_previa
                        socio_existente.estado_cuota = socio_data.estado_cuota
                        socio_existente.email = socio_data.email
                        socio_existente.distancia_km = socio_data.distancia_km
                        socio_existente.localidad = socio_data.localidad
                        socio_existente.activo = True
                        socio_existente.fecha_modificacion = (
                            socio_data.fecha_modificacion or datetime.now(UTC)
                        )
                        socio_existente.actualizado_en = datetime.now(UTC)
                        actualizados += 1
                    else:
                        # Verificar colisión de DNI con otro socio
                        colision_dni = (
                            db.query(Socio)
                            .filter(
                                Socio.club_id == club.id,
                                Socio.dni == socio_data.dni,
                            )
                            .first()
                        )
                        if colision_dni:
                            rechazo = RechazoDetail(
                                id_externo=socio_data.id_externo,
                                field="dni",
                                codigo="DUPLICATE_DNI",
                                motivo=f"El DNI {socio_data.dni} ya pertenece a otro socio ({colision_dni.id_externo}).",
                            )
                            rechazos_list.append(rechazo)
                            db.add(
                                SocioCargaRechazo(
                                    id=uuid4(),
                                    carga_id_uuid=carga.id,
                                    id_externo=rechazo.id_externo,
                                    field=rechazo.field,
                                    codigo=rechazo.codigo,
                                    motivo=rechazo.motivo,
                                )
                            )
                            continue

                        nuevo_socio = Socio(
                            id=uuid4(),
                            club_id=club.id,
                            id_externo=socio_data.id_externo,
                            dni=socio_data.dni,
                            numero_socio=socio_data.numero_socio,
                            nombre=socio_data.nombre,
                            fecha_nacimiento=socio_data.fecha_nacimiento,
                            fecha_alta=socio_data.fecha_alta,
                            fecha_baja_previa=socio_data.fecha_baja_previa,
                            estado_cuota=socio_data.estado_cuota,
                            email=socio_data.email,
                            distancia_km=socio_data.distancia_km,
                            localidad=socio_data.localidad,
                            activo=True,
                            fecha_modificacion=socio_data.fecha_modificacion
                            or datetime.now(UTC),
                            creado_en=datetime.now(UTC),
                            actualizado_en=datetime.now(UTC),
                        )
                        db.add(nuevo_socio)
                        creados += 1

                elif accion == "modificacion":
                    if not socio_existente:
                        rechazo = RechazoDetail(
                            id_externo=socio_data.id_externo,
                            field="id_externo",
                            codigo="SOCIO_NOT_FOUND",
                            motivo=f"No se encontró el socio con id_externo '{socio_data.id_externo}' para modificar.",
                        )
                        rechazos_list.append(rechazo)
                        db.add(
                            SocioCargaRechazo(
                                id=uuid4(),
                                carga_id_uuid=carga.id,
                                id_externo=rechazo.id_externo,
                                field=rechazo.field,
                                codigo=rechazo.codigo,
                                motivo=rechazo.motivo,
                            )
                        )
                        continue

                    # Actualizar campos
                    socio_existente.dni = socio_data.dni
                    socio_existente.numero_socio = socio_data.numero_socio
                    socio_existente.nombre = socio_data.nombre
                    socio_existente.fecha_nacimiento = socio_data.fecha_nacimiento
                    socio_existente.fecha_alta = socio_data.fecha_alta
                    socio_existente.fecha_baja_previa = socio_data.fecha_baja_previa
                    socio_existente.estado_cuota = socio_data.estado_cuota
                    socio_existente.email = socio_data.email
                    socio_existente.distancia_km = socio_data.distancia_km
                    socio_existente.localidad = socio_data.localidad
                    socio_existente.activo = True
                    socio_existente.fecha_modificacion = (
                        socio_data.fecha_modificacion or datetime.now(UTC)
                    )
                    socio_existente.actualizado_en = datetime.now(UTC)
                    actualizados += 1

            elif accion == "baja":
                id_ext = cambio.id_externo
                if not id_ext:
                    rechazo = RechazoDetail(
                        field="id_externo",
                        codigo="MISSING_ID_EXTERNO",
                        motivo="La acción 'baja' requiere 'id_externo'.",
                    )
                    rechazos_list.append(rechazo)
                    db.add(
                        SocioCargaRechazo(
                            id=uuid4(),
                            carga_id_uuid=carga.id,
                            field=rechazo.field,
                            codigo=rechazo.codigo,
                            motivo=rechazo.motivo,
                        )
                    )
                    continue

                socio_existente = (
                    db.query(Socio)
                    .filter(Socio.club_id == club.id, Socio.id_externo == id_ext)
                    .first()
                )
                if not socio_existente:
                    rechazo = RechazoDetail(
                        id_externo=id_ext,
                        field="id_externo",
                        codigo="SOCIO_NOT_FOUND",
                        motivo=f"No se encontró el socio con id_externo '{id_ext}' para dar de baja.",
                    )
                    rechazos_list.append(rechazo)
                    db.add(
                        SocioCargaRechazo(
                            id=uuid4(),
                            carga_id_uuid=carga.id,
                            id_externo=rechazo.id_externo,
                            field=rechazo.field,
                            codigo=rechazo.codigo,
                            motivo=rechazo.motivo,
                        )
                    )
                    continue

                socio_existente.activo = False
                socio_existente.actualizado_en = datetime.now(UTC)
                desactivados += 1

        carga.creados = creados
        carga.actualizados = actualizados
        carga.desactivados = desactivados
        carga.rechazados = len(rechazos_list)
        carga.estado = "exitosa"
        carga.completado_en = datetime.now(UTC)
        db.commit()

        return CargaIncrementalResponse(
            lote_id=carga.carga_id,
            estado="exitosa",
            creados=creados,
            actualizados=actualizados,
            desactivados=desactivados,
            rechazados=len(rechazos_list),
            detalles_rechazos=rechazos_list,
        )

    @staticmethod
    def obtener_estado_carga(
        club: Club, carga_id: str, db: Session
    ) -> CargaStatusResponse:
        """Consulta el estado de una carga de socios y sus motivos de rechazo."""
        carga = (
            db.query(SocioCarga)
            .filter(SocioCarga.club_id == club.id, SocioCarga.carga_id == carga_id)
            .first()
        )
        if not carga:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "NOT_FOUND",
                        "message": f"No se encontró la carga con identificador '{carga_id}' para el club.",
                    }
                },
            )

        rechazos = (
            db.query(SocioCargaRechazo)
            .filter(SocioCargaRechazo.carga_id_uuid == carga.id)
            .all()
        )

        return CargaStatusResponse(
            carga_id=carga.carga_id,
            tipo=carga.tipo,
            estado=carga.estado,
            iniciado_en=carga.iniciado_en,
            completado_en=carga.completado_en,
            pagina_actual=carga.paginas_recibidas,
            total_paginas=carga.total_paginas,
            paginas_recibidas=carga.paginas_recibidas,
            total_registros=carga.total_registros,
            creados=carga.creados,
            actualizados=carga.actualizados,
            desactivados=carga.desactivados,
            rechazados=carga.rechazados,
            detalles_rechazos=[
                RechazoDetail(
                    id_externo=r.id_externo,
                    field=r.field,
                    codigo=r.codigo,
                    motivo=r.motivo,
                )
                for r in rechazos
            ],
            error_mensaje=carga.error_mensaje,
        )

    @staticmethod
    def obtener_frescura_padron(club: Club, db: Session) -> FreshnessResponse:
        """
        Verifica la frescura del padrón de socios según HU-43 / FR-008.
        Si la última carga exitosa tiene más de 24 horas (configurable), emite advertencia.
        """
        ultima_carga = (
            db.query(SocioCarga)
            .filter(SocioCarga.club_id == club.id, SocioCarga.estado == "exitosa")
            .order_by(SocioCarga.completado_en.desc())
            .first()
        )

        limite = settings.freshness_hours_limit
        if not ultima_carga or not ultima_carga.completado_en:
            return FreshnessResponse(
                club_id=str(club.id),
                club_nombre=club.nombre,
                ultima_carga_exitosa=None,
                antiguedad_horas=None,
                limite_horas=limite,
                esta_desactualizado=True,
                advertencia=f"El club no cuenta con ninguna carga de padrón exitosa. Límite de frescura: {limite}h.",
            )

        now = datetime.now(UTC)
        antiguedad = (now - ultima_carga.completado_en).total_seconds() / 3600.0
        esta_desactualizado = antiguedad > limite

        advertencia = (
            f"El padrón tiene una antigüedad de {antiguedad:.1f}h, superando el límite de {limite}h antes de calcular ranking u oleadas."
            if esta_desactualizado
            else None
        )

        return FreshnessResponse(
            club_id=str(club.id),
            club_nombre=club.nombre,
            ultima_carga_exitosa=ultima_carga.completado_en,
            antiguedad_horas=round(antiguedad, 2),
            limite_horas=limite,
            esta_desactualizado=esta_desactualizado,
            advertencia=advertencia,
        )
