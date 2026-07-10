from datetime import UTC, datetime, timedelta

from backend.database import SessionLocal, init_db
from backend.lead_filters import lead_counts_by_job, resolve_latest_scrape_job_id
from backend.models import Lead, LeadStatus, ScrapeJob, ScrapeJobStatus


def test_resolve_latest_scrape_job_id():
    init_db()
    db = SessionLocal()
    try:
        now = datetime.now(UTC).replace(tzinfo=None)
        older = ScrapeJob(
            industry="manufacturing",
            status=ScrapeJobStatus.COMPLETED,
            created_at=now - timedelta(days=2),
            completed_at=now - timedelta(days=2),
        )
        newer = ScrapeJob(
            industry="logistics",
            status=ScrapeJobStatus.COMPLETED,
            created_at=now - timedelta(hours=1),
            completed_at=now - timedelta(hours=1),
        )
        db.add_all([older, newer])
        db.commit()
        db.refresh(older)
        db.refresh(newer)

        expected = (
            db.query(ScrapeJob)
            .filter(ScrapeJob.status == ScrapeJobStatus.COMPLETED)
            .order_by(ScrapeJob.created_at.desc())
            .first()
            .id
        )
        assert resolve_latest_scrape_job_id(db) == expected

        lead = Lead(
            scrape_job_id=older.id,
            company_name="Fallback Co",
            industry="manufacturing",
            fit_score=40,
            status=LeadStatus.NEW,
            scraped_at=now,
        )
        db.add(lead)
        db.commit()

        counts = lead_counts_by_job(db, [older.id, newer.id])
        assert counts[older.id] == 1
        assert counts.get(newer.id, 0) == 0
    finally:
        db.close()
