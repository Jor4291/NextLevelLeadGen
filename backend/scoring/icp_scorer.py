from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.config_loader import load_brand_config
from backend.scrapers.website_enricher import EnrichmentResult

ERP_PAIN_WORDS = (
    "legacy",
    "migration",
    "workaround",
    "silo",
    "manual",
    "outdated",
    "replace",
    "integrat",
    "disconnected",
    "fragment",
    "moderniz",
)

NAMED_EMAIL_RE = re.compile(
    r"^[a-z]+\.[a-z]+@",
    re.IGNORECASE,
)


def parse_keyword_override(text: str | None) -> list[str]:
    """Parse comma- or newline-separated keyword overrides."""
    if not text:
        return []
    parts = re.split(r"[,;\n]+", text)
    return [p.strip().lower() for p in parts if p.strip()]


def merge_keywords(base: list[str], extra: list[str] | None) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for kw in base + (extra or []):
        lower = kw.lower().strip()
        if lower and lower not in seen:
            seen.add(lower)
            merged.append(lower)
    return merged


@dataclass
class ScoreResult:
    fit_score: float
    practice_fit: str
    pain_signals: list[str]
    score_rationale: str
    lead_tier: str = "D"
    disqualified: bool = False
    disqualify_reason: str | None = None
    evidence: list[dict] = field(default_factory=list)


def compute_lead_tier(fit_score: float, thresholds: dict | None = None) -> str:
    thresholds = thresholds or {}
    hot = thresholds.get("hot", 65)
    qualified = thresholds.get("qualified", 50)
    review = thresholds.get("review", 35)
    if fit_score >= hot:
        return "A"
    if fit_score >= qualified:
        return "B"
    if fit_score >= review:
        return "C"
    return "D"


