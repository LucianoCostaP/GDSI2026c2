#!/bin/sh
set -e

echo "==> [Entrypoint] Aplicando migraciones con Alembic..."
alembic upgrade head

# Los seeds se niegan a correr con APP_ENV=production (lo que pone render.yaml). Este despliegue
# es el entorno de demo, así que se les pasa APP_ENV=local solo a ellos; el servidor sigue en
# production. Para no cargar datos de prueba, poner SEED_ON_STARTUP=false en Render.
if [ "${SEED_ON_STARTUP:-true}" = "true" ]; then
    echo "==> [Entrypoint] Cargando datos iniciales (app.seed)..."
    APP_ENV=local python -m app.seed || echo "Aviso: app.seed ya fue aplicado o falló sin bloquear."

    if [ "${SEED_SIMULATOR_ON_STARTUP:-true}" = "true" ]; then
        echo "==> [Entrypoint] Cargando datos para simulador (app.seed_simulator)..."
        APP_ENV=local python -m app.seed_simulator || echo "Aviso: app.seed_simulator ya fue aplicado o falló sin bloquear."
    fi
fi

echo "==> [Entrypoint] Creando primer admin si no existe (app.bootstrap)..."
python -m app.bootstrap || echo "Aviso: app.bootstrap ya fue ejecutado o no se pudo aplicar."

echo "==> [Entrypoint] Iniciando servidor Uvicorn en el puerto ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --forwarded-allow-ips='*'
