#!/usr/bin/env bash
# ==============================================================================
# menu_carga.sh - Menú interactivo de carga modular en producción
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

mostrar_menu() {
    clear 2>/dev/null || true
    echo -e "${BLUE}╔══════════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║            GESTOR DE CARGA DE DATOS - PASIÓN DE 10                           ║${NC}"
    echo -e "${BLUE}║            Target API: ${YELLOW}${BASE_URL}${BLUE}                         ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════════════════════════╝${NC}"
    echo -e "${BOLD}Elegí qué conjunto de datos querés cargar:${NC}\n"
    echo -e "  ${CYAN}1)${NC} Socios con cuota al día (Messi, Maradona, Riquelme, etc.)"
    echo -e "  ${CYAN}2)${NC} Socios morosos (Palermo, Schiavi, Ibarra)"
    echo -e "  ${CYAN}3)${NC} Eventos futuros (Partidos y eventos institucionales próximos)"
    echo -e "  ${CYAN}4)${NC} Eventos históricos (Copa Intercontinental, superclásicos pasados)"
    echo -e "  ${CYAN}5)${NC} Asistencias a evento histórico (Messi y Maradona en Intercontinental)"
    echo -e "  ${CYAN}6)${NC} ${BOLD}Cargar TODO${NC} (ejecutar todos los scripts en orden)"
    echo -e "  ${RED}0) Salir${NC}\n"
}

while true; do
    mostrar_menu
    echo -ne "${BOLD}Ingresá una opción [0-6]: ${NC}"
    read -r opcion
    echo ""

    case "${opcion}" in
        1)
            bash "${SCRIPT_DIR}/cargar_socios_al_dia.sh"
            ;;
        2)
            bash "${SCRIPT_DIR}/cargar_socios_morosos.sh"
            ;;
        3)
            bash "${SCRIPT_DIR}/cargar_eventos_futuros.sh"
            ;;
        4)
            bash "${SCRIPT_DIR}/cargar_eventos_historicos.sh"
            ;;
        5)
            bash "${SCRIPT_DIR}/cargar_asistencias.sh"
            ;;
        6)
            echo -e "${YELLOW}Iniciando suite completa de carga...${NC}\n"
            bash "${SCRIPT_DIR}/cargar_socios_al_dia.sh"
            bash "${SCRIPT_DIR}/cargar_socios_morosos.sh"
            bash "${SCRIPT_DIR}/cargar_eventos_futuros.sh"
            bash "${SCRIPT_DIR}/cargar_eventos_historicos.sh"
            bash "${SCRIPT_DIR}/cargar_asistencias.sh"
            echo -e "${GREEN}Suite completa finalizada.${NC}\n"
            ;;
        0)
            echo -e "${CYAN}Saliendo del gestor.${NC}\n"
            exit 0
            ;;
        *)
            echo -e "${RED}Opción inválida. Presioná Enter para continuar...${NC}"
            read -r
            continue
            ;;
    esac

    echo -ne "${BOLD}Presioná Enter para volver al menú...${NC}"
    read -r
done
