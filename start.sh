#!/usr/bin/env bash
# macOS / Linux: start backend + frontend and open the dashboard
cd "$(dirname "$0")"
./start_backend.sh &
BACK=$!
trap 'kill $BACK 2>/dev/null' EXIT
echo "[AIRCONTROL] Waiting for the backend (first run installs packages) ..."
for i in $(seq 1 300); do curl -fs http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 1; done
( sleep 4; open http://127.0.0.1:5173 2>/dev/null || xdg-open http://127.0.0.1:5173 2>/dev/null ) &
./start_frontend.sh
