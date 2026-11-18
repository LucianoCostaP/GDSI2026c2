#!/usr/bin/env bash
# ==============================================================================
# cargar_asistencias.sh - Carga de asistencias a evento pasado en producción
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

EVENTO_ID="${1:-EVT-BOCA-HIST-01}"
TITULO="Carga de Asistencias a Evento Histórico (${EVENTO_ID})"

DETALLE="Se registrarán asistencias para el evento '${EVENTO_ID}':
  • Lionel Messi             - DNI: 30111222  | Socio: 123456
  • Diego Maradona           - DNI: 30222333  | Socio: 234567
  • Juan Román Riquelme      - DNI: 30333444  | Socio: 345678

Impacto en la base de datos:
  - Registra la concurrencia efectiva de los socios a este evento en 'asistencias'.
  - Suma puntaje de asistencia en la fórmula de ranking para estos socios."

# 1. Chequeo de salud del backend
check_backend_health

# 2. Advertencia y confirmación del usuario
show_warning "${TITULO}" "${DETALLE}"
confirm_execution

# 3. Preparación de payload
CARGA_ID="asist-${EVENTO_ID}-$(date +%s)"
PAYLOAD=$(cat <<EOF
{
  "carga_id": "${CARGA_ID}",
  "pagina": 1,
  "total_paginas": 1,
  "registros": [
    {"dni": "30111222", "numero_socio": "123456"},
    {"dni": "30222333", "numero_socio": "234567"},
    {"dni": "30333444", "numero_socio": "345678"}
  ]
}
EOF
)

# 4. Envío de petición HTTP
echo -e "${CYAN}Enviando petición a POST ${BASE_URL}/api/v1/eventos/${EVENTO_ID}/asistencia...${NC}"
RESPUESTA=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/eventos/${EVENTO_ID}/asistencia" \
  -H "Authorization: Bearer ${CLUB_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}")

HTTP_CODE=$(echo "${RESPUESTA}" | tail -n1)
BODY=$(echo "${RESPUESTA}" | sed '$d')

echo -e "\n${BOLD}Código HTTP:${NC} ${HTTP_CODE}"
echo -e "${BOLD}Respuesta de la API:${NC}"
print_json "${BODY}"

if [ "${HTTP_CODE}" -eq 202 ]; then
    echo -e "\n${GREEN}══════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}✓ Asistencias para ${EVENTO_ID} cargadas exitosamente en PRODUCCIÓN.${NC}"
    echo -e "${GREEN}══════════════════════════════════════════════════════════════════════════════${NC}\n"
else
    echo -e "\n${RED}✗ Error al cargar asistencias en producción (HTTP ${HTTP_CODE}).${NC}"
    echo -e "${YELLOW}Nota: Asegurate de haber corrido antes 'cargar_eventos_historicos.sh' para que ${EVENTO_ID} exista.${NC}\n"
    exit 1
fi
