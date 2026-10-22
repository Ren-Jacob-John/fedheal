#!/usr/bin/env bash
set -u

paths=(server/auth server/validation server/federated-server hospital-node server/model-zoo server/condition-router server/admin server/synthesis)
failed=0
for path in "${paths[@]}"; do
  echo "=== $path ==="
  (cd "$path" && python -m pytest -q) || failed=$((failed + 1))
done
exit "$failed"
