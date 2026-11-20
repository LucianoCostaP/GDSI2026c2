#!/usr/bin/env bash
# ==============================================================================
# cargar_socios_al_dia.sh - Carga de socios con cuota al día en producción
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

TITULO="Carga de Socios Activos con Cuota Al Día"

DETALLE="Se enviará un lote incremental con 6 socios en estado 'al_dia':
  • Lionel Messi             - DNI: 30111222  | Socio: 123456 | Email: socio1@example.com
  • Diego Maradona           - DNI: 30222333  | Socio: 234567 | Email: socio2@example.com
  • Juan Román Riquelme      - DNI: 30333444  | Socio: 345678 | Email: socio3@example.com
  • Carlos Tevez             - DNI: 30555666  | Socio: 567890 | Email: tevez@boca.example.com
  • Darío Benedetto          - DNI: 20000001  | Socio: B-101  | Email: benedetto@boca.example.com
  • Guillermo B. Schelotto   - DNI: 20000002  | Socio: B-102  | Email: schelotto@boca.example.com

Impacto en la base de datos:
  - Se insertarán o actualizarán en el padrón del club ('socios').
  - El trigger de base de datos los creará en la tabla 'members' para acceso."

# 1. Chequeo de salud del backend
check_backend_health

# 2. Advertencia y confirmación del usuario
show_warning "${TITULO}" "${DETALLE}"
confirm_execution

# 3. Preparación de payload
LOTE_ID="lote-aldia-$(date +%s)"
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
        "id_externo": "SOC-123456",
        "dni": "30111222",
        "numero_socio": "123456",
        "nombre": "Lionel Messi",
        "fecha_nacimiento": "1987-06-24",
        "fecha_alta": "2010-01-01",
        "estado_cuota": "al_dia",
        "email": "socio1@example.com",
        "distancia_km": 4.5,
        "localidad": "La Boca, CABA"
      }
    },
    {
      "accion": "alta",
      "socio": {
        "id_externo": "SOC-234567",
        "dni": "30222333",
        "numero_socio": "234567",
        "nombre": "Diego Maradona",
        "fecha_nacimiento": "1960-10-30",
        "fecha_alta": "2010-01-01",
        "estado_cuota": "al_dia",
        "email": "socio2@example.com",
        "distancia_km": 4.5,
        "localidad": "La Boca, CABA"
      }
    },
    {
      "accion": "alta",
      "socio": {
        "id_externo": "SOC-345678",
        "dni": "30333444",
        "numero_socio": "345678",
        "nombre": "Juan Román Riquelme",
        "fecha_nacimiento": "1978-06-24",
        "fecha_alta": "2010-01-01",
        "estado_cuota": "al_dia",
        "email": "socio3@example.com",
        "distancia_km": 4.5,
        "localidad": "La Boca, CABA"
      }
    },
    {
      "accion": "alta",
      "socio": {
        "id_externo": "SOC-567890",
        "dni": "30555666",
        "numero_socio": "567890",
        "nombre": "Carlos Tevez",
        "fecha_nacimiento": "1984-02-05",
        "fecha_alta": "2010-01-01",
        "estado_cuota": "al_dia",
        "email": "tevez@boca.example.com",
        "distancia_km": 4.5,
        "localidad": "La Boca, CABA"
      }
    },
    {
      "accion": "alta",
      "socio": {
        "id_externo": "SOC-B-101",
        "dni": "20000001",
        "numero_socio": "B-101",
        "nombre": "Darío Benedetto",
        "fecha_nacimiento": "1990-05-17",
        "fecha_alta": "2016-01-01",
        "estado_cuota": "al_dia",
        "email": "benedetto@boca.example.com",
        "distancia_km": 5.0,
        "localidad": "La Boca, CABA"
      }
    },
    {
      "accion": "alta",
      "socio": {
        "id_externo": "SOC-B-102",
        "dni": "20000002",
        "numero_socio": "B-102",
        "nombre": "Guillermo Barros Schelotto",
        "fecha_nacimiento": "1973-05-04",
        "fecha_alta": "2000-01-01",
        "estado_cuota": "al_dia",
        "email": "schelotto@boca.example.com",
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
    echo -e "${GREEN}✓ Socios con cuota al día cargados exitosamente en PRODUCCIÓN.${NC}"
    echo -e "${GREEN}══════════════════════════════════════════════════════════════════════════════${NC}\n"
else
    echo -e "\n${RED}✗ Error al cargar los socios en producción (HTTP ${HTTP_CODE}).${NC}\n"
    exit 1
fi
