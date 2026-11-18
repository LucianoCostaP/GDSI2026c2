#!/usr/bin/env bash
# ==============================================================================
# seed_api.sh - Inicialización y verificación de datos mediante API y BD
# ==============================================================================
# Carga los mismos datos que app/seed.py:
#   1. Directo en BD: Club Boca Juniors, tabla 'members' (Auth HU-01),
#      eventos pasados (eventos_visibles) y sesión de Admin.
#   2. Vía API (curl):
#      - Padrón completo de 25 socios (POST /api/v1/socios/cargas/completa)
#      - Evento histórico (POST /api/v1/eventos/historicos/batch)
#      - Eventos futuros pendientes (POST /api/v1/eventos)
#      - Eventos futuros publicados (POST /api/v1/eventos + POST /admin/events/{id}/publish)
#      - Carga de asistencia previa (POST /api/v1/eventos/EVT-BOCA-PAS-04/asistencia)
#      - Verificación de consistencia y endpoints
# ==============================================================================

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
CLUB_TOKEN="${CLUB_TOKEN:-token_boca_abc123}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@club.com}"

# Colores para salida de terminal
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}==============================================================================${NC}"
echo -e "${BLUE}        Pasión de 10 - Carga de Datos y Verificación de API                   ${NC}"
echo -e "${BLUE}==============================================================================${NC}"
echo -e "Target URL:  ${YELLOW}${BASE_URL}${NC}"
echo -e "Club Token:  ${YELLOW}${CLUB_TOKEN}${NC}"
echo -e "Admin Email: ${YELLOW}${ADMIN_EMAIL}${NC}\n"

# ------------------------------------------------------------------------------
# 0. Verificar que el backend esté accesible
# ------------------------------------------------------------------------------
echo -e "${BLUE}[0/7] Verificando estado del backend...${NC}"
if ! curl -sf "${BASE_URL}/health" > /dev/null 2>&1; then
    echo -e "${RED}ERROR: No se puede conectar a ${BASE_URL}/health.${NC}"
    echo -e "Asegurate de que el backend esté corriendo (ej. 'uv run uvicorn app.main:app --port 8000')."
    exit 1
fi
echo -e "${GREEN}✓ Backend online y saludable en ${BASE_URL}${NC}\n"

# ------------------------------------------------------------------------------
# 1. Base de Datos: Bootstrap de Club, Members (Auth), Eventos Pasados y Sesión
# ------------------------------------------------------------------------------
echo -e "${BLUE}[1/7] Ejecutando bootstrap en Base de Datos (Club, Members auth, Eventos pasados)...${NC}"

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
cd "${SCRIPT_DIR}"

