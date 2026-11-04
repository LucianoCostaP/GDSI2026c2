"""Datos de prueba para el simulador de HU-18: `uv run python -m app.seed_simulator`.

Se corre después de `app.seed` (usa el club CABJ y los socios de prueba que crea ese seed).
Arma un club con más de 100 socios y historial de asistencia variado, para poder ver la
posición estimada con la configuración por defecto (`position_min_population` = 100):

1. 120 socios más en el padrón (`socios`), al día, con distancias y fechas de alta distintas.
2. 12 partidos pasados (clases A, B y C) y 2 eventos institucionales pasados, publicados.
3. Una carga de asistencia exitosa por evento pasado, con tasas de asistencia distintas por socio.
4. Dos partidos futuros publicados más (clase A y C), además de los de `app.seed`.

Perfiles fijos para los socios que pueden iniciar sesión (los de `app.seed`):
- socio1@example.com (Messi): va a ~60 % de los partidos -> mitad de tabla, rango amplio.
- socio2@example.com (Maradona): va a todos -> cerca del puesto 1.
- socio3@example.com (Riquelme): no va a ninguno -> fondo de la tabla.

Es idempotente: vuelve a escribir los mismos eventos y reemplaza las cargas de asistencia de
este seed. Después hay que calcular el ranking (Admin -> Ranking) para que el simulador lo use.
"""

import random
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from .config import settings
from .db import SessionLocal
from .models.domain import (
    AsistenciaDB,
    CargaParticipacionDB,
    Club,
    EventoVisibleDB,
    Socio,
)
from .models.enums import EstadoCargaParticipacion, OrigenCarga, TipoParticipacion

CLUB_CODE = "CABJ"
NEW_MEMBERS = 120
PREFIX = "SIM"  # id_externo de eventos y cargas de este seed
CARGA_PREFIX = "carga-sim-"
STADIUM = "Estadio Alberto J. Armando (La Bombonera)"

# DNI -> probabilidad de asistir a cada partido.
FIXED_RATES = {
    "30111222": 0.6,  # socio1 - Messi
    "30222333": 1.0,  # socio2 - Maradona
    "30333444": 0.0,  # socio3 - Riquelme
}

# (días atrás, clase) de los partidos pasados. Todos caen en la ventana del ranking
# (año anterior completo + año en curso).
PAST_MATCHES = [
    (12, "A"),
    (26, "B"),
    (40, "C"),
    (54, "A"),
    (68, "B"),
    (82, "B"),
    (96, "A"),
    (110, "C"),
    (124, "B"),
    (138, "A"),
    (152, "B"),
    (166, "C"),
]
# (días atrás, puntos) de los eventos institucionales pasados.
PAST_INSTITUTIONAL = [(30, 20), (90, 40)]


def _member_rate(rng: random.Random) -> float:
    """Mezcla de perfiles para que el ranking tenga puntajes bien distintos."""
    roll = rng.random()
    if roll < 0.15:
        return rng.uniform(0.85, 1.0)  # fanáticos
    if roll < 0.30:
        return rng.uniform(0.0, 0.1)  # casi nunca van
    return rng.uniform(0.2, 0.8)


