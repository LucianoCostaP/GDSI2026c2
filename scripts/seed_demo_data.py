#!/usr/bin/env python3
"""Script de generación y siembra de datos para la Demo (GDSI 2026c2).

Basado en:
- Guía datos demo.docx
- Guión presentación y demo.docx

Genera exactamente:
- 1.000 socios al día (incluyendo Andrés, Nico y Flor)
- 40 socios morosos
- 30 partidos históricos (7 A, 10 B, 13 C) espaciados cada 12 días
- 8 eventos institucionales (hace 330d hasta hace 30d)
- 3 eventos futuros (P1 clásico +6d, P2 clase C +13d, P3 asamblea +20d)
- ~10.600 asistencias a partidos y ~620 asistencias institucionales
- Cuentas activadas listas para Andrés, Nico y Flor
"""

import argparse
import os
import random
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

# Localidades coherentes según bracket de distancia
LOCALIDADES_BY_BRACKET = {
    "<10": [
        ("Barracas", 3),
        ("La Boca", 2),
        ("San Telmo", 4),
        ("Caballito", 6),
        ("Palermo", 8),
        ("Boedo", 5),
        ("Almagro", 6),
        ("Villa Crespo", 7),
    ],
    "10-50": [
        ("Lanús", 12),
        ("Avellaneda", 10),
        ("Quilmes", 18),
        ("Lomas de Zamora", 15),
        ("Morón", 24),
        ("San Isidro", 28),
        ("Tigre", 35),
        ("La Plata", 50),
    ],
    "50-200": [
        ("Zárate", 90),
        ("Campana", 85),
        ("Mercedes", 100),
        ("Chascomús", 120),
        ("San Pedro", 170),
        ("Luján", 70),
        ("Cañuelas", 65),
    ],
    "200-500": [
        ("Rosario", 300),
        ("San Nicolás", 240),
        ("Tandil", 360),
        ("Mar del Plata", 400),
        ("Santa Fe", 470),
        ("Gualeguaychú", 230),
    ],
    "500-1000": [
        ("Santa Rosa (La Pampa)", 600),
        ("Bahía Blanca", 650),
        ("Córdoba", 700),
        ("Paraná", 500),
        ("Río Cuarto", 610),
        ("San Luis", 790),
        ("Mendoza", 1000),
    ],
    "1000-2000": [
        ("Tucumán", 1300),
        ("Neuquén", 1150),
        ("Salta", 1500),
        ("Bariloche", 1580),
        ("Posadas", 1000),
        ("San Juan", 1120),
        ("Comodoro Rivadavia", 1750),
    ],
    ">2000": [
        ("Río Gallegos", 2500),
        ("Río Grande", 2800),
        ("Ushuaia", 3000),
    ],
}

NOMBRES_HOMBRES = [
    "Juan",
    "Carlos",
    "Lucas",
    "Mateo",
    "Joaquín",
    "Santiago",
    "Gabriel",
    "Martín",
    "Agustín",
    "Federico",
    "Gonzalo",
    "Tomás",
    "Facundo",
    "Ignacio",
    "Mariano",
    "Emiliano",
    "Esteban",
    "Julián",
    "Sebastián",
    "Rodrigo",
    "Lautaro",
    "Maximiliano",
    "Damián",
]
NOMBRES_MUJERES = [
    "María",
    "Lucía",
    "Sofía",
    "Camila",
    "Valentina",
    "Martina",
    "Paula",
    "Julieta",
    "Florencia",
    "Agustina",
    "Catalina",
    "Mariana",
    "Victoria",
    "Carolina",
    "Daniela",
    "Micaela",
    "Antonella",
    "Rocío",
    "Sol",
    "Belén",
    "Luciana",
    "Malena",
]
APELLIDOS = [
    "González",
    "Rodríguez",
    "Gómez",
    "Fernández",
    "López",
    "Díaz",
    "Martínez",
    "Pérez",
    "García",
    "Sánchez",
    "Romero",
    "Sosa",
    "Álvarez",
    "Torres",
    "Ruiz",
    "Ramírez",
    "Flores",
    "Acosta",
    "Benítez",
    "Medina",
    "Herrera",
    "Suárez",
    "Castro",
    "Giménez",
]


