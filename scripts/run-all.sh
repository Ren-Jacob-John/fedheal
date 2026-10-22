#!/usr/bin/env bash
set -euo pipefail

export FEDHEAL_ENV="${FEDHEAL_ENV:-development}"
for service in auth validation admin synthesis dashboard; do
  scripts/run-one.sh "$service" >"${service}.log" 2>&1 &
  echo "Started $service (pid $!)"
done
echo "Use scripts/run-one.sh federated-server to start the optional Flower server."
