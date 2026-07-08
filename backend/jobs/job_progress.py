"""Shared progress percent calculation for scrape jobs."""

from __future__ import annotations

import re


def percent_from_message(message: str, status: str) -> int:
    message = message or ""
    status = (status or "pending").lower()

    if status == "pending":
        return 0
    if status in ("completed", "failed", "cancelled"):
        return 100

    enriching = re.search(r"Enriching (\d+)/(\d+)", message, re.I)
    website_lookup = re.search(r"Website lookup (\d+)/(\d+)", message, re.I)
    resolving = re.search(r"Resolving websites for (\d+)", message, re.I)
    found = re.search(r"Found (\d+) companies", message, re.I)

    if enriching:
        current, total = int(enriching.group(1)), int(enriching.group(2))
        return min(99, round(50 + (current / max(total, 1)) * 49))
    if found:
        return 50
    if website_lookup:
        current, total = int(website_lookup.group(1)), int(website_lookup.group(2))
        return min(49, round(15 + (current / max(total, 1)) * 34))
    if resolving:
        return 14
    if re.search(r"Searching Google Maps", message, re.I):
        return 6
    if re.search(r"Trying Bing", message, re.I):
        return 10
    if re.search(r"Starting discovery", message, re.I):
        return 2
    if re.search(r"Cancellation requested", message, re.I):
        return 0
    return 8