def generar_datos_demo(
    andres_email: str = "socio1@example.com",
    nico_email: str = "socio2@example.com",
    flor_email: str = "socio3@example.com",
    base_date: datetime | None = None,
):
    if base_date is None:
        base_date = datetime.now(UTC)

    rng = random.Random(42)

    # 1. Protagonistas
    protagonistas = [
        {
            "id_externo": "SOC-123456",
            "dni": "30111222",
            "numero_socio": "123456",
            "nombre": "Andrés Moyano",
            "fecha_nacimiento": date(1958, 8, 20),
            "fecha_alta": date(1986, 5, 10),
            "localidad": "Lanús",
            "distancia_km": Decimal("12.00"),
            "email": andres_email,
            "estado_cuota": "al_dia",
            "perfil": "Clasiquero",
            "rol_demo": "Andrés",
        },
        {
            "id_externo": "SOC-234567",
            "dni": "30222333",
            "numero_socio": "234567",
            "nombre": "Nicolás Puccar",
            "fecha_nacimiento": date(1992, 4, 12),
            "fecha_alta": date(2014, 3, 1),
            "localidad": "Barracas",
            "distancia_km": Decimal("3.00"),
            "email": nico_email,
            "estado_cuota": "al_dia",
            "perfil": "Fanático",
            "rol_demo": "Nico",
        },
        {
            "id_externo": "SOC-345678",
            "dni": "30333444",
            "numero_socio": "345678",
            "nombre": "Florencia Villar",
            "fecha_nacimiento": date(1995, 2, 3),
            "fecha_alta": date(2019, 7, 1),
            "localidad": "Santa Rosa (La Pampa)",
            "distancia_km": Decimal("600.00"),
            "email": flor_email,
            "estado_cuota": "al_dia",
            "perfil": "Habitual",
            "rol_demo": "Flor",
        },
    ]

    # Cuotas de distancias (1.000 socios en total; restan los 3 protagonistas: Nico <10, Andrés 10-50, Flor 500-1000)
    cuotas_distancia = {
        "<10": 360 - 1,
        "10-50": 225 - 1,
        "50-200": 133,
        "200-500": 100,
        "500-1000": 73 - 1,
        "1000-2000": 71,
        ">2000": 38,
    }
    distancia_pool = []
    for bracket, count in cuotas_distancia.items():
        distancia_pool.extend([bracket] * count)
    rng.shuffle(distancia_pool)

    # Cuotas de edad (1.000 socios; restan: Andrés 68a [60-74], Nico 34a [30-44], Flor 31a [30-44])
    cuotas_edad = {
        "<30": 70,
        "30-44": 328 - 2,
        "45-59": 307,
        "60-74": 221 - 1,
        "75+": 74,
    }

    # Cuotas de antigüedad (1.000 socios; restan: Flor 7a [5-9], Nico 12a [10-19], Andrés 40a [20+])
    cuotas_antiguedad = {
        "<1": 103,
        "1-4": 227,
        "5-9": 250 - 1,
        "10-19": 282 - 1,
        "20+": 138 - 1,
    }

    # Para evitar incongruencias biológicas (ej. alguien de 25 años con 20 años de antigüedad),
    # generamos primero los pares coherentes (edad, antigüedad)
    pares_edad_ant = []

    # 1. Socios con antigüedad 20+: solo pueden tener edad 45-59, 60-74 o 75+
    # Necesitamos 137 socios con antigüedad 20+
    candidatos_20_plus = ["45-59"] * 60 + ["60-74"] * 50 + ["75+"] * 27
    for edad_b in candidatos_20_plus:
        pares_edad_ant.append((edad_b, "20+"))
        cuotas_edad[edad_b] -= 1
        cuotas_antiguedad["20+"] -= 1

    # 2. Socios con antigüedad 10-19: pueden tener edad 30-44, 45-59, 60-74, 75+
    candidatos_10_19 = ["30-44"] * 100 + ["45-59"] * 100 + ["60-74"] * 50 + ["75+"] * 31
    for edad_b in candidatos_10_19:
        pares_edad_ant.append((edad_b, "10-19"))
        cuotas_edad[edad_b] -= 1
        cuotas_antiguedad["10-19"] -= 1

    # 3. Socios con antigüedad 5-9: pueden tener cualquier edad, preferentemente <30, 30-44, 45-59
    candidatos_5_9 = (
        ["<30"] * 25 + ["30-44"] * 120 + ["45-59"] * 80 + ["60-74"] * 20 + ["75+"] * 4
    )
    for edad_b in candidatos_5_9:
        pares_edad_ant.append((edad_b, "5-9"))
        cuotas_edad[edad_b] -= 1
        cuotas_antiguedad["5-9"] -= 1

    # 4. Socios con antigüedad 1-4
    candidatos_1_4 = (
        ["<30"] * 30 + ["30-44"] * 80 + ["45-59"] * 50 + ["60-74"] * 55 + ["75+"] * 12
    )
    for edad_b in candidatos_1_4:
        pares_edad_ant.append((edad_b, "1-4"))
        cuotas_edad[edad_b] -= 1
        cuotas_antiguedad["1-4"] -= 1

    # 5. Socios con antigüedad <1 (nuevos socios)
    for edad_b, count in list(cuotas_edad.items()):
        for _ in range(count):
            pares_edad_ant.append((edad_b, "<1"))
            cuotas_antiguedad["<1"] -= 1

    assert len(pares_edad_ant) == 997, (
        f"Esperado 997 pares, obtenido {len(pares_edad_ant)}"
    )
    rng.shuffle(pares_edad_ant)

    # Perfiles de los 997 restantes
    perfil_pool = (
        ["Fanático"] * 145
        + ["Habitual"] * 395
        + ["Clasiquero"] * 239
        + ["Ocasional"] * 119
        + ["Inactivo"] * 99
    )
    rng.shuffle(perfil_pool)

    socios_al_dia = list(protagonistas)

    for i in range(997):
        num_soc = 100000 + i + 1
        while num_soc in (123456, 234567, 345678):
            num_soc += 50000

        dni_num = 31000000 + i + 1
        while dni_num in (30111222, 30222333, 30333444):
            dni_num += 50000

        bracket_dist = distancia_pool[i]
        loc_nombre, km_base = rng.choice(LOCALIDADES_BY_BRACKET[bracket_dist])
        km_val = Decimal(str(max(1, km_base + rng.randint(-3, 3))))

        bracket_edad, bracket_ant = pares_edad_ant[i]
        if bracket_edad == "<30":
            edad = rng.randint(18, 29)
        elif bracket_edad == "30-44":
            edad = rng.randint(30, 44)
        elif bracket_edad == "45-59":
            edad = rng.randint(45, 59)
        elif bracket_edad == "60-74":
            edad = rng.randint(60, 74)
        else:
            edad = rng.randint(75, 84)

        fecha_nac = date(base_date.year - edad, rng.randint(1, 12), rng.randint(1, 28))

        if bracket_ant == "<1":
            dias_ant = rng.randint(10, 340)
            fecha_alta = (base_date - timedelta(days=dias_ant)).date()
        elif bracket_ant == "1-4":
            anios_ant = rng.randint(1, 4)
            fecha_alta = date(
                base_date.year - anios_ant, rng.randint(1, 12), rng.randint(1, 28)
            )
        elif bracket_ant == "5-9":
            anios_ant = rng.randint(5, 9)
            fecha_alta = date(
                base_date.year - anios_ant, rng.randint(1, 12), rng.randint(1, 28)
            )
        elif bracket_ant == "10-19":
            anios_ant = rng.randint(10, 19)
            fecha_alta = date(
                base_date.year - anios_ant, rng.randint(1, 12), rng.randint(1, 28)
            )
        else:
            max_ant = min(edad - 18, 45)
            anios_ant = rng.randint(20, max(20, max_ant))
            fecha_alta = date(
                base_date.year - anios_ant, rng.randint(1, 12), rng.randint(1, 28)
            )

        nombre = f"{rng.choice(NOMBRES_HOMBRES if rng.random() > 0.3 else NOMBRES_MUJERES)} {rng.choice(APELLIDOS)}"
        email = f"socio_{dni_num}@pasiondemo.local"

        socios_al_dia.append(
            {
                "id_externo": f"SOC-{num_soc}",
                "dni": str(dni_num),
                "numero_socio": str(num_soc),
                "nombre": nombre,
                "fecha_nacimiento": fecha_nac,
                "fecha_alta": fecha_alta,
                "localidad": loc_nombre,
                "distancia_km": km_val,
                "email": email,
                "estado_cuota": "al_dia",
                "perfil": perfil_pool[i],
                "rol_demo": None,
            }
        )

    # 2. 40 socios morosos
    socios_morosos = []
    for i in range(40):
        num_soc = 900000 + i + 1
        dni_num = 39000000 + i + 1
        nombre = f"{rng.choice(NOMBRES_HOMBRES)} {rng.choice(APELLIDOS)}"
        socios_morosos.append(
            {
                "id_externo": f"SOC-{num_soc}",
                "dni": str(dni_num),
                "numero_socio": str(num_soc),
                "nombre": nombre,
                "fecha_nacimiento": date(1985, 1, 1),
                "fecha_alta": date(2018, 1, 1),
                "localidad": "La Boca",
                "distancia_km": Decimal("2.00"),
                "email": f"moroso_{dni_num}@pasiondemo.local",
                "estado_cuota": "moroso",
                "perfil": "Inactivo",
                "rol_demo": None,
            }
        )

    # 3. 30 Partidos Jugados
    dias_partidos = [350 - i * 12 for i in range(29)] + [10]
    indices_a = {2, 6, 11, 15, 20, 25, 28}
    indices_b = {0, 4, 8, 10, 13, 17, 19, 22, 24, 27}

    rivales_a = [
        "River Plate",
        "Racing Club",
        "Independiente",
        "San Lorenzo",
        "Palmeiras",
        "Flamengo",
        "Nacional",
    ]
    rivales_b = [
        "Rosario Central",
        "Newell's Old Boys",
        "Vélez Sarsfield",
        "Estudiantes de La Plata",
        "Gimnasia LP",
        "Talleres de Córdoba",
        "Belgrano",
        "Argentinos Juniors",
        "Huracán",
        "Colón",
    ]
    rivales_c = [
        "Deportivo Riestra",
        "Barracas Central",
        "Sarmiento de Junín",
        "Central Córdoba",
        "Platense",
        "Tigre",
        "Banfield",
        "Lanús",
        "Unión de Santa Fe",
        "Instituto",
        "Independiente Rivadavia",
        "Godoy Cruz",
        "Defensa y Justicia",
    ]

    rival_a_iter = iter(rivales_a)
    rival_b_iter = iter(rivales_b)
    rival_c_iter = iter(rivales_c)

    partidos_historicos = []
    for idx, dias in enumerate(dias_partidos):
        fecha_partido = base_date - timedelta(days=dias)
        if idx in indices_a:
            clase = "A"
            rival = next(rival_a_iter)
        elif idx in indices_b:
            clase = "B"
            rival = next(rival_b_iter)
        else:
            clase = "C"
            rival = next(rival_c_iter)

        partidos_historicos.append(
            {
                "id_externo": f"EVT-PARTIDO-{idx + 1:02d}",
                "id_interno": f"EVT-INT-PARTIDO-{idx + 1:02d}",
                "titulo": f"Boca Juniors vs {rival}",
                "fecha_hora": fecha_partido.replace(
                    hour=20, minute=0, second=0, microsecond=0
                ),
                "lugar": "Estadio Alberto J. Armando (La Bombonera)",
                "tipo": "Partido",
                "clase": clase,
                "puntos": None,
                "dias_atras": dias,
                "idx": idx,
            }
        )

    # 4. 8 Eventos Institucionales del último año
    eventos_institucionales_data = [
        (330, "Asamblea Ordinaria Anual", 25),
        (300, "Reunión Nacional de Filiales", 15),
        (260, "Elecciones de Comisión Directiva", 40),
        (200, "Celebración Aniversario del Club", 10),
        (150, "Jornada Solidaria en el Barrio", 10),
        (110, "Votación de Reforma del Estatuto", 20),
        (75, "Asamblea Extraordinaria sobre el Modelo de Club", 30),
        (30, "Cena y Brindis de Fin de Temporada", 10),
    ]

    eventos_institucionales = []
    for idx, (dias, titulo, pts) in enumerate(eventos_institucionales_data):
        fecha_evento = base_date - timedelta(days=dias)
        eventos_institucionales.append(
            {
                "id_externo": f"EVT-INST-{idx + 1:02d}",
                "id_interno": f"EVT-INT-INST-{idx + 1:02d}",
                "titulo": titulo,
                "fecha_hora": fecha_evento.replace(
                    hour=18, minute=30, second=0, microsecond=0
                ),
                "lugar": "Sede Social del Club / Polideportivo",
                "tipo": "Institucional",
                "clase": None,
                "puntos": pts,
                "dias_atras": dias,
                "idx": idx,
            }
        )

    # 5. 3 Eventos Futuros
    eventos_futuros = [
        {
            "id_externo": "EVT-FUT-01",
            "id_interno": "EVT-INT-FUT-01",
            "titulo": "Boca Juniors vs River Plate - Torneo Clausura (Fecha 1)",
            "fecha_hora": (base_date + timedelta(days=6)).replace(
                hour=19, minute=0, second=0, microsecond=0
            ),
            "lugar": "Estadio Alberto J. Armando (La Bombonera)",
            "tipo": "Partido",
            "clase": "A",
            "puntos": None,
            "descripcion": "P1 de la Demo: primer clásico para armar las oleadas en vivo.",
        },
        {
            "id_externo": "EVT-FUT-02",
            "id_interno": "EVT-INT-FUT-02",
            "titulo": "Boca Juniors vs Deportivo Riestra (Fecha 2)",
            "fecha_hora": (base_date + timedelta(days=13)).replace(
                hour=17, minute=0, second=0, microsecond=0
            ),
            "lugar": "Estadio Alberto J. Armando (La Bombonera)",
            "tipo": "Partido",
            "clase": "C",
            "puntos": None,
            "descripcion": "P2 de la Demo: partido de baja convocatoria para probar el simulador de socios.",
        },
        {
            "id_externo": "EVT-FUT-03",
            "id_interno": "EVT-INT-FUT-03",
            "titulo": "Asamblea General Ordinaria de Socios",
            "fecha_hora": (base_date + timedelta(days=20)).replace(
                hour=18, minute=30, second=0, microsecond=0
            ),
            "lugar": "Polideportivo Quinquela Martín",
            "tipo": "Institucional",
            "clase": None,
            "puntos": 30,
            "descripcion": "P3 de la Demo: evento institucional futuro con 30 puntos.",
        },
    ]

    # 5b. 2 Eventos Futuros Pendientes de Publicación (para la bandeja de aprobación del Admin)
    eventos_pendientes = [
        {
            "id_externo": "EVT-PEND-01",
            "id_interno": "EVT-INT-PEND-01",
            "titulo": "Boca Juniors vs Platense - Torneo Clausura (Fecha 4)",
            "fecha_hora": (base_date + timedelta(days=25)).replace(
                hour=20, minute=0, second=0, microsecond=0
            ),
            "lugar": "Estadio Alberto J. Armando (La Bombonera)",
            "tipo": "Partido",
            "descripcion": "Partido de torneo local pendiente de definición de importancia (Clase A, B o C) y posterior publicación.",
        },
        {
            "id_externo": "EVT-PEND-02",
            "id_interno": "EVT-INT-PEND-02",
            "titulo": "Jornada Institucional y Visita al Museo de la Pasión",
            "fecha_hora": (base_date + timedelta(days=32)).replace(
                hour=11, minute=0, second=0, microsecond=0
            ),
            "lugar": "Museo de la Pasión Boquense (Brandsen 805)",
            "tipo": "Institucional",
            "descripcion": "Jornada cultural y societaria pendiente de asignación de puntaje y posterior publicación.",
        },
    ]

    # 6. Asistencias a Partidos (~10.600 en total)
    partidos_a = [p for p in partidos_historicos if p["clase"] == "A"]
    partidos_b = [p for p in partidos_historicos if p["clase"] == "B"]
    partidos_c = [p for p in partidos_historicos if p["clase"] == "C"]

    asistencias_por_socio = {}

    # Andrés: 3 A (los 3 más recientes), 2 B (2 recientes), 0 C (5 de 30)
    asistencias_por_socio["30111222"] = set(
        [p["id_externo"] for p in sorted(partidos_a, key=lambda x: x["dias_atras"])[:3]]
        + [
            p["id_externo"]
            for p in sorted(partidos_b, key=lambda x: x["dias_atras"])[:2]
        ]
    )

    # Nico: 7 A, 10 B, 12 C (29 de 30)
    asistencias_por_socio["30222333"] = set(
        [p["id_externo"] for p in partidos_a]
        + [p["id_externo"] for p in partidos_b]
        + [
            p["id_externo"]
            for p in sorted(partidos_c, key=lambda x: x["dias_atras"])[:12]
        ]
    )

    # Flor: 5 A, 5 B, 1 C (11 de 30)
    asistencias_por_socio["30333444"] = set(
        [p["id_externo"] for p in sorted(partidos_a, key=lambda x: x["dias_atras"])[:5]]
        + [
            p["id_externo"]
            for p in sorted(partidos_b, key=lambda x: x["dias_atras"])[:5]
        ]
        + [
            p["id_externo"]
            for p in sorted(partidos_c, key=lambda x: x["dias_atras"])[:1]
        ]
    )

    prob_perfiles = {
        "Fanático": (0.97, 0.93, 0.85),
        "Habitual": (0.85, 0.65, 0.40),
        "Clasiquero": (0.75, 0.30, 0.06),
        "Ocasional": (0.40, 0.20, 0.08),
        "Inactivo": (0.05, 0.03, 0.00),
    }

    def factor_distancia(km: Decimal) -> float:
        if km <= 50:
            return 1.0
        elif km <= 200:
            return 0.85
        elif km <= 500:
            return 0.60
        elif km <= 1000:
            return 0.40
        elif km <= 2000:
            return 0.25
        else:
            return 0.20

    # 80 socios sin ninguna asistencia
    inactivos_sin_asistencia = [
        s["dni"] for s in socios_al_dia[3:] if s["perfil"] == "Inactivo"
    ]
    socios_sin_asistencia = set(inactivos_sin_asistencia[:80])

    for s in socios_al_dia[3:]:
        dni = s["dni"]
        if dni in socios_sin_asistencia:
            asistencias_por_socio[dni] = set()
            continue

        perfil = s["perfil"]
        p_a, p_b, p_c = prob_perfiles[perfil]
        f_dist = factor_distancia(s["distancia_km"])

        p_a_eff = p_a * f_dist * 0.95
        p_b_eff = p_b * f_dist * 0.95
        p_c_eff = p_c * f_dist * 0.95

        asistio_partidos = set()
        for p in partidos_a:
            if rng.random() < p_a_eff:
                asistio_partidos.add(p["id_externo"])
        for p in partidos_b:
            if rng.random() < p_b_eff:
                asistio_partidos.add(p["id_externo"])
        for p in partidos_c:
            if rng.random() < p_c_eff:
                asistio_partidos.add(p["id_externo"])

        # Garantizar que solo los 80 designados tengan exactamente 0 asistencias
        if not asistio_partidos:
            asistio_partidos.add(rng.choice(partidos_c)["id_externo"])

        asistencias_por_socio[dni] = asistio_partidos

    # 7. Asistencias Institucionales (~620 asistencias, 249 socios con puntos)
    institucionales_por_socio = {}
    institucionales_por_socio["30111222"] = {"EVT-INST-01"}
    institucionales_por_socio["30222333"] = {
        "EVT-INST-01",
        "EVT-INST-03",
        "EVT-INST-07",
    }
    institucionales_por_socio["30333444"] = set()

    candidatos_inst = [
        s
        for s in socios_al_dia[3:]
        if s["dni"] not in socios_sin_asistencia
        and s["perfil"] in ("Fanático", "Habitual", "Clasiquero")
    ]
    socios_con_inst = rng.sample(candidatos_inst, 247)
    eventos_inst_ids = [e["id_externo"] for e in eventos_institucionales]

    for s in socios_al_dia[3:]:
        dni = s["dni"]
        if s in socios_con_inst:
            cant_eventos = rng.choices([1, 2, 3, 4], weights=[0.10, 0.40, 0.35, 0.15])[
                0
            ]
            institucionales_por_socio[dni] = set(
                rng.sample(eventos_inst_ids, cant_eventos)
            )
        else:
            institucionales_por_socio[dni] = set()

    total_asistencias_partidos = sum(len(v) for v in asistencias_por_socio.values())
    total_asistencias_inst = sum(len(v) for v in institucionales_por_socio.values())
    total_socios_con_inst = sum(
        1 for v in institucionales_por_socio.values() if len(v) > 0
    )
    total_sin_asistencia = sum(1 for v in asistencias_por_socio.values() if len(v) == 0)

    print("=== RESUMEN GENERACIÓN DE DATOS DEMO ===")
    print(f"Total Socios al día: {len(socios_al_dia)}")
    print(f"Total Socios morosos: {len(socios_morosos)}")
    print(f"Total Partidos históricos: {len(partidos_historicos)} (7 A, 10 B, 13 C)")
    print(f"Total Eventos institucionales: {len(eventos_institucionales)}")
    print(f"Total Eventos futuros visibles: {len(eventos_futuros)}")
    print(
        f"Total Eventos pendientes de publicación: {len(eventos_pendientes)} (1 partido + 1 institucional)"
    )
    print(
        f"Total Asistencias a partidos: {total_asistencias_partidos} (objetivo ~10.600)"
    )
    print(
        f"Total Asistencias institucionales: {total_asistencias_inst} (objetivo ~620)"
    )
    print(
        f"Total Socios con puntos institucionales: {total_socios_con_inst} (objetivo 249)"
    )
    print(
        f"Total Socios sin asistencia a partidos: {total_sin_asistencia} (objetivo 80)"
    )
    print("----------------------------------------")
    print(
        f"Andrés (30111222 / {andres_email}): {len(asistencias_por_socio['30111222'])} partidos, {len(institucionales_por_socio['30111222'])} inst."
    )
    print(
        f"Nico (30222333 / {nico_email}): {len(asistencias_por_socio['30222333'])} partidos, {len(institucionales_por_socio['30222333'])} inst."
    )
    print(
        f"Flor (30333444 / {flor_email}): {len(asistencias_por_socio['30333444'])} partidos, {len(institucionales_por_socio['30333444'])} inst."
    )

    return {
        "socios_al_dia": socios_al_dia,
        "socios_morosos": socios_morosos,
        "partidos_historicos": partidos_historicos,
        "eventos_institucionales": eventos_institucionales,
        "eventos_futuros": eventos_futuros,
        "eventos_pendientes": eventos_pendientes,
        "asistencias_por_socio": asistencias_por_socio,
        "institucionales_por_socio": institucionales_por_socio,
    }


