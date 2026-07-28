"""
User-editable settings with JSON persistence (matches the repo's file-store
convention). Holds FBA fee overrides and default per-unit costs so the numbers
can be tuned from the UI without editing code.

Defaults come from fba_calculator; only the values the user changes are stored,
and they are merged over the defaults on read.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

from . import fba_calculator as calc

SETTINGS_FILE = Path(os.getenv(
    "FBA_SETTINGS_FILE",
    str(Path(__file__).resolve().parent.parent / "fba_settings.json"),
))


def defaults() -> Dict[str, Any]:
    """Full default settings, derived from the calculator's fee tables."""
    return {
        "referral_fee_pct": dict(calc.REFERRAL_FEE_PCT),
        "referral_minimum": calc.REFERRAL_MINIMUM,
        "storage_fee_per_cuft": calc.STORAGE_FEE_PER_CUFT,
        "oversize_base_fee": calc.OVERSIZE_BASE_FEE,
        # per-unit cost defaults used by the scan engine
        "default_inbound_shipping": 0.50,
        "default_prep_cost": 0.30,
        "default_capture_rate": 0.30,
    }


def _load_overrides() -> Dict[str, Any]:
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def current() -> Dict[str, Any]:
    """Defaults merged with saved overrides (overrides win)."""
    merged = defaults()
    overrides = _load_overrides()
    for key, val in overrides.items():
        if key == "referral_fee_pct" and isinstance(val, dict):
            merged["referral_fee_pct"].update(val)   # merge per-category
        elif key in merged:
            merged[key] = val
    return merged


# Fields that must be numeric and non-negative.
_NUMERIC_FIELDS = {
    "referral_minimum", "storage_fee_per_cuft", "oversize_base_fee",
    "default_inbound_shipping", "default_prep_cost",
}


def update(patch: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a partial update, persist it merged over existing overrides."""
    overrides = _load_overrides()

    for key, val in patch.items():
        if key == "referral_fee_pct":
            if not isinstance(val, dict):
                raise ValueError("referral_fee_pct must be an object")
            clean = {}
            for cat, pct in val.items():
                pct = float(pct)
                if not 0 <= pct <= 1:
                    raise ValueError(f"referral_fee_pct[{cat}] must be between 0 and 1")
                clean[cat] = pct
            overrides.setdefault("referral_fee_pct", {}).update(clean)
        elif key == "default_capture_rate":
            v = float(val)
            if not 0 < v <= 1:
                raise ValueError("default_capture_rate must be between 0 and 1")
            overrides[key] = v
        elif key in _NUMERIC_FIELDS:
            v = float(val)
            if v < 0:
                raise ValueError(f"{key} must be >= 0")
            overrides[key] = v
        # unknown keys are ignored

    with open(SETTINGS_FILE, "w") as f:
        json.dump(overrides, f, indent=2)
    return current()


def reset() -> Dict[str, Any]:
    """Delete all overrides, returning to defaults."""
    if SETTINGS_FILE.exists():
        SETTINGS_FILE.unlink()
    return current()
