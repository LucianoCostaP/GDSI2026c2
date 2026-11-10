"""Carga 100 socios con datos variados y nombres coherentes para Boca Juniors (CABJ).

Ejecución: `uv run python -m app.seed_100_socios`

Crea:
1. 100 socios activos y con cuota al día con nombres reales del fútbol argentino / Boca.
2. Comportamientos y perfiles variados:
   - 5 bandas de edad (< 30, 30-45, 45-60, 60-75, 75+)
   - 5 bandas de antigüedad (< 1, 1-5, 5-10, 10-20, 20+)
   - 6 bandas de distancia (< 10, 10-50, 50-200, 200-500, 500-1000, 1000+)
3. Partidos pasados de Clase A, B y C con cargas de asistencia realistas.
4. Eventos institucionales con puntos.
5. Recálculo automático del ranking oficial para que HU-30 disponga de los 100 socios.
"""

import random
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from .config import settings
from .database import SessionLocal
from .models.auth import User
from .models.domain import (
    AsistenciaDB,
    CargaParticipacionDB,
    Club,
    EventoVisibleDB,
    Socio,
)
from .models.enums import EstadoCargaParticipacion, OrigenCarga, TipoParticipacion
from .services.ranking_run_service import start_run

BOCA_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
CLUB_CODE = "CABJ"
STADIUM = "Estadio Alberto J. Armando (La Bombonera)"

# 100 nombres coherentes y emblemáticos vinculados a Boca y la Selección Argentina
NAMES_100 = [
    # Los 4 socios al día iniciales de app.seed
    ("30111222", "123456", "Lionel Messi"),
    ("30222333", "234567", "Diego Maradona"),
    ("30333444", "345678", "Juan Román Riquelme"),
    ("30555666", "567890", "Carlos Tevez"),
    # Históricos B-101 a B-120
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
    # Nuevos socios para completar los 100
    ("20000021", "B-121", "Edinson Cavani"),
    ("20000022", "B-122", "Miguel Merentiel"),
    ("20000023", "B-123", "Luis Advíncula"),
    ("20000024", "B-124", "Marcos Rojo"),
    ("20000025", "B-125", "Sergio Romero"),
    ("20000026", "B-126", "Cristian Lema"),
    ("20000027", "B-127", "Marcelo Saracchi"),
    ("20000028", "B-128", "Pol Fernández"),
    ("20000029", "B-129", "Ignacio Miramón"),
    ("20000030", "B-130", "Agustín Martegani"),
    ("20000031", "B-131", "Milton Giménez"),
    ("20000032", "B-132", "Brian Aguirre"),
    ("20000033", "B-133", "Exequiel Zeballos"),
    ("20000034", "B-134", "Lucas Janson"),
    ("20000035", "B-135", "Norberto Briasco"),
    ("20000036", "B-136", "Frank Fabra"),
    ("20000037", "B-137", "Javier García"),
    ("20000038", "B-138", "Leandro Brey"),
    ("20000039", "B-139", "Aaron Anselmino"),
    ("20000040", "B-140", "Mauricio Benítez"),
    ("20000041", "B-141", "Jabes Saralegui"),
    ("20000042", "B-142", "Mateo Mendia"),
    ("20000043", "B-143", "Lautaro Di Lollo"),
    ("20000044", "B-144", "Cristian Medina"),
    ("20000045", "B-145", "Kevin Zenón"),
    ("20000046", "B-146", "Ezequiel Fernández"),
    ("20000047", "B-147", "Valentín Barco"),
    ("20000048", "B-148", "Alan Varela"),
    ("20000049", "B-149", "Luca Langoni"),
    ("20000050", "B-150", "Agustín Sández"),
    ("20000051", "B-151", "Luis Vázquez"),
    ("20000052", "B-152", "Gonzalo Morales"),
    ("20000053", "B-153", "Vicente Taborda"),
    ("20000054", "B-154", "Nicolás Valentini"),
    ("20000055", "B-155", "Gabriel Vega"),
    ("20000056", "B-156", "Renzo Giampaoli"),
    ("20000057", "B-157", "Pedro Velurtas"),
    ("20000058", "B-158", "Maximiliano Zalazar"),
    ("20000059", "B-159", "Brandon Cortés"),
    ("20000060", "B-160", "Alexander Díaz"),
    ("20000061", "B-161", "Walter Samuel"),
    ("20000062", "B-162", "Pablo Aimar"),
    ("20000063", "B-163", "Roberto Ayala"),
    ("20000064", "B-164", "Lionel Scaloni"),
    ("20000065", "B-165", "César Luis Menotti"),
    ("20000066", "B-166", "Carlos Bilardo"),
    ("20000067", "B-167", "Alejandro Sabella"),
    ("20000068", "B-168", "Marcelo Bielsa"),
    ("20000069", "B-169", "José Pékerman"),
    ("20000070", "B-170", "Alfio Basile"),
    ("20000071", "B-171", "Carlos Bianchi"),
    ("20000072", "B-172", "Miguel Ángel Russo"),
    ("20000073", "B-173", "Gustavo Alfaro"),
    ("20000074", "B-174", "Rodolfo Arruabarrena"),
    ("20000075", "B-175", "Julio César Falcioni"),
    ("20000076", "B-176", "Miguel Ángel Brindisi"),
    ("20000077", "B-177", "Héctor Veira"),
    ("20000078", "B-178", "Carlos Babington"),
    ("20000079", "B-179", "Silvio Marzolini"),
    ("20000080", "B-180", "Antonio Rattín"),
    ("20000081", "B-181", "Ángel Clemente Rojas"),
    ("20000082", "B-182", "Alfredo Di Stéfano"),
    ("20000083", "B-183", "Mario Kempes"),
    ("20000084", "B-184", "Daniel Passarella"),
    ("20000085", "B-185", "Ubaldo Fillol"),
    ("20000086", "B-186", "Américo Gallego"),
    ("20000087", "B-187", "Osvaldo Ardiles"),
    ("20000088", "B-188", "Ricardo Bochini"),
    ("20000089", "B-189", "Norberto Alonso"),
    ("20000090", "B-190", "Reinaldo Merlo"),
    ("20000091", "B-191", "René Houseman"),
    ("20000092", "B-192", "Jorge Valdano"),
    ("20000093", "B-193", "Claudio Borghi"),
    ("20000094", "B-194", "Enzo Francescoli"),
    ("20000095", "B-195", "Ariel Ortega"),
    ("20000096", "B-196", "Pablo Guiñazú"),
    ("20000097", "B-197", "Leonardo Ponzio"),
    ("20000098", "B-198", "Javier Mascherano"),
    ("20000099", "B-199", "Esteban Cambiasso"),
    ("20000100", "B-200", "Juan Sebastián Verón"),
]

