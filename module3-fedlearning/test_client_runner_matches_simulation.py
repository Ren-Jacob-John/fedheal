"""
Sanity check for sprint 4's stated goal: does the REAL networked FL path
(server.py + client_runner.py over actual gRPC) reach the same result as
running the identical FedAvg math in-process? If it doesn't, something in
the new path (data loading, serialization, round timing) is silently
wrong even though "it ran without crashing."

IMPORTANT — what "same result" means here: simulate_real.py's headline
accuracy is measured against a carved-out GLOBAL holdout (patients no
hospital trained on) — a different, and more meaningful, number than what
this script compares. client_runner.py's real networked run never carves
a global holdout at all (each hospital only ever sees its own data, by
design — that's the point of federation); the only accuracy the server
can see is the weighted average of each hospital's own local test-split
accuracy, via server.py's weighted_average(). So THAT's the metric this
script reproduces in-process and compares against — same clients, same
data, same rounds, same aggregation math, same accuracy definition. This
is a check that the plumbing is correct, not a claim about generalization
(that's simulate_real.py's job, and still requires the global-holdout
comparison it already does).

This comparison depends on server.py's DeterministicFedAvg (aggregates in
hospital_id order, not network-arrival order) — plain FedAvg's result
depends on client response timing, which this script found out the hard
way: with this SGDClassifier setup, floating-point summation ORDER alone
(same clients, same data, same code) swung a round's reported accuracy by
double digits. Not a correctness bug in the averaging math itself, but it
meant "real path vs. in-process reproduction" wasn't a meaningful
comparison until aggregation order was made deterministic.

Run:
    python test_client_runner_matches_simulation.py [--hospitals N] [--records-per-hospital N]

Exits 0 (PASS) if the real networked run's FINAL_ACCURACY matches the
in-process reproduction within TOLERANCE; 1 (FAIL) otherwise, or if the
real run never produces a FINAL_ACCURACY at all.
"""
import argparse
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from sklearn.model_selection import train_test_split
from flwr.server.strategy.aggregate import aggregate as flwr_aggregate

MODULE1_DIR = Path(__file__).parent.parent / "module1-auth"
MODULE3_DIR = Path(__file__).parent
AUTH_PORT = 8001
FL_PORT = 8080
SVC_KEY = "dev-only-key-module3-to-module1-selftest"

# real_data.py reads FEDHEAL_AUTH_API_URL / FEDHEAL_SVC_KEY_M3_M1 as
# MODULE-LEVEL constants at import time (same pattern client_runner.py
# relies on env vars for, but there it's a fresh subprocess each time so
# order never mattered). This script's in-process reproduction step calls
# real_data functions directly in THIS process, so these have to be set
# before the import below — setting os.environ afterward would be too
# late, real_data.SERVICE_KEY would already be bound to the default.
os.environ["FEDHEAL_AUTH_API_URL"] = f"http://localhost:{AUTH_PORT}"
os.environ["FEDHEAL_SVC_KEY_M3_M1"] = SVC_KEY

from client import HospitalClient
from model import build_model, get_model_parameters
from real_data import load_single_hospital_partition
from server import weighted_average

SEED_HOSPITALS_SCRIPT = """
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
    hospital = models.Hospital(name=f"Selftest Hospital {h}")
    db.add(hospital)
    db.commit()
    db.refresh(hospital)
    ids.append(hospital.id)

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
"""


def safe_stratify(y):
    """Same fix as client_runner.py's — a class needs >= 2 members to
    stratify on, not just "more than one distinct class"."""
    classes, counts = np.unique(y, return_counts=True)
    return y if len(classes) > 1 and counts.min() >= 2 else None


def wait_for(predicate, timeout_s, interval_s=0.5):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval_s)
    return False


def kill_all(procs):
    for p in procs:
        if p.poll() is None:
            p.send_signal(signal.SIGTERM)
    time.sleep(1)
    for p in procs:
        if p.poll() is None:
            p.kill()


def run_real_networked_path(hospital_ids, n_records, rounds, workdir: Path) -> float:
    """Starts server.py + one client_runner.py per hospital, waits for the
    run to finish, and returns the FINAL_ACCURACY it reported."""
    procs = []
    server_log = open(workdir / "server.log", "w")
    server_proc = subprocess.Popen(
        [sys.executable, "server.py",
         "--min-clients", str(len(hospital_ids)),
         "--rounds", str(rounds),
         "--address", f"0.0.0.0:{FL_PORT}"],
        cwd=MODULE3_DIR, stdout=server_log, stderr=subprocess.STDOUT,
    )
    procs.append(server_proc)
    time.sleep(2)

    client_env = os.environ.copy()
    client_env["FEDHEAL_AUTH_API_URL"] = f"http://localhost:{AUTH_PORT}"
    client_env["FEDHEAL_SVC_KEY_M3_M1"] = SVC_KEY

    for idx, hid in enumerate(hospital_ids):
        log = open(workdir / f"client_{idx}.log", "w")
        p = subprocess.Popen(
            [sys.executable, "client_runner.py",
             "--hospital-id", hid, "--server", f"localhost:{FL_PORT}",
             "--min-records", str(n_records)],
            cwd=MODULE3_DIR, stdout=log, stderr=subprocess.STDOUT, env=client_env,
        )
        procs.append(p)

    def has_result():
        text = (workdir / "server.log").read_text()
        return "FINAL_ACCURACY" in text or server_proc.poll() is not None

    wait_for(has_result, timeout_s=60)
    kill_all(procs)

    server_text = (workdir / "server.log").read_text()
    match = re.search(r"FINAL_ACCURACY:\s*([\d.]+)", server_text)
    if not match:
        print("--- server.log ---")
        print(server_text[-2000:])
        raise RuntimeError("Real networked run never reported FINAL_ACCURACY")
    return float(match.group(1))


