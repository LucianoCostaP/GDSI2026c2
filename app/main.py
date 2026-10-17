from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .config import settings
from .db import engine
from .routers import admin_accounts, auth, member_auth

app = FastAPI(title="Pasión de 10 API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.front_origin],
    allow_methods=["*"],
    allow_headers=["*"],
    # El front lo usa para mostrar cuánto falta para reenviar un código o salir del bloqueo.
    expose_headers=["Retry-After"],
)
app.include_router(auth.router)
app.include_router(member_auth.router)
app.include_router(admin_accounts.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict[str, str]:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ready"}
