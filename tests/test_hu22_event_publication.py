"""
Suite de pruebas exhaustiva para HU-22: Definición de Importancia y Publicación de Eventos.
(Feature: Define Event Class or Points and Publish)

Cubre:
- Escenario 1: Listado de eventos pendientes con tiempo restante y deadline (FR-001).
- Escenario 2: Publicación manual de un Partido definiendo su clase (A, B o C) y verificación en HU-17 (FR-002, FR-003).
- Escenario 3: Selector de clases con significados, demanda y factores de ponderación (FR-002, SC-002).
- Escenario 4: Publicación manual de Evento Institucional definiendo puntos (1 a 100) y validaciones de exclusividad (FR-002).
- Escenario 5: Antelación mínima de 48 horas obligatoria para publicación manual (FR-004, SC-004).
- Escenario 6: Publicación automática al alcanzar el deadline con valores predeterminados (Clase B y 20 puntos) (FR-005, SC-001, SC-002).
- Escenario 7: Evento publicado antes del deadline no es republicado automáticamente (FR-006, SC-003).
- Escenario 8 & 9: Transición atómica y exclusiva (409 Conflict si ya fue publicado, sin cambios posteriores) (FR-006, FR-008, SC-003).
- Edge Cases:
  - Aritmética de deadline: evento que comienza 60h tras importación tiene deadline a las 12h.
  - Antelación de 48h perdida al momento de publicación automática (omisión segura).
  - Eventos históricos y descartados no aparecen en pendientes.
- Seguridad y Autorización:
  - Sin token -> 401 Unauthorized.
  - Rol Socio -> 403 Forbidden.
  - Rol Admin -> 200 OK.
"""

import threading
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.exceptions import EventoYaPublicadoError
from app.db import SessionLocal
from app.models import AuditLog, FeeStatus, User
from app.repositories.factory import get_evento_repository
from app.repositories.postgres_repo import PostgresEventoRepository
from app.schemas.eventos import EventoCreateRequest
from tests.conftest import MakeMember, Outbox, admin_token, bearer, member_token

BOCA_ID = "11111111-1111-1111-1111-111111111111"
RIVER_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def socio_boca(make_member: MakeMember) -> tuple[User, str]:
    return make_member(activated=True, fee_status=FeeStatus.UP_TO_DATE)


def auditoria_de(db: Session, id_interno: str) -> list[AuditLog]:
    return list(
        db.scalars(
            select(AuditLog).where(
                AuditLog.entity == "event", AuditLog.entity_id == id_interno
            )
        )
    )


# ==============================================================================
# SEGURIDAD Y CONTROL DE ACCESO
# ==============================================================================
def test_seguridad_sin_autenticacion_retorna_401(client: TestClient):
    """Peticiones sin autenticación a endpoints admin retornan 401."""
    res_pending = client.get("/admin/events/pending")
    assert res_pending.status_code == 401

    res_classes = client.get("/admin/events/classes")
    assert res_classes.status_code == 401

    res_publish = client.post(
        "/admin/events/EVT-01/publish",
        json={"clase": "A"},
    )
    assert res_publish.status_code == 401


def test_seguridad_rol_socio_prohibido_retorna_403(
    client: TestClient, outbox: Outbox, socio_boca
):
    """Un usuario con rol socio (MEMBER) no puede acceder a endpoints admin (403 Forbidden)."""
    token = member_token(client, outbox, socio_boca)
    headers = bearer(token)

    res_pending = client.get("/admin/events/pending", headers=headers)
    assert res_pending.status_code == 403

    res_classes = client.get("/admin/events/classes", headers=headers)
    assert res_classes.status_code == 403

    res_publish = client.post(
        "/admin/events/EVT-01/publish",
        json={"clase": "A"},
        headers=headers,
    )
    assert res_publish.status_code == 403


