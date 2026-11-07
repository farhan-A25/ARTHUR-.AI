#!/bin/bash
# ============================================================
#  ARTHUR — Full App Launcher (one app, one command)
#  Owner: Mohammed Farhan
#  Reads arthur.config.json (single shared config) and starts:
#    API server + dashboard AND the CLI with 24/7 worker.
#  It also auto-writes mobile/.env so the phone app talks to
#  this same backend — everything combined, nothing to wire.
#  Usage:  bash start-arthur.sh
# ============================================================
set -e
cd "$(dirname "$0")"

API_URL=$(python3 -c "import json;print(json.load(open('arthur.config.json')).get('api_url','http://localhost:8000'))")
API_HOST=$(python3 -c "import json;print(json.load(open('arthur.config.json')).get('api_host','127.0.0.1'))")
API_PORT=$(python3 -c "import json;print(json.load(open('arthur.config.json')).get('api_port',8000))")
DEMO_MODE_CFG=$(python3 -c "import json;print(str(json.load(open('arthur.config.json')).get('demo_mode',True)).lower())")

if [ ! -d .venv ]; then
  echo ">> First run: creating virtual environment..."
  python3 -m venv .venv
fi

echo ">> Installing requirements..."
.venv/bin/pip install -q -r requirements.txt

# Combine: point the mobile app at this backend automatically.
echo "EXPO_PUBLIC_ARTHUR_API_URL=$API_URL" > mobile/.env
echo ">> Mobile app wired to backend: $API_URL"

export DEMO_MODE="${DEMO_MODE:-$DEMO_MODE_CFG}"

echo ">> Starting ARTHUR API + dashboard at $API_URL ..."
.venv/bin/python -m uvicorn backend.api.server:app --host "$API_HOST" --port "$API_PORT" &
API_PID=$!
trap "kill $API_PID 2>/dev/null" EXIT INT TERM
sleep 2

echo ">> Dashboard: $API_URL"
echo ">> Starting ARTHUR console (worker included). Type /quit to stop everything."
echo ""
DEMO_MODE="$DEMO_MODE" .venv/bin/python backend/main.py