def main() -> None:
    if settings.app_env == "production":
        raise SystemExit("El seed de datos de prueba no se corre en producción")

    rng = random.Random(18)  # fijo: mismos datos en cada corrida
    ahora = datetime.now(UTC)

    with SessionLocal() as db:
        club = db.scalar(select(Club).where(Club.codigo_identificador == CLUB_CODE))
        if club is None:
            raise SystemExit(
                "No existe el club CABJ: corré primero `uv run python -m app.seed`."
            )
        club_id = club.id

        # 1. Padrón: 120 socios más, al día y activos (entran a la población del ranking).
        socios_payload = []
        for i in range(1, NEW_MEMBERS + 1):
            dni = f"{40000000 + i}"
            # Algunos con alta reciente: su denominador de partidos es más chico.
            alta = date(2026, 6, 1) if i % 10 == 0 else date(2012, 3, 1)
            socios_payload.append(
                {
                    "id": uuid.uuid4(),
                    "club_id": club_id,
                    "id_externo": f"SOC-{PREFIX}-{i:03d}",
                    "dni": dni,
                    "numero_socio": f"S-{i:03d}",
                    "nombre": f"Socio Simulador {i:03d}",
                    "fecha_nacimiento": date(1990, 1, 1),
                    "fecha_alta": alta,
                    "fecha_baja_previa": None,
                    "estado_cuota": "al_dia",
                    "email": f"sim{i:03d}@boca.example.com",
                    "distancia_km": Decimal(
                        rng.choice([3, 8, 15, 40, 120, 400, 900, 1500])
                    ),
                    "localidad": "Buenos Aires",
                    "activo": True,
                }
            )
        insert_socios = insert(Socio).values(socios_payload)
        db.execute(
            insert_socios.on_conflict_do_update(
                constraint="uq_socios_club_dni",
                set_={
                    col: insert_socios.excluded[col]
                    for col in (
                        "nombre",
                        "estado_cuota",
                        "activo",
                        "fecha_alta",
                        "distancia_km",
                    )
                },
            )
        )
        print(f"✓ {NEW_MEMBERS} socios del simulador cargados en el padrón.")

        # 2. Eventos publicados: pasados (con asistencia) y futuros (para simular).
        def evento(
            key: str, *, dias: float, titulo: str, tipo: str, clase=None, puntos=None
        ) -> dict:
            return {
                "id_interno": f"INT-EVT-{PREFIX}-{key}",
                "club_id": club_id,
                "id_externo": f"EVT-{PREFIX}-{key}",
                "titulo": titulo,
                "fecha_hora": ahora + timedelta(days=dias),
                "lugar": STADIUM
                if tipo == "Partido"
                else "Polideportivo Quinquela Martín",
                "tipo": tipo,
                "descripcion": "Evento de prueba del simulador (HU-18).",
                "clase": clase,
                "puntos": puntos,
                "publicado_por": "admin",
                "es_default": False,
            }

        past = [
            evento(
                f"PAS-{n:02d}",
                dias=-d,
                titulo=f"Partido de prueba {n:02d} (clase {c})",
                tipo="Partido",
                clase=c,
            )
            for n, (d, c) in enumerate(PAST_MATCHES, start=1)
        ] + [
            evento(
                f"INS-{n:02d}",
                dias=-d,
                titulo=f"Evento institucional de prueba {n:02d}",
                tipo="Institucional",
                puntos=p,
            )
            for n, (d, p) in enumerate(PAST_INSTITUTIONAL, start=1)
        ]
        future = [
            evento(
                "FUT-A",
                dias=6,
                titulo="Boca Juniors vs. Estudiantes - Simulador (clase A)",
                tipo="Partido",
                clase="A",
            ),
            evento(
                "FUT-C",
                dias=12,
                titulo="Boca Juniors vs. Sarmiento - Simulador (clase C)",
                tipo="Partido",
                clase="C",
            ),
        ]
        insert_eventos = insert(EventoVisibleDB).values(past + future)
        db.execute(
            insert_eventos.on_conflict_do_update(
                constraint="uq_eventos_visibles_club_externo",
                set_={
                    col: insert_eventos.excluded[col]
                    for col in (
                        "titulo",
                        "fecha_hora",
                        "lugar",
                        "tipo",
                        "clase",
                        "puntos",
                        "descripcion",
                    )
                },
            )
        )
        print(
            f"✓ {len(past)} eventos pasados y {len(future)} partidos futuros publicados."
        )

        # 3. Asistencias: se reemplazan las cargas previas de este seed.
        old_cargas = select(CargaParticipacionDB.id).where(
            CargaParticipacionDB.club_id == club_id,
            CargaParticipacionDB.carga_id_externo.like(f"{CARGA_PREFIX}%"),
        )
        db.execute(delete(AsistenciaDB).where(AsistenciaDB.carga_id.in_(old_cargas)))
        db.execute(
            delete(CargaParticipacionDB).where(
                CargaParticipacionDB.club_id == club_id,
                CargaParticipacionDB.carga_id_externo.like(f"{CARGA_PREFIX}%"),
            )
        )

        population = db.execute(
            select(Socio.dni, Socio.numero_socio, Socio.fecha_alta).where(
                Socio.club_id == club_id,
                Socio.activo.is_(True),
                Socio.estado_cuota == "al_dia",
            )
        ).all()
        rates = {
            dni: FIXED_RATES.get(dni, _member_rate(rng)) for dni, _, _ in population
        }

        total = 0
        for ev in past:
            played = ev["fecha_hora"]
            attendees = [
                (dni, numero)
                for dni, numero, alta in population
                if alta <= played.date() and rng.random() < rates[dni]
            ]
            carga_id = uuid.uuid4()
            db.add(
                CargaParticipacionDB(
                    id=carga_id,
                    club_id=club_id,
                    tipo=TipoParticipacion.ASISTENCIA,
                    origen=OrigenCarga.CLUB,
                    carga_id_externo=f"{CARGA_PREFIX}{ev['id_externo'].lower()}",
                    evento_id_externo=ev["id_externo"],
                    estado=EstadoCargaParticipacion.SUCCESSFUL,
                    total_paginas=1,
                    paginas_recibidas=1,
                    total_registros=len(attendees),
                    registros_incorporados=len(attendees),
                    registros_actualizados=0,
                    registros_rechazados=0,
                    creado_en=played + timedelta(days=1),
                    actualizado_en=played + timedelta(days=1),
                )
            )
            db.flush()
            db.add_all(
                AsistenciaDB(
                    id=uuid.uuid4(),
                    club_id=club_id,
                    evento_id_externo=ev["id_externo"],
                    dni=dni,
                    numero_socio=numero,
                    carga_id=carga_id,
                    creado_en=played + timedelta(days=1),
                )
                for dni, numero in attendees
            )
            total += len(attendees)
        print(
            f"✓ {total} asistencias cargadas en {len(past)} eventos ({len(population)} socios al día)."
        )

        db.commit()

    print(
        "\n Seed del simulador completado. Ahora, como Admin: publicá la fórmula (si no está)"
        " y calculá el ranking en /admin/ranking."
    )


if __name__ == "__main__":
    main()