# ==============================================================================
# ESCENARIO 3: SELECTOR DE CLASES (FR-002, SC-002)
# ==============================================================================
def test_escenario_3_selector_de_clases(
    client: TestClient, outbox: Outbox, admin: User
):
    """
    Escenario 3:
    Muestra las clases A, B y C con su significado, su factor y la aclaración
    de que un factor mayor premia la asistencia a partidos de menor convocatoria.
    """
    token = admin_token(client, outbox, admin)
    res = client.get("/admin/events/classes", headers=bearer(token))
    assert res.status_code == 200

    data = res.json()
    assert len(data) == 3

    clases = {c["clase"]: c for c in data}
    assert "A" in clases
    assert "B" in clases
    assert "C" in clases

    # Clase A: alta demanda, factor 1.0, no default
    assert clases["A"]["factor"] == 1.0
    assert clases["A"]["demanda"] == "alta"
    assert not clases["A"]["es_default"]
    assert "premia la asistencia" in clases["A"]["descripcion"].lower()

    # Clase B: regular demanda, factor 1.3, default del sistema
    assert clases["B"]["factor"] == 1.3
    assert clases["B"]["demanda"] == "regular"
    assert clases["B"]["es_default"] is True

    # Clase C: baja demanda, factor 1.8, no default
    assert clases["C"]["factor"] == 1.8
    assert clases["C"]["demanda"] == "baja"
    assert not clases["C"]["es_default"]


# ==============================================================================
# ESCENARIO 1: LISTADO DE EVENTOS PENDIENTES Y DEADLINES (FR-001)
# ==============================================================================
def test_escenario_1_listado_pendientes_con_tiempo_restante(
    db: Session, client: TestClient, outbox: Outbox, admin: User
):
    """
    Escenario 1:
    Admin abre la lista de pendientes y ve todos los eventos con el tiempo
    restante para su deadline de publicación.
    """
    token = admin_token(client, outbox, admin)
    repo = get_evento_repository(db)

    ahora = datetime.now(UTC)
    # Evento a disputarse en 72 horas (creado ahora)
    # Deadline = min(ahora + 24h, (ahora + 72h) - 48h) = ahora + 24h
    req = EventoCreateRequest(
        id_externo="EVT-PEND-1",
        titulo="Boca vs Racing",
        fecha_hora=ahora + timedelta(hours=72),
        lugar="La Bombonera",
        tipo="Partido",
    )
    id_interno = repo.insert_pendiente(club_id=BOCA_ID, evento=req)

    res = client.get("/admin/events/pending", headers=bearer(token))
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1

    ev = items[0]
    assert ev["id_interno"] == id_interno
    assert ev["id_externo"] == "EVT-PEND-1"
    assert ev["titulo"] == "Boca vs Racing"
    assert ev["tipo"] == "Partido"
    assert not ev["plazo_expirado"]
    # Los segundos restantes deben ser cercanos a 24 horas (86400 seg)
    assert 86300 <= ev["segundos_restantes_deadline"] <= 86400


def test_listado_pendientes_paginado(
    db: Session, client: TestClient, outbox: Outbox, admin: User
):
    """Cross-cutting §6: las listas del Admin están paginadas (limit/offset y X-Total-Count)."""
    token = admin_token(client, outbox, admin)
    repo = get_evento_repository(db)
    ahora = datetime.now(UTC)
    # Inicio a 50h, 60h y 70h: deadlines a 2h, 12h y 22h (orden de la lista)
    for i, horas in enumerate((70, 50, 60)):
        repo.insert_pendiente(
            club_id=BOCA_ID,
            evento=EventoCreateRequest(
                id_externo=f"EVT-PAG-{i}",
                titulo=f"Partido {horas}h",
                fecha_hora=ahora + timedelta(hours=horas),
                lugar="L",
                tipo="Partido",
            ),
        )

    pagina_1 = client.get(
        "/admin/events/pending", params={"limit": 2}, headers=bearer(token)
    )
    assert pagina_1.status_code == 200
    assert pagina_1.headers["X-Total-Count"] == "3"
    assert [e["titulo"] for e in pagina_1.json()] == ["Partido 50h", "Partido 60h"]

    pagina_2 = client.get(
        "/admin/events/pending",
        params={"limit": 2, "offset": 2},
        headers=bearer(token),
    )
    assert pagina_2.headers["X-Total-Count"] == "3"
    assert [e["titulo"] for e in pagina_2.json()] == ["Partido 70h"]

    fuera_de_rango = client.get(
        "/admin/events/pending", params={"limit": 501}, headers=bearer(token)
    )
    assert fuera_de_rango.status_code == 422


