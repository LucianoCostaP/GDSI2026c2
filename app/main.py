from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text

from .config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)

app = FastAPI(title="Pasión de 10 API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.front_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict[str, str]:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ready"}