# Casos especiales de HU-01: Martín Palermo sigue estando moroso (no entra a ranking)
PALERMO = {
    "dni": "30444555",
    "numero_socio": "456789",
    "nombre": "Martín Palermo",
    "estado_cuota": "moroso",
    "fecha_nacimiento": date(1973, 11, 7),
    "fecha_alta": date(1997, 7, 1),
    "distancia_km": Decimal("4.5"),
}

# Fechas de nacimiento distribuidas en las 5 bandas (<30, 30-45, 45-60, 60-75, 75+)
# Cálculo relativo a 2026:
# < 30: nacidos 1997 - 2007 (19 a 29 años)
# 30-45: nacidos 1982 - 1996 (30 a 44 años)
# 45-60: nacidos 1967 - 1981 (45 a 59 años)
# 60-75: nacidos 1952 - 1966 (60 a 74 años)
# 75+: nacidos 1940 - 1951 (75 a 86 años)
AGE_POOLS = {
    "u30": [date(y, m, 15) for y in range(1998, 2007) for m in (2, 6, 10)],
    "30_45": [date(y, m, 15) for y in range(1983, 1996) for m in (3, 7, 11)],
    "45_60": [date(y, m, 15) for y in range(1968, 1981) for m in (1, 5, 9)],
    "60_75": [date(y, m, 15) for y in range(1953, 1966) for m in (4, 8, 12)],
    "75p": [date(y, m, 15) for y in range(1942, 1951) for m in (3, 9)],
}