def test_escenario_1_eventos_historicos_no_se_listan_como_pendientes(
    db: Session, client: TestClient, outbox: Outbox, admin: User
):
    """Los eventos históricos o descartados no deben aparecer en la lista de pendientes."""
    token = admin_token(client, outbox, admin)
    repo = get_evento_repository(db)

    # Evento histórico
    req = EventoCreateRequest(
        id_externo="EVT-HIST-1",
        titulo="Partido Pasado 2020",
        fecha_hora=datetime(2020, 1, 1, 12, 0, tzinfo=UTC),
        lugar="La Bombonera",
        tipo="Historico",
        es_historico=True,
    )
    repo.insert_pendiente(
        club_id=BOCA_ID, evento=req, estado="Historico", es_historico=True
    )

    res = client.get("/admin/events/pending", headers=bearer(token))
    assert res.status_code == 200
    assert len(res.json()) == 0


# ==============================================================================
# ESCENARIOS 2, 4: PUBLICACIÓN MANUAL (PARTIDO E INSTITUCIONAL) Y HU-17 (FR-002, FR-003)
# ==============================================================================
def test_escenario_2_publicacion_manual_partido_con_clase_visible_en_hu17(
    db: Session, client: TestClient, outbox: Outbox, admin: User, socio_boca
):
    """
    Escenario 2:
    Admin elige la clase A de un Partido pendiente y publica.
    El evento pasa a 'published' y se vuelve visible para los socios en HU-17.
    """
    token_admin = admin_token(client, outbox, admin)
    token_socio = member_token(client, outbox, socio_boca)
    repo = get_evento_repository(db)

    # 1. Crear evento pendiente a 96 horas en el futuro
    req = EventoCreateRequest(
        id_externo="EVT-PUB-01",
        titulo="Boca vs San Lorenzo",
        fecha_hora=datetime.now(UTC) + timedelta(hours=96),
        lugar="La Bombonera",
        tipo="Partido",
    )
    id_interno = repo.insert_pendiente(club_id=BOCA_ID, evento=req)

    # El socio no lo ve aún
    res_socio_antes = client.get("/events/upcoming", headers=bearer(token_socio))
    assert res_socio_antes.json()["total"] == 0

    # 2. Admin publica con Clase A
    res_pub = client.post(
        f"/admin/events/{id_interno}/publish",
        json={"clase": "A"},
        headers=bearer(token_admin),
    )
    assert res_pub.status_code == 200
    data_pub = res_pub.json()
    assert data_pub["id_interno"] == id_interno
    assert data_pub["clase"] == "A"
    assert data_pub["publicado_por"] == "admin"
    assert not data_pub["es_default"]

    # FR-007: queda guardado quién publicó y que la clase fue elegida
    (publicado,) = repo.find_proximos_eventos_publicados(club_id=BOCA_ID)
    assert publicado["publicado_por"] == "admin"
    assert publicado["es_default"] is False

    # Auditoría (cross-cutting §6): quién y los valores anteriores y nuevos
    (registro,) = auditoria_de(db, id_interno)
    assert registro.action == "event.published"
    assert registro.actor_user_id == admin.id
    assert registro.details["published_by"] == "admin"
    assert registro.details["before"] == {"estado": "pendiente_definicion_importancia"}
    assert registro.details["after"] == {
        "estado": "publicado",
        "clase": "A",
        "puntos": None,
    }

    # 3. El socio ahora SÍ lo ve en HU-17
    res_socio_despues = client.get("/events/upcoming", headers=bearer(token_socio))
    assert res_socio_despues.json()["total"] == 1
    ev_socio = res_socio_despues.json()["eventos"][0]
    assert ev_socio["titulo"] == "Boca vs San Lorenzo"
    assert ev_socio["tipo"] == "Partido"
    # No expone la clase del partido al socio
    assert "clase" not in ev_socio


def test_escenario_4_publicacion_manual_institucional_con_puntos(
    db: Session, client: TestClient, outbox: Outbox, admin: User, socio_boca
):
    """
    Escenario 4:
    Admin define los puntos (1 a 100) para un evento institucional y confirma.
    El evento se publica y aparece en HU-17 como 'Evento institucional/amateur'.
    """
    token_admin = admin_token(client, outbox, admin)
    token_socio = member_token(client, outbox, socio_boca)
    repo = get_evento_repository(db)

    req = EventoCreateRequest(
        id_externo="EVT-INST-01",
        titulo="Asamblea General Ordinaria",
        fecha_hora=datetime.now(UTC) + timedelta(hours=72),
        lugar="Sede Social",
        tipo="Institucional",
    )
    id_interno = repo.insert_pendiente(club_id=BOCA_ID, evento=req)

    # Publicar con 50 puntos
    res_pub = client.post(
        f"/admin/events/{id_interno}/publish",
        json={"puntos": 50},
        headers=bearer(token_admin),
    )
    assert res_pub.status_code == 200
    assert res_pub.json()["puntos"] == 50
    assert res_pub.json()["clase"] is None

    # Verificación en HU-17
    res_socio = client.get("/events/upcoming", headers=bearer(token_socio))
    assert res_socio.json()["total"] == 1
    assert res_socio.json()["eventos"][0]["tipo"] == "Evento institucional/amateur"


