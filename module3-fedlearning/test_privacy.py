import numpy as np
import pytest

from privacy import transform_update, update_transform_config


def test_update_transform_configuration_is_off_by_default(monkeypatch):
    monkeypatch.delenv("FEDHEAL_UPDATE_CLIP_NORM", raising=False)
    monkeypatch.delenv("FEDHEAL_UPDATE_NOISE_MULTIPLIER", raising=False)
    assert update_transform_config() == (0.0, 0.0)


def test_noise_configuration_requires_clipping(monkeypatch):
    monkeypatch.delenv("FEDHEAL_UPDATE_CLIP_NORM", raising=False)
    monkeypatch.setenv("FEDHEAL_UPDATE_NOISE_MULTIPLIER", "0.1")
    with pytest.raises(ValueError, match="requires"):
        update_transform_config()


def test_privacy_transform_defaults_preserve_update_exactly():
    base = [np.array([0.1, 0.2]), np.array([4.0])]
    updated = [np.array([0.3, -0.4]), np.array([3.0])]
    result = transform_update(base, updated)
    assert all(np.array_equal(actual, expected) for actual, expected in zip(result, updated))


def test_client_update_is_globally_l2_clipped():
    result = transform_update(
        [np.zeros(1), np.zeros(1)],
        [np.array([3.0]), np.array([4.0])],
        clip_norm=2.0,
    )
    assert np.allclose(result[0], [1.2])
    assert np.allclose(result[1], [1.6])
    assert np.isclose(np.linalg.norm(np.concatenate(result)), 2.0)


def test_gaussian_noise_uses_configured_clip_scaled_standard_deviation():
    seed = 17
    expected_noise = np.random.default_rng(seed).normal(0.0, 0.5, size=(2,))
    result = transform_update(
        [np.zeros(2)], [np.zeros(2)],
        clip_norm=2.0, noise_multiplier=0.25, rng=np.random.default_rng(seed),
    )
    assert np.allclose(result[0], expected_noise)


def test_noise_requires_positive_clipping_bound():
    with pytest.raises(ValueError, match="requires a positive clip_norm"):
        transform_update([np.zeros(1)], [np.ones(1)], noise_multiplier=0.1)
