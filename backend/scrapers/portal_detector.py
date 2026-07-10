from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from backend.config_loader import load_icp_config
from backend.settings import settings

logger = logging.getLogger(__name__)

PORTAL_PATHS = [
    "login",
    "signin",
    "sign-in",
    "portal",
    "employee",
    "employees",
    "intranet",
    "dealer",
    "partner",
    "vendor",
    "client-area",
    "client-portal",
    "customer-portal",
    "my-account",
    "account",
    "dashboard",
    "app",
]

SUBDOMAIN_PREFIXES = [
    "app",
    "portal",
    "my",
    "login",
    "employee",
    "intranet",
    "dealer",
    "partner",
    "vendor",
    "client",
    "customers",
]

CUSTOMER_LINK_PATTERNS = re.compile(
    r"sign\s*in|log\s*in|customer\s*portal|client\s*portal|my\s*account|member\s*login",
    re.IGNORECASE,
)
EMPLOYEE_LINK_PATTERNS = re.compile(
    r"employee\s*login|employee\s*portal|staff\s*login|intranet|team\s*portal|hr\s*portal",
    re.IGNORECASE,
)
VENDOR_LINK_PATTERNS = re.compile(
    r"dealer\s*login|dealer\s*portal|partner\s*login|partner\s*portal|vendor\s*login|distributor\s*login",
    re.IGNORECASE,
)

AUTH_VENDOR_MARKERS = [
    "okta.com",
    "auth0.com",
    "login.microsoftonline.com",
    "force.com",
    "salesforce.com",
    "sharepoint.com",
    "onelogin.com",
    "pingidentity.com",
    "duosecurity.com",
]

PLATFORM_TEXT_MARKERS = [
    "our platform",
    "proprietary system",
    "custom-built",
    "custom built",
    "built in-house",
    "in-house platform",
    "legacy system",
    "legacy platform",
    "member portal",
    "client portal",
]


@dataclass
class PortalSignals:
    portal_detected: bool = False
    portal_type: str | None = None
    portal_urls: list[str] = field(default_factory=list)
    platform_signals: list[dict] = field(default_factory=list)
    confidence: float = 0.0
    evidence: list[dict] = field(default_factory=list)


