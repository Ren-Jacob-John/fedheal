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


@dataclass
class SpecialistFinding:
    specialist_id: str
    prediction: object              # a module5 PredictionResult
    explanations: list = field(default_factory=list)  # list of Explanation


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
            known = sorted(s.canonical_name for s in CONDITION_REGISTRY.values())
            raise UnknownConditionError(
                f"Condition {condition_name!r} isn't registered yet. "
                f"Known conditions: {known}. "
                f"To add it: register a ConditionSpec in conditions.py, pointing at an "
                f"existing or new specialist — see docs/model-algorithm-catalog.md for "
                f"which model family fits the data you have."
            )

        findings = []
        for specialist_id in spec.specialist_ids:
            if specialist_id not in case_data:
                continue  # caller didn't supply data for this specialist this time — skip, don't fail
            specialist = self.specialists[specialist_id]
            prediction = specialist.predict(case_data[specialist_id])

            explanations = []
            for explainer_name in spec.explainer_names:
                explainer = self.explainers[explainer_name]
                if not explainer.is_available():
                    continue
                try:
                    explanations.append(explainer.explain(specialist, case_data[specialist_id], prediction))
                except (ValueError, KeyError) as e:
                    # Not every explainer fits every specialist (e.g. SHAP needs a
                    # `.model` attribute) — record why it was skipped rather than
                    # crash the whole report over one incompatible pairing.
                    from explainers.base import Explanation
                    explanations.append(Explanation(
                        method=explainer_name,
                        summary=f"Skipped: {e}",
                        is_stub=True,
                    ))

            findings.append(SpecialistFinding(
                specialist_id=specialist_id, prediction=prediction, explanations=explanations
            ))

        return ConditionReport(condition=spec.canonical_name, findings=findings)
