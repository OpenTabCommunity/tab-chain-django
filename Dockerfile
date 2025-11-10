# Multi-stage Dockerfile for a Django app using Poetry
# - builder: installs Python deps into /venv
# - dev: development image (bind-mount code)
# - prod: production image (copies sources)

# Base (shared)
FROM python:3.11-slim-bullseye AS base
ARG UID=1000
ARG GID=1000
ARG APP_USER=appuser
ENV PATH="/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Use a non-root user and create app directories
RUN groupadd -g "${GID}" -r ${APP_USER} \
 && useradd -m -u "${UID}" -g "${GID}" -r -s /bin/bash ${APP_USER} \
 && mkdir -p /app /var/www/django/static /var/www/django/media \
 && chown -R ${APP_USER}:${APP_USER} /app /var/www/django/static /var/www/django/media

WORKDIR /app

# Install minimal apt deps required at runtime 
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates gettext \
 && rm -rf /var/lib/apt/lists/*

# Builder
FROM base as builder
ARG POETRY_VERSION=1.5.1
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_HOME="/opt/poetry"

# build dependencies
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential gcc libpq-dev curl \
 && rm -rf /var/lib/apt/lists/*

# create venv and install poetry
RUN python -m venv /venv \
 && /venv/bin/python -m pip install --upgrade pip setuptools wheel \
 && /venv/bin/python -m pip install "poetry==${POETRY_VERSION}"

# copy pyproject & lock first for cached dependency install
COPY pyproject.toml poetry.lock* /app/

# install project deps into venv (no-root ensures deps installed to /venv)
# For production container builds, pass BUILD_ENV=production to build args and set extras accordingly
ARG BUILD_ENV=development
RUN --mount=type=cache,target=/root/.cache/pip \
    if [ "${BUILD_ENV}" = "production" ]; then \
      /venv/bin/poetry install --no-dev --no-interaction --no-ansi; \
    else \
      /venv/bin/poetry install --no-interaction --no-ansi; \
    fi

# Development image 
FROM base AS dev
ENV DJANGO_ENV=development
# copy venv from builder
COPY --from=builder --chown=${APP_USER}:${APP_USER} /venv /venv

# copy entrypoint and make executable
COPY docker/django/entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
 && chown ${APP_USER}:${APP_USER} /usr/local/bin/docker-entrypoint.sh

# switch to non-root user for safety
USER ${APP_USER}
WORKDIR /app

# dev target expects source mounted into /app via docker-compose
EXPOSE 8000
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# Production image 
FROM dev AS prod
ENV DJANGO_ENV=production
# Copy application code (owned by appuser)
COPY --chown=${APP_USER}:${APP_USER} . /app

# Create an unprivileged directory for sockets/worker pids, logs
RUN mkdir -p /app/run && mkdir -p /app/log && chown -R ${APP_USER}:${APP_USER} /app/run /app/log

# Default production command: gunicorn config
# Configure number of workers via env var GUNICORN_WORKERS or auto-calc at runtime
ENV GUNICORN_BIND=0.0.0.0:8000 \
    GUNICORN_WORKERS=3 \
    GUNICORN_TIMEOUT=120

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD [ "sh", "-c", "wget -qO- --timeout=2 http://127.0.0.1:8000/healthz || exit 1" ]

# Use exec form so signals are forwarded to Gunicorn
CMD ["gunicorn", "project.wsgi:application", \
      "--bind", "0.0.0.0:8000", \
      "--workers", "${GUNICORN_WORKERS}", \
      "--timeout", "${GUNICORN_TIMEOUT}", \
      "--log-level", "info", \
      "--access-logfile", "-", \
      "--error-logfile", "-" ]
