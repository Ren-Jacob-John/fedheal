"""
Data for the FedAvg simulation.

Uses a synthetic tabular dataset (sklearn's make_classification) shaped like
the UCI Heart Disease / Diabetes datasets mentioned in the proposal — same
role (structured vitals -> binary diagnosis label), but generated locally so
the simulation runs offline with no download step.

SWAP THIS FILE for a loader over a real public dataset (UCI Heart Disease,
MIMIC-III-derived features, etc.) once you're ready to demo Module 3
against real numbers — nothing else in this folder needs to change, since
everything downstream just consumes (X, y) arrays.
"""
import numpy as np
from sklearn.datasets import make_classification
from sklearn.model_selection import train_test_split

FEATURE_NAMES = [
    "age", "resting_bp", "cholesterol", "max_heart_rate",
    "bmi", "glucose", "num_medications", "prior_admissions",
]
N_FEATURES = len(FEATURE_NAMES)


def load_full_dataset(n_samples: int = 2500, seed: int = 42):
    X, y = make_classification(
        n_samples=n_samples,
        n_features=N_FEATURES,
        n_informative=5,
        n_redundant=1,
        n_clusters_per_class=2,
        weights=[0.6, 0.4],  # mild class imbalance, like real diagnosis rates
        random_state=seed,
    )
    # Carve off a global holdout set that NO hospital ever trains or locally
    # tests on — it represents "the general patient population" and is the
    # only fair way to compare a single hospital's local model against the
    # federated global model. (Testing a hospital's model on its OWN local
    # slice makes it look artificially strong, since train/local-test share
    # the same skew — see partition_for_hospitals.)
    X_pool, X_global_holdout, y_pool, y_global_holdout = train_test_split(
        X, y, test_size=0.15, random_state=seed, stratify=y
    )
    return X_pool, y_pool, X_global_holdout, y_global_holdout


def partition_for_hospitals(X, y, n_hospitals: int, non_iid: bool = True, alpha: float = 3.0, seed: int = 42):
    """
    Splits (X, y) into n_hospitals partitions to simulate separate hospitals'
    local data.

    non_iid=True uses a Dirichlet(alpha) split per class — the standard way
    to simulate label-skewed non-IID data in FL research (Hsu et al. 2019).
    Lower alpha = more skew (hospitals look very different from each other,
    down to some hospitals having almost no examples of one class); higher
    alpha = closer to uniform. alpha=3.0 gives a realistic mild skew (e.g.
    one hospital sees more positive cases than another) without collapsing
    any hospital's local class balance to near-zero, which would make its
    own local baseline meaningless to compare against.

    Tip: drop alpha toward 0.3-0.5 if you want to specifically stress-test
    FedAvg under severe non-IID conditions, but expect the federated
    accuracy to genuinely suffer relative to local-only baselines in that
    regime — that's a real, well-documented FedAvg limitation, not a bug.
    """
    rng = np.random.default_rng(seed)

    if not non_iid:
        idx = rng.permutation(len(y))
        return [(X[part], y[part]) for part in np.array_split(idx, n_hospitals)]

    classes = np.unique(y)
    hospital_indices = [[] for _ in range(n_hospitals)]
    min_floor = 0.05  # no hospital gets less than 5% of any class, even by chance

    for c in classes:
        class_idx = np.where(y == c)[0]
        rng.shuffle(class_idx)

        proportions = rng.dirichlet(alpha=[alpha] * n_hospitals)
        proportions = np.clip(proportions, min_floor, None)
        proportions = proportions / proportions.sum()

        counts = (proportions * len(class_idx)).astype(int)
        counts[-1] = len(class_idx) - counts[:-1].sum()  # last hospital absorbs rounding remainder

        start = 0
        for h, count in enumerate(counts):
            hospital_indices[h].extend(class_idx[start:start + count].tolist())
            start += count

    return [(X[idx], y[idx]) for idx in hospital_indices]


def train_test_split_per_hospital(partitions, test_size: float = 0.2, seed: int = 42):
    """Each hospital keeps its own local held-out test set — never shared."""
    return [
        train_test_split(X, y, test_size=test_size, random_state=seed, stratify=y if len(set(y)) > 1 else None)
        for X, y in partitions
    ]
