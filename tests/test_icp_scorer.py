from backend.scoring.icp_scorer import score_lead
from backend.scrapers.website_enricher import EnrichmentResult


def test_portal_detection_boosts_score():
    enrichment = EnrichmentResult(
        website="https://example.com",
        emails=["ops@example.com"],
        phones=["(555) 555-5555"],
        page_text="manufacturing operations",
        portal_detected=True,
        portal_type="customer",
        portal_urls=["https://example.com/login"],
        platform_signals=[{"signal": "platform_text", "value": "our platform"}],
    )
    result = score_lead(
        company_name="Example Manufacturing",
        industry="manufacturing",
        enrichment=enrichment,
        state="TX",
        has_website=True,
    )
    assert result.fit_score >= 15
    assert result.practice_fit == "Custom Software"
    assert any("Portal detected" in signal for signal in result.pain_signals)


def test_disqualified_company_scores_zero():
    enrichment = EnrichmentResult(
        website="https://agency.com",
        page_text="we are a marketing agency serving clients nationwide",
        evidence=[
            {
                "type": "disqualifier",
                "keyword": "marketing agency",
                "snippet": "marketing agency",
                "source_url": "https://agency.com",
            }
        ],
    )
    result = score_lead(
        company_name="Best Marketing Agency",
        industry="manufacturing",
        enrichment=enrichment,
    )
    assert result.disqualified is True
    assert result.fit_score == 0
