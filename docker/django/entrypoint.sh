#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

postgres_ready() {
  python - "$TABCHAIN_POSTGRES_DB" "$TABCHAIN_POSTGRES_USER" "$TABCHAIN_POSTGRES_PASSWORD" "$TABCHAIN_POSTGRES_HOST" "$TABCHAIN_POSTGRES_PORT" <<'PY'
import sys, time
from time import sleep
try:
    import psycopg2
except Exception as e:
    print("psycopg2 not installed; exiting", file=sys.stderr)
    sys.exit(1)

dbname, user, pwd, host, port = sys.argv[1:]
try:
    psycopg2.connect(dbname=dbname, user=user, password=pwd, host=host, port=port, connect_timeout=3)
except Exception:
    sys.exit(2)
sys.exit(0)
PY
}

: "${TABCHAIN_POSTGRES_HOST:=db}"
: "${TABCHAIN_POSTGRES_PORT:=5432}"
: "${TABCHAIN_POSTGRES_DB:=postgres}"
: "${TABCHAIN_POSTGRES_USER:=postgres}"
: "${TABCHAIN_POSTGRES_PASSWORD:=postgres}"

# Wait for Postgres to be ready
echo "Waiting for Postgres at ${TABCHAIN_POSTGRES_HOST}:${TABCHAIN_POSTGRES_PORT}..."
TRIES=0
until postgres_ready; do
  TRIES=$((TRIES+1))
  if [ $TRIES -ge 60 ]; then
    echo "Postgres did not become available after $TRIES attempts; exiting"
    exit 1
  fi
  sleep 1
done
echo "Postgres is available."

# Only run migrations and collectstatic in production or when asked
if [ "${DJANGO_ENV:-development}" = "production" ] || [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  echo "Apply migrations..."
  python manage.py makemigrations --no-input || true
  python manage.py makemigrations game
  python manage.py migrate --no-input

  echo "Collect static files..."
  # python manage.py collectstatic --noinput
fi

# Optionally compile messages
if [ "${COMPILE_MESSAGES:-0}" = "1" ]; then
  python manage.py compilemessages || true
fi

# Allow overriding the final command
if [ "$#" -gt 0 ]; then
  exec "$@"
else
  # Default: development uses runserver; production Dockerfile sets CMD to gunicorn
  if [ "${DJANGO_ENV:-production}" = "development" ]; then
    exec python manage.py runserver 0.0.0.0:8000
  else
    exec gunicorn project.wsgi:application --bind 0.0.0.0:8000 --workers "${GUNICORN_WORKERS:-3}" --timeout "${GUNICORN_TIMEOUT:-120}"
  fi
fi
