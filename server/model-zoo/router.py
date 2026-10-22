"""
The task/modality router. Per the proposal: "In practice it's usually
simple: metadata (DICOM tags telling you it's a chest X-ray vs. MRI), the
clinical question being asked, or a lightweight classifier trained just to
sort inputs into modality/task buckets before the real specialist model
ever runs."

This implementation uses metadata (the simple, safety-critical-by-design
option) — a case must declare its own modality rather than the router
guessing from raw pixels. Swap in `ClassifierBasedRouter` (stubbed at the
bottom) once you have labeled data to train a modality classifier.
"""
from base import PredictionResult
from registry import build_registry


class UnroutableCaseError(Exception):
    """Raised when a case's declared modality has no registered specialist.
    Never silently falls through to a random model — see the proposal's
    point that running the wrong specialist on an input produces a
    confident, meaningless answer, which is worse than no answer."""


class MetadataRouter:
    def __init__(self, registry: dict[str, list] | None = None):
        self.registry = registry or build_registry()

    def route(self, case: dict) -> PredictionResult:
        """
        `case` must include a "modality" key — e.g. set from a DICOM tag,
        an upload form's dropdown, or Module 2's validated record type.
        Never inferred from the raw pixel/feature data itself.
        """
        modality = case.get("modality")
        if modality not in self.registry:
            raise UnroutableCaseError(
                f"No specialist registered for modality={modality!r}. "
                f"Known modalities: {sorted(self.registry.keys())}"
            )

        candidates = self.registry[modality]
        # Simplest case: one specialist per modality. If a modality later has
        # multiple candidate models (e.g. two chest-X-ray vendors), that
        # selection policy (best validation AUC? hospital preference?) goes here.
        model = candidates[0]
        return model.predict(case)

    def route_multi(self, cases: list[dict]) -> list[PredictionResult]:
        """Route several cases for the same patient (e.g. vitals + a chest X-ray
        taken the same visit) — results are combined downstream by fusion.py."""
        return [self.route(case) for case in cases]


class ClassifierBasedRouter:
    """
    Stub for the "lightweight classifier" routing option from the proposal —
    useful once you have labeled examples of what each modality's raw input
    looks like and want the router to work without a hospital reliably
    tagging every upload correctly. Not implemented yet: needs a training
    set of (raw_input -> modality label) pairs, which doesn't exist until
    Module 2's ingestion pipeline has real hospital data flowing through it.
    """
    def __init__(self, registry: dict[str, list] | None = None):
        self.registry = registry or build_registry()
        raise NotImplementedError(
            "ClassifierBasedRouter needs labeled modality-classification "
            "training data before it can replace MetadataRouter — next sprint."
        )