def test_validaciones_exclusividad_clase_y_puntos(
    db: Session, client: TestClient, outbox: Outbox, admin: User
):
    """
    Reglas de exclusividad:
    - Partido NO puede llevar puntos (422).
    - Partido DEBE llevar clase A, B o C (422).
    - Institucional NO puede llevar clase (422).
    - Institucional DEBE llevar puntos 1..100 (422).
    """
    token = admin_token(client, outbox, admin)
    repo = get_evento_repository(db)
    fh = datetime.now(UTC) + timedelta(hours=72)

    # 1. Partido con puntos -> error 422
    id_p = repo.insert_pendiente(
        club_id=BOCA_ID,
        evento=EventoCreateRequest(
            id_externo="P-1", titulo="P", fecha_hora=fh, lugar="L", tipo="Partido"
        ),
    )
    res1 = client.post(
        f"/admin/events/{id_p}/publish",
        json={"clase": "A", "puntos": 15},
        headers=bearer(token),
    )
    assert res1.status_code == 422
    assert "Los puntos no aplican" in res1.json()["detail"]["message"]

    # 2. Partido sin clase -> error 422
    res2 = client.post(
        f"/admin/events/{id_p}/publish",
        json={},
        headers=bearer(token),
    )
    assert res2.status_code == 422
    assert "Debe especificar una clase" in res2.json()["detail"]["message"]

    # 3. Institucional con clase -> error 422
    id_i = repo.insert_pendiente(
        club_id=BOCA_ID,
        evento=EventoCreateRequest(
            id_externo="I-1",
            titulo="I",
            fecha_hora=fh,
            lugar="L",
            tipo="Institucional",
        ),
    )
    res3 = client.post(
        f"/admin/events/{id_i}/publish",
        json={"clase": "B", "puntos": 20},
        headers=bearer(token),
    )
    assert res3.status_code == 422
    assert (
        "La clase solo aplica a eventos de tipo Partido"
        in res3.json()["detail"]["message"]
    )

    # 4. Institucional con puntos fuera de rango (0 o 101)
    res4 = client.post(
        f"/admin/events/{id_i}/publish",
        json={"puntos": 0},
        headers=bearer(token),
    )
    assert res4.status_code == 422


# ==============================================================================
# ESCENARIO 5: ANTELACIÓN MÍNIMA DE 48 HORAS (FR-004, SC-004)
# ==============================================================================
def test_escenario_5_antelacion_minima_48h_para_publicacion_manual(
    db: Session, client: TestClient, outbox: Outbox, admin: User
):
    """
    Escenario 5:
    La publicación manual SOLO se acepta si faltan al menos 48 horas para el inicio.
    Si faltan menos (ej. 30h), es rechazada con 422.
    """
    token = admin_token(client, outbox, admin)
    repo = get_evento_repository(db)

    # Evento con fecha a 30 horas del presente
    fh = datetime.now(UTC) + timedelta(hours=30)
    req = EventoCreateRequest(
        id_externo="EVT-SHORT-LEAD",
        titulo="Partido Demorado",
        fecha_hora=fh,
        lugar="Estadio",
        tipo="Institucional",  # Creado sin validar 48h en import
    )
    id_interno = repo.insert_pendiente(club_id=BOCA_ID, evento=req)

    res = client.post(
        f"/admin/events/{id_interno}/publish",
        json={"puntos": 20},
        headers=bearer(token),
    )
    assert res.status_code == 422
    assert "faltan menos de 48 horas" in res.json()["detail"]["message"]


