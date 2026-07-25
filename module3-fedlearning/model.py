"""
The shared model architecture every hospital trains locally: logistic
regression via sklearn's SGDClassifier (loss="log_loss"), trained
incrementally with partial_fit. This stands in for "gradient-boosted trees
or a small neural net" from the proposal — logistic regression is the
simplest thing whose weights are a flat, easy-to-average numpy array, which
makes it the clearest way to see FedAvg actually working before adding
XGBoost/PyTorch's extra complexity.

Swap in XGBoost or a PyTorch model later by changing get/set_model_parameters
and the client's fit/evaluate — the Flower simulation loop in simulate.py
doesn't need to change.
"""
import numpy as np
from sklearn.linear_model import SGDClassifier

from data import N_FEATURES

N_CLASSES = 2


def build_model() -> SGDClassifier:
    model = SGDClassifier(loss="log_loss", max_iter=1, warm_start=True, random_state=42)
    # SGDClassifier needs coef_/intercept_ to exist before we can set them
    # externally, so seed it with one partial_fit call on dummy balanced data.
    model.classes_ = np.array([0, 1])
    model.coef_ = np.zeros((1, N_FEATURES))
    model.intercept_ = np.zeros(1)
    return model


def get_model_parameters(model: SGDClassifier) -> list[np.ndarray]:
    """Flower expects a list of numpy arrays — this is what gets sent over the wire."""
    return [model.coef_.copy(), model.intercept_.copy()]


def set_model_parameters(model: SGDClassifier, params: list[np.ndarray]) -> SGDClassifier:
    model.coef_ = params[0]
    model.intercept_ = params[1]
    model.classes_ = np.array([0, 1])
    return model
