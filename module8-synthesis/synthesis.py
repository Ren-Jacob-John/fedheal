"""
Module 8 — Synthesis / review-packet layer.

Aggregates Module 6's ConditionReport (raw specialist predictions +
explanations) — and optionally Module 5's FusedAssessment — into one
structured SynthesisReport meant for a clinician to review. See this
module's README.md "What this deliberately is NOT" before extending it:
in short, this layer summarizes model evidence, it never issues a
diagnosis, treatment plan, or drug/dosage recommendation.
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "module6-condition-router"))
sys.path.insert(0, str(Path(__file__).parent.parent / "module5-modelzoo"))

from condition_router import ConditionReport  # noqa: E402
from fusion import FusedAssessment  # noqa: E402

DISCLAIMER = (
    "Computational decision-support output only. Every finding below comes "
    "from a statistical/ML model — some of them placeholder stubs, clearly "
    "marked — operating on the data supplied for this run. Nothing here is "
    "a diagnosis, and nothing here recommends a treatment, medication, dose, "
    "or prognosis. It requires review, confirmation, and clinical judgment "
    "by a licensed clinician before it informs any care decision."
)


@dataclass
class FindingSummary:
    specialist_id: str
    model_name: str
    model_impression: str            # renamed from "label" to avoid reading as a verdict
    confidence: float
    is_stub: bool
    severity_weight: Optional[float] = None   # from module5's fusion table, if available
    explanation_summaries: list[str] = field(default_factory=list)
    unavailable_explainers: list[str] = field(default_factory=list)


@dataclass
class SynthesisReport:
    condition_queried: str
    findings: list[FindingSummary]
    data_completeness: list[str]           # specialist_ids the condition defines but no data was given for
    used_any_stub_models: bool
    overall_risk_score: Optional[float] = None      # from module5 FusionLayer, if supplied
    overall_risk_level: Optional[str] = None
    urgent_review_flags: list[str] = field(default_factory=list)
    requires_clinician_review: bool = True  # intentionally not a parameter — always true
    disclaimer: str = DISCLAIMER

    def to_markdown(self) -> str:
        lines = [
            f"# Review Packet — {self.condition_queried}",
            "",
            f"> {self.disclaimer}",
            "",
        ]
        if self.overall_risk_score is not None:
            lines.append(
                f"**Combined risk score (Module 5 fusion):** "
                f"{self.overall_risk_score:.3f} ({self.overall_risk_level})"
            )
            lines.append("")
        if self.urgent_review_flags:
            lines.append("**Urgent review flags:** " + "; ".join(self.urgent_review_flags))
            lines.append("")

        lines.append("## Specialist findings")
        for f in self.findings:
            stub_note = "  ⚠️ STUB — placeholder model, not a trained specialist" if f.is_stub else ""
            lines.append(
                f"- **{f.specialist_id}** ({f.model_name}): `{f.model_impression}` "
                f"— confidence {f.confidence:.2f}{stub_note}"
            )
            for e in f.explanation_summaries:
                lines.append(f"  - {e}")
            for u in f.unavailable_explainers:
                lines.append(f"  - (explainer unavailable: {u})")

        if self.data_completeness:
            lines.append("")
            lines.append(
                "## Missing inputs\n"
                "No data was supplied for the following specialists this condition "
                "normally uses, so this report is based on partial evidence:"
            )
            for s in self.data_completeness:
                lines.append(f"- {s}")

        lines.append("")
        lines.append(f"**Requires clinician review before any action:** {self.requires_clinician_review}")
        return "\n".join(lines)


def build_synthesis(
    condition_report: ConditionReport,
    all_specialist_ids_for_condition: list[str],
    fused: Optional[FusedAssessment] = None,
) -> SynthesisReport:
    """
    `all_specialist_ids_for_condition` should come from the ConditionSpec
    (conditions.py) that produced `condition_report`, so we can report
    which specialists were *defined* for this condition but had no data
    supplied — condition_router.py silently skips those (by design, so a
    caller with partial data doesn't get a hard failure), but a clinician
    reading the final report needs to know the picture is incomplete.
    """
    supplied_ids = {f.specialist_id for f in condition_report.findings}
    missing = [sid for sid in all_specialist_ids_for_condition if sid not in supplied_ids]

    findings = []
    used_any_stub = False
    for f in condition_report.findings:
        pred = f.prediction
        used_any_stub = used_any_stub or pred.is_stub

        severity_weight = None
        urgent = pred.metadata.get("flag_for_urgent_review", False) if pred.metadata else False

        explanation_summaries, unavailable = [], []
        for exp in f.explanations:
            if exp.is_stub:
                unavailable.append(f"{exp.method}: {exp.summary}")
            else:
                explanation_summaries.append(f"[{exp.method}] {exp.summary}")

        findings.append(FindingSummary(
            specialist_id=f.specialist_id,
            model_name=pred.model_name,
            model_impression=pred.label,
            confidence=pred.confidence,
            is_stub=pred.is_stub,
            severity_weight=severity_weight,
            explanation_summaries=explanation_summaries,
            unavailable_explainers=unavailable,
        ))
        if urgent:
            pass  # placeholder hook — urgent_review_flags populated below from fused, if present

    urgent_flags = list(fused.urgent_review_flags) if fused else []

    return SynthesisReport(
        condition_queried=condition_report.condition,
        findings=findings,
        data_completeness=missing,
        used_any_stub_models=used_any_stub or (fused.used_any_stub_models if fused else False),
        overall_risk_score=fused.overall_risk_score if fused else None,
        overall_risk_level=fused.risk_level if fused else None,
        urgent_review_flags=urgent_flags,
    )