# ==============================================================================
# ESCENARIOS 6, 7: PUBLICACIÓN AUTOMÁTICA POR DEADLINE (FR-005, SC-001, SC-002)
# ==============================================================================
def test_escenario_6_publicacion_automatica_con_valores_default(
    db: Session, client: TestClient, outbox: Outbox, admin: User
):
    """
    Escenario 6:
    Al llegar el deadline, los eventos se publican automáticamente:
    - Partido sin clase elegida obtiene Clase B (por defecto).
    - Evento institucional sin puntos obtiene 20 puntos (por defecto).
    - Se registra como hecho por el sistema ('system', es_default=True).
    """
    token = admin_token(client, outbox, admin)
    repo = get_evento_repository(db)

    ahora = datetime.now(UTC)
    partido_start = ahora + timedelta(hours=80)  # Faltan 80h (> 48h lead)

    # 1. Partido pendiente
    req_partido = EventoCreateRequest(
        id_externo="P-AUTO",
        titulo="Partido Auto",
        fecha_hora=partido_start,
        lugar="Estadio",
        tipo="Partido",
    )
    id_partido = repo.insert_pendiente(club_id=BOCA_ID, evento=req_partido)

    # 2. Institucional pendiente
    req_inst = EventoCreateRequest(
        id_externo="I-AUTO",
        titulo="Elecciones de Comisión",
        fecha_hora=partido_start,
        lugar="Sede",
        tipo="Institucional",
    )
    id_inst = repo.insert_pendiente(club_id=BOCA_ID, evento=req_inst)

    # 3. Disparar la publicación automática 25h después de la recepción
    # (deadline de 24h vencido, todavía faltan 55h para el inicio)
    reloj = (ahora + timedelta(hours=25)).isoformat()
    res_auto = client.post(
        "/admin/events/auto-publish",
        headers=bearer(token),
        params={"reloj_simulado": reloj},
    )
    assert res_auto.status_code == 200
    data_auto = res_auto.json()
    assert data_auto["publicados"] == 2
    assert id_partido in data_auto["eventos_publicados"]
    assert id_inst in data_auto["eventos_publicados"]

    # Verificar valores publicados
    visibles = {
        v["id_interno"]: v
        for v in repo.find_proximos_eventos_publicados(club_id=BOCA_ID)
    }
    assert visibles[id_partido]["clase"] == "B"  # Default Clase B
    assert visibles[id_inst]["puntos"] == 20  # Default 20 puntos

    # FR-007: publicado por el sistema con los valores por defecto
    for id_evt in (id_partido, id_inst):
        assert visibles[id_evt]["publicado_por"] == "system"
        assert visibles[id_evt]["es_default"] is True

    # Auditoría: sin usuario (lo hizo el sistema) y con el valor aplicado
    (registro,) = auditoria_de(db, id_partido)
    assert registro.actor_user_id is None
    assert registro.details["published_by"] == "system"
    assert registro.details["es_default"] is True
    assert registro.details["after"]["clase"] == "B"
    (registro_inst,) = auditoria_de(db, id_inst)
    assert registro_inst.details["after"]["puntos"] == 20


def test_escenario_7_evento_publicado_antes_del_deadline_no_se_republica(
    db: Session, client: TestClient, outbox: Outbox, admin: User
):
    """
    Escenario 7:
    Si el Admin publicó antes del deadline, al llegar el deadline no ocurre nada automáticamente.
    """
    token = admin_token(client, outbox, admin)
    repo = get_evento_repository(db)

    fh = datetime.now(UTC) + timedelta(hours=72)
    req = EventoCreateRequest(
        id_externo="EVT-ALREADY",
        titulo="Ya Publicado",
        fecha_hora=fh,
        lugar="L",
        tipo="Partido",
    )
    id_interno = repo.insert_pendiente(club_id=BOCA_ID, evento=req)

    # 1. Admin publica manualmente con Clase C
    res_pub = client.post(
        f"/admin/events/{id_interno}/publish",
        json={"clase": "C"},
        headers=bearer(token),
    )
    assert res_pub.status_code == 200

    # 2. Se ejecuta auto-publish (incluso simulando tiempo futuro)
    sim_time = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    res_auto = client.post(
        f"/admin/events/auto-publish?reloj_simulado={sim_time}",
        headers=bearer(token),
    )
    assert res_auto.status_code == 200
    assert res_auto.json()["publicados"] == 0


