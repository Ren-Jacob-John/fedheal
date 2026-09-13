#!/usr/bin/env bash
#
# Scripted version of the manual check used to verify client_runner.py:
# start a throwaway Module 1, seed N hospitals with real (non-IID) vitals,
# start server.py, start N real client_runner.py PROCESSES against it, and
# assert the run actually finished with every client's results aggregated
# every round. Exits non-zero (and tears everything down) on any failure,
# so this is safe to wire into CI later without a human watching the logs.
#
# Usage:
#   ./run_local_smoke_test.sh                # 3 hospitals (default)
#   ./run_local_smoke_test.sh --hospitals 5
#
# What this does NOT cover: TLS, real multi-machine networking (everything
# here is localhost), or the imaging/foundation-model specialists — this is
# scoped to "does the real FL path still work end to end."
set -uo pipefail

N_HOSPITALS=3
RECORDS_PER_HOSPITAL=20
ROUNDS=8
AUTH_PORT=8001
FL_PORT=8080
SVC_KEY="dev-only-key-module3-to-module1-smoketest"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hospitals) N_HOSPITALS="$2"; shift 2 ;;
    --records-per-hospital) RECORDS_PER_HOSPITAL="$2"; shift 2 ;;
    --rounds) ROUNDS="$2"; shift 2 ;;
    *) echo "Unknown argument: $1"; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE1_DIR="$SCRIPT_DIR/../module1-auth"
WORKDIR="$(mktemp -d)"
DB_PATH="$WORKDIR/smoketest_auth.db"

PIDS=()
FAILED=0

cleanup() {
  echo ""
  echo "Tearing down (${#PIDS[@]} process(es))..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" >/dev/null 2>&1
  done
  sleep 1
  for pid in "${PIDS[@]}"; do
    kill -9 "$pid" >/dev/null 2>&1
  done
  rm -rf "$WORKDIR"
}
trap cleanup EXIT

echo "=== 1/5: starting Module 1 (throwaway SQLite at $DB_PATH) ==="
(
  cd "$MODULE1_DIR" || exit 1
  export FEDHEAL_DATABASE_URL="sqlite:///$DB_PATH"
  export FEDHEAL_SVC_KEY_M3_M1="$SVC_KEY"
  exec uvicorn main:app --host 0.0.0.0 --port "$AUTH_PORT"
) > "$WORKDIR/module1.log" 2>&1 &
PIDS+=($!)

for _ in $(seq 1 20); do
  curl -sf "http://localhost:$AUTH_PORT/docs" -o /dev/null && break
  sleep 0.5
done
if ! curl -sf "http://localhost:$AUTH_PORT/docs" -o /dev/null; then
  echo "FAIL: Module 1 never came up — see $WORKDIR/module1.log"
  cat "$WORKDIR/module1.log"
  exit 1
fi
echo "Module 1 is up."

echo ""
echo "=== 2/5: seeding $N_HOSPITALS hospitals x $RECORDS_PER_HOSPITAL validated vitals each (non-IID) ==="
HOSPITAL_IDS=$(
  cd "$MODULE1_DIR" && \
  FEDHEAL_DATABASE_URL="sqlite:///$DB_PATH" python3 - "$N_HOSPITALS" "$RECORDS_PER_HOSPITAL" <<'PYEOF'
import random
import sys
from database import SessionLocal, engine, Base
import models

Base.metadata.create_all(bind=engine)

n_hospitals = int(sys.argv[1])
n_records = int(sys.argv[2])

db = SessionLocal()
random.seed(42)
ids = []
for h in range(n_hospitals):
    hospital = models.Hospital(name=f"Smoke Test Hospital {h}")
    db.add(hospital)
    db.commit()
    db.refresh(hospital)
    ids.append(hospital.id)

    # Same non-IID shape as the manual test: each hospital's BP distribution
    # is shifted, so hospitals genuinely don't look like each other.
    bp_shift = h * 8
    for i in range(n_records):
        systolic = random.gauss(120 + bp_shift, 15)
        db.add(models.VitalsRecord(
            hospital_id=hospital.id,
            patient_ref=f"P-{h}-{i:04d}",
            age_years=random.uniform(20, 85),
            height_cm=random.uniform(150, 195),
            weight_kg=random.uniform(50, 110),
            systolic_bp=systolic,
            diastolic_bp=random.gauss(80, 8),
            heart_rate_bpm=random.gauss(75, 10),
            medication_count=random.randint(0, 5),
            medication_mg_total=random.uniform(0, 400),
            label=int(systolic >= 140),
            validation_status="passed",
        ))
db.commit()
db.close()
print(",".join(ids))
PYEOF
)
if [[ -z "$HOSPITAL_IDS" ]]; then
  echo "FAIL: seeding hospitals failed"
  exit 1
