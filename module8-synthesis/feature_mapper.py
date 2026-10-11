"""
Module 1 stored record  ->  the vitals specialist's input vector.

This is the ONE place that decides which stored field feeds which model
feature. It is deliberately boring:

  * The mapping is an explicit table (VITALS_MAPPING), one row per model
    feature. Every row is the identity — the specialist's declared feature
    names ARE Module 1's stored field names, in natural units, in the order
    Module 3's real_data.FEATURE_KEYS uses. No unit conversion, no
    imputation, no derived value, no renaming of a field to a different
    concept.
  * A field that is absent, null or NaN is reported as MISSING. It is never
    defaulted to a mean, a zero, or "the same as another field".
  * The label (`label`, `label_source`) is never an input.
  * `verify_mapping()` fails loudly if the table and the specialist's
    declared feature names ever drift apart, so a renamed feature can't
    silently shift every SHAP attribution onto the wrong column.

See docs/DATA_CONTRACT.md for the field-by-field contract across modules,
including the legacy heart-disease feature names this replaces.
"""
import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class FeatureRule:
    model_feature: str
    source_field: str      # Module 1 `StoredVitalsOut` field
    unit: str
    transform: str = "identity"


VITALS_MAPPING: tuple[FeatureRule, ...] = (
    FeatureRule("age_years", "age_years", "years"),
    FeatureRule("systolic_bp", "systolic_bp", "mmHg"),
    FeatureRule("diastolic_bp", "diastolic_bp", "mmHg"),
    FeatureRule("heart_rate_bpm", "heart_rate_bpm", "beats/min"),
    FeatureRule("weight_kg", "weight_kg", "kg"),
    FeatureRule("height_cm", "height_cm", "cm"),
    FeatureRule("medication_count", "medication_count", "count"),
    FeatureRule("medication_mg_total", "medication_mg_total", "mg"),
)

OPTIONAL_VITALS_MAPPING: tuple[FeatureRule, ...] = (
    FeatureRule("temperature_c", "temperature_c", "degrees C"),
    FeatureRule("spo2_percent", "spo2_percent", "percent"),
    FeatureRule("respiratory_rate_bpm", "respiratory_rate_bpm", "breaths/min"),
)

VITALS_SCHEMA_VERSIONS = {
    "v1": VITALS_MAPPING,
    "v2": VITALS_MAPPING + OPTIONAL_VITALS_MAPPING,
}

CONTEXT_MAPPING = {
    "admission_reason": "case.admission_reason",
    "current_condition": "case.current_condition",
    "presenting_symptoms": "case.presenting_symptoms",
    "medical_history": "history",
}

# Stored-record fields that are never model inputs.
NON_INPUT_FIELDS = ("id", "patient_ref", "label", "label_source", "validation_status", "hospital_id")


class MappingDriftError(RuntimeError):
    """The mapping table and the specialist's declared feature names disagree."""


def verify_mapping(specialist_feature_names: list[str]) -> None:
    requested = list(specialist_feature_names)
    if not any([rule.model_feature for rule in rules] == requested
               for rules in VITALS_SCHEMA_VERSIONS.values()):
        raise MappingDriftError(
            f"feature mapping does not match a supported versioned schema: {requested}"
        )


@dataclass
class MappedInput:
    features: list                      # ordered like the specialist; None where missing
    missing: list[str] = field(default_factory=list)     # model feature names
    invalid: list[str] = field(default_factory=list)     # present but not a finite number
    inputs: list[dict] = field(default_factory=list)     # {feature, source_field, value, unit, transform}

    @property
    def complete(self) -> bool:
        return not self.missing and not self.invalid


def map_record(record: dict, feature_names: list[str] | None = None) -> MappedInput:
    features, missing, invalid, inputs = [], [], [], []
    if feature_names is None:
        rules = VITALS_SCHEMA_VERSIONS["v1"]
    else:
        selected = list(feature_names)
        matched = next((schema for schema in VITALS_SCHEMA_VERSIONS.values()
                        if [rule.model_feature for rule in schema] == selected), None)
        if matched is None:
            raise MappingDriftError(f"unsupported model feature schema: {selected}")
        rules = matched

    for rule in rules:
        raw = record.get(rule.source_field)
        value = None
        if raw is None or (isinstance(raw, float) and math.isnan(raw)):
            missing.append(rule.model_feature)
        elif isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
            invalid.append(rule.model_feature)
        else:
            value = float(raw)
        features.append(value)
        inputs.append({
            "feature": rule.model_feature,
            "source_field": rule.source_field,
            "value": value,
            "unit": rule.unit,
            "transform": rule.transform,
        })
    return MappedInput(features=features, missing=missing, invalid=invalid, inputs=inputs)


def map_case_context(case: dict, history: dict | None, record: dict,
                     model_feature_names: list[str]) -> dict:
    """Map context availability/use without returning any clinical free text."""
    used = set(model_feature_names)
    symptoms = case.get("presenting_symptoms") or []
    history_fields = (
        "conditions", "previous_diagnoses", "surgeries", "allergies",
        "medications", "family_history", "previous_admissions", "symptoms",
    )
    drivers = [
        {"source": "vitals", "available": True, "used_by_model": True,
         "fields": [rule.model_feature for rule in VITALS_SCHEMA_VERSIONS["v2"]
                    if rule.model_feature in used]},
        {"source": "medical_history", "available": history is not None, "used_by_model": False,
         "fields": [name for name in history_fields if history and history.get(name)]},
        {"source": "presenting_symptoms", "available": bool(symptoms), "used_by_model": False},
        {"source": "admission_reason", "available": bool(case.get("admission_reason")), "used_by_model": False},
        {"source": "condition", "available": bool(case.get("current_condition")),
         "used_by_model": False, "used_for": "specialist selection"},
    ]
    optional_missing = [rule.model_feature for rule in OPTIONAL_VITALS_MAPPING
                        if record.get(rule.source_field) is None]
    optional_unused = [rule.model_feature for rule in OPTIONAL_VITALS_MAPPING
                       if record.get(rule.source_field) is not None and rule.model_feature not in used]
    context_missing = [item["source"] for item in drivers[1:] if not item["available"]]
    return {
        "input_drivers": drivers,
        "missing_inputs": {"optional_vitals": optional_missing, "context": context_missing},
        "unused_inputs": [
            item["source"] for item in drivers[1:] if item["available"]
        ] + optional_unused,
    }
