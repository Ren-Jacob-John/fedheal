"""
One HospitalClient instance = one simulated hospital's local node.

This is the piece that, in the real system, runs inside each hospital's own
application (see the proposal's "hospital-side application" component) —
it only ever touches that hospital's own local (X, y) partition. Flower calls
fit()/evaluate() on it once per round; only the returned weight arrays travel
back to the server, never X or y.
"""
import numpy as np
import flwr as fl
from sklearn.metrics import log_loss

from model import build_model, get_model_parameters, set_model_parameters


class HospitalClient(fl.client.NumPyClient):
    def __init__(self, hospital_id: str, X_train, y_train, X_test, y_test):
        self.hospital_id = hospital_id
        self.X_train, self.y_train = X_train, y_train
        self.X_test, self.y_test = X_test, y_test
        self.model = build_model()

    def get_parameters(self, config):
        return get_model_parameters(self.model)

    def fit(self, parameters, config):
        set_model_parameters(self.model, parameters)
        # One local epoch of SGD on this hospital's own data only.
        self.model.partial_fit(self.X_train, self.y_train, classes=np.array([0, 1]))
        return get_model_parameters(self.model), len(self.X_train), {"hospital_id": self.hospital_id}

    def evaluate(self, parameters, config):
        set_model_parameters(self.model, parameters)
        probs = self.model.predict_proba(self.X_test)
        loss = log_loss(self.y_test, probs, labels=[0, 1])
        accuracy = self.model.score(self.X_test, self.y_test)
        return loss, len(self.X_test), {"accuracy": accuracy, "hospital_id": self.hospital_id}
