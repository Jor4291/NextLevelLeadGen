import pytest

from backend.scrapers.portal_detector import PortalDetector


CUSTOMER_PORTAL_HTML = """
<html><body>
  <a href="/login">Customer Portal</a>
  <form action="/auth"><input type="password" name="password"></form>
</body></html>
"""

EMPLOYEE_PORTAL_HTML = """
<html><body>
  <a href="/employee">Employee Login</a>
  <p>Access our intranet for staff resources.</p>
</body></html>
"""

VENDOR_PORTAL_HTML = """
<html><body>
  <a href="/dealer-login">Dealer Access</a>
  <p>Partner portal for distributors.</p>
</body></html>
"""

PLATFORM_HTML = """
<html><body>
  <p>We built our own platform to manage client workflows.</p>
  <script src="https://login.okta.com/js/okta-sign-in.min.js"></script>
</body></html>
"""


@pytest.mark.asyncio
async def test_detects_customer_login_form():
    detector = PortalDetector()
    pages = {"https://example.com/login": CUSTOMER_PORTAL_HTML}
    result = await detector.detect("https://example.com", pages)
    assert result.portal_detected is True
    assert result.portal_type in ("customer", "mixed", "unknown")


@pytest.mark.asyncio
async def test_detects_employee_portal_links():
    detector = PortalDetector()
    pages = {"https://example.com/": EMPLOYEE_PORTAL_HTML}
    result = await detector.detect("https://example.com", pages)
    assert result.portal_detected is True
    assert result.portal_type in ("employee", "mixed")


@pytest.mark.asyncio
async def test_detects_vendor_portal_links():
    detector = PortalDetector()
    pages = {"https://example.com/": VENDOR_PORTAL_HTML}
    result = await detector.detect("https://example.com", pages)
    assert result.portal_detected is True
    assert result.portal_type in ("vendor", "mixed")


@pytest.mark.asyncio
async def test_detects_platform_and_auth_vendor_signals():
    detector = PortalDetector()
    pages = {"https://example.com/about": PLATFORM_HTML}
    result = await detector.detect("https://example.com", pages)
    assert result.portal_detected is True
    assert any(s["signal"] == "auth_vendor" for s in result.platform_signals)
    assert any(s["signal"] == "platform_text" for s in result.platform_signals)


@pytest.mark.asyncio
async def test_no_portal_on_plain_site():
    detector = PortalDetector()
    pages = {"https://example.com/": "<html><body><h1>About Us</h1><p>We make widgets.</p></body></html>"}
    result = await detector.detect("https://example.com", pages)
    assert result.portal_detected is False
    assert result.portal_urls == []
