from __future__ import annotations

import logging
import platform
from pathlib import Path

from backend.settings import settings

logger = logging.getLogger(__name__)


def scrape_readiness() -> tuple[bool, list[str]]:
    notes: list[str] = []
    ready = True

    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except ImportError:
        ready = False
        notes.append("Install Playwright: pip install playwright")

    if not _chromium_available():
        ready = False
        notes.append("Install Chromium browser: playwright install chromium")

    icp_path = Path(settings.icp_config_path)
    if not icp_path.exists():
        ready = False
        notes.append(f"Missing ICP config: {icp_path}")

    if ready:
        notes.append("Scrape engine ready. Use city + state for best results.")

    return ready, notes


def _chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception as exc:
        logger.debug("Chromium check failed: %s", exc)
        if platform.system() == "Windows":
            chromium_path = Path.home() / "AppData" / "Local" / "ms-playwright"
            return chromium_path.exists()
        return False
