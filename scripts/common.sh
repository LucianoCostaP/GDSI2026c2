#!/usr/bin/env bash
# ==============================================================================
# common.sh - Utilidades compartidas para scripts de carga en producción
# ==============================================================================

set -euo pipefail

# Configuración base (sobreescribible por variables de entorno)
BASE_URL="${API_URL:-https://gdsi2026c2.onrender.com}"
# Quitar trailing slashes de la URL
BASE_URL="${BASE_URL%/}"
CLUB_TOKEN="${CLUB_TOKEN:-token_boca_abc123}"

# Códigos de color ANSI para mensajes legibles
RED='\033[1;31m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
CYAN='\033[1;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Función para verificar conectividad con la API
check_backend_health() {
    echo -e "${CYAN}Conectando a ${BASE_URL}/health...${NC}"
    if ! curl -sf --max-time 10 "${BASE_URL}/health" > /dev/null 2>&1; then
        echo -e "\n${RED}╔════════════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${RED}║ ERROR: No se puede conectar con el backend en:                         ║${NC}"
        echo -e "${RED}║ ${BASE_URL}                                           ║${NC}"
        echo -e "${RED}║ Verificá que el servicio esté activo y que no esté suspendido.         ║${NC}"
        echo -e "${RED}╚════════════════════════════════════════════════════════════════════════╝${NC}\n"
        exit 1
    fi
    echo -e "${GREEN}✓ Conexión establecida con éxito.${NC}\n"
}

# Muestra el banner de advertencia visual para producción
show_warning() {
    local titulo="$1"
    local detalle="$2"

    echo -e "${RED}╔══════════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║ ⚠️  ADVERTENCIA: VAS A IMPACTAR DATOS EN PRODUCCIÓN                           ║${NC}"
    echo -e "${RED}╚══════════════════════════════════════════════════════════════════════════════╝${NC}"
    echo -e "${BOLD}Target API:${NC}   ${YELLOW}${BASE_URL}${NC}"
    echo -e "${BOLD}Operación:${NC}    ${CYAN}${titulo}${NC}"
    echo -e "${BOLD}Club Token:${NC}   ${YELLOW}${CLUB_TOKEN}${NC}"
    echo -e "\n${BOLD}Detalle de datos a enviar:${NC}"
    echo -e "${YELLOW}${detalle}${NC}"
    echo -e "${RED}──────────────────────────────────────────────────────────────────────────────${NC}"
}

# Solicita confirmación explícita al usuario
confirm_execution() {
    echo -ne "${BOLD}${RED}¿Confirmás la ejecución y carga de estos datos en PRODUCCIÓN? [s/N]: ${NC}"
    read -r respuesta
    case "${respuesta}" in
        [sS]|[sS][iI]|[yY]|[yY][eE][sS])
            echo -e "${GREEN}Confirmación recibida. Procediendo con la carga...${NC}\n"
            ;;
        *)
            echo -e "\n${YELLOW}[CANCELADO] Operación cancelada por el usuario. No se envió ningún dato.${NC}\n"
            exit 0
            ;;
    esac
}

# Formatea e imprime respuesta JSON
print_json() {
    local raw="$1"
    if command -v python3 > /dev/null 2>&1; then
        echo "${raw}" | python3 -m json.tool 2>/dev/null || echo "${raw}"
    else
        echo "${raw}"
    fi
}
