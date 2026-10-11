"""
One HospitalClient instance = one simulated hospital's local node.

This is the piece that, in the real system, runs inside each hospital's own
application (see the proposal's "hospital-side application" component) —
it only ever touches that hospital's own local (X, y) partition. Flower calls
fit()/evaluate() on it once per round. Model weights, hospital/request ids,
counts and aggregate evaluation metrics travel to the server, never X or y.
"""
import numpy as np
import flwr as fl
from sklearn.metrics import log_loss

from model import build_model, get_model_parameters, set_model_parameters
from privacy import transform_update, update_transform_config


class HospitalClient(fl.client.NumPyClient):
    def __init__(self, hospital_id: str, X_train, y_train, X_test, y_test,
                 training_provenance: dict | None = None, retraining_request_id: str | None = None):
        self.hospital_id = hospital_id
        self.X_train, self.y_train = X_train, y_train
        self.X_test, self.y_test = X_test, y_test
        self.training_provenance = training_provenance
        self.retraining_request_id = retraining_request_id
        self.model = build_model(X_train.shape[1])

    def get_parameters(self, config):
        return get_model_parameters(self.model)

    def fit(self, parameters, config):
        set_model_parameters(self.model, parameters)
        base_weights = get_model_parameters(self.model)
        # One local epoch of SGD on this hospital's own data only.
        self.model.partial_fit(self.X_train, self.y_train, classes=np.array([0, 1]))
        clip_norm, noise_multiplier = update_transform_config()
        updated = transform_update(
            base_weights,
            get_model_parameters(self.model),
            clip_norm=clip_norm,
            noise_multiplier=noise_multiplier,
        )
        metrics = {"hospital_id": self.hospital_id}
        if self.training_provenance is not None:
            metrics.update(self.training_provenance)
        if self.retraining_request_id is not None:
            metrics["retraining_request_id"] = self.retraining_request_id
        return updated, len(self.X_train), metrics

    def evaluate(self, parameters, config):
        set_model_parameters(self.model, parameters)
        probs = self.model.predict_proba(self.X_test)
        loss = log_loss(self.y_test, probs, labels=[0, 1])
        accuracy = self.model.score(self.X_test, self.y_test)
        metrics = {
            "accuracy": accuracy,
            "hospital_id": self.hospital_id,
            "positive_label_count": int(np.sum(self.y_test)),
        }
        if self.retraining_request_id is not None:
            metrics["retraining_request_id"] = self.retraining_request_id
        return loss, len(self.X_test), metrics
