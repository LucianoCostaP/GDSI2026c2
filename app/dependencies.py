from contextvars import ContextVar
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db, set_current_club_context
from .models.domain import Club
from .repositories.factory import get_evento_repository

# Esquema OpenAPI para Swagger UI
http_bearer = HTTPBearer(auto_error=False)

# ContextVar para propagar club_id en contextos asíncronos si se requiere
current_club_var: ContextVar[Club | None] = ContextVar("current_club_var", default=None)


def get_current_club(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(http_bearer),
    authorization: str | None = Header(None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> Club:
    """
    Valida el token Bearer del club según el contrato de la API:
    - Extrae el token desde la cabecera Authorization o Swagger UI HTTPBearer.
    - Autentica contra la base de datos PostgreSQL y fija el contexto multi-tenant 'app.current_club_id'.
    - Si el motor está configurado en memoria (tests unitarios), autentica contra el repositorio en memoria.
    - Devuelve 401 Unauthorized ante tokens faltantes, inválidos o revocados.
    """
    token: str | None = None

    if credentials and credentials.credentials:
        token = credentials.credentials
    elif authorization:
        parts = authorization.strip().split(" ")
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1].strip()
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "detail": "No autorizado: Formato de cabecera inválido. Debe ser 'Bearer <token>'.",
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Formato de autorización inválido. Debe ser 'Bearer <token>'.",
                    },
                },
            )
    else:
        # Fallback de inspección directa en request headers
        raw_header = request.headers.get("authorization") or request.headers.get(
            "Authorization"
        )
        if raw_header:
            parts = raw_header.strip().split(" ")
            if len(parts) == 2 and parts[0].lower() == "bearer":
                token = parts[1].strip()
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={
                        "detail": "No autorizado: Formato de cabecera inválido. Debe ser 'Bearer <token>'.",
                        "error": {
                            "code": "UNAUTHORIZED",
                            "message": "Formato de autorización inválido. Debe ser 'Bearer <token>'.",
                        },
                    },
                )

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "detail": "No autorizado: Cabecera Authorization no provista.",
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "Cabecera Authorization no provista.",
                },
            },
        )

    club: Club | None = None

    # 1. Búsqueda en PostgreSQL si está configurado
    if settings.db_engine.lower() == "postgres":
        try:
            club = (
                db.query(Club)
                .filter(Club.api_token == token, Club.activo == True)
                .first()
            )
            if club:
                set_current_club_context(db, club.id)
        except Exception:  # noqa: BLE001
            club = None

    # 2. Si no se encontró en DB o el motor es 'memory', buscar en el repositorio en memoria
    if not club:
        repo = get_evento_repository(db)
        club_domain = repo.get_club_by_token(token)
        if club_domain:
            club = Club(
                id=UUID(club_domain.id),
                nombre=club_domain.nombre,
                codigo_identificador=club_domain.codigo_identificador,
                api_token=club_domain.api_token,
                activo=club_domain.activo,
                creado_en=club_domain.creado_en,
            )

    if not club:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "detail": "No autorizado: Token inválido, expirado o revocado.",
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "Credenciales de club inválidas o club inactivo.",
                },
            },
        )

    current_club_var.set(club)
    return club
