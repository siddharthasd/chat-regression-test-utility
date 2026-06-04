"""Bundled-schema loading + the cached Draft 2020-12 validator (research R2/R5/R8).

``BUNDLED_CONTRACT_VERSION`` is the single source of truth for the runtime
version gate (FR-015). The schema is loaded once from package data.
"""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from importlib import resources

from jsonschema import Draft202012Validator, FormatChecker

#: The one bundled schema's version. Single source of truth for the version gate.
BUNDLED_CONTRACT_VERSION: int = 1

_SCHEMA_PACKAGE = "harness.contract.schemas"
_SCHEMA_FILENAME = "standard_evaluation_contract.schema.json"

# A FormatChecker that actually enforces ISO-8601 / RFC 3339 for `date-time`
# (FR-013) without requiring the optional rfc3339-validator dependency.
_format_checker = FormatChecker()


@_format_checker.checks("date-time", raises=(ValueError, TypeError))
def _is_iso8601_datetime(value: object) -> bool:
    if not isinstance(value, str):
        return True  # non-strings are caught by the schema's `type` keyword
    # datetime.fromisoformat handles the common RFC 3339 forms; normalize the
    # trailing 'Z' (UTC) which older Pythons don't accept directly.
    datetime.fromisoformat(value.replace("Z", "+00:00"))
    return True


@lru_cache(maxsize=1)
def load_schema() -> dict:
    """Load the bundled contract schema (cached)."""
    text = (
        resources.files(_SCHEMA_PACKAGE).joinpath(_SCHEMA_FILENAME).read_text(encoding="utf-8")
    )
    return json.loads(text)


@lru_cache(maxsize=1)
def get_validator() -> Draft202012Validator:
    """Return the cached Draft 2020-12 validator with date-time format assertion."""
    return Draft202012Validator(load_schema(), format_checker=_format_checker)