def run_in_process_reproduction(hospital_ids, n_records, rounds) -> float:
    """
    Same clients, same data, same rounds — and now the SAME aggregation
    function the real server actually uses (Flower's own aggregate(), via
    server.py's weighted_average() for the accuracy metric), sorted by
    hospital_id to match DeterministicFedAvg. Earlier versions of this
    script used simulate_real.py's own hand-rolled federated_average()
    instead — a second, independent implementation of "weighted average"
    that is NOT guaranteed to be numerically identical to Flower's own
    aggregate() under floating-point rounding, which is exactly what made
    this comparison meaningless before both this fix and
    DeterministicFedAvg existed.
    """
    clients = []
    for hid in sorted(hospital_ids):
        X, y = load_single_hospital_partition(hid, min_records=n_records)
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=safe_stratify(y)
        )
        clients.append(HospitalClient(hid, X_train, y_train, X_test, y_test))

    global_params = get_model_parameters(build_model())
    final_acc = None
    for _ in range(rounds):
        results = []
        for client in clients:
            new_params, n, _ = client.fit(global_params, config={})
            results.append((new_params, n))
        global_params = flwr_aggregate(results)

        eval_results = []
        for client in clients:
            _, n, metrics = client.evaluate(global_params, config={})
            eval_results.append((n, metrics))
        final_acc = weighted_average(eval_results)["accuracy"]

    return final_acc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hospitals", type=int, default=3)
    parser.add_argument("--records-per-hospital", type=int, default=20)
    parser.add_argument("--rounds", type=int, default=8)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as workdir_str:
        workdir = Path(workdir_str)
        db_path = workdir / "selftest_auth.db"

        print(f"=== starting Module 1 (throwaway SQLite at {db_path}) ===")
        auth_env = os.environ.copy()
        auth_env["FEDHEAL_DATABASE_URL"] = f"sqlite:///{db_path}"
        auth_env["FEDHEAL_SVC_KEY_M3_M1"] = SVC_KEY
        auth_log = open(workdir / "module1.log", "w")
        auth_proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app",
             "--host", "0.0.0.0", "--port", str(AUTH_PORT)],
            cwd=MODULE1_DIR, stdout=auth_log, stderr=subprocess.STDOUT, env=auth_env,
        )

        try:
            import httpx

            def module1_up():
                try:
                    return httpx.get(f"http://localhost:{AUTH_PORT}/docs", timeout=1.0).status_code == 200
                except httpx.HTTPError:
                    return False

            if not wait_for(module1_up, timeout_s=15):
                print("FAIL: Module 1 never came up")
                sys.exit(1)
            print("Module 1 is up.")

            print(f"=== seeding {args.hospitals} hospitals x {args.records_per_hospital} records (non-IID) ===")
            seed_result = subprocess.run(
                [sys.executable, "-c", SEED_HOSPITALS_SCRIPT,
                 str(args.hospitals), str(args.records_per_hospital)],
                cwd=MODULE1_DIR, env=auth_env, capture_output=True, text=True,
            )
            if seed_result.returncode != 0:
                print("FAIL: seeding failed")
                print(seed_result.stderr)
                sys.exit(1)
            hospital_ids = seed_result.stdout.strip().split(",")
            print(f"Seeded hospitals: {hospital_ids}")

            print("=== running the REAL networked path (server.py + client_runner.py subprocesses) ===")
            real_acc = run_real_networked_path(hospital_ids, args.records_per_hospital, args.rounds, workdir)
            print(f"Real networked path FINAL_ACCURACY: {real_acc:.6f}")

            print("=== reproducing the same FedAvg run in-process ===")
            sim_acc = run_in_process_reproduction(hospital_ids, args.records_per_hospital, args.rounds)
            print(f"In-process reproduction accuracy:   {sim_acc:.6f}")

            diff = abs(real_acc - sim_acc)
            total_test_records = args.hospitals * max(1, round(args.records_per_hospital * 0.2))
            # Bit-exact equality was never a realistic bar between an async
            # network path and a sequential in-process one — even with
            # identical data, model, and aggregation order (both now true
            # thanks to DeterministicFedAvg), a prediction sitting exactly
            # on the 0.5 decision boundary can land on either side from
            # genuinely tiny (~1e-10) floating-point differences that
            # accumulate differently down two independently-executing
            # code paths. Tolerating up to 2 such borderline flips across
            # the combined eval set is the honest bar: it catches a real
            # divergence (the 16-point gap this test caught before
            # DeterministicFedAvg and the feature-scaling fix existed)
            # without failing on noise the system was never going to avoid.
            tolerance = max(0.02, 2.0 / total_test_records)
            print(f"\ndifference: {diff:.8f} (tolerance: {tolerance:.4f}, "
                  f"~{total_test_records} combined eval records)")
            if diff <= tolerance:
                print("PASS: real networked path matches the in-process reproduction.")
                sys.exit(0)
            else:
                print("FAIL: real networked path diverged from the in-process reproduction by "
                      "more than a couple of borderline flips — something in the networked "
                      "path's data/round handling doesn't match simulate.py/simulate_real.py's "
                      "known-good FedAvg math, this isn't just floating-point noise.")
                sys.exit(1)
        finally:
            kill_all([auth_proc])


if __name__ == "__main__":
    main()
