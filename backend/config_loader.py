from functools import lru_cache
import re
from pathlib import Path
from typing import Any

import yaml

from backend.settings import ROOT_DIR, settings
from backend.icp_scoring_config import merge_icp_overrides

CUSTOM_INDUSTRIES_PATH = ROOT_DIR / "config" / "custom_industries.yaml"


def slugify_industry_id(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower().strip())
    return slug.strip("_")[:64]


def _load_custom_industries_file() -> dict[str, Any]:
    if not CUSTOM_INDUSTRIES_PATH.exists():
        return {"industries": {}}
    with CUSTOM_INDUSTRIES_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if "industries" not in data:
        data["industries"] = {}
    return data


def _merge_custom_industries(config: dict[str, Any]) -> dict[str, Any]:
    custom = _load_custom_industries_file().get("industries", {})
    if custom:
        merged = dict(config.get("industries", {}))
        merged.update(custom)
        config = dict(config)
        config["industries"] = merged
    return config


@lru_cache
def load_icp_config() -> dict[str, Any]:
    path = Path(settings.icp_config_path)
    with path.open(encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    config = merge_icp_overrides(config)
    return _merge_custom_industries(config)


@lru_cache
def load_brand_config() -> dict[str, Any]:
    path = Path(settings.brand_config_path)
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_brand_config() -> dict[str, Any]:
    return load_brand_config()


def get_industry_config(industry_id: str) -> dict[str, Any]:
    return load_icp_config().get("industries", {}).get(industry_id, {})


def get_discovery_queries(industry_id: str, label_hint: str | None = None) -> list[str]:
    """Maps/Bing search phrases for an industry slug."""
    cfg = get_industry_config(industry_id)
    queries = [q.strip() for q in cfg.get("search_queries", []) if str(q).strip()]
    if queries:
        return queries[:3]

    label = (label_hint or cfg.get("label") or industry_id.replace("_", " ")).strip()
    if not label:
        label = industry_id.replace("_", " ")
    return [f"{label} company", label]


def get_industry_options() -> list[dict[str, str]]:
    config = load_icp_config()
    custom_ids = set(_load_custom_industries_file().get("industries", {}).keys())
    return [
        {
            "id": key,
            "label": data["label"],
            "custom": key in custom_ids,
            "search_queries": data.get("search_queries", [])[:3],
        }
        for key, data in config.get("industries", {}).items()
    ]


def get_metro_options() -> list[dict[str, str]]:
    return load_icp_config().get("metros", [])


def add_custom_industry(label: str) -> dict[str, str]:
    clean_label = label.strip()
    if not clean_label:
        raise ValueError("Industry label is required")

    industry_id = slugify_industry_id(clean_label)
    if not industry_id:
        raise ValueError("Industry label must contain letters or numbers")

    base_path = Path(settings.icp_config_path)
    with base_path.open(encoding="utf-8") as f:
        base_config = yaml.safe_load(f) or {}
    if industry_id in base_config.get("industries", {}):
        raise ValueError(
            f"'{clean_label}' matches an existing default industry ({industry_id})"
        )

    custom_data = _load_custom_industries_file()
    industries = custom_data.setdefault("industries", {})

    words = [w.lower() for w in re.split(r"[\s/,&+-]+", clean_label) if len(w) > 2]
    industries[industry_id] = {
        "label": clean_label,
        "search_queries": [
            f"{clean_label} company",
            clean_label,
        ],
        "keywords": words or [industry_id.replace("_", " ")],
    }

    CUSTOM_INDUSTRIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CUSTOM_INDUSTRIES_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(custom_data, f, default_flow_style=False, sort_keys=False)

    load_icp_config.cache_clear()
    return {"id": industry_id, "label": clean_label, "custom": True}
