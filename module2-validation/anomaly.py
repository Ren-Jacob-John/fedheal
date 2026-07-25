"""
Statistical outlier detection over a batch of records, on top of the hard
rule checks in rules.py. An isolation forest flags records that are
*statistically* unusual relative to the rest of the batch even when no
single value breaks a plausibility rule — e.g. a hospital whose whole
upload looks shifted (wrong units, a miscalibrated device).

This is a soft signal (flag for review), not an automatic rejection —
rule violations in rules.py are the hard rejections.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

NUMERIC_FIELDS = [
    "age_years", "height_cm", "weight_kg",
    "systolic_bp", "diastolic_bp", "heart_rate_bpm",
    "medication_count", "medication_mg_total",
]


def flag_outliers(records: list[dict], contamination: float = 0.05) -> list[bool]:
    """
    Returns a list of booleans (same length/order as records): True means
    "flagged as a statistical outlier within this batch".

    Needs a reasonable batch size to be meaningful — with fewer than ~10
    records, isolation forest scores are noisy, so we skip flagging.
    """
    if len(records) < 10:
        return [False] * len(records)

    df = pd.DataFrame(records)[NUMERIC_FIELDS].apply(pd.to_numeric, errors="coerce")
    df = df.fillna(df.median(numeric_only=True))

    model = IsolationForest(contamination=contamination, random_state=42)
    predictions = model.fit_predict(df.values)  # -1 = outlier, 1 = normal
    return [bool(p == -1) for p in predictions]
