from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from backend.config_loader import load_icp_config
from backend.settings import settings


EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.IGNORECASE
)
PHONE_RE = re.compile(
    r"(?:\+1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}"
)
EMPLOYEE_RE = re.compile(
    r"(\d{1,4})\+?\s*(?:employees|team members|people|staff)", re.IGNORECASE
)

GENERIC_EMAIL_PREFIXES = {
    "noreply",
    "no-reply",
    "donotreply",
    "privacy",
    "legal",
    "abuse",
    "postmaster",
    "webmaster",
    "support",
    "help",
    "sales",
    "marketing",
    "newsletter",
    "jobs",
    "careers",
    "hr",
    "recruiting",
}


@dataclass
class EnrichmentResult:
    website: str | None = None
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    contact_name: str | None = None
    contact_title: str | None = None
    employee_estimate: int | None = None
    page_text: str = ""
    pages_scraped: list[str] = field(default_factory=list)
    matched_keywords: list[dict] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)


class WebsiteEnricher:
    CONTACT_PATHS = [
        "",
        "contact",
        "contact-us",
        "about",
        "about-us",
        "company",
        "team",
        "leadership",
        "careers",
        "jobs",
        "news",
    ]

    def __init__(self) -> None:
        self.config = load_icp_config()
        self.rate_limit = settings.scrape_rate_limit_seconds
        self.headers = {"User-Agent": settings.scrape_user_agent}
        self.process_keywords = [
            k.lower() for k in self.config.get("process_opt_keywords", [])
        ]
        self.software_keywords = [
            k.lower() for k in self.config.get("custom_software_keywords", [])
        ]
        self.erp_systems = [k.lower() for k in self.config.get("erp_systems", [])]
        self.hiring_signals = [
            k.lower() for k in self.config.get("hiring_signals", [])
        ]
        self.decision_titles = self.config.get("decision_maker_titles", [])
        self.disqualifiers = [
            k.lower() for k in self.config.get("disqualifier_keywords", [])
        ]
        self.positive_keywords = [
            k.lower() for k in self.config.get("positive_keywords", [])
        ]
        self.negative_keywords = [
            k.lower() for k in self.config.get("negative_keywords", [])
        ]

    async def enrich(self, website: str | None, company_name: str) -> EnrichmentResult:
        result = EnrichmentResult(website=website)
        if not website:
            return result

        base_url = self._normalize_url(website)
        if not base_url:
            return result

        domain = urlparse(base_url).netloc.lower().removeprefix("www.")
        combined_text_parts: list[str] = []

        async with httpx.AsyncClient(
            headers=self.headers, follow_redirects=True, timeout=20.0
        ) as client:
            for path in self.CONTACT_PATHS:
                url = base_url if not path else urljoin(base_url + "/", path)
                html = await self._fetch_page(client, url)
                if not html:
                    continue

                result.pages_scraped.append(url)
                soup = BeautifulSoup(html, "lxml")
                text = soup.get_text(" ", strip=True)
                combined_text_parts.append(text)

                result.emails.extend(self._extract_emails(html, domain))
                result.phones.extend(self._extract_phones(text))

                if not result.contact_name:
                    contact = self._extract_decision_maker(soup, text)
                    if contact:
                        result.contact_name = contact.get("name")
                        result.contact_title = contact.get("title")

                if not result.employee_estimate:
                    result.employee_estimate = self._extract_employee_count(text)

                await asyncio.sleep(self.rate_limit)

        result.page_text = " ".join(combined_text_parts).lower()
        result.emails = self._rank_emails(list(dict.fromkeys(result.emails)), domain)
        result.phones = list(dict.fromkeys(result.phones))[:3]
        result.matched_keywords = self._scan_keywords(result.page_text, result.pages_scraped)
        result.evidence = [
            {
                "type": kw["category"],
                "keyword": kw["keyword"],
                "snippet": kw["snippet"],
                "source_url": kw["source_url"],
            }
            for kw in result.matched_keywords
        ]

        lower_name = company_name.lower()
        for dq in self.disqualifiers:
            if dq in result.page_text or dq in lower_name:
                result.evidence.append(
                    {
                        "type": "disqualifier",
                        "keyword": dq,
                        "snippet": f"Possible disqualifier match: {dq}",
                        "source_url": base_url,
                    }
                )

        return result

    async def _fetch_page(self, client: httpx.AsyncClient, url: str) -> str | None:
        try:
            resp = await client.get(url)
            if resp.status_code >= 400:
                return None
            content_type = resp.headers.get("content-type", "")
            if "text/html" not in content_type and "application/xhtml" not in content_type:
                return None
            return resp.text
        except httpx.HTTPError:
            return None

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

    def _extract_emails(self, html: str, domain: str) -> list[str]:
        emails: list[str] = []
        soup = BeautifulSoup(html, "lxml")
        for a in soup.select('a[href^="mailto:"]'):
            href = a.get("href", "")
            email = href.replace("mailto:", "").split("?")[0].strip()
            if email:
                emails.append(email.lower())

        for match in EMAIL_RE.findall(html):
            emails.append(match.lower())

        filtered = []
        for email in emails:
            prefix = email.split("@")[0]
            if prefix in GENERIC_EMAIL_PREFIXES:
                continue
            if email.endswith((".png", ".jpg", ".gif", ".svg", ".webp")):
                continue
            if domain and domain not in email and not email.endswith(f".{domain}"):
                continue
            filtered.append(email)
        return filtered

    def _extract_phones(self, text: str) -> list[str]:
        phones = []
        for match in PHONE_RE.findall(text):
            digits = re.sub(r"\D", "", match)
            if len(digits) >= 10:
                phones.append(self._format_phone(match))
        return phones

    def _format_phone(self, phone: str) -> str:
        digits = re.sub(r"\D", "", phone)
        if len(digits) == 10:
            return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        if len(digits) == 11 and digits.startswith("1"):
            return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
        return phone.strip()

    def _extract_employee_count(self, text: str) -> int | None:
        match = EMPLOYEE_RE.search(text)
        if match:
            return int(match.group(1))
        return None

    def _extract_decision_maker(
        self, soup: BeautifulSoup, text: str
    ) -> dict[str, str] | None:
        for title in self.decision_titles:
            pattern = re.compile(
                rf"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){{0,2}})\s*[,|\-–—]?\s*{re.escape(title)}",
                re.IGNORECASE,
            )
            match = pattern.search(text)
            if match:
                return {"name": match.group(1).strip(), "title": title}

        for card in soup.select(
            ".team-member, .leadership, .staff, .person, .bio, [class*='team']"
        ):
            card_text = card.get_text(" ", strip=True)
            for title in self.decision_titles:
                if title.lower() in card_text.lower():
                    name_el = card.select_one("h2, h3, h4, .name, strong")
                    name = name_el.get_text(strip=True) if name_el else None
                    if name and len(name.split()) <= 4:
                        return {"name": name, "title": title}
        return None

    def _scan_keywords(self, text: str, pages: list[str]) -> list[dict]:
        matches: list[dict] = []
        source_url = pages[0] if pages else ""

        def add_match(category: str, keyword: str) -> None:
            idx = text.find(keyword)
            snippet = text[max(0, idx - 60) : idx + len(keyword) + 60].strip()
            matches.append(
                {
                    "category": category,
                    "keyword": keyword,
                    "snippet": snippet,
                    "source_url": source_url,
                }
            )

        for kw in self.process_keywords:
            if kw in text:
                add_match("process_opt", kw)

        for kw in self.software_keywords:
            if kw in text:
                add_match("custom_software", kw)

        for erp in self.erp_systems:
            if erp.lower() in text:
                add_match("erp_system", erp)

        for signal in self.hiring_signals:
            if signal in text:
                add_match("hiring_signal", signal)

        for kw in self.positive_keywords:
            if kw in text:
                add_match("positive_keyword", kw)

        for kw in self.negative_keywords:
            if kw in text:
                add_match("negative_keyword", kw)

        return matches

    def _rank_emails(self, emails: list[str], domain: str) -> list[str]:
        priority_prefixes = [
            "engage",
            "contact",
            "info",
            "hello",
            "sales",
            "ops",
            "operations",
        ]

        def score(email: str) -> tuple[int, str]:
            prefix = email.split("@")[0]
            if prefix in ("contact", "info", "hello", "engage", "ops", "operations"):
                return (0, email)
            if domain and email.endswith(f"@{domain}"):
                return (1, email)
            if "." in prefix and len(prefix) > 3:
                return (2, email)
            return (3, email)

        return sorted(emails, key=score)


async def enrich_company(website: str | None, company_name: str) -> EnrichmentResult:
    enricher = WebsiteEnricher()
    return await enricher.enrich(website, company_name)
