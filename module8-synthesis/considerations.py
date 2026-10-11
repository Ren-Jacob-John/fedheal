"""Versioned, reviewable workflow considerations for the clinician packet.

These are operational reminders, not clinical guidance. A condition without
an explicit rule match gets no suggestion.
"""

RULESET_VERSION = "1.0.0"
UNVALIDATED = "unvalidated - for clinician review"

RULES = (
    {
        "id": "heart-disease-review-context-v1",
        "version": "1.0.0",
        "condition": "heart_disease",
        "text": (
            "Review the available case information and confirm the model output "
            "against the clinical record before making a care decision."
        ),
        "source": "docs/MVP_SCOPE.md#what-works-today-and-what-is-planned",
        "provenance": (
            "Operational reminder derived from the repository's clinician-review "
            "requirement; not clinical evidence or a treatment recommendation."
        ),
        "validation_status": UNVALIDATED,
    },
)


def considerations_for(condition: str) -> dict:
    """Return only explicitly configured rules for a canonical condition."""
    matches = [dict(rule) for rule in RULES if rule["condition"] == condition]
    return {
        "ruleset_version": RULESET_VERSION,
        "status": "matched" if matches else "no_match",
        "message": None if matches else "no suggestion available",
        "items": matches,
    }
