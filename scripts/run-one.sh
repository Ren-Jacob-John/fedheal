#!/usr/bin/env bash
set -euo pipefail

service="${1:?Usage: scripts/run-one.sh <auth|validation|federated-server|admin|synthesis|dashboard>}"
export FEDHEAL_ENV="${FEDHEAL_ENV:-development}"

case "$service" in
  auth) python -m uvicorn main:app --app-dir server/auth --port 8001 ;;
  validation) python -m uvicorn main:app --app-dir server/validation --port 8002 ;;
  federated-server) python server/federated-server/server.py --address 0.0.0.0:8080 ;;
  admin) python -m uvicorn main:app --app-dir server/admin --port 8005 ;;
  synthesis) python -m uvicorn main:app --app-dir server/synthesis --port 8006 ;;
  dashboard) npm --prefix client/dashboard run dev ;;
  *) echo "Unknown service: $service" >&2; exit 2 ;;
esac