BOOTSTRAP_OUTPUT=$(uv run python -c '
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from sqlalchemy.dialects.postgresql import insert
from app.db import SessionLocal
from app.models import FeeStatus, Member, User, Role, AdminAccountState
from app.models.domain import Club, EventoVisibleDB
from app.auth import create_session

BOCA_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
ahora = datetime.now(UTC)

with SessionLocal() as db:
    # 1. Club
    club = db.query(Club).filter((Club.id == BOCA_ID) | (Club.codigo_identificador == "CABJ")).first()
    if not club:
        club = Club(id=BOCA_ID, nombre="Club Atlético Boca Juniors", codigo_identificador="CABJ", api_token="token_boca_abc123", activo=True)
        db.add(club)
    else:
        club.api_token = "token_boca_abc123"
        club.activo = True
    db.flush()

    # 2. Admin User & Sesión
    admin = db.query(User).filter(User.email == "admin@club.com").first()
    if not admin:
        admin = User(email="admin@club.com", name="Admin Demo", role=Role.ADMIN, admin_state=AdminAccountState.ACTIVE, club_id=club.id)
        db.add(admin)
        db.flush()
    token = create_session(db, admin)

    # 3. Members (HU-01: Auth de socios)
    members_data = [
        {"member_id": "123456", "dni": "30111222", "email": "socio1@example.com", "name": "Lionel Messi", "fee_status": FeeStatus.UP_TO_DATE},
        {"member_id": "234567", "dni": "30222333", "email": "socio2@example.com", "name": "Diego Maradona", "fee_status": FeeStatus.UP_TO_DATE},
        {"member_id": "345678", "dni": "30333444", "email": "socio3@example.com", "name": "Juan Román Riquelme", "fee_status": FeeStatus.UP_TO_DATE},
        {"member_id": "456789", "dni": "30444555", "email": "socio4@example.com", "name": "Martín Palermo", "fee_status": FeeStatus.OVERDUE},
        {"member_id": "567890", "dni": "30555666", "email": None, "name": "Carlos Tevez", "fee_status": FeeStatus.UP_TO_DATE},
    ]
    stmt_m = insert(Member).values([{**m, "club_id": club.id} for m in members_data])
    stmt_m = stmt_m.on_conflict_do_update(
        index_elements=[Member.member_id],
        set_={col: stmt_m.excluded[col] for col in ("dni", "email", "name", "fee_status", "club_id")},
    )
    db.execute(stmt_m)

    # 4. Eventos pasados visibles (elegibles para HU-24; no pueden publicarse vía API por regla de antelación)
    eventos_pasados = [
        {"id_interno": "INT-EVT-BOCA-PAS-01", "club_id": club.id, "id_externo": "EVT-BOCA-PAS-01", "titulo": "Boca Juniors vs. River Plate - Superclásico", "fecha_hora": ahora - timedelta(days=3), "lugar": "Estadio Alberto J. Armando (La Bombonera)", "tipo": "Partido", "descripcion": "Superclásico de Primera División.", "clase": "A", "puntos": None, "publicado_por": "admin", "es_default": False},
        {"id_interno": "INT-EVT-BOCA-PAS-02", "club_id": club.id, "id_externo": "EVT-BOCA-PAS-02", "titulo": "Boca Juniors vs. San Lorenzo - Torneo Clausura", "fecha_hora": ahora - timedelta(days=7), "lugar": "Estadio Alberto J. Armando (La Bombonera)", "tipo": "Partido", "descripcion": "Fecha 10 del Torneo Clausura.", "clase": "B", "puntos": None, "publicado_por": "admin", "es_default": False},
        {"id_interno": "INT-EVT-BOCA-PAS-03", "club_id": club.id, "id_externo": "EVT-BOCA-PAS-03", "titulo": "Asamblea Anual Ordinaria de Socios y Representantes", "fecha_hora": ahora - timedelta(days=14), "lugar": "Polideportivo Quinquela Martín", "tipo": "Institucional", "descripcion": "Presentación de Memoria y Balance Anual.", "clase": None, "puntos": 30, "publicado_por": "admin", "es_default": False},
        {"id_interno": "INT-EVT-BOCA-PAS-04", "club_id": club.id, "id_externo": "EVT-BOCA-PAS-04", "titulo": "Boca Juniors vs. Independiente (Con Asistencia Previa)", "fecha_hora": ahora - timedelta(days=21), "lugar": "Estadio Alberto J. Armando (La Bombonera)", "tipo": "Partido", "descripcion": "Partido histórico para probar sustitución de asistencia.", "clase": "A", "puntos": None, "publicado_por": "admin", "es_default": False},
    ]
    stmt_ev = insert(EventoVisibleDB).values(eventos_pasados)
    stmt_ev = stmt_ev.on_conflict_do_update(
        constraint="uq_eventos_visibles_club_externo",
        set_={col: stmt_ev.excluded[col] for col in ("titulo", "fecha_hora", "lugar", "tipo", "clase", "puntos", "descripcion")},
    )
    db.execute(stmt_ev)
    db.commit()

    print(f"ADMIN_TOKEN={token}")
')

ADMIN_TOKEN=$(echo "${BOOTSTRAP_OUTPUT}" | grep "ADMIN_TOKEN=" | cut -d'=' -f2)
echo -e "${GREEN}✓ Club Boca Juniors, 5 members en tabla auth y 4 eventos pasados configurados en BD.${NC}"
echo -e "${GREEN}✓ Token de Administrador generado para llamadas de API.${NC}\n"

# ------------------------------------------------------------------------------
# 2. API: Cargar Padrón de 25 Socios (POST /api/v1/socios/cargas/completa)
# ------------------------------------------------------------------------------
echo -e "${BLUE}[2/7] Cargando padrón de 25 socios vía API (POST /api/v1/socios/cargas/completa)...${NC}"

CARGA_ID="carga-seed-$(date +%s)"
SOCIOS_JSON=$(cat <<EOF
{
  "carga_id": "${CARGA_ID}",
  "pagina": 1,
  "total_paginas": 1,
  "socios": [
    {"id_externo": "SOC-123456", "dni": "30111222", "numero_socio": "123456", "nombre": "Lionel Messi", "fecha_nacimiento": "1985-06-24", "fecha_alta": "2010-01-01", "estado_cuota": "al_dia", "email": "socio1@example.com", "distancia_km": 4.5, "localidad": "La Boca, CABA"},
    {"id_externo": "SOC-234567", "dni": "30222333", "numero_socio": "234567", "nombre": "Diego Maradona", "fecha_nacimiento": "1985-06-24", "fecha_alta": "2010-01-01", "estado_cuota": "al_dia", "email": "socio2@example.com", "distancia_km": 4.5, "localidad": "La Boca, CABA"},
    {"id_externo": "SOC-345678", "dni": "30333444", "numero_socio": "345678", "nombre": "Juan Román Riquelme", "fecha_nacimiento": "1985-06-24", "fecha_alta": "2010-01-01", "estado_cuota": "al_dia", "email": "socio3@example.com", "distancia_km": 4.5, "localidad": "La Boca, CABA"},
    {"id_externo": "SOC-456789", "dni": "30444555", "numero_socio": "456789", "nombre": "Martín Palermo", "fecha_nacimiento": "1985-06-24", "fecha_alta": "2010-01-01", "estado_cuota": "moroso", "email": "socio4@example.com", "distancia_km": 4.5, "localidad": "La Boca, CABA"},
    {"id_externo": "SOC-567890", "dni": "30555666", "numero_socio": "567890", "nombre": "Carlos Tevez", "fecha_nacimiento": "1985-06-24", "fecha_alta": "2010-01-01", "estado_cuota": "al_dia", "email": "socio_30555666@example.com", "distancia_km": 4.5, "localidad": "La Boca, CABA"},
    {"id_externo": "SOC-B-101", "dni": "20000001", "numero_socio": "B-101", "nombre": "Darío Benedetto", "fecha_nacimiento": "1980-01-01", "fecha_alta": "2005-01-01", "estado_cuota": "al_dia", "email": "20000001@boca.example.com", "distancia_km": 5.0, "localidad": "La Boca, CABA"},
    {"id_externo": "SOC-B-102", "dni": "20000002", "numero_socio": "B-102", "nombre": "Guillermo Barros Schelotto", "fecha_nacimiento": "1980-01-01", "fecha_alta": "2005-01-01", "estado_cuota": "al_dia", "email": "20000002@boca.example.com", "distancia_km": 5.0, "localidad": "La Boca, CABA"},
    {"id_externo": "SOC-B-103", "dni": "20000003", "numero_socio": "B-103", "nombre": "Roberto Abbondanzieri", "fecha_nacimiento": "1980-01-01", "fecha_alta": "2005-01-01", "estado_cuota": "al_dia", "email": "20000003@boca.example.com", "distancia_km": 5.0, "localidad": "La Boca, CABA"},
    {"id_externo": "SOC-B-104", "dni": "20000004", "numero_socio": "B-104", "nombre": "Rolando Schiavi", "fecha_nacimiento": "1980-01-01", "fecha_alta": "2005-01-01", "estado_cuota": "al_dia", "email": "20000004@boca.example.com", "distancia_km": 5.0, "localidad": "La Boca, CABA"},
    {"id_externo": "SOC-B-105", "dni": "20000005", "numero_socio": "B-105", "nombre": "Hugo Ibarra", "fecha_nacimiento": "1980-01-01", "fecha_alta": "2005-01-01", "estado_cuota": "al_dia", "email": "20000005@boca.example.com", "distancia_km": 5.0, "localidad": "La Boca, CABA"},
    {"id_externo": "SOC-B-106", "dni": "20000006", "numero_socio": "B-106", "nombre": "Sebastián Battaglia", "fecha_nacimiento": "1980-01-01", "fecha_alta": "2005-01-01", "estado_cuota": "al_dia", "email": "20000006@boca.example.com", "distancia_km": 5.0, "localidad": "La Boca, CABA"},
    {"id_externo": "SOC-B-107", "dni": "20000007", "numero_socio": "B-107", "nombre": "Mauricio Serna", "fecha_nacimiento": "1980-01-01", "fecha_alta": "2005-01-01", "estado_cuota": "al_dia", "email": "20000007@boca.example.com", "distancia_km": 5.0, "localidad": "La Boca, CABA"},
    {"id_externo": "SOC-B-108", "dni": "20000008", "numero_socio": "B-108", "nombre": "Jorge Bermúdez", "fecha_nacimiento": "1980-01-01", "fecha_alta": "2005-01-01", "estado_cuota": "al_dia", "email": "20000008@boca.example.com", "distancia_km": 5.0, "localidad": "La Boca, CABA"},
    {"id_externo": "SOC-B-109", "dni": "20000009", "numero_socio": "B-109", "nombre": "Marcelo Delgado", "fecha_nacimiento": "1980-01-01", "fecha_alta": "2005-01-01", "estado_cuota": "al_dia", "email": "20000009@boca.example.com", "distancia_km": 5.0, "localidad": "La Boca, CABA"},
    {"id_externo": "SOC-B-110", "dni": "20000010", "numero_socio": "B-110", "nombre": "Antonio Barijho", "fecha_nacimiento": "1980-01-01", "fecha_alta": "2005-01-01", "estado_cuota": "al_dia", "email": "20000010@boca.example.com", "distancia_km": 5.0, "localidad": "La Boca, CABA"},
    {"id_externo": "SOC-B-111", "dni": "20000011", "numero_socio": "B-111", "nombre": "Clemente Rodríguez", "fecha_nacimiento": "1980-01-01", "fecha_alta": "2005-01-01", "estado_cuota": "al_dia", "email": "20000011@boca.example.com", "distancia_km": 5.0, "localidad": "La Boca, CABA"},
    {"id_externo": "SOC-B-112", "dni": "20000012", "numero_socio": "B-112", "nombre": "Nicolás Burdisso", "fecha_nacimiento": "1980-01-01", "fecha_alta": "2005-01-01", "estado_cuota": "al_dia", "email": "20000012@boca.example.com", "distancia_km": 5.0, "localidad": "La Boca, CABA"},
    {"id_externo": "SOC-B-113", "dni": "20000013", "numero_socio": "B-113", "nombre": "Diego Cagna", "fecha_nacimiento": "1980-01-01", "fecha_alta": "2005-01-01", "estado_cuota": "al_dia", "email": "20000013@boca.example.com", "distancia_km": 5.0, "localidad": "La Boca, CABA"},
    {"id_externo": "SOC-B-114", "dni": "20000014", "numero_socio": "B-114", "nombre": "Fernando Gago", "fecha_nacimiento": "1980-01-01", "fecha_alta": "2005-01-01", "estado_cuota": "al_dia", "email": "20000014@boca.example.com", "distancia_km": 5.0, "localidad": "La Boca, CABA"},
    {"id_externo": "SOC-B-115", "dni": "20000015", "numero_socio": "B-115", "nombre": "Rodrigo Palacio", "fecha_nacimiento": "1980-01-01", "fecha_alta": "2005-01-01", "estado_cuota": "al_dia", "email": "20000015@boca.example.com", "distancia_km": 5.0, "localidad": "La Boca, CABA"},
    {"id_externo": "SOC-B-116", "dni": "20000016", "numero_socio": "B-116", "nombre": "Blas Giunta", "fecha_nacimiento": "1980-01-01", "fecha_alta": "2005-01-01", "estado_cuota": "al_dia", "email": "20000016@boca.example.com", "distancia_km": 5.0, "localidad": "La Boca, CABA"},
    {"id_externo": "SOC-B-117", "dni": "20000017", "numero_socio": "B-117", "nombre": "Alberto Márcico", "fecha_nacimiento": "1980-01-01", "fecha_alta": "2005-01-01", "estado_cuota": "al_dia", "email": "20000017@boca.example.com", "distancia_km": 5.0, "localidad": "La Boca, CABA"},
    {"id_externo": "SOC-B-118", "dni": "20000018", "numero_socio": "B-118", "nombre": "Óscar Córdoba", "fecha_nacimiento": "1980-01-01", "fecha_alta": "2005-01-01", "estado_cuota": "al_dia", "email": "20000018@boca.example.com", "distancia_km": 5.0, "localidad": "La Boca, CABA"},
    {"id_externo": "SOC-B-119", "dni": "20000019", "numero_socio": "B-119", "nombre": "Claudio Caniggia", "fecha_nacimiento": "1980-01-01", "fecha_alta": "2005-01-01", "estado_cuota": "al_dia", "email": "20000019@boca.example.com", "distancia_km": 5.0, "localidad": "La Boca, CABA"},
    {"id_externo": "SOC-B-120", "dni": "20000020", "numero_socio": "B-120", "nombre": "Gabriel Batistuta", "fecha_nacimiento": "1980-01-01", "fecha_alta": "2005-01-01", "estado_cuota": "al_dia", "email": "20000020@boca.example.com", "distancia_km": 5.0, "localidad": "La Boca, CABA"}
  ]
}
EOF
)

RESP_SOCIOS=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/socios/cargas/completa" \
  -H "Authorization: Bearer ${CLUB_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "${SOCIOS_JSON}")

HTTP_CODE=$(echo "${RESP_SOCIOS}" | tail -n1)
BODY=$(echo "${RESP_SOCIOS}" | sed '$d')

if [ "${HTTP_CODE}" -ne 202 ]; then
    echo -e "${RED}Error al cargar socios (HTTP ${HTTP_CODE}): ${BODY}${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Snapshot de 25 socios cargado y activado exitosamente (HTTP 202).${NC}\n"

# ------------------------------------------------------------------------------
# 3. API: Cargar Evento Histórico (POST /api/v1/eventos/historicos/batch)
# ------------------------------------------------------------------------------
echo -e "${BLUE}[3/7] Cargando evento histórico vía API (POST /api/v1/eventos/historicos/batch)...${NC}"

FECHA_HIST=$(date -u -d "-365 days" +"%Y-%m-%dT15:00:00Z")
HIST_JSON=$(cat <<EOF
[
  {
    "id_externo": "EVT-BOCA-HIST-01",
    "titulo": "Boca Juniors vs. Real Madrid - Copa Intercontinental 2000",
    "fecha_hora": "${FECHA_HIST}",
    "lugar": "Estadio Nacional de Tokio",
    "tipo": "Partido",
    "descripcion": "Partido histórico cargado en archivo retrospectivo."
  }
]
EOF
)

RESP_HIST=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/eventos/historicos/batch" \
  -H "Authorization: Bearer ${CLUB_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "${HIST_JSON}")

HTTP_CODE=$(echo "${RESP_HIST}" | tail -n1)
if [ "${HTTP_CODE}" -ne 207 ]; then
    echo -e "${RED}Error al cargar evento histórico (HTTP ${HTTP_CODE})${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Evento histórico 'EVT-BOCA-HIST-01' registrado con éxito (HTTP 207).${NC}\n"

# ------------------------------------------------------------------------------
# 4. API: Cargar Eventos Futuros Pendientes (HU-22) (POST /api/v1/eventos)
# ------------------------------------------------------------------------------
echo -e "${BLUE}[4/7] Registrando eventos futuros pendientes vía API (POST /api/v1/eventos)...${NC}"

FECHA_FUT_PEND_01=$(date -u -d "+5 days" +"%Y-%m-%dT20:00:00Z")
FECHA_FUT_PEND_02=$(date -u -d "+10 days" +"%Y-%m-%dT21:00:00Z")

# Evento Pendiente 1: Partido (+5 días)
curl -s -X POST "${BASE_URL}/api/v1/eventos" \
  -H "Authorization: Bearer ${CLUB_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"id_externo\": \"EVT-BOCA-FUT-PEND-01\",
    \"titulo\": \"Boca Juniors vs. Racing Club - Cuartos de Final\",
    \"fecha_hora\": \"${FECHA_FUT_PEND_01}\",
    \"lugar\": \"Estadio Alberto J. Armando (La Bombonera)\",
    \"tipo\": \"Partido\",
    \"descripcion\": \"Partido de eliminación directa. Requiere definir clase y publicar.\"
  }" > /dev/null

