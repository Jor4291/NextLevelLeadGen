from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from backend.settings import ROOT_DIR, settings


@lru_cache
def load_icp_config() -> dict[str, Any]:
    path = Path(settings.icp_config_path)
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache
def load_brand_config() -> dict[str, Any]:
    path = Path(settings.brand_config_path)
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_brand_config() -> dict[str, Any]:
    return load_brand_config()


def get_industry_options() -> list[dict[str, str]]:
    config = load_icp_config()
    return [
        {"id": key, "label": data["label"]}
        for key, data in config.get("industries", {}).items()
    ]


def get_metro_options() -> list[dict[str, str]]:
    return load_icp_config().get("metros", [])
