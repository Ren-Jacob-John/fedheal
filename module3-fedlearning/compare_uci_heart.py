"""
Federated vs. solo, on real UCI Heart Disease data — offline.

Run: python compare_uci_heart.py

This is Sprint A's headline deliverable: the federated-vs-solo accuracy
comparison demonstrated on a real, publicly citable dataset with real
clinical outcome labels, rather than on `make_classification` output or on
rule-based placeholder labels.

Relationship to the other two comparison scripts in this folder:

  * `simulate.py`          — synthetic data, offline. Still useful for
                             stress-testing FedAvg under controlled skew
                             (alpha sweeps) that a fixed 303-row real
                             dataset can't produce.
  * `compare_uci_heart.py` — THIS. Real data, real labels, offline. No
                             services, no network, no database. This is
                             what to run to get a defensible number.
  * `simulate_real.py`     — real data pulled live from Module 1, which
                             proves the whole upload -> validate -> store
                             -> train integration works. Seed it first with
                             `seed_uci_heart.py` and it trains on this same
                             Cleveland data through the real pipeline.

The FedAvg loop and the solo baseline are imported from `fedavg.py`, the
same ones `simulate_real.py` uses, so the offline number and the
through-the-stack number are directly comparable rather than two
independent implementations that happen to agree.

READ `uci_heart.py`'s module docstring before quoting the output. Short
version: only 3 of the 8 feature slots carry real Cleveland measurements,
so this is "federated learning on 3 real vitals features", not "UCI Heart
Disease state of the art". The majority-class floor is 54.1%.
"""
from __future__ import annotations

import argparse
import statistics

import numpy as np

import uci_heart
from data import train_test_split_per_hospital
from fedavg import federated_average, run_local_only_baseline
from model import build_model, get_model_parameters
from real_data import carve_global_holdout

N_ROUNDS = 8


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Federated vs solo accuracy on real UCI Heart Disease data, offline."
    )
    parser.add_argument("--hospitals", type=int, default=3,
                        help="Number of simulated hospitals to split across (default: 3).")
    parser.add_argument("--alpha", type=float, default=3.0,
                        help="Dirichlet concentration for the non-IID split; lower = "
                             "more inter-hospital skew (default: 3.0).")
    parser.add_argument("--rounds", type=int, default=N_ROUNDS,
                        help=f"Federated rounds to run (default: {N_ROUNDS}).")
    parser.add_argument("--iid", action="store_true",
                        help="Split uniformly instead of non-IID.")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed (default: 42).")
    parser.add_argument("--sweep", type=int, metavar="N", default=None,
                        help="Repeat the whole comparison over N seeds (1..N) and report "
                             "the DISTRIBUTION instead of a single run. Strongly "
                             "recommended for anything you intend to quote — see the "
                             "note in run_sweep().")
    return parser.parse_args()


def run_once(hospitals: int, non_iid: bool, alpha: float, rounds: int,
             seed: int, verbose: bool) -> tuple[float, float] | None:
    """One federated-vs-solo comparison. Returns (federated, solo) accuracy,
    or None if this seed produced an unusable (single-class) holdout."""
    partitions = uci_heart.load_partitions(
        n_hospitals=hospitals, non_iid=non_iid, alpha=alpha, seed=seed,
    )

    # Carve the global holdout per-hospital BEFORE local splitting — same
    # reasoning as real_data.carve_global_holdout's docstring: pooling first
    # would let the same record be trained on and held out.
    partitions, X_holdout, y_holdout = carve_global_holdout(partitions, seed=seed)
    if len(np.unique(y_holdout)) < 2:
        return None

    hospital_splits = train_test_split_per_hospital(partitions, seed=seed)

    if verbose:
        names = [f"Hospital {i + 1}" for i in range(len(hospital_splits))]
        for name, (X_train, X_test, y_train, y_test) in zip(names, hospital_splits):
            print(f"  {name}: {len(X_train):>3} train / {len(X_test):>3} local-test, "
                  f"positive rate {y_train.mean():.2f}")
        print(f"  global holdout: {len(X_holdout)} records "
              f"(no hospital trained on these), positive rate {y_holdout.mean():.2f}\n")

    baseline_acc = run_local_only_baseline(hospital_splits, X_holdout, y_holdout)
    if verbose:
        print(f"SOLO baseline — mean accuracy of hospitals trained alone, "
              f"scored on the global holdout: {baseline_acc:.3f}\n")
        print(f"{'round':>5} | {'federated global model accuracy':>34}")
        print("-" * 44)

    clients = [
        (build_model(), X_train, y_train)
        for X_train, X_test, y_train, y_test in hospital_splits
    ]
    global_params = get_model_parameters(build_model())
    eval_model = build_model()

    global_acc = baseline_acc
    for round_num in range(1, rounds + 1):
        client_params, client_sizes = [], []
        for model, X_train, y_train in clients:
            model.coef_, model.intercept_ = global_params[0].copy(), global_params[1].copy()
            model.classes_ = np.array([0, 1])
            model.partial_fit(X_train, y_train, classes=np.array([0, 1]))
            client_params.append(get_model_parameters(model))
            client_sizes.append(len(X_train))

        global_params = federated_average(client_params, client_sizes)

        eval_model.coef_, eval_model.intercept_ = global_params[0], global_params[1]
        eval_model.classes_ = np.array([0, 1])
        global_acc = eval_model.score(X_holdout, y_holdout)
        if verbose:
            print(f"{round_num:>5} | {global_acc:>34.3f}")

    return global_acc, baseline_acc


