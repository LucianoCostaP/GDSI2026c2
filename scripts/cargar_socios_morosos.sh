#!/usr/bin/env bash
# ==============================================================================
# cargar_socios_morosos.sh - Carga de socios con cuota morosa en producción
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

TITULO="Carga de Socios con Cuota Morosa"

DETALLE="Se enviará un lote incremental con 3 socios en estado 'moroso':
  • Martín Palermo           - DNI: 30444555  | Socio: 456789 | Email: socio4@example.com   | Estado: MOROSO
  • Rolando Schiavi          - DNI: 20000004  | Socio: B-104  | Email: schiavi@boca.example.com | Estado: MOROSO
  • Hugo Ibarra              - DNI: 20000005  | Socio: B-105  | Email: ibarra@boca.example.com  | Estado: MOROSO

Impacto en la base de datos:
  - Se insertarán o actualizarán en el padrón del club ('socios') con cuota morosa.
  - Permite validar rechazos en login por cuota impaga o cálculo de ranking según reglas de negocio."

# 1. Chequeo de salud del backend
check_backend_health

# 2. Advertencia y confirmación del usuario
show_warning "${TITULO}" "${DETALLE}"
confirm_execution

# 3. Preparación de payload
LOTE_ID="lote-morosos-$(date +%s)"
DESDE=$(python3 -c "from datetime import datetime, UTC, timedelta; print((datetime.now(UTC) - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ'))")
HASTA=$(python3 -c "from datetime import datetime, UTC; print(datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ'))")

PAYLOAD=$(cat <<EOF
{
  "lote_id": "${LOTE_ID}",
  "desde": "${DESDE}",
  "hasta": "${HASTA}",
  "cambios": [
    {
      "accion": "alta",
      "socio": {
        "id_externo": "SOC-456789",
        "dni": "30444555",
        "numero_socio": "456789",
        "nombre": "Martín Palermo",
        "fecha_nacimiento": "1973-11-07",
        "fecha_alta": "2010-01-01",
        "estado_cuota": "moroso",
        "email": "socio4@example.com",
        "distancia_km": 4.5,
        "localidad": "La Boca, CABA"
      }
    },
    {
      "accion": "alta",
      "socio": {
        "id_externo": "SOC-B-104",
        "dni": "20000004",
        "numero_socio": "B-104",
        "nombre": "Rolando Schiavi",
        "fecha_nacimiento": "1973-01-18",
        "fecha_alta": "2001-01-01",
        "estado_cuota": "moroso",
        "email": "schiavi@boca.example.com",
        "distancia_km": 5.0,
        "localidad": "La Boca, CABA"
      }
    },
    {
      "accion": "alta",
      "socio": {
        "id_externo": "SOC-B-105",
        "dni": "20000005",
        "numero_socio": "B-105",
        "nombre": "Hugo Ibarra",
        "fecha_nacimiento": "1974-04-01",
        "fecha_alta": "2002-01-01",
        "estado_cuota": "moroso",
        "email": "ibarra@boca.example.com",
        "distancia_km": 5.0,
        "localidad": "La Boca, CABA"
      }
    }
  ]
}
EOF
)

# 4. Envío de petición HTTP
echo -e "${CYAN}Enviando petición a POST ${BASE_URL}/api/v1/socios/cargas/incremental...${NC}"
RESPUESTA=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/socios/cargas/incremental" \
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
    echo -e "${GREEN}✓ Socios morosos cargados exitosamente en PRODUCCIÓN.${NC}"
    echo -e "${GREEN}══════════════════════════════════════════════════════════════════════════════${NC}\n"
else
    echo -e "\n${RED}✗ Error al cargar socios morosos en producción (HTTP ${HTTP_CODE}).${NC}\n"
    exit 1
fi
