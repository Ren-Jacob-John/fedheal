"""Experimental client-side update bounding/noise; not a differential-privacy claim."""
import os

import numpy as np


def update_transform_config() -> tuple[float, float]:
    """Read validated client update settings; both are disabled by default."""
    values = []
    for name in ("FEDHEAL_UPDATE_CLIP_NORM", "FEDHEAL_UPDATE_NOISE_MULTIPLIER"):
        raw = os.environ.get(name)
        if raw is None or not raw.strip():
            values.append(0.0)
            continue
        try:
            value = float(raw)
        except ValueError as exc:
            raise ValueError(f"{name} must be a non-negative number") from exc
        if not np.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be a non-negative finite number")
        values.append(value)
    clip_norm, noise_multiplier = values
    if noise_multiplier and not clip_norm:
        raise ValueError("FEDHEAL_UPDATE_NOISE_MULTIPLIER requires FEDHEAL_UPDATE_CLIP_NORM")
    return clip_norm, noise_multiplier


def transform_update(base_weights, updated_weights, *, clip_norm: float = 0.0,
                     noise_multiplier: float = 0.0, rng=None):
    """Bound a client's flattened update and optionally add Gaussian noise.

    The disabled defaults preserve the original Flower update. Noise is
    scaled to the clip bound, but no privacy accountant or epsilon is
    computed; callers must not describe this as an epsilon-DP guarantee.
    """
    if clip_norm < 0 or noise_multiplier < 0:
        raise ValueError("clip_norm and noise_multiplier must be non-negative")
    if noise_multiplier and not clip_norm:
        raise ValueError("noise_multiplier requires a positive clip_norm")
    if len(base_weights) != len(updated_weights):
        raise ValueError("base and updated weight lists must have the same length")
    if clip_norm == 0 and noise_multiplier == 0:
        return [np.asarray(weights, dtype=float).copy() for weights in updated_weights]

    deltas = []
    squared_norm = 0.0
    for base, updated in zip(base_weights, updated_weights):
        base_arr = np.asarray(base, dtype=float)
        updated_arr = np.asarray(updated, dtype=float)
        if base_arr.shape != updated_arr.shape:
            raise ValueError("base and updated weight shapes must match")
        delta = updated_arr - base_arr
        if not np.all(np.isfinite(delta)):
            raise ValueError("weight update contains a non-finite value")
        deltas.append(delta)
        squared_norm += float(np.sum(delta * delta))

    factor = 1.0
    if clip_norm > 0:
        norm = float(np.sqrt(squared_norm))
        if norm > clip_norm:
            factor = clip_norm / norm
    rng = rng or np.random.default_rng()
    result = []
    for base, delta in zip(base_weights, deltas):
        bounded = delta * factor
        if noise_multiplier:
            bounded = bounded + rng.normal(0.0, noise_multiplier * clip_norm, size=bounded.shape)
        result.append(np.asarray(base, dtype=float) + bounded)
    return result
