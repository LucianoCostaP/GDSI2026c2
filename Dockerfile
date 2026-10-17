FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
ENV PATH="/app/.venv/bin:$PATH"
CMD ["sh", "-c", "alembic upgrade head && python -m app.bootstrap && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --forwarded-allow-ips='*'"]