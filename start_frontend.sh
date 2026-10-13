#!/usr/bin/env bash
# macOS / Linux: install npm packages (first run) and start the dashboard on http://127.0.0.1:5173
set -e
cd "$(dirname "$0")/frontend"
[ -d node_modules ] || npm install
exec npm run dev -- --host 127.0.0.1 --port 5173
