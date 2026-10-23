#!/bin/sh
# FarmTrack API container entrypoint: bring the database schema up to date, then start the server (the CMD).
#   AUTO_MIGRATE=1 (default in the image)  run `alembic upgrade head` first; retry while the database is still starting
#   AUTO_MIGRATE=0                         skip it (several replicas: run the migration once from the deploy step)
set -eu

if [ "${AUTO_MIGRATE:-1}" = "1" ]; then
    attempt=1
    max_attempts="${MIGRATE_ATTEMPTS:-10}"
    until python -m alembic upgrade head; do
        if [ "$attempt" -ge "$max_attempts" ]; then
            echo "database migration failed after $attempt attempts, not starting the server" >&2
            exit 1
        fi
        attempt=$((attempt + 1))
        echo "database not ready or migration failed, retrying in 3 s (attempt $attempt of $max_attempts)" >&2
        sleep 3
    done
fi

exec "$@"
