# -*- coding: utf-8 -*-
"""
SPEC - the vocabulary, the rules, and the hotel's own configuration.

Everything here is DATA the engine reads at runtime, not code. `spec/canonical_fields.json`,
`spec/ir/*.json`, `spec/providers/*.json` and `spec/tenants/*.json` are the specification; this
package loads them, validates them, and refuses the ones that would run and answer about
nothing.

That is what makes success criterion 6 true rather than claimed: nothing in the engine knows
what control 6 is, the control index is the directory listing, and a twelfth control is a file.
"""
from .errors import Problem, SpecError
from .ir import ControlIR, available, load, load_schema, validate
from .registry import FieldSpec, Registry
from .schema import SchemaFeatureUnsupported
from .tenant import TenantConfig

__all__ = [
    "ControlIR",
    "FieldSpec",
    "Problem",
    "Registry",
    "SchemaFeatureUnsupported",
    "SpecError",
    "TenantConfig",
    "available",
    "load",
    "load_schema",
    "validate",
]