class ICPScorer:
    def __init__(self) -> None:
        self.config = load_icp_config()
        self.weights = self.config.get("scoring_weights", {})
        self.negative_weights = self.config.get("negative_weights", {})
        self.employee_bands = self.config.get("employee_bands", {})
        self.thresholds = self.config.get("thresholds", {})
        self.disqualifiers = [
            k.lower() for k in self.config.get("disqualifier_keywords", [])
        ]
        self.industries = self.config.get("industries", {})
        self.decision_maker_titles = [
            t.lower() for t in self.config.get("decision_maker_titles", [])
        ]
        brand = load_brand_config()
        self.fit_signal_label = brand.get("fit_signal_label", "ICP fit")
        self.positive_keywords = [
            k.lower() for k in self.config.get("positive_keywords", [])
        ]
        self.negative_keywords = [
            k.lower() for k in self.config.get("negative_keywords", [])
        ]

    def _count_keyword_hits(
        self, keywords: list[str], page_text: str, company_name: str
    ) -> list[str]:
        lower_name = company_name.lower()
        return [kw for kw in keywords if kw in page_text or kw in lower_name]

    def _is_decision_maker(self, title: str | None) -> bool:
        if not title:
            return False
        lower = title.lower()
        return any(dm in lower for dm in self.decision_maker_titles)

    def _erp_has_pain_context(self, snippet: str) -> bool:
        lower = snippet.lower()
        return any(word in lower for word in ERP_PAIN_WORDS)

    def _has_named_email(self, emails: list[str]) -> bool:
        return any(NAMED_EMAIL_RE.match(e) for e in emails)

    def score(
        self,
        company_name: str,
        industry: str,
        enrichment: EnrichmentResult,
        job_signal_keywords: list[str] | None = None,
        state: str | None = None,
        has_website: bool = True,
        positive_keywords_extra: list[str] | None = None,
        negative_keywords_extra: list[str] | None = None,
    ) -> ScoreResult:
        job_signal_keywords = job_signal_keywords or []
        positive_keywords = merge_keywords(
            self.positive_keywords, positive_keywords_extra
        )
        negative_keywords = merge_keywords(
            self.negative_keywords, negative_keywords_extra
        )
        points = 0.0
        rationale_parts: list[str] = []
        pain_signals: list[str] = []
        evidence = list(enrichment.evidence)
        process_hits = 0
        software_hits = 0
        hiring_hits = 0

        lower_name = company_name.lower()
        page_text = enrichment.page_text.lower()

        for dq in self.disqualifiers:
            if dq in page_text or dq in lower_name:
                return ScoreResult(
                    fit_score=0,
                    practice_fit="None",
                    pain_signals=[],
                    score_rationale=f"Disqualified: matches competitor/vendor pattern '{dq}'.",
                    lead_tier="D",
                    disqualified=True,
                    disqualify_reason=dq,
                    evidence=evidence,
                )

        industry_cfg = self.industries.get(industry, {})
        industry_keywords = [k.lower() for k in industry_cfg.get("keywords", [])]
        if any(kw in page_text or kw in lower_name for kw in industry_keywords):
            w = self.weights.get("industry_match", 15)
            points += w
            rationale_parts.append(f"Industry match ({industry_cfg.get('label', industry)}): +{w}")

        emp = enrichment.employee_estimate
        sweet_min = self.employee_bands.get("sweet_spot_min", 15)
        sweet_max = self.employee_bands.get("sweet_spot_max", 250)
        acc_min = self.employee_bands.get("acceptable_min", 5)
        acc_max = self.employee_bands.get("acceptable_max", 1000)

        if emp is not None:
            if sweet_min <= emp <= sweet_max:
                w = self.weights.get("employee_sweet_spot", 20)
                points += w
                rationale_parts.append(
                    f"Employee sweet spot (~{emp} employees, $2M–$50M proxy): +{w}"
                )
            elif acc_min <= emp <= acc_max:
                w = self.weights.get("employee_sweet_spot", 20) * 0.4
                points += w
                rationale_parts.append(
                    f"Employee count acceptable (~{emp}): +{w:.0f}"
                )
            elif emp < acc_min or emp > acc_max:
                penalty = self.negative_weights.get("employee_out_of_band", 10)
                points -= penalty
                rationale_parts.append(
                    f"Employee count (~{emp}) outside ideal band: -{penalty}"
                )
        else:
            rationale_parts.append("Employee count unknown; partial size scoring skipped.")

        for match in enrichment.matched_keywords:
            cat = match.get("category", "")
            kw = match.get("keyword", "")
            snippet = match.get("snippet", "")

            if cat == "process_opt":
                process_hits += 1
                pain_signals.append(f"Process Opt: '{kw}' — {snippet[:100]}")
            elif cat == "custom_software":
                software_hits += 1
                pain_signals.append(f"Custom Software: '{kw}' — {snippet[:100]}")
            elif cat == "erp_system":
                if self._erp_has_pain_context(snippet):
                    software_hits += 1
                    pain_signals.append(f"ERP pain: '{kw}' — {snippet[:100]}")
            elif cat == "hiring_signal":
                hiring_hits += 1
                pain_signals.append(f"Hiring signal: '{kw}'")
            elif cat == "positive_keyword":
                pain_signals.append(f"{self.fit_signal_label}: '{kw}' — {snippet[:100]}")
            elif cat == "negative_keyword":
                pain_signals.append(f"Weak fit signal: '{kw}'")

        positive_matched = self._count_keyword_hits(
            positive_keywords, page_text, company_name
        )
        negative_matched = self._count_keyword_hits(
            negative_keywords, page_text, company_name
        )
        for kw in positive_matched:
            if not any(f"'{kw}'" in s and self.fit_signal_label in s for s in pain_signals):
                pain_signals.append(f"{self.fit_signal_label}: '{kw}'")
        for kw in negative_matched:
            if not any(f"'{kw}'" in s and "Weak fit" in s for s in pain_signals):
                pain_signals.append(f"Weak fit signal: '{kw}'")

        if process_hits:
            w = min(self.weights.get("process_opt_pain", 25), process_hits * 8)
            points += w
            rationale_parts.append(f"Process optimization pain signals ({process_hits}): +{w:.0f}")

        if software_hits:
            w = min(self.weights.get("custom_software_pain", 25), software_hits * 8)
            points += w
            rationale_parts.append(f"Custom software/integration signals ({software_hits}): +{w:.0f}")

        for kw in job_signal_keywords:
            hiring_hits += 1
            pain_signals.append(f"Job posting signal: '{kw}'")

        if hiring_hits:
            w = min(self.weights.get("hiring_signal", 10), hiring_hits * 4)
            points += w
            rationale_parts.append(f"Hiring/pain job signals ({hiring_hits}): +{w:.0f}")

        contact_score = 0
        if enrichment.emails:
            contact_score += 2
        if enrichment.phones:
            contact_score += 2
        if enrichment.contact_name:
            contact_score += 1
        if contact_score:
            w = min(self.weights.get("contact_quality", 5), contact_score)
            points += w
            rationale_parts.append(f"Contact data quality: +{w:.0f}")

        if self._is_decision_maker(enrichment.contact_title):
            w = self.weights.get("decision_maker", 5)
            points += w
            rationale_parts.append(f"Decision-maker contact ({enrichment.contact_title}): +{w}")

        if self._has_named_email(enrichment.emails):
            w = self.weights.get("named_email", 2)
            points += w
            rationale_parts.append(f"Named-person email pattern: +{w}")

        if positive_matched:
            w = min(
                self.weights.get("positive_keyword", 12),
                len(positive_matched) * 4,
            )
            points += w
            rationale_parts.append(
                f"{self.fit_signal_label} keywords ({len(positive_matched)}): +{w:.0f}"
            )

        if negative_matched:
            penalty = min(
                self.weights.get("negative_keyword", 8),
                len(negative_matched) * 3,
            )
            points -= penalty
            rationale_parts.append(
                f"Weak-fit keywords ({len(negative_matched)}): -{penalty:.0f}"
            )

        if not has_website and not enrichment.website:
            penalty = self.negative_weights.get("no_website", 8)
            points -= penalty
            rationale_parts.append(f"No website found: -{penalty}")

        has_email = bool(enrichment.emails)
        has_phone = bool(enrichment.phones)
        if not has_email and not has_phone:
            penalty = self.negative_weights.get("no_contact", 5)
            points -= penalty
            rationale_parts.append(f"No email or phone: -{penalty}")

        if state and len(state) == 2:
            rationale_parts.append(f"US geography ({state.upper()}).")

        has_evidence = (
            process_hits > 0
            or software_hits > 0
            or hiring_hits > 0
            or len(positive_matched) > 0
        )
        evidence_floor = self.thresholds.get("evidence_floor", 40)
        if not has_evidence and points > evidence_floor:
            rationale_parts.append(
                f"No pain/hiring evidence — score capped at {evidence_floor}."
            )
            points = min(points, evidence_floor)

        fit_score = max(0.0, min(100.0, round(points, 1)))
        lead_tier = compute_lead_tier(fit_score, self.thresholds)

        if process_hits and software_hits:
            practice_fit = "Both"
        elif process_hits:
            practice_fit = "Process Opt"
        elif software_hits:
            practice_fit = "Custom Software"
        elif hiring_hits:
            practice_fit = "Process Opt"
        else:
            practice_fit = "Needs Review"

        if not pain_signals and fit_score < 30:
            rationale_parts.append(
                "Limited public pain signals found — recommend human review before calling."
            )

        return ScoreResult(
            fit_score=fit_score,
            practice_fit=practice_fit,
            pain_signals=pain_signals[:10],
            score_rationale=" | ".join(rationale_parts),
            lead_tier=lead_tier,
            evidence=evidence,
        )


def score_lead(
    company_name: str,
    industry: str,
    enrichment: EnrichmentResult,
    job_signal_keywords: list[str] | None = None,
    state: str | None = None,
    has_website: bool = True,
    positive_keywords_extra: list[str] | None = None,
    negative_keywords_extra: list[str] | None = None,
) -> ScoreResult:
    scorer = ICPScorer()
    return scorer.score(
        company_name=company_name,
        industry=industry,
        enrichment=enrichment,
        job_signal_keywords=job_signal_keywords,
        state=state,
        has_website=has_website,
        positive_keywords_extra=positive_keywords_extra,
        negative_keywords_extra=negative_keywords_extra,
    )
