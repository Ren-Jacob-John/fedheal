"""
Module 6 — Condition Router (Stage 3 / Week 3)

The auto-switch layer: mention a disease/condition by name, get routed
automatically to the right specialist model(s) (Section 1-9 of the
catalog) AND the right reasoning method(s) (Section 10 of the catalog) —
no manual model selection required.

This sits ABOVE module5's MetadataRouter, not instead of it: module5
routes "what modality is this" -> "which specialist"; module6 routes
"what disease is this" -> "which specialist(s) AND which reasoning
method(s)", which is the finer-grained, clinically meaningful question.
"""
from dataclasses import dataclass, field

import paths  # noqa: F401
from conditions import resolve_condition, CONDITION_REGISTRY
from condition_registry_builder import build_condition_registry

from explainers.shap_explainer import ShapExplainer
from explainers.knowledge_graph_reasoner import KnowledgeGraphReasoner
from explainers.gradcam_explainer import GradCamExplainer


class UnknownConditionError(Exception):
    """Raised when a condition name doesn't match any registered condition or
    alias. Never silently guesses — see ConditionRouter.route()'s docstring
    for why a wrong guess here is worse than an explicit failure."""


class IncompleteDataError(Exception):
    """Raised when a specialist's required inputs are missing. Carries which
    specialist and which named features, so the caller can tell the user
    exactly what to supply. Never filled in, defaulted or imputed."""

    def __init__(self, specialist_id: str, missing_features: list[str], detail: str = ""):
        self.specialist_id = specialist_id
        self.missing_features = missing_features
        super().__init__(
            f"Specialist {specialist_id!r} cannot run: missing required input(s) "
            f"{missing_features}. {detail}".strip()
        )


class SpecialistUnavailableError(Exception):
    """The specialist exists in the registry but cannot answer (e.g. not fitted)."""

    def __init__(self, specialist_id: str, status: dict):
        self.specialist_id = specialist_id
        self.status = status
        super().__init__(f"Specialist {specialist_id!r} is unavailable: {status}")


@dataclass
class SpecialistFinding:
    specialist_id: str
    prediction: object              # a module5 PredictionResult
    explanations: list = field(default_factory=list)  # list of Explanation
    # Module 5 status card at prediction time (model_name/version, is_stub,
    # is_fallback, training_status, feature_names). Authoritative — a
    # consumer should not infer stub/fallback from names.
    status: dict = field(default_factory=dict)


@dataclass
class ConditionReport:
    condition: str
    findings: list[SpecialistFinding]
    unresolved_explainers: list[str] = field(default_factory=list)


class ConditionRouter:
    def __init__(self):
        self.specialists = build_condition_registry()
        self.explainers = {
            "shap": ShapExplainer(),
            "knowledge_graph": KnowledgeGraphReasoner(),
            "grad_cam": GradCamExplainer(),
        }

    def status_for_condition(self, condition_name: str) -> list[dict]:
        """Status cards for every specialist a condition routes to."""
        spec = resolve_condition(condition_name)
        if spec is None:
            raise UnknownConditionError(self._unknown_message(condition_name))
        cards = []
        for sid in spec.specialist_ids:
            specialist = self.specialists.get(sid)
            card = specialist.describe() if specialist is not None and hasattr(specialist, "describe") else {}
            cards.append({"specialist_id": sid, "registered": specialist is not None, **card})
        return cards

    @staticmethod
    def _unknown_message(condition_name: str) -> str:
        known = sorted(s.canonical_name for s in CONDITION_REGISTRY.values())
        return (
            f"Condition {condition_name!r} isn't registered yet. Known conditions: {known}. "
            f"To add it: register a ConditionSpec in conditions.py, pointing at an existing "
            f"or new specialist — see docs/model-algorithm-catalog.md."
        )

    @staticmethod
    def _check_required_inputs(specialist_id: str, specialist, data: dict) -> None:
        """Tabular specialists declare `feature_names`; their `features` must
        be a list of that exact length with no missing (None/NaN) entry."""
        names = getattr(specialist, "feature_names", None)
        if not names or "features" not in data:
            return
        values = data["features"]
        if not isinstance(values, (list, tuple)) or len(values) != len(names):
            raise IncompleteDataError(
                specialist_id, list(names),
                f"Expected {len(names)} values in this order: {list(names)}.",
            )
        missing = [
            n for n, v in zip(names, values)
            if v is None or (isinstance(v, float) and v != v)
        ]
        if missing:
            raise IncompleteDataError(specialist_id, missing)

    def route(self, condition_name: str, case_data: dict[str, dict]) -> ConditionReport:
        """
        `case_data` maps specialist_id -> that specialist's input dict, e.g.
        {"cbc_leukemia": {"features": [...]}, "genomic_leukemia": {"expression": [...]}}
        — the caller supplies input for whichever of the condition's
        specialist_ids it actually has data for (see demo.py for examples).

        Raises UnknownConditionError for an unrecognized condition rather
        than falling back to a random/default model — per the proposal's
        own reasoning, running the wrong specialist "would produce a
        confident, meaningless answer," which is worse than a clear error
        the caller can act on (e.g. by adding the condition to conditions.py).
        """
        spec = resolve_condition(condition_name)
        if spec is None:
            raise UnknownConditionError(self._unknown_message(condition_name))

        findings = []
        unresolved: list[str] = []
        for specialist_id in spec.specialist_ids:
            if specialist_id not in case_data:
                continue  # caller didn't supply data for this specialist this time — skip, don't fail
            specialist = self.specialists[specialist_id]
            card = specialist.describe() if hasattr(specialist, "describe") else {}
            if card and not card.get("available", True):
                raise SpecialistUnavailableError(specialist_id, card)
            self._check_required_inputs(specialist_id, specialist, case_data[specialist_id])
            prediction = specialist.predict(case_data[specialist_id])

            explanations = []
            for explainer_name in spec.explainer_names:
                explainer = self.explainers[explainer_name]
                if not explainer.is_available():
                    # Recorded, not silently skipped: a consumer must be able to
                    # say "no explanation was produced, and why".
                    unresolved.append(f"{specialist_id}:{explainer_name}: explainer not available in this environment")
                    continue
                try:
                    explanations.append(explainer.explain(specialist, case_data[specialist_id], prediction))
                except (ValueError, KeyError) as e:
                    # Not every explainer fits every specialist (e.g. SHAP needs a
                    # `.model` attribute) — record why it was skipped rather than
                    # crash the whole report over one incompatible pairing.
                    from explainers.base import Explanation
                    unresolved.append(f"{specialist_id}:{explainer_name}: {e}")
                    explanations.append(Explanation(
                        method=explainer_name,
                        summary=f"Skipped: {e}",
                        is_stub=True,
                    ))

            findings.append(SpecialistFinding(
                specialist_id=specialist_id, prediction=prediction, explanations=explanations,
                status=card,
            ))

        return ConditionReport(condition=spec.canonical_name, findings=findings,
                               unresolved_explainers=unresolved)
