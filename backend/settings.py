from pathlib import Path

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


def _load_brand_defaults() -> dict:
    path = ROOT_DIR / "config" / "brand.yaml"
    if path.exists():
        with path.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


_brand = _load_brand_defaults()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = f"sqlite:///{(ROOT_DIR / 'data' / 'leads.db').as_posix()}"
    scrape_rate_limit_seconds: float = 2.0
    scrape_user_agent: str = _brand.get(
        "scrape_user_agent",
        "NextLevelLeadBot/1.0 (+https://nextlevelstudio.com)",
    )
    skip_website_resolution: bool = False
    skip_job_signals: bool = False
    max_companies_per_job: int = 25
    google_sheets_credentials_path: str = str(
        ROOT_DIR / "credentials" / "google-service-account.json"
    )
    google_sheet_id: str = ""
    resend_api_key: str = ""
    email_from: str = _brand.get("contact_email", "info@nextlevelstudio.com")
    email_from_name: str = _brand.get("email_from_name", "Next Level Studio")
    icp_config_path: str = str(ROOT_DIR / "config" / "icp.yaml")
    brand_config_path: str = str(ROOT_DIR / "config" / "brand.yaml")

    # Auth & deployment
    auth_required: bool = False
    jwt_secret: str = "change-me-in-production"
    jwt_expire_hours: int = 72
    allow_registration: bool = False
    admin_email: str = ""
    admin_password: str = ""
    admin_name: str = "Admin"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    def cors_origin_list(self) -> list[str]:
        if not self.cors_origins.strip():
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
