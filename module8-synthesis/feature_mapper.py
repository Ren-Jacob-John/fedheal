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

# Stored-record fields that are never model inputs.
NON_INPUT_FIELDS = ("id", "patient_ref", "label", "label_source", "validation_status", "hospital_id")


class MappingDriftError(RuntimeError):
    """The mapping table and the specialist's declared feature names disagree."""


def verify_mapping(specialist_feature_names: list[str]) -> None:
    table = [r.model_feature for r in VITALS_MAPPING]
    if table != list(specialist_feature_names):
        raise MappingDriftError(
            f"feature mapping {table} does not match the specialist's declared "
            f"feature names {list(specialist_feature_names)}"
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


def map_record(record: dict) -> MappedInput:
    features, missing, invalid, inputs = [], [], [], []
    for rule in VITALS_MAPPING:
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