# Fechas de alta en las 5 bandas (<1, 1-5, 5-10, 10-20, 20+)
# Relativo a 2026:
# < 1: 2026 (e.g. 2026-03-01)
# 1-5: 2022 a 2024
# 5-10: 2017 a 2020
# 10-20: 2007 a 2015
# 20+: 1985 a 2005
SENIORITY_POOLS = {
    "u1": [date(2026, m, 1) for m in (1, 2, 3, 4, 5)],
    "1_5": [date(y, m, 1) for y in (2022, 2023, 2024) for m in (1, 6)],
    "5_10": [date(y, m, 1) for y in (2017, 2018, 2019, 2020) for m in (1, 6)],
    "10_20": [date(y, m, 1) for y in range(2007, 2016, 2) for m in (1, 6)],
    "20p": [date(y, m, 1) for y in range(1985, 2005, 3) for m in (1, 6)],
}

# Distancias en las 6 bandas (<10, 10-50, 50-200, 200-500, 500-1000, 1000+)
DIST_POOLS = {
    "u10": [Decimal(str(d)) for d in (1.5, 2.8, 3.5, 4.2, 5.0, 6.4, 7.8, 8.9)],
    "10_50": [Decimal(str(d)) for d in (12.0, 15.5, 18.0, 24.0, 32.0, 38.0, 45.0)],
    "50_200": [Decimal(str(d)) for d in (55.0, 68.0, 85.0, 110.0, 140.0, 175.0)],
    "200_500": [Decimal(str(d)) for d in (220.0, 260.0, 310.0, 380.0, 420.0, 470.0)],
    "500_1000": [Decimal(str(d)) for d in (550.0, 620.0, 710.0, 800.0, 890.0, 960.0)],
    "1000p": [
        Decimal(str(d)) for d in (1050.0, 1180.0, 1300.0, 1450.0, 1600.0, 1800.0)
    ],
}


def build_socio_profiles() -> list[dict[str, Any]]:
    """Genera 100 perfiles distribuidos de forma balanceada y variada."""
    rng = random.Random(42)  # semilla determinística
    profiles = []

    # Distribución objetivo de 100 socios:
    # Edad: 20 u30, 25 30_45, 25 45_60, 18 60_75, 12 75p = 100
    age_keys = (
        ["u30"] * 20 + ["30_45"] * 25 + ["45_60"] * 25 + ["60_75"] * 18 + ["75p"] * 12
    )
    # Antigüedad: 15 u1, 20 1_5, 25 5_10, 22 10_20, 18 20p = 100
    sen_keys = (
        ["u1"] * 15 + ["1_5"] * 20 + ["5_10"] * 25 + ["10_20"] * 22 + ["20p"] * 18
    )
    # Distancia: 22 u10, 22 10_50, 18 50_200, 16 200_500, 12 500_1000, 10 1000p = 100
    dist_keys = (
        ["u10"] * 22
        + ["10_50"] * 22
        + ["50_200"] * 18
        + ["200_500"] * 16
        + ["500_1000"] * 12
        + ["1000p"] * 10
    )

    rng.shuffle(age_keys)
    rng.shuffle(sen_keys)
    rng.shuffle(dist_keys)

    # Limitar exactamente a 100 socios al día
    names = NAMES_100[:100]

    for i, (dni, num_soc, name) in enumerate(names):
        bday = rng.choice(AGE_POOLS[age_keys[i]])
        alta = rng.choice(SENIORITY_POOLS[sen_keys[i]])
        # Asegurar coherencia: fecha de alta posterior al nacimiento + 16 años
        min_alta_year = bday.year + 16
        if alta.year < min_alta_year:
            alta = date(min_alta_year, alta.month, 1)

        dist = rng.choice(DIST_POOLS[dist_keys[i]])

        # Tasa de asistencia esperada según perfil
        if i < 15:
            rate = rng.uniform(0.85, 1.0)  # Fanáticos
        elif i < 50:
            rate = rng.uniform(0.50, 0.80)  # Frecuentes
        elif i < 80:
            rate = rng.uniform(0.20, 0.45)  # Ocasionales
        else:
            rate = rng.uniform(0.0, 0.10)  # Rara vez / nunca

        profiles.append(
            {
                "dni": dni,
                "numero_socio": num_soc,
                "nombre": name,
                "fecha_nacimiento": bday,
                "fecha_alta": alta,
                "distancia_km": dist,
                "estado_cuota": "al_dia",
                "attendance_rate": rate,
                "attends_institutional": (
                    i % 3 != 0
                ),  # ~66% asiste a algún evento institucional
            }
        )
    return profiles