# Evento Pendiente 2: Institucional (+10 días)
curl -s -X POST "${BASE_URL}/api/v1/eventos" \
  -H "Authorization: Bearer ${CLUB_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"id_externo\": \"EVT-BOCA-FUT-PEND-02\",
    \"titulo\": \"Cena y Gala Anual de Fin de Año\",
    \"fecha_hora\": \"${FECHA_FUT_PEND_02}\",
    \"lugar\": \"Salón Filiberto - La Bombonera\",
    \"tipo\": \"Institucional\",
    \"descripcion\": \"Cena institucional para vitalicios y directivos.\"
  }" > /dev/null

echo -e "${GREEN}✓ Eventos pendientes EVT-BOCA-FUT-PEND-01 y 02 creados correctamente.${NC}\n"

# ------------------------------------------------------------------------------
# 5. API: Registrar y Publicar Eventos Futuros (HU-17 / HU-22)
# ------------------------------------------------------------------------------
echo -e "${BLUE}[5/7] Creando y publicando eventos futuros vía API de Admin...${NC}"

FECHA_FUT_PUB_01=$(date -u -d "+4 days" +"%Y-%m-%dT17:00:00Z")
FECHA_FUT_PUB_02=$(date -u -d "+8 days" +"%Y-%m-%dT10:00:00Z")

