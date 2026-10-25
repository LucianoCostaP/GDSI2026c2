import re

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import SessionLocal
from app.mailer import get_mailer
from app.main import app
from app.models import Member, User
from app.rate_limit import identifier_limiter, ip_limiter
from tests.conftest import BOCA_HEADERS


def test_flujo_unificado_socio_carga_y_login_member():
    """
    Verifica la integración total entre la carga de socios de los clubes y el login de socios:
    1. El club Boca Juniors carga un socio nuevo a través de la API de clubes (/api/v1/socios/cargas/completa).
    2. El trigger de la base de datos sincroniza automáticamente al socio en la tabla `members`.
    3. El socio ingresa al portal y solicita su código de activación por DNI (/auth/member/activation/request).
    4. El socio verifica el código de 6 dígitos enviado a su email (/auth/member/activation/verify) activando su cuenta.
    5. El socio inicia sesión con su código OTP (/auth/member/login/request y /auth/member/login/verify) y obtiene su sesión activa.
    """
    outbox = []
    ip_limiter.reset()
    identifier_limiter.reset()
    app.dependency_overrides[get_mailer] = lambda: lambda *email: outbox.append(email)

    # Limpiar tablas de socios de clubes y datos específicos de este test
    with SessionLocal() as db:
        db.execute(
            text(
                "TRUNCATE TABLE socios_staging_completa, socios_cargas_rechazos, "
                "socios_cargas_paginas, socios_cargas, socios CASCADE;"
            )
        )
        member = db.query(Member).filter(Member.dni == "45999888").first()
        if member:
            user = db.query(User).filter(User.member_id == member.member_id).first()
            if user:
                db.execute(
                    text("DELETE FROM audit_log WHERE actor_user_id = :uid"),
                    {"uid": user.id},
                )
                db.execute(
                    text("DELETE FROM sessions WHERE user_id = :uid"), {"uid": user.id}
                )
                db.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user.id})
            db.execute(
                text("DELETE FROM access_codes WHERE member_id = :mid"),
                {"mid": member.member_id},
            )
            db.execute(
                text("DELETE FROM members WHERE member_id = :mid"),
                {"mid": member.member_id},
            )
        db.commit()

    with TestClient(app) as client:
        # 1. Carga de padrón por el club (POST /api/v1/socios/cargas/completa)
        payload = {
            "carga_id": "full-e2e-001",
            "pagina": 1,
            "total_paginas": 1,
            "socios": [
                {
                    "id_externo": "EXT-E2E-1",
                    "dni": "45999888",
                    "numero_socio": "SOC-888",
                    "nombre": "Carlos Tevez",
                    "fecha_nacimiento": "1984-02-05",
                    "fecha_alta": "2001-01-10",
                    "fecha_baja_previa": None,
                    "estado_cuota": "al_dia",
                    "email": "carlitos@example.com",
                    "distancia_km": 1.2,
                    "localidad": "Fuerte Apache",
                    "fecha_modificacion": "2026-10-20T10:00:00Z",
                }
            ],
        }

        res_club = client.post(
            "/api/v1/socios/cargas/completa", json=payload, headers=BOCA_HEADERS
        )
        assert res_club.status_code == 202, res_club.text
        data_club = res_club.json()
        assert data_club["estado"] == "exitosa"
        assert len(data_club["rechazos"]) == 0

        # 2. Verificar sincronización automática en tabla `members` vía trigger
        with SessionLocal() as db:
            member = db.query(Member).filter(Member.dni == "45999888").first()
            assert member is not None
            assert member.email == "carlitos@example.com"
            assert member.name == "Carlos Tevez"
            assert member.fee_status.value == "up_to_date"
            assert member.account_state.value == "not_activated"

        # 3. Socio pide código de activación en el portal
        res_req = client.post(
            "/auth/member/activation/request", json={"identifier": "45999888"}
        )
        assert res_req.status_code == 202, res_req.text
        req_data = res_req.json()
        challenge = req_data["challenge"]
        assert len(outbox) == 1
        assert outbox[0][0] == "carlitos@example.com"

        # Extraer código de 6 dígitos del email
        match = re.search(r"\b(\d{6})\b", outbox[0][2])
        assert match
        code = match.group(1)

        # 4. Socio verifica código de activación
        res_verify = client.post(
            "/auth/member/activation/verify",
            json={"challenge": challenge, "code": code},
        )
        assert res_verify.status_code == 204, res_verify.text

        # Verificar que el miembro quedó ACTIVATED y se creó su User
        with SessionLocal() as db:
            member = db.query(Member).filter(Member.dni == "45999888").first()
            assert member.account_state.value == "activated"
            user = db.query(User).filter(User.member_id == member.member_id).first()
            assert user is not None
            assert user.email == "carlitos@example.com"
            assert user.role.value == "member"

        # 5. Socio inicia sesión con login OTP
        res_login_req = client.post(
            "/auth/member/login/request", json={"identifier": "45999888"}
        )
        assert res_login_req.status_code == 202, res_login_req.text
        login_challenge = res_login_req.json()["challenge"]
        assert len(outbox) == 2
        match_login = re.search(r"\b(\d{6})\b", outbox[1][2])
        assert match_login
        login_code = match_login.group(1)

        res_login_verify = client.post(
            "/auth/member/login/verify",
            json={"challenge": login_challenge, "code": login_code},
        )
        assert res_login_verify.status_code == 200, res_login_verify.text
        login_data = res_login_verify.json()
        assert "token" in login_data
        assert login_data["user"]["email"] == "carlitos@example.com"
        assert login_data["user"]["name"] == "Carlos Tevez"
        assert login_data["user"]["role"] == "member"

    # Limpiar los registros creados por el test
    with SessionLocal() as db:
        member = db.query(Member).filter(Member.dni == "45999888").first()
        if member:
            user = db.query(User).filter(User.member_id == member.member_id).first()
            if user:
                db.execute(
                    text("DELETE FROM audit_log WHERE actor_user_id = :uid"),
                    {"uid": user.id},
                )
                db.execute(
                    text("DELETE FROM sessions WHERE user_id = :uid"), {"uid": user.id}
                )
                db.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user.id})
            db.execute(
                text("DELETE FROM access_codes WHERE member_id = :mid"),
                {"mid": member.member_id},
            )
            db.execute(
                text("DELETE FROM members WHERE member_id = :mid"),
                {"mid": member.member_id},
            )
        db.commit()

    app.dependency_overrides.clear()
