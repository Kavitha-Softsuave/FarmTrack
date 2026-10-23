# syntax=docker/dockerfile:1.7
# FarmTrack API image. Build with the named contexts for the shared data (the build context is ./backend only):
#   docker build -t farmtrack-api:dev --build-context data=../data --build-context voice=../voice .
# (docker-compose.yml and `make docker-build` do this for you.)

# ---------------------------------------------------------------- builder: dependencies only, into a virtualenv
FROM python:3.13-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY pyproject.toml ./
# Extras baked into the image: pg (PostgreSQL driver, pgvector) and fcm (cryptography, for PUSH_PROVIDER=fcm). Not ml (torch).
ARG EXTRAS="pg fcm"
RUN python -m venv /opt/venv \
 && python -c "import sys, tomllib; p = tomllib.load(open('pyproject.toml', 'rb'))['project']; print('\n'.join(p['dependencies'] + [d for e in sys.argv[1:] for d in p['optional-dependencies'][e]]))" $EXTRAS > requirements.txt \
 && /opt/venv/bin/pip install -r requirements.txt

# ---------------------------------------------------------------- runtime
FROM python:3.13-slim
# ENV=prod is the image's default so a deployment that forgets to set it fails closed (start-up refuses the development
# secrets) instead of running with the fixed development login code. A local demo sets ENV=dev in ../.env on purpose.
ENV PYTHONDONTWRITEBYTECODE=1 \
    ENV=prod \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    DATA_DIR=/data \
    VOICE_DIR=/voice \
    STORAGE_DIR=/app/storage \
    AUTO_MIGRATE=1

# Non-root user. The app runs from /app (not installed into site-packages) so its default paths resolve: /data, /voice, /app/storage.
RUN groupadd --system --gid 10001 farmtrack \
 && useradd --system --uid 10001 --gid farmtrack --home-dir /app --shell /usr/sbin/nologin farmtrack \
 && mkdir -p /app/storage /data /voice \
 && chown -R farmtrack:farmtrack /app /data /voice

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=farmtrack:farmtrack app ./app
COPY --chown=farmtrack:farmtrack alembic.ini ./
COPY --chown=farmtrack:farmtrack migrations ./migrations
COPY --chown=farmtrack:farmtrack docker-entrypoint.sh ./
# Strip Windows line endings in case the file was checked out with CRLF (sh would choke on "set -eu\r").
RUN sed -i 's/\r$//' /app/docker-entrypoint.sh

# Reference data and demo data (named build contexts). Photos, model-test kits and scripts are not needed at run time.
COPY --from=data --chown=farmtrack:farmtrack reference /data/reference
COPY --from=data --chown=farmtrack:farmtrack weather /data/weather
COPY --from=data --chown=farmtrack:farmtrack iot/sensor_readings.csv /data/iot/sensor_readings.csv
COPY --from=data --chown=farmtrack:farmtrack mock_zoho /data/mock_zoho
COPY --from=data --chown=farmtrack:farmtrack farmers.csv demo_scenarios.json /data/
COPY --from=voice --chown=farmtrack:farmtrack . /voice

USER farmtrack
VOLUME ["/app/storage"]
EXPOSE 8000

# start-period leaves room for the migrations the entrypoint applies before the server starts.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]

# The entrypoint runs `alembic upgrade head` (unless AUTO_MIGRATE=0) and then starts the CMD below.
# One worker on purpose: the alert scheduler and the rate limiters live in the process (scale out only after moving them to a shared service).
ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
