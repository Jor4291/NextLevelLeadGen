"""ICP scoring field metadata and override persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from backend.settings import ROOT_DIR, settings

ICP_OVERRIDES_PATH = ROOT_DIR / "config" / "icp_overrides.yaml"
SCORING_SECTIONS = (
    "scoring_weights",
    "negative_weights",
    "thresholds",
    "employee_bands",
)

SCORING_FIELD_META: dict[str, dict[str, dict[str, Any]]] = {
    "scoring_weights": {
        "industry_match": {
            "label": "Industry match",
            "description": "Lead's website or name matches target industry keywords.",
            "min": 0,
            "max": 50,
        },
        "employee_sweet_spot": {
            "label": "Employee sweet spot",
            "description": "Company size is in the ideal employee band.",
            "min": 0,
            "max": 50,
        },
        "process_opt_pain": {
            "label": "Process optimization pain",
            "description": "Cap for points from manual workflow / spreadsheet pain signals.",
            "min": 0,
            "max": 50,
        },
        "custom_software_pain": {
            "label": "Custom software pain",
            "description": "Cap for points from integration, ERP, and software pain signals.",
            "min": 0,
            "max": 50,
        },
        "hiring_signal": {
            "label": "Hiring signal",
            "description": "Cap for points from careers pages and job posting signals.",
            "min": 0,
            "max": 30,
        },
        "contact_quality": {
            "label": "Contact quality",
            "description": "Points for having email, phone, and named contact.",
            "min": 0,
            "max": 20,
        },
        "decision_maker": {
            "label": "Decision maker",
            "description": "Contact title matches VP/Director/Owner patterns.",
            "min": 0,
            "max": 20,
        },
        "named_email": {
            "label": "Named email",
            "description": "Email looks like firstname.lastname@company.",
            "min": 0,
            "max": 10,
        },
        "portal_detection": {
            "label": "Portal / login detected",
            "description": "Customer, employee, or vendor portal found on website.",
            "min": 0,
            "max": 40,
        },
        "positive_keyword": {
            "label": "Positive ICP keyword",
            "description": "Cap for points from strong-fit keywords in icp.yaml.",
            "min": 0,
            "max": 30,
        },
        "negative_keyword": {
            "label": "Weak-fit keyword penalty",
            "description": "Cap for score reduction from weak-fit keywords.",
            "min": 0,
            "max": 30,
        },
    },
    "negative_weights": {
        "no_website": {
            "label": "No website",
            "description": "Penalty when no company website is found.",
            "min": 0,
            "max": 30,
        },
        "no_contact": {
            "label": "No contact info",
            "description": "Penalty when no email or phone is found.",
            "min": 0,
            "max": 30,
        },
        "employee_out_of_band": {
            "label": "Employee out of band",
            "description": "Penalty when employee count is outside acceptable range.",
            "min": 0,
            "max": 30,
        },
    },
    "thresholds": {
        "hot": {
            "label": "Tier A (hot)",
            "description": "Minimum score for A-tier leads.",
            "min": 0,
            "max": 100,
        },
        "qualified": {
            "label": "Tier B (qualified)",
            "description": "Minimum score for B-tier leads.",
            "min": 0,
            "max": 100,
        },
        "review": {
            "label": "Tier C (review)",
            "description": "Minimum score for C-tier leads.",
            "min": 0,
            "max": 100,
        },
        "min_persist": {
            "label": "Minimum persist score",
            "description": "Low-score leads without contact are dropped.",
            "min": 0,
            "max": 100,
        },
        "evidence_floor": {
            "label": "Evidence floor cap",
            "description": "Max score when no pain/hiring evidence is found.",
            "min": 0,
            "max": 100,
        },
    },
    "employee_bands": {
        "sweet_spot_min": {
            "label": "Sweet spot min employees",
            "description": "Lower bound of ideal company size.",
            "min": 1,
            "max": 10000,
        },
        "sweet_spot_max": {
            "label": "Sweet spot max employees",
            "description": "Upper bound of ideal company size.",
            "min": 1,
            "max": 10000,
        },
        "acceptable_min": {
            "label": "Acceptable min employees",
            "description": "Lower bound before out-of-band penalty.",
            "min": 1,
            "max": 10000,
        },
        "acceptable_max": {
            "label": "Acceptable max employees",
            "description": "Upper bound before out-of-band penalty.",
            "min": 1,
            "max": 50000,
        },
    },
}

SECTION_LABELS = {
    "scoring_weights": "Scoring weights (points added)",
    "negative_weights": "Penalties (points subtracted)",
    "thresholds": "Score thresholds & tiers",
    "employee_bands": "Employee count bands",
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_base_icp_config() -> dict[str, Any]:
    path = Path(settings.icp_config_path)
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_icp_overrides_file() -> dict[str, Any]:
    if not ICP_OVERRIDES_PATH.exists():
        return {}
    with ICP_OVERRIDES_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def merge_icp_overrides(config: dict[str, Any]) -> dict[str, Any]:
    overrides = load_icp_overrides_file()
    if not overrides:
        return config

    config = dict(config)
    for section in SCORING_SECTIONS:
        if section in overrides and overrides[section]:
            base_section = dict(config.get(section, {}))
            config[section] = _deep_merge(base_section, overrides[section])
    return config


def _coerce_number(value: Any, field_meta: dict[str, Any]) -> float | int:
    if isinstance(value, bool):
        raise ValueError("Boolean values are not allowed")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Value must be a number") from exc

    if number != int(number):
        number = float(number)
    else:
        number = int(number)

    min_val = field_meta.get("min")
    max_val = field_meta.get("max")
    if min_val is not None and number < min_val:
        raise ValueError(f"Value must be at least {min_val}")
    if max_val is not None and number > max_val:
        raise ValueError(f"Value must be at most {max_val}")
    return number


def _validate_section(section: str, values: dict[str, Any]) -> dict[str, float | int]:
    if section not in SCORING_SECTIONS:
        raise ValueError(f"Unknown scoring section: {section}")

    meta = SCORING_FIELD_META.get(section, {})
    validated: dict[str, float | int] = {}
    for key, value in values.items():
        if key not in meta:
            raise ValueError(f"Unknown field '{key}' in {section}")
        validated[key] = _coerce_number(value, meta[key])
    return validated


def get_scoring_settings() -> dict[str, Any]:
    base = _load_base_icp_config()
    overrides = load_icp_overrides_file()

    merged = merge_icp_overrides(dict(base))
    return {
        "values": {section: merged.get(section, {}) for section in SCORING_SECTIONS},
        "defaults": {section: base.get(section, {}) for section in SCORING_SECTIONS},
        "overrides": {section: overrides.get(section, {}) for section in SCORING_SECTIONS},
        "fields": SCORING_FIELD_META,
        "sections": SECTION_LABELS,
        "overrides_path": "config/icp_overrides.yaml",
    }


def update_scoring_settings(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        raise ValueError("No scoring settings provided")

    current = load_icp_overrides_file()
    base = _load_base_icp_config()

    for section, values in payload.items():
        if section not in SCORING_SECTIONS:
            raise ValueError(f"Unknown scoring section: {section}")
        if not isinstance(values, dict):
            raise ValueError(f"{section} must be an object")

        validated = _validate_section(section, values)
        section_defaults = base.get(section, {})
        section_overrides: dict[str, float | int] = {}

        for key, value in validated.items():
            default_value = section_defaults.get(key)
            if default_value is None or value != default_value:
                section_overrides[key] = value

        if section_overrides:
            current[section] = section_overrides
        elif section in current:
            current.pop(section)

    ICP_OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ICP_OVERRIDES_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(current, f, default_flow_style=False, sort_keys=False)

    from backend.config_loader import load_icp_config

    load_icp_config.cache_clear()
    return get_scoring_settings()


def reset_scoring_overrides() -> dict[str, Any]:
    if ICP_OVERRIDES_PATH.exists():
        ICP_OVERRIDES_PATH.unlink()

    from backend.config_loader import load_icp_config

    load_icp_config.cache_clear()
    return get_scoring_settings()