def main() -> None:
    if settings.app_env == "production":
        raise SystemExit("El seed no se corre en producción.")

    ahora = datetime.now(UTC)

    with SessionLocal() as db:
        club = db.scalar(select(Club).where(Club.codigo_identificador == CLUB_CODE))
        if club is None:
            raise SystemExit("No existe el club CABJ. Corré primero app.seed.")
        club_id = club.id

        admin = db.scalar(select(User).where(User.role == "admin"))
        if admin is None:
            raise SystemExit("No se encontró usuario admin.")

        profiles = build_socio_profiles()

        # 1. Padrón (Socio): cargar los 100 socios + Palermo (moroso)
        socios_payload = []
        for p in profiles:
            socios_payload.append(
                {
                    "id": uuid.uuid4(),
                    "club_id": club_id,
                    "id_externo": f"SOC-{p['numero_socio']}",
                    "dni": p["dni"],
                    "numero_socio": p["numero_socio"],
                    "nombre": p["nombre"],
                    "fecha_nacimiento": p["fecha_nacimiento"],
                    "fecha_alta": p["fecha_alta"],
                    "fecha_baja_previa": None,
                    "estado_cuota": p["estado_cuota"],
                    "email": f"{p['dni']}@boca.example.com",
                    "distancia_km": p["distancia_km"],
                    "localidad": "Buenos Aires",
                    "activo": True,
                }
            )

        # Agregar Palermo (moroso)
        socios_payload.append(
            {
                "id": uuid.uuid4(),
                "club_id": club_id,
                "id_externo": f"SOC-{PALERMO['numero_socio']}",
                "dni": PALERMO["dni"],
                "numero_socio": PALERMO["numero_socio"],
                "nombre": PALERMO["nombre"],
                "fecha_nacimiento": PALERMO["fecha_nacimiento"],
                "fecha_alta": PALERMO["fecha_alta"],
                "fecha_baja_previa": None,
                "estado_cuota": PALERMO["estado_cuota"],
                "email": "palermo@boca.example.com",
                "distancia_km": PALERMO["distancia_km"],
                "localidad": "La Boca, CABA",
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
                        "fecha_nacimiento",
                        "fecha_alta",
                        "distancia_km",
                        "estado_cuota",
                        "activo",
                    )
                },
            )
        )
        print(
            f"[OK] {len(profiles)} socios activos + 1 moroso sincronizados en padron."
        )

        # 2. Partidos y Eventos pasados (Clase A, B, C e Institucionales)
        past_events_def = [
            (
                "PAS-01",
                -12,
                "Partido",
                "A",
                None,
                "Boca Juniors vs. River Plate (Superclásico)",
            ),
            ("PAS-02", -26, "Partido", "B", None, "Boca Juniors vs. San Lorenzo"),
            (
                "PAS-03",
                -35,
                "Institucional",
                None,
                30,
                "Asamblea Extraordinaria del Club",
            ),
            ("PAS-04", -48, "Partido", "A", None, "Boca Juniors vs. Racing Club"),
            (
                "PAS-05",
                -62,
                "Partido",
                "C",
                None,
                "Boca Juniors vs. Central Norte (Copa Argentina)",
            ),
            (
                "PAS-06",
                -76,
                "Partido",
                "C",
                None,
                "Boca Juniors vs. Gimnasia y Tiro (Amistoso)",
            ),
            ("PAS-07", -90, "Partido", "B", None, "Boca Juniors vs. Vélez Sarsfield"),
            (
                "PAS-08",
                -105,
                "Institucional",
                None,
                25,
                "Jornada de Integración y Vida Social",
            ),
            (
                "PAS-09",
                -120,
                "Partido",
                "C",
                None,
                "Boca Juniors vs. Almirante Brown (Copa Argentina)",
            ),
        ]

        eventos_payload: list[dict[str, Any]] = []
        for ext_suffix, days_ago, tipo, clase, puntos, titulo in past_events_def:
            eventos_payload.append(
                {
                    "id_interno": f"INT-EVT-BOCA-{ext_suffix}",
                    "club_id": club_id,
                    "id_externo": f"EVT-BOCA-{ext_suffix}",
                    "titulo": titulo,
                    "fecha_hora": ahora + timedelta(days=days_ago),
                    "lugar": STADIUM
                    if tipo == "Partido"
                    else "Polideportivo Quinquela Martín",
                    "tipo": tipo,
                    "descripcion": f"Evento de prueba ({tipo} {clase or ''})",
                    "clase": clase,
                    "puntos": puntos,
                    "publicado_por": "admin",
                    "es_default": False,
                }
            )

        insert_evts = insert(EventoVisibleDB).values(eventos_payload)
        db.execute(
            insert_evts.on_conflict_do_update(
                constraint="uq_eventos_visibles_club_externo",
                set_={
                    col: insert_evts.excluded[col]
                    for col in ("titulo", "fecha_hora", "tipo", "clase", "puntos")
                },
            )
        )
        print(
            f"[OK] {len(past_events_def)} eventos pasados (incluye Clase C e Inst) sincronizados."
        )

        # 3. Limpiar asistencias y cargas previas de estos eventos para reinsertar ordenadamente
        db.execute(delete(AsistenciaDB).where(AsistenciaDB.club_id == club_id))
        db.execute(
            delete(CargaParticipacionDB).where(CargaParticipacionDB.club_id == club_id)
        )

        # 4. Generar cargas de asistencia y asistencias
        rng = random.Random(99)
        total_asistencias = 0

        for ev in eventos_payload:
            played: datetime = ev["fecha_hora"]
            ev_id_externo: str = str(ev["id_externo"])
            created_at: datetime = played + timedelta(days=1)
            is_institutional = ev["tipo"] == "Institucional"
            is_class_c = ev["clase"] == "C"

            attendees = []
            for p in profiles:
                # Solo puede asistir si ya era socio en la fecha del evento
                alta_date: date = p["fecha_alta"]
                if alta_date > played.date():
                    continue

                if is_institutional:
                    # Participación institucional si el perfil participa
                    if p["attends_institutional"] and rng.random() < 0.60:
                        attendees.append((p["dni"], p["numero_socio"]))
                elif is_class_c:
                    # En partidos clase C, aseguramos que al menos ~50 socios asistan a alguno
                    # para que la variable 'class_c_attendance' tenga más de 10 socios.
                    if rng.random() < max(p["attendance_rate"], 0.45):
                        attendees.append((p["dni"], p["numero_socio"]))
                else:
                    if rng.random() < p["attendance_rate"]:
                        attendees.append((p["dni"], p["numero_socio"]))

            carga_id = uuid.uuid4()
            db.add(
                CargaParticipacionDB(
                    id=carga_id,
                    club_id=club_id,
                    tipo=TipoParticipacion.ASISTENCIA,
                    origen=OrigenCarga.CLUB,
                    carga_id_externo=f"carga-{ev_id_externo.lower()}",
                    evento_id_externo=ev_id_externo,
                    estado=EstadoCargaParticipacion.SUCCESSFUL,
                    total_paginas=1,
                    paginas_recibidas=1,
                    total_registros=len(attendees),
                    registros_incorporados=len(attendees),
                    registros_actualizados=0,
                    registros_rechazados=0,
                    creado_en=created_at,
                    actualizado_en=created_at,
                )
            )
            db.flush()

            db.add_all(
                AsistenciaDB(
                    id=uuid.uuid4(),
                    club_id=club_id,
                    evento_id_externo=ev_id_externo,
                    dni=dni,
                    numero_socio=num_soc,
                    carga_id=carga_id,
                    creado_en=created_at,
                )
                for dni, num_soc in attendees
            )
            total_asistencias += len(attendees)

        print(f"[OK] {total_asistencias} registros de asistencia creados en total.")
        db.commit()

        # 5. Ejecutar el cálculo oficial del Ranking (HU-25)
        print("Calculando ranking con los 100 socios...")
        nuevo_ranking = start_run(db, admin, club_id)
        print(f"[OK] Ranking ID {nuevo_ranking.id} completado con éxito!")


if __name__ == "__main__":
    main()