class PortalDetector:
    def __init__(self) -> None:
        config = load_icp_config()
        self.portal_keywords = [
            k.lower() for k in config.get("portal_keywords", [])
        ]
        self.platform_keywords = [
            k.lower() for k in config.get("platform_signal_keywords", [])
        ]
        self.rate_limit = settings.scrape_rate_limit_seconds
        self.headers = {"User-Agent": settings.scrape_user_agent}

    async def detect(
        self,
        website: str | None,
        pages_html: dict[str, str],
    ) -> PortalSignals:
        result = PortalSignals()
        if not website and not pages_html:
            return result

        base_url = self._normalize_url(website) if website else None
        domain = urlparse(base_url).netloc.lower().removeprefix("www.") if base_url else ""

        type_hits: dict[str, int] = {
            "customer": 0,
            "employee": 0,
            "vendor": 0,
            "unknown": 0,
        }
        urls: set[str] = set()

        for page_url, html in pages_html.items():
            if not html:
                continue
            soup = BeautifulSoup(html, "lxml")
            text = soup.get_text(" ", strip=True).lower()

            if self._has_login_form(soup):
                type_hits["unknown"] += 2
                result.evidence.append(
                    {
                        "type": "portal_login_form",
                        "keyword": "password form",
                        "snippet": "Login form with password field detected",
                        "source_url": page_url,
                    }
                )
                urls.add(page_url)

            for link in soup.find_all("a", href=True):
                href = link.get("href", "").strip()
                link_text = link.get_text(" ", strip=True)
                full_url = urljoin(page_url, href)
                link_type = self._classify_link(href, link_text, full_url)
                if link_type:
                    type_hits[link_type] += 1
                    urls.add(full_url)
                    result.evidence.append(
                        {
                            "type": f"portal_link_{link_type}",
                            "keyword": link_text[:80] or href,
                            "snippet": f"Portal link: {link_text or href}",
                            "source_url": full_url,
                        }
                    )

            for kw in self.portal_keywords:
                if kw in text:
                    portal_type = self._keyword_portal_type(kw)
                    type_hits[portal_type] += 1
                    idx = text.find(kw)
                    snippet = text[max(0, idx - 40) : idx + len(kw) + 40].strip()
                    result.evidence.append(
                        {
                            "type": "portal_keyword",
                            "keyword": kw,
                            "snippet": snippet,
                            "source_url": page_url,
                        }
                    )

            for marker in AUTH_VENDOR_MARKERS:
                if marker in html.lower():
                    type_hits["customer"] += 1
                    result.platform_signals.append(
                        {
                            "signal": "auth_vendor",
                            "value": marker,
                            "source_url": page_url,
                        }
                    )
                    result.evidence.append(
                        {
                            "type": "auth_vendor",
                            "keyword": marker,
                            "snippet": f"Third-party auth vendor: {marker}",
                            "source_url": page_url,
                        }
                    )

            for kw in self.platform_keywords + PLATFORM_TEXT_MARKERS:
                if kw in text:
                    result.platform_signals.append(
                        {
                            "signal": "platform_text",
                            "value": kw,
                            "source_url": page_url,
                        }
                    )
                    idx = text.find(kw)
                    snippet = text[max(0, idx - 40) : idx + len(kw) + 40].strip()
                    result.evidence.append(
                        {
                            "type": "platform_signal",
                            "keyword": kw,
                            "snippet": snippet,
                            "source_url": page_url,
                        }
                    )

        if base_url and domain:
            path_urls = [urljoin(base_url, p) for p in PORTAL_PATHS]
            for url in path_urls:
                if url in pages_html:
                    portal_type = self._path_portal_type(urlparse(url).path)
                    type_hits[portal_type] += 1
                    urls.add(url)

            subdomain_urls = await self._probe_subdomains(domain, base_url)
            for sub_url, sub_type in subdomain_urls:
                type_hits[sub_type] += 2
                urls.add(sub_url)
                result.evidence.append(
                    {
                        "type": "portal_subdomain",
                        "keyword": urlparse(sub_url).netloc,
                        "snippet": f"Active portal subdomain: {sub_url}",
                        "source_url": sub_url,
                    }
                )

        total_hits = sum(type_hits.values())
        if total_hits == 0 and not result.platform_signals:
            return result

        result.portal_detected = True
        result.portal_urls = sorted(urls)[:15]
        result.portal_type = self._resolve_portal_type(type_hits)
        result.confidence = min(1.0, round(total_hits * 0.15 + len(result.platform_signals) * 0.1, 2))
        return result

    def _normalize_url(self, website: str) -> str | None:
        website = website.strip()
        if not website:
            return None
        if not website.startswith(("http://", "https://")):
            website = f"https://{website}"
        parsed = urlparse(website)
        if not parsed.netloc:
            return None
        return f"{parsed.scheme}://{parsed.netloc}/"

    def _has_login_form(self, soup: BeautifulSoup) -> bool:
        for form in soup.find_all("form"):
            if form.find("input", attrs={"type": "password"}):
                return True
            if form.find("input", attrs={"name": re.compile(r"password", re.I)}):
                return True
        if soup.find("input", attrs={"type": "password"}):
            return True
        return False

    def _classify_link(self, href: str, link_text: str, full_url: str) -> str | None:
        combined = f"{href} {link_text}".lower()
        path = urlparse(full_url).path.lower()

        if EMPLOYEE_LINK_PATTERNS.search(combined):
            return "employee"
        if VENDOR_LINK_PATTERNS.search(combined):
            return "vendor"
        if CUSTOMER_LINK_PATTERNS.search(combined):
            return "customer"

        for segment in PORTAL_PATHS:
            if f"/{segment}" in path or path.rstrip("/").endswith(segment):
                return self._path_portal_type(path)

        return None

    def _path_portal_type(self, path: str) -> str:
        lower = path.lower()
        if any(k in lower for k in ("employee", "intranet", "staff")):
            return "employee"
        if any(k in lower for k in ("dealer", "partner", "vendor", "distributor")):
            return "vendor"
        if any(k in lower for k in ("login", "portal", "account", "client", "customer")):
            return "customer"
        return "unknown"

    def _keyword_portal_type(self, keyword: str) -> str:
        if any(k in keyword for k in ("employee", "intranet", "staff")):
            return "employee"
        if any(k in keyword for k in ("dealer", "partner", "vendor", "distributor")):
            return "vendor"
        if any(k in keyword for k in ("customer", "client", "login", "portal", "account")):
            return "customer"
        return "unknown"

    async def _probe_subdomains(
        self, domain: str, base_url: str
    ) -> list[tuple[str, str]]:
        scheme = urlparse(base_url).scheme or "https"
        found: list[tuple[str, str]] = []

        async with httpx.AsyncClient(
            headers=self.headers, follow_redirects=True, timeout=8.0
        ) as client:
            for prefix in SUBDOMAIN_PREFIXES:
                host = f"{prefix}.{domain}"
                url = f"{scheme}://{host}/"
                try:
                    resp = await client.head(url)
                    if resp.status_code < 400:
                        portal_type = "employee" if prefix in ("employee", "intranet") else (
                            "vendor" if prefix in ("dealer", "partner", "vendor") else "customer"
                        )
                        found.append((str(resp.url), portal_type))
                except httpx.HTTPError:
                    logger.debug("Subdomain probe failed for %s", url)
                await asyncio.sleep(self.rate_limit * 0.5)
        return found

    def _resolve_portal_type(self, type_hits: dict[str, int]) -> str:
        ranked = sorted(
            ((k, v) for k, v in type_hits.items() if v > 0 and k != "unknown"),
            key=lambda x: x[1],
            reverse=True,
        )
        if not ranked:
            return "unknown" if type_hits.get("unknown") else "customer"
        if len(ranked) >= 2 and ranked[0][1] == ranked[1][1]:
            return "mixed"
        return ranked[0][0]


async def detect_portals(
    website: str | None, pages_html: dict[str, str]
) -> PortalSignals:
    detector = PortalDetector()
    return await detector.detect(website, pages_html)
