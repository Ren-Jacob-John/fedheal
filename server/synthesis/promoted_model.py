"""
The PROMOTED federated model, as served by Module 7's registry.

Inference rule (docs/MODEL_STATUS.md): if the registry has a promoted model
for the condition, THAT is what runs. The demo fallback may be used only when
it is explicitly enabled (FEDHEAL_ALLOW_DEMO_MODEL=true) and is then labelled
NON-CLINICAL / DEMO. Nothing is cached for longer than a few seconds, so a
promotion or rollback in the registry takes effect almost immediately.

The weights are re-hashed here before use: a registry record whose weights do
not match its own artifact_hash is refused, not served.
"""
import hashlib
import math
import os
import struct
import time
from dataclasses import dataclass

import httpx

import config
import service_auth

ADMIN_API_URL = os.environ.get("FEDHEAL_ADMIN_API_URL", "http://localhost:8005")
SIGNING_KEY = config.get_secret("FEDHEAL_SVC_SIGNING_KEY_M8_M7", dev_default="dev-only-signing-key-module8-to-module7")
CACHE_SECONDS = float(os.environ.get("FEDHEAL_PROMOTED_MODEL_CACHE_SECONDS", "5"))
_cache: dict[str, tuple[float, "PromotedModel | None"]] = {}


class RegistryUnavailable(RuntimeError):
    """The registry could not be reached or answered unexpectedly: we cannot know what is promoted."""


class PromotedModelIntegrityError(RuntimeError):
    """Registry weights do not hash to the registry's own artifact_hash."""


@dataclass(frozen=True)
class PromotedModel:
    model_id: str
    name: str
    version: str
    condition: str
    artifact_hash: str
    training_round: int
    n_hospitals: int
    metrics: dict
    approved_at: str | None
    coef: tuple
    intercept: float
    feature_names: tuple
    center: tuple
    scale: tuple

    def provenance(self) -> dict:
        return {"registry_id": self.model_id, "artifact_hash": self.artifact_hash, "training_round": self.training_round,
                "n_participating_hospitals": self.n_hospitals, "approved_at": self.approved_at,
                "gate_metrics": {k: v for k, v in self.metrics.items() if v is not None},
                "metrics_note": "Reported by the training side from a held-out split of its own data; "
                                "not evidence of performance on any other hospital's patients."}

    def predict(self, features: dict) -> dict:
        """features: {name: raw value} for every input, none missing (the caller guarantees it)."""
        x = [(float(features[n]) - c) / s for n, c, s in zip(self.feature_names, self.center, self.scale)]
        contrib = [w * v for w, v in zip(self.coef, x)]
        z = sum(contrib) + self.intercept
        p1 = 1.0 / (1.0 + math.exp(-z)) if z > -700 else 0.0
        label = 1 if p1 >= 0.5 else 0
        return {"label": label, "score_class_1": p1, "confidence": p1 if label == 1 else 1 - p1,
                "contributions": [{"feature": n, "value": float(features[n]), "contribution": c}
                                  for n, c in zip(self.feature_names, contrib)],
                "intercept": self.intercept}


def _canonical_hash(coef, intercept) -> str:
    h = hashlib.sha256()
    h.update(str((1, len(coef))).encode())
    h.update(struct.pack(f"<{len(coef)}d", *coef))
    h.update(str((1,)).encode())
    h.update(struct.pack("<1d", intercept))
    return h.hexdigest()


def _parse(body: dict) -> PromotedModel:
    coef = [float(v) for v in body["parameters"]["coef"][0]]
    intercept = float(body["parameters"]["intercept"][0])
    if _canonical_hash(coef, intercept) != body["artifact_hash"]:
        raise PromotedModelIntegrityError("promoted weights do not match their artifact_hash")
    spec = body["input_spec"]
    return PromotedModel(
        model_id=body["id"], name=body["model_name"], version=body["version"], condition=body["condition"],
        artifact_hash=body["artifact_hash"], training_round=int(body["training_round"]),
        n_hospitals=int(body["n_participating_hospitals"]), metrics=body.get("metrics") or {},
        approved_at=str(body["approved_at"]) if body.get("approved_at") else None,
        coef=tuple(coef), intercept=intercept, feature_names=tuple(spec["feature_names"]),
        center=tuple(float(v) for v in spec["center"]), scale=tuple(float(v) for v in spec["scale"]),
    )


def fetch_promoted(condition: str, *, use_cache: bool = True) -> "PromotedModel | None":
    """The promoted model for `condition`, or None if the registry says there is none.
    Raises RegistryUnavailable if the registry cannot answer (unknown is not the same as 'none')."""
    now = time.monotonic()
    hit = _cache.get(condition)
    if use_cache and hit and now - hit[0] < CACHE_SECONDS:
        return hit[1]
    token = service_auth.mint_service_token(SIGNING_KEY, caller="module8", audience=service_auth.AUD_PROMOTED_MODEL,
                                            hospital_id=service_auth.ANY_HOSPITAL, ttl_seconds=60)
    try:
        r = httpx.get(f"{ADMIN_API_URL}/admin/models/promoted", params={"condition": condition},
                      headers={"X-Service-Key": token}, timeout=5.0)
    except httpx.HTTPError:
        raise RegistryUnavailable("Module 7 (model registry) could not be reached")
    if r.status_code == 404:
        model = None
    elif r.status_code == 200:
        model = _parse(r.json())
    else:
        raise RegistryUnavailable(f"Module 7 (model registry) answered {r.status_code}")
    _cache[condition] = (now, model)
    return model


def clear_cache() -> None:
    _cache.clear()