# Registrar como eventos entrantes
curl -s -X POST "${BASE_URL}/api/v1/eventos" \
  -H "Authorization: Bearer ${CLUB_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"id_externo\": \"EVT-BOCA-FUT-PUB-01\",
    \"titulo\": \"Boca Juniors vs. Vélez Sarsfield - Fecha 14\",
    \"fecha_hora\": \"${FECHA_FUT_PUB_01}\",
    \"lugar\": \"Estadio Alberto J. Armando (La Bombonera)\",
    \"tipo\": \"Partido\",
    \"descripcion\": \"Partido de Primera División.\"
  }" > /dev/null

curl -s -X POST "${BASE_URL}/api/v1/eventos" \
  -H "Authorization: Bearer ${CLUB_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"id_externo\": \"EVT-BOCA-FUT-PUB-02\",
    \"titulo\": \"Clínica Abierta de Básquetbol Infantil y Juvenil\",
    \"fecha_hora\": \"${FECHA_FUT_PUB_02}\",
    \"lugar\": \"Polideportivo Quinquela Martín\",
    \"tipo\": \"Institucional\",
    \"descripcion\": \"Entrenamiento formativo abierto a socios y familiares.\"
  }" > /dev/null

# Publicar con credenciales de Admin
curl -s -X POST "${BASE_URL}/admin/events/EVT-BOCA-FUT-PUB-01/publish" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"clase": "B"}' > /dev/null

