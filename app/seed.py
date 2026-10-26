"""Carga datos de prueba en la base de datos: `uv run python -m app.seed`.

Incluye:
1. Socios en `members` (para autenticación y acceso de socios).
2. Socios en `socios` (padrón del club para validación de cargas y asistencias).
3. Eventos en `eventos_visibles` (eventos pasados elegibles para HU-24 y futuros para HU-17).
4. Eventos en `eventos_pendientes_verificacion` (pendientes de definir importancia para HU-22 e históricos para HU-24).
5. Asistencia previa de prueba en `asistencias` y `cargas_participacion` para probar reemplazos en HU-24.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.dialects.postgresql import insert

from .config import settings
from .db import SessionLocal
from .models import FeeStatus, Member
from .models.domain import (
    AsistenciaDB,
    CargaParticipacionDB,
    Club,
    EventoPendienteDB,
    EventoVisibleDB,
    Socio,
)
from .models.enums import EstadoCargaParticipacion, OrigenCarga, TipoParticipacion

BOCA_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")

MEMBERS: list[dict[str, Any]] = [
    {
        "member_id": "123456",
        "dni": "30111222",
        "email": "socio1@example.com",
        "name": "Lionel Messi",
        "fee_status": FeeStatus.UP_TO_DATE,
    },
    {
        "member_id": "234567",
        "dni": "30222333",
        "email": "socio2@example.com",
        "name": "Diego Maradona",
        "fee_status": FeeStatus.UP_TO_DATE,
    },
    {
        "member_id": "345678",
        "dni": "30333444",
        "email": "socio3@example.com",
        "name": "Juan Román Riquelme",
        "fee_status": FeeStatus.UP_TO_DATE,
    },
    # Casos de HU-01: cuotas en mora y sin email registrado.
    {
        "member_id": "456789",
        "dni": "30444555",
        "email": "socio4@example.com",
        "name": "Martín Palermo",
        "fee_status": FeeStatus.OVERDUE,
    },
    {
        "member_id": "567890",
        "dni": "30555666",
        "email": None,
        "name": "Carlos Tevez",
        "fee_status": FeeStatus.UP_TO_DATE,
    },
]


def main() -> None:
    if settings.app_env == "production":
        raise SystemExit("El seed de datos de prueba no se corre en producción")

    ahora = datetime.now(UTC)

    with SessionLocal() as db:
        # 1. Asegurar existencia de club Boca Juniors
        club_boca = (
            db.query(Club)
            .filter((Club.id == BOCA_ID) | (Club.codigo_identificador == "CABJ"))
            .first()
        )
        if not club_boca:
            club_boca = Club(
                id=BOCA_ID,
                nombre="Club Atlético Boca Juniors",
                codigo_identificador="CABJ",
                api_token="token_boca_abc123",
                activo=True,
            )
            db.add(club_boca)
            db.flush()

        club_id = club_boca.id

        # 2. Cargar tabla members (Auth / HU-01)
        insert_members = insert(Member).values(MEMBERS)
        club_data = ("dni", "email", "name", "fee_status")
        db.execute(
            insert_members.on_conflict_do_update(
                index_elements=[Member.member_id],
                set_={column: insert_members.excluded[column] for column in club_data},
            )
        )
        print(f"✓ {len(MEMBERS)} socios cargados en tabla 'members' (Auth).")

        # 3. Cargar tabla socios (Padrón del Club para HU-21/HU-24)
        socios_payload = [
            {
                "id": uuid.uuid4(),
                "club_id": club_id,
                "id_externo": f"SOC-{m['member_id']}",
                "dni": m["dni"],
                "numero_socio": m["member_id"],
                "nombre": m["name"] or "Socio Sin Nombre",
                "fecha_nacimiento": date(1985, 6, 24),
                "fecha_alta": date(2010, 1, 1),
                "fecha_baja_previa": None,
                "estado_cuota": (
                    "al_dia" if m["fee_status"] == FeeStatus.UP_TO_DATE else "moroso"
                ),
                "email": m["email"] or f"socio_{m['dni']}@example.com",
                "distancia_km": Decimal("4.5"),
                "localidad": "La Boca, CABA",
                "activo": True,
            }
            for m in MEMBERS
        ]
        for dni_ext, num_soc, nom in [
            ("20000001", "B-101", "Darío Benedetto"),
            ("20000002", "B-102", "Guillermo Barros Schelotto"),
            ("20000003", "B-103", "Roberto Abbondanzieri"),
            ("20000004", "B-104", "Rolando Schiavi"),
            ("20000005", "B-105", "Hugo Ibarra"),
            ("20000006", "B-106", "Sebastián Battaglia"),
            ("20000007", "B-107", "Mauricio Serna"),
            ("20000008", "B-108", "Jorge Bermúdez"),
            ("20000009", "B-109", "Marcelo Delgado"),
            ("20000010", "B-110", "Antonio Barijho"),
            ("20000011", "B-111", "Clemente Rodríguez"),
            ("20000012", "B-112", "Nicolás Burdisso"),
            ("20000013", "B-113", "Diego Cagna"),
            ("20000014", "B-114", "Fernando Gago"),
            ("20000015", "B-115", "Rodrigo Palacio"),
            ("20000016", "B-116", "Blas Giunta"),
            ("20000017", "B-117", "Alberto Márcico"),
            ("20000018", "B-118", "Óscar Córdoba"),
            ("20000019", "B-119", "Claudio Caniggia"),
            ("20000020", "B-120", "Gabriel Batistuta"),
        ]:
            socios_payload.append(
                {
                    "id": uuid.uuid4(),
                    "club_id": club_id,
                    "id_externo": f"SOC-{num_soc}",
                    "dni": dni_ext,
                    "numero_socio": num_soc,
                    "nombre": nom,
                    "fecha_nacimiento": date(1980, 1, 1),
                    "fecha_alta": date(2005, 1, 1),
                    "fecha_baja_previa": None,
                    "estado_cuota": "al_dia",
                    "email": f"{dni_ext}@boca.example.com",
                    "distancia_km": Decimal("5.0"),
                    "localidad": "La Boca, CABA",
                    "activo": True,
                }
            )
        insert_socios = insert(Socio).values(socios_payload)
        socio_update_cols = (
            "nombre",
            "email",
            "estado_cuota",
            "numero_socio",
            "activo",
        )
        db.execute(
            insert_socios.on_conflict_do_update(
                constraint="uq_socios_club_dni",
                set_={col: insert_socios.excluded[col] for col in socio_update_cols},
            )
        )
        print(
            f"✓ {len(socios_payload)} socios cargados en tabla 'socios' (Padrón del Club)."
        )

        # 4. Eventos Visibles (Publicados)
        # Incluye pasados (elegibles para HU-24) y futuros (para HU-17)
        eventos_visibles_payload = [
            # Pasado 1: Partido Clase A - Elegible para carga de asistencia (HU-24)
            {
                "id_interno": "INT-EVT-BOCA-PAS-01",
                "club_id": club_id,
                "id_externo": "EVT-BOCA-PAS-01",
                "titulo": "Boca Juniors vs. River Plate - Superclásico",
                "fecha_hora": ahora - timedelta(days=3),
                "lugar": "Estadio Alberto J. Armando (La Bombonera)",
                "tipo": "Partido",
                "descripcion": "Superclásico de Primera División.",
                "clase": "A",
                "puntos": None,
                "publicado_por": "admin",
                "es_default": False,
            },
            # Pasado 2: Partido Clase B - Elegible para carga de asistencia (HU-24)
            {
                "id_interno": "INT-EVT-BOCA-PAS-02",
                "club_id": club_id,
                "id_externo": "EVT-BOCA-PAS-02",
                "titulo": "Boca Juniors vs. San Lorenzo - Torneo Clausura",
                "fecha_hora": ahora - timedelta(days=7),
                "lugar": "Estadio Alberto J. Armando (La Bombonera)",
                "tipo": "Partido",
                "descripcion": "Fecha 10 del Torneo Clausura.",
                "clase": "B",
                "puntos": None,
                "publicado_por": "admin",
                "es_default": False,
            },
            # Pasado 3: Institucional - Elegible para carga de asistencia (HU-24)
            {
                "id_interno": "INT-EVT-BOCA-PAS-03",
                "club_id": club_id,
                "id_externo": "EVT-BOCA-PAS-03",
                "titulo": "Asamblea Anual Ordinaria de Socios y Representantes",
                "fecha_hora": ahora - timedelta(days=14),
                "lugar": "Polideportivo Quinquela Martín",
                "tipo": "Institucional",
                "descripcion": "Presentación de Memoria y Balance Anual.",
                "clase": None,
                "puntos": 30,
                "publicado_por": "admin",
                "es_default": False,
            },
            # Pasado 4: Con carga previa cargada - Para probar reemplazos / confirmación (HU-24)
            {
                "id_interno": "INT-EVT-BOCA-PAS-04",
                "club_id": club_id,
                "id_externo": "EVT-BOCA-PAS-04",
                "titulo": "Boca Juniors vs. Independiente (Con Asistencia Previa)",
                "fecha_hora": ahora - timedelta(days=21),
                "lugar": "Estadio Alberto J. Armando (La Bombonera)",
                "tipo": "Partido",
                "descripcion": "Partido histórico para probar sustitución de asistencia.",
                "clase": "A",
                "puntos": None,
                "publicado_por": "admin",
                "es_default": False,
            },
            # Futuro 1: Partido publicado Clase B (Para HU-17)
            {
                "id_interno": "INT-EVT-BOCA-FUT-PUB-01",
                "club_id": club_id,
                "id_externo": "EVT-BOCA-FUT-PUB-01",
                "titulo": "Boca Juniors vs. Vélez Sarsfield - Fecha 14",
                "fecha_hora": ahora + timedelta(days=4),
                "lugar": "Estadio Alberto J. Armando (La Bombonera)",
                "tipo": "Partido",
                "descripcion": "Partido de Primera División.",
                "clase": "B",
                "puntos": None,
                "publicado_por": "admin",
                "es_default": False,
            },
            # Futuro 2: Evento Institucional publicado con puntos (Para HU-17)
            {
                "id_interno": "INT-EVT-BOCA-FUT-PUB-02",
                "club_id": club_id,
                "id_externo": "EVT-BOCA-FUT-PUB-02",
                "titulo": "Clínica Abierta de Básquetbol Infantil y Juvenil",
                "fecha_hora": ahora + timedelta(days=8),
                "lugar": "Polideportivo Quinquela Martín",
                "tipo": "Institucional",
                "descripcion": "Entrenamiento formativo abierto a socios y familiares.",
                "clase": None,
                "puntos": 15,
                "publicado_por": "admin",
                "es_default": False,
            },
        ]
        insert_visibles = insert(EventoVisibleDB).values(eventos_visibles_payload)
        vis_update_cols = (
            "titulo",
            "fecha_hora",
            "lugar",
            "tipo",
            "clase",
            "puntos",
            "descripcion",
        )
        db.execute(
            insert_visibles.on_conflict_do_update(
                constraint="uq_eventos_visibles_club_externo",
                set_={col: insert_visibles.excluded[col] for col in vis_update_cols},
            )
        )
        print(
            f"✓ {len(eventos_visibles_payload)} eventos visibles cargados (pasados para HU-24 y futuros para HU-17)."
        )

        # 5. Eventos Pendientes de Verificación (Para HU-22 e Históricos de HU-24)
        eventos_pendientes_payload = [
            # Histórico: Partido pasado confirmado sin regla de 48h (Elegible para HU-24)
            {
                "id_interno": "INT-EVT-BOCA-HIST-01",
                "club_id": club_id,
                "id_externo": "EVT-BOCA-HIST-01",
                "titulo": "Boca Juniors vs. Real Madrid - Copa Intercontinental 2000",
                "fecha_hora": ahora - timedelta(days=365),
                "lugar": "Estadio Nacional de Tokio",
                "tipo": "Partido",
                "descripcion": "Partido histórico cargado en archivo retrospectivo.",
                "es_historico": True,
                "estado": "Historico",
            },
            # Pendiente 1: Partido futuro pendiente de definir clase A, B o C (HU-22)
            {
                "id_interno": "INT-EVT-BOCA-FUT-PEND-01",
                "club_id": club_id,
                "id_externo": "EVT-BOCA-FUT-PEND-01",
                "titulo": "Boca Juniors vs. Racing Club - Cuartos de Final",
                "fecha_hora": ahora + timedelta(days=5),
                "lugar": "Estadio Alberto J. Armando (La Bombonera)",
                "tipo": "Partido",
                "descripcion": "Partido de eliminación directa. Requiere definir clase y publicar.",
                "es_historico": False,
                "estado": "pendiente_definicion_importancia",
            },
            # Pendiente 2: Institucional futuro pendiente de asignar puntos (HU-22)
            {
                "id_interno": "INT-EVT-BOCA-FUT-PEND-02",
                "club_id": club_id,
                "id_externo": "EVT-BOCA-FUT-PEND-02",
                "titulo": "Cena y Gala Anual de Fin de Año",
                "fecha_hora": ahora + timedelta(days=10),
                "lugar": "Salón Filiberto - La Bombonera",
                "tipo": "Institucional",
                "descripcion": "Cena institucional para vitalicios y directivos.",
                "es_historico": False,
                "estado": "pendiente_definicion_importancia",
            },
        ]
        insert_pendientes = insert(EventoPendienteDB).values(eventos_pendientes_payload)
        pend_update_cols = (
            "titulo",
            "fecha_hora",
            "lugar",
            "tipo",
            "descripcion",
            "es_historico",
            "estado",
        )
        db.execute(
            insert_pendientes.on_conflict_do_update(
                constraint="uq_eventos_pendientes_club_externo",
                set_={col: insert_pendientes.excluded[col] for col in pend_update_cols},
            )
        )
        print(
            f"✓ {len(eventos_pendientes_payload)} eventos pendientes cargados (histórico para HU-24 y pendientes para HU-22)."
        )

        # 6. Asistencia previa para EVT-BOCA-PAS-04
        # Esto permite que el Admin pruebe el flujo de confirmación / reemplazo de HU-24 de inmediato
        carga_previa_id = uuid.uuid4()
        carga_previa_ext = "carga-previa-boca-04"
        carga_existente = (
            db.query(CargaParticipacionDB)
            .filter(
                CargaParticipacionDB.club_id == club_id,
                CargaParticipacionDB.carga_id_externo == carga_previa_ext,
            )
            .first()
        )
        if not carga_existente:
            carga_previa = CargaParticipacionDB(
                id=carga_previa_id,
                club_id=club_id,
                tipo=TipoParticipacion.ASISTENCIA,
                origen=OrigenCarga.CLUB,
                carga_id_externo=carga_previa_ext,
                evento_id_externo="EVT-BOCA-PAS-04",
                estado=EstadoCargaParticipacion.SUCCESSFUL,
                total_paginas=1,
                paginas_recibidas=1,
                total_registros=2,
                registros_incorporados=2,
                registros_actualizados=0,
                registros_rechazados=0,
                creado_en=ahora - timedelta(days=19),
                actualizado_en=ahora - timedelta(days=19),
            )
            db.add(carga_previa)
            db.flush()

            asistencias_previas = [
                AsistenciaDB(
                    id=uuid.uuid4(),
                    club_id=club_id,
                    evento_id_externo="EVT-BOCA-PAS-04",
                    dni="30111222",  # Lionel Messi
                    numero_socio="123456",
                    carga_id=carga_previa_id,
                    creado_en=ahora - timedelta(days=19),
                ),
                AsistenciaDB(
                    id=uuid.uuid4(),
                    club_id=club_id,
                    evento_id_externo="EVT-BOCA-PAS-04",
                    dni="30222333",  # Diego Maradona
                    numero_socio="234567",
                    carga_id=carga_previa_id,
                    creado_en=ahora - timedelta(days=19),
                ),
            ]
            db.add_all(asistencias_previas)
            print(
                "✓ Asistencia previa de prueba inicializada para EVT-BOCA-PAS-04 (para probar reemplazos en HU-24)."
            )

        db.commit()

    print("\n Seed completado exitosamente.")


if __name__ == "__main__":
    main()
