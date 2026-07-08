from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from urllib.parse import quote_plus, urljoin

import httpx
from bs4 import BeautifulSoup

from backend.config_loader import load_icp_config
from backend.settings import settings


@dataclass
class JobSignal:
    title: str
    snippet: str
    source_url: str
    matched_signals: list[str] = field(default_factory=list)


class JobSignalsScraper:
    """Scan public career pages and Indeed snippets for hiring/pain signals."""

    def __init__(self) -> None:
        self.config = load_icp_config()
        self.hiring_signals = [
            k.lower() for k in self.config.get("hiring_signals", [])
        ]
        self.process_keywords = [
            k.lower() for k in self.config.get("process_opt_keywords", [])
        ]
        self.software_keywords = [
            k.lower() for k in self.config.get("custom_software_keywords", [])
        ]
        self.headers = {"User-Agent": settings.scrape_user_agent}

    async def scan(
        self, company_name: str, website: str | None = None
    ) -> list[JobSignal]:
        signals: list[JobSignal] = []

        if website:
            career_signals = await self._scan_careers_page(website)
            signals.extend(career_signals)

        indeed_signals = await self._scan_indeed(company_name)
        signals.extend(indeed_signals)

        return signals

    async def _scan_careers_page(self, website: str) -> list[JobSignal]:
        base = website if website.startswith("http") else f"https://{website}"
        paths = ["careers", "jobs", "join-us", "work-with-us"]
        results: list[JobSignal] = []

        async with httpx.AsyncClient(
            headers=self.headers, follow_redirects=True, timeout=20.0
        ) as client:
            for path in paths:
                url = urljoin(base.rstrip("/") + "/", path)
                try:
                    resp = await client.get(url)
                    if resp.status_code >= 400:
                        continue
                    text = BeautifulSoup(resp.text, "lxml").get_text(" ", strip=True).lower()
                    matched = self._match_signals(text)
                    if matched:
                        results.append(
                            JobSignal(
                                title=f"Careers page signal ({path})",
                                snippet=text[:240],
                                source_url=url,
                                matched_signals=matched,
                            )
                        )
                    await asyncio.sleep(settings.scrape_rate_limit_seconds)
                except httpx.HTTPError:
                    continue
        return results

    async def _scan_indeed(self, company_name: str) -> list[JobSignal]:
        query = quote_plus(f'company:"{company_name}"')
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(f'indeed jobs {company_name}')}"
        results: list[JobSignal] = []

        async with httpx.AsyncClient(
            headers=self.headers, follow_redirects=True, timeout=20.0
        ) as client:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except httpx.HTTPError:
                return results

            soup = BeautifulSoup(resp.text, "lxml")
            for result in soup.select(".result")[:5]:
                title_el = result.select_one(".result__a")
                snippet_el = result.select_one(".result__snippet")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
                combined = f"{title} {snippet}".lower()
                if "indeed" not in combined and "job" not in combined:
                    continue
                matched = self._match_signals(combined)
                if matched:
                    href = title_el.get("href", "")
                    results.append(
                        JobSignal(
                            title=title[:200],
                            snippet=snippet[:240],
                            source_url=href,
                            matched_signals=matched,
                        )
                    )

        return results

    def _match_signals(self, text: str) -> list[str]:
        matched = []
        all_keywords = self.hiring_signals + self.process_keywords + self.software_keywords
        for kw in all_keywords:
            if kw in text:
                matched.append(kw)
        return list(dict.fromkeys(matched))


async def scan_job_signals(
    company_name: str, website: str | None = None
) -> list[JobSignal]:
    scraper = JobSignalsScraper()
    return await scraper.scan(company_name, website)