# ==============================================================================
# ESCENARIOS 8, 9: ATOMICIDAD E INMUTABILIDAD TRAS PUBLICACIÓN (FR-006, FR-008, SC-003)
# ==============================================================================
def test_escenario_8_y_9_no_se_puede_publicar_dos_veces_409_conflict(
    db: Session, client: TestClient, outbox: Outbox, admin: User
):
    """
    Escenarios 8 y 9:
    - Transición atómica y exclusiva.
    - No se puede cambiar la clase o puntos tras haber sido publicado (409 Conflict).
    """
    token = admin_token(client, outbox, admin)
    repo = get_evento_repository(db)

    fh = datetime.now(UTC) + timedelta(hours=80)
    req = EventoCreateRequest(
        id_externo="EVT-ATOMIC",
        titulo="Partido Único",
        fecha_hora=fh,
        lugar="L",
        tipo="Partido",
    )
    id_interno = repo.insert_pendiente(club_id=BOCA_ID, evento=req)

    # Primera publicación -> 200 OK
    res1 = client.post(
        f"/admin/events/{id_interno}/publish",
        json={"clase": "A"},
        headers=bearer(token),
    )
    assert res1.status_code == 200

    # Segunda publicación (intento concurrente o cambio) -> 409 Conflict
    res2 = client.post(
        f"/admin/events/{id_interno}/publish",
        json={"clase": "B"},
        headers=bearer(token),
    )
    assert res2.status_code == 409
    assert "ya ha sido publicado previamente" in res2.json()["detail"]["message"]

    # FR-008: la clase no cambió y hay una sola publicación auditada
    (publicado,) = repo.find_proximos_eventos_publicados(club_id=BOCA_ID)
    assert publicado["clase"] == "A"
    assert len(auditoria_de(db, id_interno)) == 1


@pytest.mark.skipif(
    settings.db_engine.lower() != "postgres",
    reason="La carrera entre transacciones solo existe en PostgreSQL",
)
def test_escenario_8_publicaciones_simultaneas_solo_una_tiene_efecto():
    """
    Escenario 8 (FR-006, SC-003): dos publicaciones del mismo evento en
    transacciones simultáneas. La segunda espera el bloqueo de la fila, no
    encuentra el evento pendiente y no publica nada ni pisa la clase.
    """
    with SessionLocal() as s0:
        id_interno = PostgresEventoRepository(s0).insert_pendiente(
            club_id=BOCA_ID,
            evento=EventoCreateRequest(
                id_externo="EVT-CARRERA",
                titulo="Partido en carrera",
                fecha_hora=datetime.now(UTC) + timedelta(hours=80),
                lugar="L",
                tipo="Partido",
            ),
        )
        s0.commit()

    resultado: list[object] = []

    def segunda_publicacion() -> None:
        with SessionLocal() as s2:
            try:
                PostgresEventoRepository(s2).publish_evento(
                    club_id=None, id_externo_o_interno=id_interno, clase="C"
                )
                s2.commit()
                resultado.append("publicado")
            except EventoYaPublicadoError as err:
                resultado.append(err)

    with SessionLocal() as s1:
        # La primera toma la fila y todavía no confirma
        PostgresEventoRepository(s1).publish_evento(
            club_id=None, id_externo_o_interno=id_interno, clase="A"
        )
        hilo = threading.Thread(target=segunda_publicacion)
        hilo.start()
        hilo.join(timeout=0.5)
        assert hilo.is_alive(), "la segunda publicación debería esperar el bloqueo"
        s1.commit()
    hilo.join(timeout=5)

    assert len(resultado) == 1
    assert isinstance(resultado[0], EventoYaPublicadoError)
    with SessionLocal() as s3:
        (publicado,) = [
            e
            for e in PostgresEventoRepository(s3).find_proximos_eventos_publicados(
                club_id=BOCA_ID
            )
            if e["id_interno"] == id_interno
        ]
    assert publicado["clase"] == "A"


