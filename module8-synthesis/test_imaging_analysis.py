import pytest

from imaging_analysis import analysis_unavailable


def test_unavailable_scan_contract_has_no_finding_or_heatmap():
    result = analysis_unavailable("hospital-scan-id")
    assert result == {
        "scan_id": "hospital-scan-id",
        "status": "analysis_unavailable",
        "message": "analysis unavailable: no validated imaging model",
        "finding": None,
        "confidence": None,
        "heatmap_ref": None,
        "model_version": None,
        "model_status": "UNAVAILABLE",
        "requires_clinician_review": True,
    }


@pytest.mark.parametrize("scan_id,model_status", [("", "untrained"), ("scan-1", "")])
def test_unavailable_scan_contract_requires_identifiers(scan_id, model_status):
    with pytest.raises(ValueError):
        analysis_unavailable(scan_id, model_status)
