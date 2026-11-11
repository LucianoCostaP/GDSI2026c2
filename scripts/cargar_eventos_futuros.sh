#!/usr/bin/env bash
# ==============================================================================
# cargar_eventos_futuros.sh - Carga de eventos futuros pendientes en producción
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

TITULO="Carga de Eventos Futuros (Partidos e Institucionales)"

FECHA_01=$(python3 -c "from datetime import datetime, UTC, timedelta; print((datetime.now(UTC) + timedelta(days=5)).strftime('%Y-%m-%dT20:00:00Z'))")
FECHA_02=$(python3 -c "from datetime import datetime, UTC, timedelta; print((datetime.now(UTC) + timedelta(days=9)).strftime('%Y-%m-%dT17:00:00Z'))")
FECHA_03=$(python3 -c "from datetime import datetime, UTC, timedelta; print((datetime.now(UTC) + timedelta(days=14)).strftime('%Y-%m-%dT21:00:00Z'))")
FECHA_04=$(python3 -c "from datetime import datetime, UTC, timedelta; print((datetime.now(UTC) + timedelta(days=20)).strftime('%Y-%m-%dT10:00:00Z'))")

DETALLE="Se enviará un lote masivo con 4 eventos futuros:
  • EVT-BOCA-FUT-01: Boca Juniors vs. Racing Club - Cuartos de Final
    Fecha: ${FECHA_01} | Tipo: Partido | Lugar: La Bombonera
  • EVT-BOCA-FUT-02: Boca Juniors vs. Vélez Sarsfield - Torneo Local
    Fecha: ${FECHA_02} | Tipo: Partido | Lugar: La Bombonera
  • EVT-BOCA-FUT-03: Cena y Gala Anual de Fin de Año
    Fecha: ${FECHA_03} | Tipo: Institucional | Lugar: Salón Filiberto
  • EVT-BOCA-FUT-04: Clínica Abierta de Básquetbol Infantil
    Fecha: ${FECHA_04} | Tipo: Institucional | Lugar: Polideportivo Quinquela Martín

Impacto en la base de datos:
  - Se crearán como eventos futuros pendientes de definición de clase/puntos en 'eventos_pendientes_verificacion'.
  - Quedarán visibles en el panel de administrador para que el admin pueda definirlos y publicarlos."

# 1. Chequeo de salud del backend
check_backend_health

# 2. Advertencia y confirmación del usuario
show_warning "${TITULO}" "${DETALLE}"
confirm_execution

# 3. Preparación de payload
PAYLOAD=$(cat <<EOF
[
  {
    "id_externo": "EVT-BOCA-FUT-01",
    "titulo": "Boca Juniors vs. Racing Club - Cuartos de Final",
    "fecha_hora": "${FECHA_01}",
    "lugar": "Estadio Alberto J. Armando (La Bombonera)",
    "tipo": "Partido",
    "descripcion": "Partido de eliminación directa. Requiere definir clase y publicar."
  },
  {
    "id_externo": "EVT-BOCA-FUT-02",
    "titulo": "Boca Juniors vs. Vélez Sarsfield - Torneo Local",
    "fecha_hora": "${FECHA_02}",
    "lugar": "Estadio Alberto J. Armando (La Bombonera)",
    "tipo": "Partido",
    "descripcion": "Fecha regular del campeonato local."
  },
  {
    "id_externo": "EVT-BOCA-FUT-03",
    "titulo": "Cena y Gala Anual de Fin de Año",
    "fecha_hora": "${FECHA_03}",
    "lugar": "Salón Filiberto - La Bombonera",
    "tipo": "Institucional",
    "descripcion": "Cena institucional para socios y directivos."
  },
  {
    "id_externo": "EVT-BOCA-FUT-04",
    "titulo": "Clínica Abierta de Básquetbol Infantil",
    "fecha_hora": "${FECHA_04}",
    "lugar": "Polideportivo Quinquela Martín",
    "tipo": "Institucional",
    "descripcion": "Entrenamiento formativo abierto a socios infantiles."
  }
]
EOF
)

# 4. Envío de petición HTTP
echo -e "${CYAN}Enviando petición a POST ${BASE_URL}/api/v1/eventos/batch...${NC}"
RESPUESTA=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/eventos/batch" \
  -H "Authorization: Bearer ${CLUB_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}")

HTTP_CODE=$(echo "${RESPUESTA}" | tail -n1)
BODY=$(echo "${RESPUESTA}" | sed '$d')

echo -e "\n${BOLD}Código HTTP:${NC} ${HTTP_CODE}"
echo -e "${BOLD}Respuesta de la API:${NC}"
print_json "${BODY}"

if [ "${HTTP_CODE}" -eq 207 ] || [ "${HTTP_CODE}" -eq 201 ]; then
    echo -e "\n${GREEN}══════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}✓ Eventos futuros cargados exitosamente en PRODUCCIÓN.${NC}"
    echo -e "${GREEN}══════════════════════════════════════════════════════════════════════════════${NC}\n"
else
    echo -e "\n${RED}✗ Error al cargar eventos futuros en producción (HTTP ${HTTP_CODE}).${NC}\n"
    exit 1
fi
