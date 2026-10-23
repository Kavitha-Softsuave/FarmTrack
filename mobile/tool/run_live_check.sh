#!/usr/bin/env bash
# Live contract check (CI / Linux / macOS / Git Bash): starts the real backend OFFLINE on 127.0.0.1:$PORT, runs
# `flutter test test_live` against it and stops it again, also on failure or interrupt.
#
#   mobile/tool/run_live_check.sh                 # port 8765, apple scab hint on
#   PORT=8770 NO_HINTS=1 mobile/tool/run_live_check.sh
#
# Nothing leaves the machine and the real API key is never used: every provider is set explicitly, the keys are empty, the
# database and photo folder are temporary, and the server starts through a launcher that switches the repo .env file off.
set -u

PORT_GIVEN="${PORT:-}"
PORT="${PORT:-8765}"
HINTS="${HINTS:-Apple=Apple___Apple_scab:0.9}"
START_TIMEOUT="${START_TIMEOUT:-90}"

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mobile="$(cd "$here/.." && pwd)"
root="$(cd "$mobile/.." && pwd)"
backend="$root/backend"

if [ -x "$backend/.venv/Scripts/python.exe" ]; then
  python="$backend/.venv/Scripts/python.exe"
elif [ -x "$backend/.venv/bin/python" ]; then
  python="$backend/.venv/bin/python"
else
  python="${PYTHON:-python3}"   # CI: dependencies installed into the active interpreter
fi

use_hints=0
if [ -z "${NO_HINTS:-}" ] && grep -q "demo_disease_hints" "$backend/app/config.py"; then
  use_hints=1
elif [ -z "${NO_HINTS:-}" ]; then
  echo "WARNING: this backend has no DEMO_DISEASE_HINTS setting yet: disease results will be 'not sure / expert'." >&2
fi

# Another program on the port would make the test talk to something else. 8765 is the default; when it is taken and no PORT
# was given, the next free one is used.
port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }
if port_busy "$PORT"; then
  if [ -n "${PORT_GIVEN:-}" ]; then echo "port $PORT is already in use; pass another PORT" >&2; exit 2; fi
  for candidate in $(seq "$((PORT + 1))" "$((PORT + 40))"); do
    if ! port_busy "$candidate"; then echo "WARNING: port $PORT is in use by another program; using $candidate instead" >&2; PORT="$candidate"; break; fi
  done
  if port_busy "$PORT"; then echo "no free port found" >&2; exit 2; fi
fi

temp="$(mktemp -d "${TMPDIR:-/tmp}/farmtrack-live-XXXXXX")"
server_pid=""
exit_code=1

cleanup() {
  if [ -n "$server_pid" ] && kill -0 "$server_pid" 2>/dev/null; then
    kill "$server_pid" 2>/dev/null
    for _ in 1 2 3 4 5 6 7 8 9 10; do kill -0 "$server_pid" 2>/dev/null || break; sleep 0.5; done
    kill -9 "$server_pid" 2>/dev/null
  fi
  if [ "$exit_code" -eq 0 ]; then rm -rf "$temp"; else echo "Server logs kept in $temp"; fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM

db_path="$temp/live.db"
case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) db_path="$(cygpath -m "$db_path")"; storage="$(cygpath -m "$temp/storage")" ;; *) storage="$temp/storage" ;; esac

export ENV=dev LLM_PROVIDER=mock OPENAI_API_KEY= TTS_PROVIDER=null GOOGLE_TTS_API_KEY= \
  EMBEDDINGS_PROVIDER=hash VECTOR_STORE=memory PUSH_PROVIDER=log ZOHO_PROVIDER=mock IOT_PROVIDER=mock WEATHER_PROVIDER=csv \
  CROP_ID_PROVIDER=stub DISEASE_PROVIDER=stub FCM_CREDENTIALS_FILE= ALERT_SCHEDULER=0
export DATABASE_URL="sqlite:///$db_path" STORAGE_DIR="$storage"
export DEMO_PASSWORD=farm1234 OTP_LOGIN_ENABLED=false   # the live login is f001 / farm1234, never an OTP
if [ "$use_hints" -eq 1 ]; then export DEMO_DISEASE_HINTS="$HINTS"; else export DEMO_DISEASE_HINTS=; fi

launcher="from app.config import Settings; Settings.model_config['env_file'] = None; import uvicorn; uvicorn.run('app.main:app', host='127.0.0.1', port=$PORT, log_level='warning')"

echo "Starting the offline backend on http://127.0.0.1:$PORT (hints: $([ "$use_hints" -eq 1 ] && echo "$HINTS" || echo off))"
(cd "$backend" && exec "$python" -c "$launcher") >"$temp/server.out.log" 2>"$temp/server.err.log" &
server_pid=$!

healthy=0
for _ in $(seq 1 "$((START_TIMEOUT * 2))"); do
  kill -0 "$server_pid" 2>/dev/null || break
  if curl -s -f -o /dev/null --max-time 2 "http://127.0.0.1:$PORT/health"; then healthy=1; break; fi
  sleep 0.5
done
if [ "$healthy" -ne 1 ]; then
  echo "--- server log (last lines) ---"
  tail -n 25 "$temp/server.out.log" "$temp/server.err.log" 2>/dev/null
  echo "the backend did not become healthy" >&2
  exit 1
fi

echo "Backend is up. Running flutter test test_live ..."
cd "$mobile" || exit 1
flutter test test_live --reporter expanded \
  "--dart-define=LIVE_API_URL=http://127.0.0.1:$PORT" "--dart-define=LIVE_HINTS=$([ "$use_hints" -eq 1 ] && echo true || echo false)"
exit_code=$?

if [ "$exit_code" -eq 0 ]; then echo "LIVE CHECK PASSED"; else echo "LIVE CHECK FAILED (exit code $exit_code)"; fi
exit "$exit_code"