curl -s -X POST "${BASE_URL}/admin/events/EVT-BOCA-FUT-PUB-02/publish" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"puntos": 15}' > /dev/null

echo -e "${GREEN}✓ Eventos EVT-BOCA-FUT-PUB-01 (Clase B) y 02 (15 pts) publicados con éxito.${NC}\n"

# ------------------------------------------------------------------------------
# 6. API: Cargar Asistencia Previa para EVT-BOCA-PAS-04 (HU-24)
# ------------------------------------------------------------------------------
echo -e "${BLUE}[6/7] Cargando asistencia previa de prueba para EVT-BOCA-PAS-04 vía API...${NC}"

ASISTENCIA_JSON=$(cat <<EOF
{
  "carga_id": "carga-previa-boca-04",
  "pagina": 1,
  "total_paginas": 1,
  "registros": [
    {"dni": "30111222", "numero_socio": "123456"},
    {"dni": "30222333", "numero_socio": "234567"}
  ]
}
EOF
)

curl -s -X POST "${BASE_URL}/api/v1/eventos/EVT-BOCA-PAS-04/asistencia" \
  -H "Authorization: Bearer ${CLUB_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "${ASISTENCIA_JSON}" > /dev/null

echo -e "${GREEN}✓ Asistencia de Messi y Maradona enviada vía API para EVT-BOCA-PAS-04.${NC}\n"

