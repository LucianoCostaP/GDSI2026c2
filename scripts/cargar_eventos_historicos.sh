#!/usr/bin/env bash
# ==============================================================================
# cargar_eventos_historicos.sh - Carga de eventos pasados/históricos en producción
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

TITULO="Carga de Eventos Históricos Pasados"

FECHA_03=$(python3 -c "from datetime import datetime, UTC, timedelta; print((datetime.now(UTC) - timedelta(days=30)).strftime('%Y-%m-%dT16:00:00Z'))")
FECHA_04=$(python3 -c "from datetime import datetime, UTC, timedelta; print((datetime.now(UTC) - timedelta(days=60)).strftime('%Y-%m-%dT18:00:00Z'))")

DETALLE="Se enviará un lote con 4 eventos pasados:
  • EVT-BOCA-HIST-01: Boca Juniors vs. Real Madrid - Copa Intercontinental 2000
    Fecha: 2000-11-28T19:10:00Z | Tipo: Partido | Lugar: Estadio Nacional de Tokio
  • EVT-BOCA-HIST-02: Boca Juniors vs. AC Milan - Copa Intercontinental 2003
    Fecha: 2003-12-14T19:15:00Z | Tipo: Partido | Lugar: Estadio Yokohama
  • EVT-BOCA-HIST-03: Boca Juniors vs. River Plate - Torneo Clausura (Histórico)
    Fecha: ${FECHA_03} | Tipo: Partido | Lugar: Estadio Mario Alberto Kempes
  • EVT-BOCA-HIST-04: Boca Juniors vs. Independiente - Copa Histórica
    Fecha: ${FECHA_04} | Tipo: Partido | Lugar: La Bombonera

Impacto en la base de datos:
  - Se guardarán directamente como eventos históricos elegibles para asistencia.
  - Habilitan el registro retrospectivo de asistencias para sumar puntaje en el ranking."

# 1. Chequeo de salud del backend
check_backend_health

# 2. Advertencia y confirmación del usuario
show_warning "${TITULO}" "${DETALLE}"
confirm_execution

# 3. Preparación de payload
PAYLOAD=$(cat <<EOF
[
  {
    "id_externo": "EVT-BOCA-HIST-01",
    "titulo": "Boca Juniors vs. Real Madrid - Copa Intercontinental 2000",
    "fecha_hora": "2000-11-28T19:10:00Z",
    "lugar": "Estadio Nacional de Tokio",
    "tipo": "Partido",
    "descripcion": "Copa Intercontinental 2000 ganada por Boca Juniors."
  },
  {
    "id_externo": "EVT-BOCA-HIST-02",
    "titulo": "Boca Juniors vs. AC Milan - Copa Intercontinental 2003",
    "fecha_hora": "2003-12-14T19:15:00Z",
    "lugar": "Estadio Yokohama",
    "tipo": "Partido",
    "descripcion": "Copa Intercontinental 2003 ganada por penales."
  },
  {
    "id_externo": "EVT-BOCA-HIST-03",
    "titulo": "Boca Juniors vs. River Plate - Torneo Clausura (Histórico)",
    "fecha_hora": "${FECHA_03}",
    "lugar": "Estadio Mario Alberto Kempes",
    "tipo": "Partido",
    "descripcion": "Superclásico de eliminación directa."
  },
  {
    "id_externo": "EVT-BOCA-HIST-04",
    "titulo": "Boca Juniors vs. Independiente - Copa Histórica",
    "fecha_hora": "${FECHA_04}",
    "lugar": "Estadio Alberto J. Armando (La Bombonera)",
    "tipo": "Partido",
    "descripcion": "Partido histórico para probar asistencias y reemplazos."
  }
]
EOF
)

# 4. Envío de petición HTTP
echo -e "${CYAN}Enviando petición a POST ${BASE_URL}/api/v1/eventos/historicos/batch...${NC}"
RESPUESTA=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/eventos/historicos/batch" \
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
    echo -e "${GREEN}✓ Eventos históricos cargados exitosamente en PRODUCCIÓN.${NC}"
    echo -e "${GREEN}══════════════════════════════════════════════════════════════════════════════${NC}\n"
else
    echo -e "\n${RED}✗ Error al cargar eventos históricos en producción (HTTP ${HTTP_CODE}).${NC}\n"
    exit 1
fi
