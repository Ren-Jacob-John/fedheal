"""Safe response contract for scans when no validated imaging model is registered."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ScanAnalysisResult:
    scan_id: str
    status: str
    message: str
    finding: None
    confidence: None
    heatmap_ref: None
    model_version: None
    model_status: str
    requires_clinician_review: bool


def analysis_unavailable(scan_id: str, model_status: str = "UNAVAILABLE") -> dict:
    """Return status only; callers must authorize the scan through Module 1 first."""
    if not scan_id.strip():
        raise ValueError("scan_id is required")
    if not model_status.strip():
        raise ValueError("model_status is required")
    result = ScanAnalysisResult(
        scan_id=scan_id,
        status="analysis_unavailable",
        message="analysis unavailable: no validated imaging model",
        finding=None,
        confidence=None,
        heatmap_ref=None,
        model_version=None,
        model_status=model_status,
        requires_clinician_review=True,
    )
    return asdict(result)