def test_reloj_simulado_se_ignora_en_produccion(
    db: Session,
    client: TestClient,
    outbox: Outbox,
    admin: User,
    monkeypatch: pytest.MonkeyPatch,
):
    """En producción manda el reloj del servidor: el reloj simulado no adelanta el deadline."""
    token = admin_token(client, outbox, admin)
    repo = get_evento_repository(db)
    ahora = datetime.now(UTC)
    repo.insert_pendiente(
        club_id=BOCA_ID,
        evento=EventoCreateRequest(
            id_externo="EVT-PROD-CLOCK",
            titulo="Partido",
            fecha_hora=ahora + timedelta(hours=80),
            lugar="L",
            tipo="Partido",
        ),
    )
    reloj = (ahora + timedelta(hours=25)).isoformat()

    monkeypatch.setattr(settings, "app_env", "production")
    res = client.post(
        "/admin/events/auto-publish",
        headers=bearer(token),
        params={"reloj_simulado": reloj},
    )
    assert res.status_code == 200
    assert res.json()["publicados"] == 0

    monkeypatch.setattr(settings, "app_env", "local")
    res = client.post(
        "/admin/events/auto-publish",
        headers=bearer(token),
        params={"reloj_simulado": reloj},
    )
    assert res.json()["publicados"] == 1


# ==============================================================================
# EDGE CASES: ARITMÉTICA DE DEADLINE Y LEAD PERDIDO
# ==============================================================================
def test_edge_case_aritmetica_deadline_60h_start_es_12h_deadline(
    db: Session, client: TestClient, outbox: Outbox, admin: User
):
    """
    Edge case de la especificación:
    Un evento que comienza 60 horas tras la importación:
    deadline = min(creacion + 24h, fecha_hora - 48h)
             = min(0 + 24h, 60h - 48h) = 12 horas.
    Por ende, se publica automáticamente a las 12 horas de importado.
    """
    token = admin_token(client, outbox, admin)
    repo = get_evento_repository(db)

    creacion = datetime.now(UTC)
    # Comienza en 60 horas
    fh = creacion + timedelta(hours=60)
    req = EventoCreateRequest(
        id_externo="EVT-60H",
        titulo="Partido 60h",
        fecha_hora=fh,
        lugar="L",
        tipo="Partido",
    )
    id_interno = repo.insert_pendiente(club_id=BOCA_ID, evento=req)

    # Al consultar pendientes en el momento de creación:
    res = client.get("/admin/events/pending", headers=bearer(token))
    assert res.status_code == 200
    ev = res.json()[0]
    # Segundos restantes deben ser cercanos a 12 horas (43200 seg)
    assert 43100 <= ev["segundos_restantes_deadline"] <= 43200

    # Si simulamos que pasaron 12 horas (creacion + 12h, deadline exacto):
    sim_12h = (creacion + timedelta(hours=12)).isoformat()
    res_12h = client.get(
        f"/admin/events/pending?reloj_simulado={sim_12h}", headers=bearer(token)
    )
    assert res_12h.json()[0]["plazo_expirado"] is True

    # Ejecutar auto-publish en hora 12 (deadline alcanzado y 48h de antelación preservadas):
    res_auto = client.post(
        f"/admin/events/auto-publish?reloj_simulado={sim_12h}",
        headers=bearer(token),
    )
    assert res_auto.status_code == 200
    assert res_auto.json()["publicados"] == 1
    assert id_interno in res_auto.json()["eventos_publicados"]


def test_edge_case_lead_perdido_no_se_publica_automaticamente(
    db: Session, client: TestClient, outbox: Outbox, admin: User
):
    """
    Edge case:
    Si por una falla prolongada del scheduler se perdió la antelación de 48 horas
    (ej. el partido empieza en 40h), el sistema no debe publicarlo automáticamente
    con menos de 48h (SC-004: 0 eventos publicados con menos de 48h).
    """
    token = admin_token(client, outbox, admin)
    repo = get_evento_repository(db)

    # Recibido ahora, empieza en 70 horas
    ahora = datetime.now(UTC)
    req = EventoCreateRequest(
        id_externo="EVT-LOST-LEAD",
        titulo="Partido Con Lead Perdido",
        fecha_hora=ahora + timedelta(hours=70),
        lugar="L",
        tipo="Institucional",
    )
    repo.insert_pendiente(club_id=BOCA_ID, evento=req)

    # El scheduler recién corre 30h después: faltan 40h (lead de 48h perdido)
    reloj = (ahora + timedelta(hours=30)).isoformat()
    res_auto = client.post(
        "/admin/events/auto-publish",
        headers=bearer(token),
        params={"reloj_simulado": reloj},
    )
    assert res_auto.status_code == 200
    assert res_auto.json()["publicados"] == 0
    assert res_auto.json()["omitidos"] == 1
