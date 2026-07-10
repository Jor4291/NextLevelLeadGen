from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from backend.models import Base
from backend.settings import ROOT_DIR, settings

DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


def _engine_kwargs() -> dict:
    url = settings.database_url
    kwargs: dict = {"echo": False}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return kwargs


engine = create_engine(settings.database_url, **_engine_kwargs())
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate_schema()


def _migrate_schema() -> None:
    """Add columns introduced after initial deploy."""
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    if "scrape_jobs" in table_names:
        columns = {col["name"] for col in inspector.get_columns("scrape_jobs")}
        migrations = [
            ("cancel_requested", "BOOLEAN NOT NULL DEFAULT 0"),
            ("progress_percent", "INTEGER NOT NULL DEFAULT 0"),
            ("enrichment_mode", "VARCHAR(16) NOT NULL DEFAULT 'fast'"),
            ("positive_keywords_override", "TEXT"),
            ("negative_keywords_override", "TEXT"),
            ("created_by_user_id", "INTEGER"),
            ("industry_label", "VARCHAR(128)"),
        ]
        for col_name, col_def in migrations:
            if col_name not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text(f"ALTER TABLE scrape_jobs ADD COLUMN {col_name} {col_def}")
                    )

    if "leads" in table_names:
        lead_columns = {col["name"] for col in inspector.get_columns("leads")}
        if "lead_tier" not in lead_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE leads ADD COLUMN lead_tier VARCHAR(1)"))
                conn.execute(
                    text(
                        "UPDATE leads SET lead_tier = 'A' "
                        "WHERE disqualified = 0 AND fit_score >= 65"
                    )
                )
                conn.execute(
                    text(
                        "UPDATE leads SET lead_tier = 'B' "
                        "WHERE lead_tier IS NULL AND disqualified = 0 AND fit_score >= 50"
                    )
                )
                conn.execute(
                    text(
                        "UPDATE leads SET lead_tier = 'C' "
                        "WHERE lead_tier IS NULL AND disqualified = 0 AND fit_score >= 35"
                    )
                )
                conn.execute(text("UPDATE leads SET lead_tier = 'D' WHERE lead_tier IS NULL"))
        if "assigned_to_user_id" not in lead_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE leads ADD COLUMN assigned_to_user_id INTEGER"))

        lead_migrations = [
            ("address", "VARCHAR(512)"),
            ("portal_detected", "BOOLEAN NOT NULL DEFAULT 0"),
            ("portal_type", "VARCHAR(32)"),
            ("portal_urls", "JSON"),
            ("platform_signals", "JSON"),
        ]
        for col_name, col_def in lead_migrations:
            if col_name not in lead_columns:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE leads ADD COLUMN {col_name} {col_def}"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
