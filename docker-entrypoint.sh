#!/bin/sh
set -e

if [ ! -f "${DATABASE:-/app/data/app.db}" ]; then
    echo "[entrypoint] database not found, running init_db..."
    python scripts/init_db.py
fi

exec gunicorn --bind "0.0.0.0:${PORT:-8000}" --workers 2 "app:create_app()"