# ------------------------------------------------------------------------------
# 7. Verificación final de integridad y salud de los endpoints
# ------------------------------------------------------------------------------
echo -e "${BLUE}[7/7] Ejecutando verificaciones finales de la API...${NC}"

TOTAL_SOCIOS=$(curl -s -H "Authorization: Bearer ${CLUB_TOKEN}" "${BASE_URL}/api/v1/socios" | uv run python -c "import sys, json; print(len(json.load(sys.stdin)))")
EVENTOS_CLUB=$(curl -s -H "Authorization: Bearer ${CLUB_TOKEN}" "${BASE_URL}/api/v1/eventos" | uv run python -c "import sys, json; print(len(json.load(sys.stdin)))")
EVENTOS_PENDIENTES=$(curl -s -H "Authorization: Bearer ${ADMIN_TOKEN}" "${BASE_URL}/admin/events/pending" | uv run python -c "import sys, json; print(len(json.load(sys.stdin)))")
EVENTOS_ELEGIBLES=$(curl -s -H "Authorization: Bearer ${ADMIN_TOKEN}" "${BASE_URL}/admin/events/eligible-for-attendance" | uv run python -c "import sys, json; print(len(json.load(sys.stdin)))")
FRESHNESS=$(curl -s -H "Authorization: Bearer ${CLUB_TOKEN}" "${BASE_URL}/api/v1/socios/freshness" | uv run python -c "import sys, json; data=json.load(sys.stdin); print(f'Desactualizado={data.get(\"esta_desactualizado\")}')")

echo -e "  - Socios activos en padrón:         ${GREEN}${TOTAL_SOCIOS} socios${NC}"
echo -e "  - Total de eventos del club:        ${GREEN}${EVENTOS_CLUB} eventos${NC}"
echo -e "  - Eventos pendientes de definir:    ${GREEN}${EVENTOS_PENDIENTES} eventos${NC}"
echo -e "  - Eventos elegibles p/ asistencia:  ${GREEN}${EVENTOS_ELEGIBLES} eventos${NC}"
echo -e "  - Auditoría de frescura:            ${GREEN}${FRESHNESS}${NC}"

echo -e "\n${GREEN}==============================================================================${NC}"
echo -e "${GREEN}   Seed vía API completado y verificado con éxito!                         ${NC}"
echo -e "${GREEN}==============================================================================${NC}"