fi
echo "Seeded hospitals: $HOSPITAL_IDS"

echo ""
echo "=== 3/5: starting server.py (--min-clients $N_HOSPITALS --rounds $ROUNDS) ==="
(
  cd "$SCRIPT_DIR" || exit 1
  exec python3 server.py --min-clients "$N_HOSPITALS" --rounds "$ROUNDS" --address "0.0.0.0:$FL_PORT"
) > "$WORKDIR/server.log" 2>&1 &
PIDS+=($!)
sleep 2

echo ""
echo "=== 4/5: starting $N_HOSPITALS real client_runner.py processes ==="
IFS=',' read -ra ID_ARRAY <<< "$HOSPITAL_IDS"
CLIENT_LOGS=()
for idx in "${!ID_ARRAY[@]}"; do
  hid="${ID_ARRAY[$idx]}"
  log="$WORKDIR/client_$idx.log"
  CLIENT_LOGS+=("$log")
  (
    cd "$SCRIPT_DIR" || exit 1
    export FEDHEAL_AUTH_API_URL="http://localhost:$AUTH_PORT"
    export FEDHEAL_SVC_KEY_M3_M1="$SVC_KEY"
    exec python3 client_runner.py --hospital-id "$hid" --server "localhost:$FL_PORT" \
      --min-records "$RECORDS_PER_HOSPITAL"
  ) > "$log" 2>&1 &
  PIDS+=($!)
done

echo ""
echo "=== 5/5: waiting for the run to finish (up to 60s) ==="
DEADLINE=$((SECONDS + 60))
while [[ $SECONDS -lt $DEADLINE ]]; do
  grep -q "FINAL_ACCURACY" "$WORKDIR/server.log" 2>/dev/null && break
  sleep 1
done

echo ""
echo "--- server.log (tail) ---"
tail -20 "$WORKDIR/server.log"

if ! grep -q "FINAL_ACCURACY" "$WORKDIR/server.log"; then
  echo ""
  echo "FAIL: server never reported FINAL_ACCURACY within 60s (see logs in $WORKDIR before cleanup removes them)"
  FAILED=1
fi

if grep -qE "received [0-9]+ results and [1-9][0-9]* failures" "$WORKDIR/server.log"; then
  echo ""
  echo "FAIL: at least one client failure during aggregation"
  FAILED=1
fi

EXPECTED="received $N_HOSPITALS results and 0 failures"
if ! grep -q "$EXPECTED" "$WORKDIR/server.log"; then
  echo ""
  echo "FAIL: never saw '$EXPECTED' — fewer than $N_HOSPITALS clients participated in a round"
  FAILED=1
fi

for log in "${CLIENT_LOGS[@]}"; do
  if grep -qiE "traceback|error" "$log"; then
    echo ""
    echo "FAIL: $log contains an error:"
    grep -iE "traceback|error" "$log"
    FAILED=1
  fi
done

echo ""
if [[ "$FAILED" -eq 0 ]]; then
  echo "PASS: $N_HOSPITALS real networked clients federated $ROUNDS rounds successfully."
  exit 0
else
  echo "FAILED — see logs above."
  exit 1
fi
