from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote_plus, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from backend.config_loader import load_icp_config
from backend.settings import settings


@dataclass
class DiscoveredCompany:
    company_name: str
    website: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    source_url: str | None = None
    industry: str = ""


def _normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    return phone.strip()


def _clean_company_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"\s*[|\-–—]\s*(Google Maps|Yelp|LinkedIn).*$", "", name, flags=re.I)
    return name[:256]


def _extract_domain(url: str) -> str | None:
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        domain = parsed.netloc or parsed.path.split("/")[0]
        domain = domain.lower().removeprefix("www.")
        if domain and "." in domain:
            return domain
    except Exception:
        pass
    return None


DIRECTORY_DOMAINS = (
    "yelp.com",
    "yellowpages.com",
    "manta.com",
    "bbb.org",
    "linkedin.com",
    "facebook.com",
    "indeed.com",
    "glassdoor.com",
    "wikipedia.org",
    "thomasnet.com",
    "zoominfo.com",
    "mapquest.com",
    "google.com",
    "bing.com",
)


# Max place-detail lookups per Maps query (keeps fast mode responsive)
MAPS_DETAIL_ENRICH_LIMIT = 8


class MapsDiscoveryScraper:
    """Discover companies via Playwright Google Maps + Bing."""

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self) -> None:
        self.config = load_icp_config()
        self.rate_limit = settings.scrape_rate_limit_seconds

    async def discover(
        self,
        industry: str,
        city: str | None = None,
        state: str | None = None,
        keyword_override: str | None = None,
        max_results: int = 50,
        progress_callback=None,
        should_cancel: Callable[[], bool] | None = None,
        skip_website_resolution: bool = False,
    ) -> list[DiscoveredCompany]:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is required for discovery. Run: pip install playwright && playwright install chromium"
            ) from exc

        industry_cfg = self.config.get("industries", {}).get(industry, {})
        queries = industry_cfg.get("search_queries", [industry])[:2]
        if keyword_override:
            queries = [keyword_override]

        location = ""
        if city and state:
            location = f"{city}, {state}"
        elif state:
            location = state

        seen_names: set[str] = set()
        results: list[DiscoveredCompany] = []

        def cancelled() -> bool:
            return bool(should_cancel and should_cancel())

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(user_agent=self.USER_AGENT)

            for q_idx, query in enumerate(queries):
                if cancelled():
                    break
                if len(results) >= max_results:
                    break
                search_q = f"{query} {location}".strip()
                if progress_callback:
                    pct = 3 + int((q_idx / max(len(queries), 1)) * 8)
                    progress_callback(
                        f"Searching Google Maps ({q_idx + 1}/{len(queries)}): {search_q}",
                        pct,
                    )

                batch = await self._search_google_maps(page, search_q, industry, max_results - len(results))
                if not batch:
                    if progress_callback:
                        progress_callback(f"Trying Bing: {search_q}", 10)
                    batch = await self._search_bing(page, search_q, industry, max_results - len(results))

                for company in batch:
                    key = company.company_name.lower()
                    if key in seen_names:
                        continue
                    seen_names.add(key)
                    if company.city is None and city:
                        company.city = city
                    if company.state is None and state:
                        company.state = state
                    company.industry = industry
                    results.append(company)
                    if len(results) >= max_results:
                        break

                await asyncio.sleep(self.rate_limit)

            unresolved = [c for c in results if not c.website]
            if unresolved and not skip_website_resolution:
                total_unresolved = max(len(unresolved), 1)
                if progress_callback:
                    progress_callback(
                        f"Resolving websites for {len(unresolved)} companies...",
                        14,
                    )

                for idx, company in enumerate(unresolved, start=1):
                    if cancelled():
                        break
                    pct = min(49, round(14 + (idx / total_unresolved) * 35))
                    if progress_callback:
                        progress_callback(
                            f"Website lookup {idx}/{total_unresolved}: {company.company_name}",
                            pct,
                        )
                    try:
                        website = await asyncio.wait_for(
                            self._resolve_website(
                                page, company.company_name, company.city, company.state
                            ),
                            timeout=12.0,
                        )
                    except asyncio.TimeoutError:
                        website = None
                    if website:
                        company.website = website
                        company.source_url = company.source_url or website
                    await asyncio.sleep(self.rate_limit * 0.3)
            elif unresolved and progress_callback:
                progress_callback(
                    f"Skipping website lookup for {len(unresolved)} companies (fast mode).",
                    45,
                )

            await browser.close()

        if len(results) < max_results and not cancelled():
            httpx_batch = await self._search_duckduckgo_httpx(
                f"{queries[0]} {location} USA".strip(), industry
            )
            for company in httpx_batch:
                key = company.company_name.lower()
                if key in seen_names:
                    continue
                seen_names.add(key)
                if company.city is None and city:
                    company.city = city
                if company.state is None and state:
                    company.state = state
                company.industry = industry
                results.append(company)
                if len(results) >= max_results:
                    break

        return results[:max_results]

    async def _enrich_from_place_detail(
        self, page, place_url: str, company: DiscoveredCompany
    ) -> None:
        """Open a Maps place page and extract website, phone, and address."""
        try:
            await page.goto(place_url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(1200)

            website_loc = page.locator('a[data-item-id="authority"]').first
            if await website_loc.count() > 0:
                href = await website_loc.get_attribute("href")
                if href and href.startswith("http"):
                    domain = _extract_domain(href)
                    if domain and not any(d in domain for d in DIRECTORY_DOMAINS):
                        company.website = href

            phone_loc = page.locator(
                'button[data-item-id^="phone"], a[href^="tel:"]'
            ).first
            if await phone_loc.count() > 0:
                tel = await phone_loc.get_attribute("href")
                if tel and tel.startswith("tel:"):
                    company.phone = _normalize_phone(tel.replace("tel:", ""))
                else:
                    phone_text = await phone_loc.inner_text()
                    if phone_text:
                        company.phone = _normalize_phone(phone_text)

            address_loc = page.locator('button[data-item-id="address"]').first
            if await address_loc.count() > 0:
                address_text = await address_loc.inner_text()
                if address_text:
                    company.address = address_text.strip()
        except Exception:
            pass

    async def _search_google_maps(
        self, page, query: str, industry: str, max_results: int
    ) -> list[DiscoveredCompany]:
        companies: list[DiscoveredCompany] = []
        maps_url = f"https://www.google.com/maps/search/{quote_plus(query)}"

        try:
            await page.goto(maps_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3500)

            for _ in range(5):
                await page.mouse.wheel(0, 2500)
                await page.wait_for_timeout(600)

            items = await page.locator('a[href*="maps/place"]').all()
            seen_labels: set[str] = set()
            pending_detail: list[tuple[DiscoveredCompany, str | None]] = []

            for item in items:
                if len(companies) >= max_results:
                    break
                name = await item.get_attribute("aria-label")
                href = await item.get_attribute("href")
                if not name:
                    continue
                clean = _clean_company_name(name)
                if clean.lower() in seen_labels:
                    continue
                seen_labels.add(clean.lower())
                company = DiscoveredCompany(
                    company_name=clean,
                    source_url=href,
                    industry=industry,
                )
                companies.append(company)
                if href and len(pending_detail) < MAPS_DETAIL_ENRICH_LIMIT:
                    pending_detail.append((company, href))

            for company, href in pending_detail:
                if href:
                    await self._enrich_from_place_detail(page, href, company)
                    await asyncio.sleep(self.rate_limit * 0.2)
        except Exception:
            return companies

        return companies

    async def _search_bing(
        self, page, query: str, industry: str, max_results: int
    ) -> list[DiscoveredCompany]:
        companies: list[DiscoveredCompany] = []
        url = f"https://www.bing.com/search?q={quote_plus(query)}"

        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(1200)
            items = await page.locator("li.b_algo h2 a").all()
            for item in items[:max_results]:
                title = await item.inner_text()
                href = await item.get_attribute("href")
                if not title or self._is_likely_directory(title, href or ""):
                    continue
                companies.append(
                    DiscoveredCompany(
                        company_name=_clean_company_name(title),
                        website=href if href and href.startswith("http") else None,
                        source_url=href,
                        industry=industry,
                    )
                )
        except Exception:
            return companies

        return companies

    async def _resolve_website(
        self, page, company_name: str, city: str | None, state: str | None
    ) -> str | None:
        location = f"{city} {state}".strip() if city or state else ""
        query = quote_plus(f"{company_name} {location} official site")
        url = f"https://www.bing.com/search?q={query}"

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(500)
            items = await page.locator("li.b_algo h2 a").all()
            first_name = company_name.split()[0].lower()
            for idx, item in enumerate(items[:5]):
                title = (await item.inner_text()).lower()
                href = await item.get_attribute("href")
                if not href or not href.startswith("http"):
                    continue
                domain = _extract_domain(href)
                if not domain or any(d in domain for d in DIRECTORY_DOMAINS):
                    continue
                if first_name in title or first_name in domain or idx == 0:
                    return href
        except Exception:
            return None
        return None

    async def _search_duckduckgo_httpx(self, query: str, industry: str) -> list[DiscoveredCompany]:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        companies: list[DiscoveredCompany] = []
        headers = {"User-Agent": self.USER_AGENT}

        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=30.0) as client:
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return []
            except httpx.HTTPError:
                return []

            soup = BeautifulSoup(resp.text, "lxml")
            for result in soup.select(".result"):
                title_el = result.select_one(".result__a")
                if not title_el:
                    continue
                title = _clean_company_name(title_el.get_text(strip=True))
                href = title_el.get("href", "")
                if not title or self._is_likely_directory(title, href):
                    continue
                companies.append(
                    DiscoveredCompany(
                        company_name=title,
                        website=self._resolve_ddg_redirect(href),
                        source_url=href,
                        industry=industry,
                    )
                )
        return companies

    def _resolve_ddg_redirect(self, href: str) -> str | None:
        if "uddg=" in href:
            match = re.search(r"uddg=([^&]+)", href)
            if match:
                return unquote(match.group(1))
        if href.startswith("http"):
            return href
        return None

    def _is_likely_directory(self, title: str, href: str) -> bool:
        lower_title = title.lower()
        if any(x in lower_title for x in ("top 10", "best ", "near me", "directory")):
            return True
        domain = _extract_domain(href or "")
        return bool(domain and any(d in domain for d in DIRECTORY_DOMAINS))


async def discover_companies(
    industry: str,
    city: str | None = None,
    state: str | None = None,
    keyword_override: str | None = None,
    max_results: int = 50,
    progress_callback=None,
    should_cancel: Callable[[], bool] | None = None,
    skip_website_resolution: bool = False,
) -> list[DiscoveredCompany]:
    scraper = MapsDiscoveryScraper()
    return await scraper.discover(
        industry=industry,
        city=city,
        state=state,
        keyword_override=keyword_override,
        max_results=max_results,
        progress_callback=progress_callback,
        should_cancel=should_cancel,
        skip_website_resolution=skip_website_resolution,
    )
