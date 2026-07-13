#!/bin/sh
set -e
exec uvicorn harness.ui:create_app \
    --factory \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers "${WORKERS:-1}" \
    --log-level "${LOG_LEVEL:-info}"