def run_sweep(args, info) -> int:
    """
    Repeat the comparison over N seeds and report the spread.

    This exists because a single run of this comparison is not a result.
    303 records split three ways leaves a ~47-record global holdout, so one
    misclassified patient moves accuracy by two points, and the
    federated-vs-solo delta swings sign between seeds. Reporting whichever
    single seed happened to run is how a project ends up defending a number
    it can't reproduce in front of the people it's demoing to.

    Report the mean, the spread, and the win rate. All three.
    """
    fed, solo, skipped = [], [], 0
    for seed in range(1, args.sweep + 1):
        result = run_once(args.hospitals, not args.iid, args.alpha,
                          args.rounds, seed, verbose=False)
        if result is None:
            skipped += 1
            continue
        f, s = result
        fed.append(f)
        solo.append(s)

    if len(fed) < 2:
        print("Not enough usable seeds to report a distribution.")
        return 1

    deltas = [f - s for f, s in zip(fed, solo)]
    wins = sum(1 for d in deltas if d > 0)

    print(f"Sweep over {len(fed)} seeds"
          + (f" ({skipped} skipped: single-class holdout)" if skipped else ""))
    print("-" * 62)
    print(f"  FEDERATED   mean {statistics.mean(fed):.3f}   sd {statistics.stdev(fed):.3f}   "
          f"range {min(fed):.3f}–{max(fed):.3f}")
    print(f"  SOLO        mean {statistics.mean(solo):.3f}   sd {statistics.stdev(solo):.3f}   "
          f"range {min(solo):.3f}–{max(solo):.3f}")
    print(f"  DELTA       mean {statistics.mean(deltas):+.3f}  sd {statistics.stdev(deltas):.3f}")
    print(f"  Federation beat solo in {wins}/{len(fed)} seeds")
    print(f"  Majority floor {info['majority_class_floor']:.3f}")
    print()
    print("How to quote this: give the mean delta AND the win rate AND the fact that "
          "individual\nseeds go the other way. The spread is a property of a 303-record "
          "dataset split three\nways, not noise to be averaged away and forgotten.")
    return 0


def main() -> int:
    args = parse_args()
    info = uci_heart.summary()

    print("Federated vs solo — UCI Heart Disease (Cleveland), offline")
    print("=" * 62)
    print(f"  records            {info['records']} "
          f"({info['positive']} positive / {info['negative']} negative)")
    print(f"  labels             REAL clinical outcomes (num > 0), no placeholders")
    print(f"  real features      {len(info['real_features'])} of 8 — "
          f"{', '.join(info['real_features'])}")
    print(f"  constant features  {len(info['constant_features'])} — not measured by "
          f"Cleveland, pinned to the normalization mean (zero contribution)")
    print(f"  majority floor     {info['majority_class_floor']:.1%} — anything at or below "
          f"this has learned nothing")
    print(f"  split              {args.hospitals} hospitals, "
          f"{'IID' if args.iid else f'non-IID (Dirichlet alpha={args.alpha})'}")
    print()

    if args.sweep:
        return run_sweep(args, info)

    result = run_once(args.hospitals, not args.iid, args.alpha,
                      args.rounds, args.seed, verbose=True)
    if result is None:
        print("Global holdout came out single-class — try a different --seed.")
        return 1
    global_acc, baseline_acc = result

    delta = global_acc - baseline_acc
    print()
    print(f"FEDERATED (final):  {global_acc:.3f}")
    print(f"SOLO (baseline):    {baseline_acc:.3f}")
    print(f"Difference:         {delta:+.3f}")
    print(f"Majority floor:     {info['majority_class_floor']:.3f}")
    print()

    if global_acc <= info["majority_class_floor"]:
        print("The federated model is at or below the majority-class floor — it has not "
              "learned anything useful. Report that plainly; don't report the delta as "
              "a win.")
    elif delta > 0:
        print("Federation beat the solo baseline on data no hospital trained on. That's "
              "the claim this project makes, now measured on a real cited dataset.")
    else:
        print("Federation did NOT beat the solo baseline on this split. That is a real "
              "and well-documented FedAvg outcome under non-IID data with few features "
              "and a small sample — report it, don't tune --seed until it flips.")

    print("\nONE SEED IS NOT A RESULT. The ~47-record global holdout means a single "
          "patient\nmoves accuracy by two points, and the sign of the delta above "
          "changes between seeds.\nRun `--sweep 20` before quoting any of this.")

    print("\nCaveat that belongs next to every number above: 3 real features, "
          "303 records,\nlogistic regression. This is evidence the federated pipeline "
          "works on real clinical\ndata with real outcomes — not a clinical performance "
          "claim. See uci_heart.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