def ejecutar_limpieza_y_siembra(
    db_url: str,
    club_codigo: str = "CABJ",
    andres_email: str = "socio1@example.com",
    nico_email: str = "socio2@example.com",
    flor_email: str = "socio3@example.com",
    clean: bool = True,
):
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import Session
    except ImportError:
        print(
            "\nERROR: Falta instalar 'sqlalchemy' y 'psycopg' para conectarse a la base de datos."
        )
        print("Ejecutá el script usando el entorno del backend:")
        print(
            "  cd backend && uv run python scripts/seed_demo_data.py --database-url '...'"
        )
        sys.exit(1)

    print(f"\nConectando a la base de datos: {db_url[:25]}... (redactado)")
    engine = create_engine(db_url)

    datos = generar_datos_demo(andres_email, nico_email, flor_email)

    with Session(engine) as session:
        # 1. Obtener o verificar Club
        res = session.execute(
            text("SELECT id, nombre FROM clubes WHERE codigo_identificador = :codigo"),
            {"codigo": club_codigo},
        ).fetchone()

        if res:
            club_id = res[0]
            club_nombre = res[1]
            print(f"Club existente encontrado: {club_nombre} ({club_id})")
        else:
            club_id = UUID("11111111-1111-1111-1111-111111111111")
            session.execute(
                text(
                    "INSERT INTO clubes (id, nombre, codigo_identificador, api_token, activo) "
                    "VALUES (:id, 'Club Atlético Boca Juniors', :codigo, 'token_boca_abc123', true)"
                ),
                {"id": club_id, "codigo": club_codigo},
            )
            print(f"Club creado: Boca Juniors ({club_id})")

        if clean:
            print(
                "\nLimpiando tablas operativas respetando cuentas de administradores..."
            )
            session.execute(text("DELETE FROM wave_schedules"))
            session.execute(text("DELETE FROM wave_segmentations"))
            session.execute(text("DELETE FROM ranking_entries"))
            session.execute(text("DELETE FROM rankings"))
            session.execute(text("DELETE FROM formula_locks"))
            session.execute(text("DELETE FROM rules_versions"))
            session.execute(text("DELETE FROM asistencias"))
            session.execute(text("DELETE FROM asistencias_staging"))
            session.execute(text("DELETE FROM actividades_recurrentes"))
            session.execute(text("DELETE FROM cargas_participacion_rechazos"))
            session.execute(text("DELETE FROM cargas_participacion"))
            session.execute(text("DELETE FROM event_reprogrammings"))
            session.execute(text("DELETE FROM eventos_visibles"))
            session.execute(text("DELETE FROM eventos_pendientes_verificacion"))
            session.execute(text("DELETE FROM eventos_cambios_pendientes"))
            session.execute(text("DELETE FROM notifications"))
            session.execute(text("DELETE FROM socios_staging_completa"))
            session.execute(text("DELETE FROM socios_cargas_rechazos"))
            session.execute(text("DELETE FROM socios_cargas_paginas"))
            session.execute(text("DELETE FROM socios_cargas"))
            session.execute(text("DELETE FROM socios"))
            # Limpiar accesos, auditoría y sesiones de socios (no admins)
            session.execute(
                text(
                    "DELETE FROM audit_log WHERE actor_user_id IN (SELECT id FROM users WHERE role = 'member')"
                )
            )
            session.execute(
                text(
                    "DELETE FROM access_codes WHERE member_id IS NOT NULL "
                    "OR user_id IN (SELECT id FROM users WHERE role = 'member')"
                )
            )
            session.execute(
                text(
                    "DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE role = 'member')"
                )
            )
            session.execute(text("DELETE FROM users WHERE role = 'member'"))
            session.execute(text("DELETE FROM members"))
            print("Tablas operativas limpiadas con éxito.")

        now = datetime.now(UTC)

        # 2. Insertar socios (en lote para alta velocidad)
        print(
            f"\nInsertando {len(datos['socios_al_dia'])} socios al día y {len(datos['socios_morosos'])} morosos en lote..."
        )
        socios_payload = []
        for s in datos["socios_al_dia"] + datos["socios_morosos"]:
            socios_payload.append(
                {
                    "id": uuid4(),
                    "club_id": club_id,
                    "id_externo": s["id_externo"],
                    "dni": s["dni"],
                    "numero_socio": s["numero_socio"],
                    "nombre": s["nombre"],
                    "fecha_nacimiento": s["fecha_nacimiento"],
                    "fecha_alta": s["fecha_alta"],
                    "estado_cuota": s["estado_cuota"],
                    "email": s["email"],
                    "distancia_km": s["distancia_km"],
                    "localidad": s["localidad"],
                    "now": now,
                }
            )

        # Chunks de 500 para socios (ejecuta los triggers de members por lote)
        for i in range(0, len(socios_payload), 500):
            session.execute(
                text(
                    "INSERT INTO socios (id, club_id, id_externo, dni, numero_socio, nombre, "
                    "fecha_nacimiento, fecha_alta, estado_cuota, email, distancia_km, localidad, "
                    "activo, creado_en, actualizado_en) "
                    "VALUES (:id, :club_id, :id_externo, :dni, :numero_socio, :nombre, "
                    ":fecha_nacimiento, :fecha_alta, :estado_cuota, :email, :distancia_km, :localidad, "
                    "true, :now, :now)"
                ),
                socios_payload[i : i + 500],
            )

        # 3. Activar cuentas y crear usuarios para Andrés, Nico y Flor
        print("Activando cuentas de acceso para Andrés, Nico y Flor...")
        for p in datos["socios_al_dia"][:3]:
            session.execute(
                text(
                    "UPDATE members SET account_state = 'activated', club_id = :club_id "
                    "WHERE member_id = :member_id OR dni = :dni"
                ),
                {"club_id": club_id, "member_id": p["id_externo"], "dni": p["dni"]},
            )
            session.execute(
                text(
                    "INSERT INTO users (member_id, name, email, role, admin_state, club_id, created_at) "
                    "VALUES (:member_id, :name, :email, 'member', 'active', :club_id, :now)"
                ),
                {
                    "member_id": p["id_externo"],
                    "name": p["nombre"],
                    "email": p["email"],
                    "club_id": club_id,
                    "now": now,
                },
            )

        # 4. Insertar Eventos Visibles en lote (30 partidos históricos, 8 institucionales, 3 futuros)
        print("Insertando eventos visibles en lote...")
        todos_los_eventos = (
            datos["partidos_historicos"]
            + datos["eventos_institucionales"]
            + datos["eventos_futuros"]
        )
        eventos_payload = [
            {
                "id_interno": e["id_interno"],
                "club_id": club_id,
                "id_externo": e["id_externo"],
                "titulo": e["titulo"],
                "fecha_hora": e["fecha_hora"],
                "lugar": e["lugar"],
                "tipo": e["tipo"],
                "clase": e.get("clase"),
                "puntos": e.get("puntos"),
                "now": now,
            }
            for e in todos_los_eventos
        ]
        session.execute(
            text(
                "INSERT INTO eventos_visibles (id_interno, club_id, id_externo, titulo, "
                "fecha_hora, lugar, tipo, clase, puntos, estado, cancelado_por_el_club, "
                "publicado_por, es_default, publicado_en, actualizado_en, version) "
                "VALUES (:id_interno, :club_id, :id_externo, :titulo, "
                ":fecha_hora, :lugar, :tipo, :clase, :puntos, 'publicado', false, "
                "'system', true, :now, :now, 1)"
            ),
            eventos_payload,
        )

        # 4b. Insertar Eventos Pendientes de Publicación (para bandeja del Admin)
        print("Insertando eventos pendientes de publicación en lote...")
        eventos_pendientes_payload = [
            {
                "id_interno": e["id_interno"],
                "club_id": club_id,
                "id_externo": e["id_externo"],
                "titulo": e["titulo"],
                "fecha_hora": e["fecha_hora"],
                "lugar": e["lugar"],
                "tipo": e["tipo"],
                "descripcion": e.get("descripcion"),
                "es_historico": False,
                "estado": "pendiente_definicion_importancia",
                "cancelado_por_el_club": False,
                "now": now,
            }
            for e in datos.get("eventos_pendientes", [])
        ]
        if eventos_pendientes_payload:
            session.execute(
                text(
                    "INSERT INTO eventos_pendientes_verificacion ("
                    "id_interno, club_id, id_externo, titulo, fecha_hora, lugar, "
                    "tipo, descripcion, es_historico, estado, cancelado_por_el_club, "
                    "creado_en, actualizado_en) "
                    "VALUES (:id_interno, :club_id, :id_externo, :titulo, :fecha_hora, :lugar, "
                    ":tipo, :descripcion, :es_historico, :estado, :cancelado_por_el_club, "
                    ":now, :now)"
                ),
                eventos_pendientes_payload,
            )

        # 5. Insertar Cargas de Participación en lote
        print("Registrando cargas de participación de asistencia...")
        carga_por_evento = {}
        cargas_payload = []
        for p in datos["partidos_historicos"]:
            c_id = uuid4()
            carga_por_evento[p["id_externo"]] = c_id
            cargas_payload.append(
                {
                    "id": c_id,
                    "club_id": club_id,
                    "carga_ext": f"CARGA-{p['id_externo']}",
                    "evt_ext": p["id_externo"],
                    "tot": 1000,
                    "now": now,
                }
            )

        carga_inst_id = uuid4()
        cargas_payload.append(
            {
                "id": carga_inst_id,
                "club_id": club_id,
                "carga_ext": "CARGA-INSTITUCIONALES",
                "evt_ext": None,
                "tot": 624,
                "now": now,
            }
        )
        for e in datos["eventos_institucionales"]:
            carga_por_evento[e["id_externo"]] = carga_inst_id

        session.execute(
            text(
                "INSERT INTO cargas_participacion (id, club_id, tipo, origen, carga_id_externo, "
                "evento_id_externo, estado, total_paginas, paginas_recibidas, total_registros, "
                "registros_incorporados, registros_actualizados, registros_rechazados, creado_en, actualizado_en) "
                "VALUES (:id, :club_id, 'asistencia', 'api', :carga_ext, :evt_ext, "
                "'successful', 1, 1, :tot, :tot, 0, 0, :now, :now)"
            ),
            cargas_payload,
        )

        # 6. Insertar Asistencias en lotes de 2.000 registros (para minimizar latencia de red)
        print("Preparando e insertando asistencias en lotes optimizados...")
        socio_map = {s["dni"]: s["numero_socio"] for s in datos["socios_al_dia"]}
        asistencias_payload = []

        for dni, partidos in datos["asistencias_por_socio"].items():
            num_soc = socio_map[dni]
            for p_ext_id in partidos:
                asistencias_payload.append(
                    {
                        "id": uuid4(),
                        "club_id": club_id,
                        "evento_id_externo": p_ext_id,
                        "dni": dni,
                        "numero_socio": num_soc,
                        "carga_id": carga_por_evento[p_ext_id],
                        "now": now,
                    }
                )

        for dni, insts in datos["institucionales_por_socio"].items():
            num_soc = socio_map[dni]
            for inst_ext_id in insts:
                asistencias_payload.append(
                    {
                        "id": uuid4(),
                        "club_id": club_id,
                        "evento_id_externo": inst_ext_id,
                        "dni": dni,
                        "numero_socio": num_soc,
                        "carga_id": carga_por_evento[inst_ext_id],
                        "now": now,
                    }
                )

        CHUNK_SIZE = 2000
        for i in range(0, len(asistencias_payload), CHUNK_SIZE):
            chunk = asistencias_payload[i : i + CHUNK_SIZE]
            session.execute(
                text(
                    "INSERT INTO asistencias (id, club_id, evento_id_externo, dni, numero_socio, carga_id, creado_en) "
                    "VALUES (:id, :club_id, :evento_id_externo, :dni, :numero_socio, :carga_id, :now)"
                ),
                chunk,
            )

        session.commit()
        print(
            f"\n¡Éxito! Se insertaron {len(asistencias_payload)} registros de asistencia en lotes."
        )
        print("Base de datos lista para la Demo 1 y Demo 2.")


