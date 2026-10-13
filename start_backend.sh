#!/usr/bin/env bash
# macOS / Linux: create the venv (first run), install requirements, start the backend on http://127.0.0.1:8000
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3.12}"; command -v "$PY" >/dev/null 2>&1 || PY=python3
if [ ! -d backend/venv ]; then
  echo "[AIRCONTROL] Creating virtual environment with $($PY --version) ..."
  "$PY" -m venv backend/venv
fi
source backend/venv/bin/activate
pip install -q -r backend/requirements.txt
echo "[AIRCONTROL] Backend starting on http://127.0.0.1:8000  (Ctrl+C to stop)"
exec python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
