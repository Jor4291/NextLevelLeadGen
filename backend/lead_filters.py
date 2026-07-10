"""Lead inbox filter helpers."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models import Lead, ScrapeJob, ScrapeJobStatus


def lead_counts_by_job(db: Session, job_ids: list[int]) -> dict[int, int]:
    if not job_ids:
        return {}
    rows = (
        db.query(Lead.scrape_job_id, func.count(Lead.id))
        .filter(Lead.scrape_job_id.in_(job_ids))
        .group_by(Lead.scrape_job_id)
        .all()
    )
    return {job_id: count for job_id, count in rows}


def resolve_latest_scrape_job_id(db: Session) -> int | None:
    """Most recent completed scrape job, or the job that produced the newest lead."""
    job = (
        db.query(ScrapeJob)
        .filter(ScrapeJob.status == ScrapeJobStatus.COMPLETED)
        .order_by(ScrapeJob.created_at.desc())
        .first()
    )
    if job:
        return job.id

    row = (
        db.query(Lead.scrape_job_id)
        .filter(Lead.scrape_job_id.isnot(None))
        .order_by(Lead.scraped_at.desc())
        .first()
    )
    return row[0] if row else None
