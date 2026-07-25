"""
Rule-based checks that run BEFORE anything reaches a model. Three layers:

1. De-identification screen — reject the whole upload if an identifying field
   shows up, before we even look at the values.
2. Range/plausibility checks — is this value physically possible for a human?
3. Cross-field consistency checks — do the fields agree with each other?

These are intentionally simple, explicit, and easy for a non-ML teammate to
extend — add a new tuple/function rather than touching the pipeline logic.
"""
from schema import VitalsRecord

# Any of these column/key names appearing in an upload triggers an outright
# rejection of that record (not just a warning) — this is a hard boundary,
# not a data-quality signal.
FORBIDDEN_FIELDS = {
    "name", "first_name", "last_name", "full_name",
    "address", "street", "city", "zip", "postal_code",
    "ssn", "social_security_number", "mrn", "medical_record_number",
    "phone", "email", "dob", "date_of_birth",
}

# (min, max) plausible physical ranges for adult + pediatric humans combined.
PLAUSIBLE_RANGES = {
    "age_years": (0, 120),
    "height_cm": (25, 250),      # newborn to very tall adult
    "weight_kg": (0.5, 400),
    "systolic_bp": (40, 300),
    "diastolic_bp": (20, 200),
    "heart_rate_bpm": (20, 250),
}


def check_forbidden_fields(raw_record: dict) -> list[str]:
    """Returns a list of forbidden keys found in a raw (pre-schema) record dict."""
    lowered_keys = {k.lower() for k in raw_record.keys()}
    return sorted(lowered_keys & FORBIDDEN_FIELDS)


def check_plausible_ranges(record: VitalsRecord) -> list[str]:
    """Returns a list of human-readable reasons for any implausible values."""
    reasons = []
    for field, (lo, hi) in PLAUSIBLE_RANGES.items():
        value = getattr(record, field, None)
        if value is None:
            continue
        if not (lo <= value <= hi):
            reasons.append(f"{field}={value} outside plausible range [{lo}, {hi}]")
    return reasons


def check_cross_field_consistency(record: VitalsRecord) -> list[str]:
    """
    Checks where one field's value only makes sense in light of another.
    Extend this as clinical reviewers flag more patterns.
    """
    reasons = []

    # A newborn/infant shouldn't be on a large combined daily medication dose.
    if record.age_years < 2 and record.medication_mg_total > 500:
        reasons.append(
            f"medication_mg_total={record.medication_mg_total} is unusually high "
            f"for age_years={record.age_years}"
        )

    # medication_count says there are meds, but total dose is 0 (or vice versa).
    if record.medication_count > 0 and record.medication_mg_total == 0:
        reasons.append("medication_count > 0 but medication_mg_total == 0")
    if record.medication_count == 0 and record.medication_mg_total > 0:
        reasons.append("medication_mg_total > 0 but medication_count == 0")

    # BMI sanity check (very loose bounds — this is a plausibility check, not
    # a clinical judgement) — catches unit-mixups like height in inches/meters.
    height_m = record.height_cm / 100
    if height_m > 0:
        bmi = record.weight_kg / (height_m ** 2)
        if not (8 <= bmi <= 90):
            reasons.append(
                f"implied BMI={bmi:.1f} from height/weight looks like a unit error"
            )

    # Diastolic shouldn't exceed systolic.
    if record.systolic_bp is not None and record.diastolic_bp is not None:
        if record.diastolic_bp >= record.systolic_bp:
            reasons.append(
                f"diastolic_bp={record.diastolic_bp} >= systolic_bp={record.systolic_bp}"
            )

    return reasons
