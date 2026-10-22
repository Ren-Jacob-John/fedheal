# Server shared code

The audit confirmed byte-identical copies of `service_auth.py`, `audit.py`,
`docs_theme.py`, and `limits.py` across services. They remain service-local
for now because every backend uses flat imports such as `import service_auth`
from a service-specific working directory. Moving them to this directory
would require changing import resolution and container startup semantics,
which is outside a structural-only move and could alter behavior.

The copies and their SHA-256 comparison are recorded in
`docs/RESTRUCTURE_PLAN.md`. Any later consolidation should add compatibility
imports and import-smoke tests before removing the service-local copies.