def main():
    parser = argparse.ArgumentParser(
        description="Siembra de datos para demo GDSI 2026c2"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula la generación de datos sin tocar la base de datos",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        default=True,
        help="Limpia datos operativos previos antes de sembrar (default: True)",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="URL de PostgreSQL (por defecto lee de la variable DATABASE_URL)",
    )
    parser.add_argument(
        "--club-code",
        default="CABJ",
        help="Código del club (default: CABJ)",
    )
    parser.add_argument(
        "--andres-email",
        default=os.getenv("ANDRES_EMAIL", "socio1@example.com"),
        help="Email para la cuenta de Andrés (default: socio1@example.com)",
    )
    parser.add_argument(
        "--nico-email",
        default=os.getenv("NICO_EMAIL", "socio2@example.com"),
        help="Email para la cuenta de Nico (default: socio2@example.com)",
    )
    parser.add_argument(
        "--flor-email",
        default=os.getenv("FLOR_EMAIL", "socio3@example.com"),
        help="Email para la cuenta de Flor (default: socio3@example.com)",
    )

    args = parser.parse_args()

    if args.dry_run or not args.database_url:
        print("Ejecutando en modo DRY RUN (o no se proporcionó DATABASE_URL)...")
        generar_datos_demo(args.andres_email, args.nico_email, args.flor_email)
        if not args.database_url and not args.dry_run:
            print(
                "\nNota: Para aplicar los cambios a la base, proporcioná --database-url 'postgresql://...'"
            )
        return

    db_url = args.database_url
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

    ejecutar_limpieza_y_siembra(
        db_url=db_url,
        club_codigo=args.club_code,
        andres_email=args.andres_email,
        nico_email=args.nico_email,
        flor_email=args.flor_email,
        clean=args.clean,
    )


if __name__ == "__main__":
    main()
