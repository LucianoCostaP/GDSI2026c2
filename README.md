# Pasión de 10

Sistema para que un club calcule un ranking de sus socios según su participación (asistencia a eventos, actividades, antigüedad) y lo use para ordenar el acceso por oleadas.

## Stack

- **Back:** Python 3.12 con FastAPI, SQLAlchemy 2 y migraciones con Alembic. Dependencias manejadas con uv.
- **Base de datos:** PostgreSQL 16 (Docker en local, Neon en producción).
- **Hosting:** Render, con el Blueprint de `render.yaml`.
- **Integración continua:** GitHub Actions con ruff, mypy, migraciones y pytest.

## Estructura

| Ruta | Contenido |
|---|---|
| `app/` | Código del back |
| `alembic/` | Migraciones de la base |
| `tests/` | Tests |
| `specs/` | Specs funcionales de cada historia y documentos compartidos ([índice](specs/README.md)) |
| `docs/roadmap.md` | [Qué falta para pasar del spec al código y en qué orden](docs/roadmap.md) |
| `docs/bootstrap.md` | [Pasos manuales de infraestructura](docs/bootstrap.md) |

## Cómo levantar el proyecto

### Requisitos

Solo hay que instalar dos cosas. El resto lo instalan ellas.

| Qué | Versión | Cómo se instala | Cómo verificar |
|---|---|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Con Docker Compose v2 (el comando es `docker compose`, sin guion) | Descargarlo de la web | `docker compose version` |
| [uv](https://docs.astral.sh/uv/) | Una reciente (el proyecto no fija versión) | `brew install uv` | `uv --version` |

Lo que **no** hace falta instalar a mano:

| Qué | Versión | Quién lo instala |
|---|---|---|
| Python | 3.12 (fijada en `.python-version`) | uv, en el paso 3 |
| Dependencias de Python (FastAPI, SQLAlchemy, Alembic, etc.) | Las exactas de `uv.lock` | uv, en el paso 3 |
| PostgreSQL | 16 | Docker, en el paso 2 |
| Mailpit | La última | Docker, en el paso 2 |

### Pasos

1. Iniciar el daemon de Docker (Docker Desktop).
2. Levantar la base de datos (Postgres) y Mailpit:
   ```bash
   docker compose up -d
   docker compose ps   # db y mailpit tienen que aparecer como "healthy"
   ```
3. Instalar las dependencias (la primera vez y cada vez que cambie `uv.lock`):
   ```bash
   uv sync
   ```
4. Aplicar las migraciones:
   ```bash
   uv run alembic upgrade head
   ```
5. Levantar el back:
   ```bash
   uv run uvicorn app.main:app --reload
   ```
6. Verificar:
   - http://localhost:8000/healthz → `{"status":"ok"}`
   - http://localhost:8000/readyz → `{"status":"ready"}` (el back llega a la base)
   - http://localhost:8000/docs → documentación de la API
   - http://localhost:8025 → bandeja de Mailpit, donde llegan los correos en local

No hace falta un `.env`: los valores por defecto de `app/config.py` coinciden con los de `docker-compose.yml`.

**Tests y chequeos** (los mismos que corre la integración continua):
```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest
```

**Para apagar todo:** Ctrl+C en la terminal del back y `docker compose down`. Los datos de la base se conservan.

**Si falla con `role "app" does not exist`:** hay otro Postgres ocupando el puerto 5432, por lo general uno instalado con Homebrew. Apagarlo con `brew services stop postgresql@14` (o la versión que tengas) y volver al paso 2.
