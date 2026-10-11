# Imaging status

Scans can be stored and linked to a hospital case, but no validated
task-specific imaging artifact or dataset/license provenance is available in
this checkout. The Module 5 imaging registry therefore selects no imaging
model; untrained torchvision architectures and untrained foundation-model
heads are not inference candidates. A stub returns `analysis unavailable`
with zero confidence, and Module 6 refuses to route a stub as a finding.

Module 8 exposes `POST /cases/{case_id}/scans/{scan_id}/analyze` as an
authenticated, hospital-scoped status-only endpoint. It forwards the
clinician's existing JWT to Module 1 to verify case/scan membership, then
returns `analysis_unavailable`, the message
`analysis unavailable: no validated imaging model`, `model_status:
UNAVAILABLE`, null finding/confidence/model version/heatmap reference, and
`requires_clinician_review: true`. It does not retrieve or process raw scan
bytes, and audit data contains identifiers only. Cross-hospital and
unlinked-scan requests are refused.

This remains an unavailable specialist contract, not imaging analysis.
Return unavailable until a licensed/public dataset, its version/license, a
validated weights artifact/hash, preprocessing contract, and independent
validation are recorded. No findings or heatmaps may be fabricated or
returned from untrained models.
