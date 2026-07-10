from __future__ import annotations

import asyncio
import logging
import threading
import traceback
from datetime import datetime

from sqlalchemy.orm import Session

from backend.config_loader import load_icp_config
from backend.jobs.job_progress import percent_from_message
from backend.models import Lead, LeadStatus, ScrapeJob, ScrapeJobStatus
from backend.scrapers.job_signals import scan_job_signals
from backend.scrapers.maps_discovery import discover_companies
from backend.scrapers.website_enricher import enrich_company
from backend.scoring.icp_scorer import parse_keyword_override, score_lead
from backend.settings import settings

logger = logging.getLogger(__name__)
_worker_lock = threading.Lock()


class ScrapeJobCancelled(Exception):
    """Raised when a user cancels a running scrape job."""


def is_job_cancelled(job_id: int, db_factory) -> bool:
    db: Session = db_factory()
    try:
        job = db.get(ScrapeJob, job_id)
        return bool(job and job.cancel_requested)
    finally:
        db.close()


def cleanup_stale_jobs(db: Session) -> int:
    """Mark orphaned RUNNING/PENDING jobs as cancelled (e.g. after server restart)."""
    stale = (
        db.query(ScrapeJob)
        .filter(ScrapeJob.status.in_([ScrapeJobStatus.PENDING, ScrapeJobStatus.RUNNING]))
        .all()
    )
    for job in stale:
        job.status = ScrapeJobStatus.CANCELLED
        job.cancel_requested = True
        job.progress_message = "Stopped — server restarted. Start a new scrape."
        job.progress_percent = 100
        job.completed_at = datetime.utcnow()
    if stale:
        db.commit()
    return len(stale)


def cancel_all_active_jobs(db: Session) -> int:
    active = (
        db.query(ScrapeJob)
        .filter(ScrapeJob.status.in_([ScrapeJobStatus.PENDING, ScrapeJobStatus.RUNNING]))
        .all()
    )
    for job in active:
        job.cancel_requested = True
        job.status = ScrapeJobStatus.CANCELLED
        job.progress_message = "Cancelled by user."
        job.progress_percent = 100
        job.completed_at = datetime.utcnow()
    if active:
        db.commit()
    return len(active)


def request_job_cancel(job_id: int, db: Session) -> ScrapeJob:
    job = db.get(ScrapeJob, job_id)
    if not job:
        raise ValueError("Job not found")
    if job.status in (ScrapeJobStatus.COMPLETED, ScrapeJobStatus.FAILED, ScrapeJobStatus.CANCELLED):
        raise ValueError(f"Cannot cancel a job with status '{job.status.value}'")

    job.cancel_requested = True
    job.status = ScrapeJobStatus.CANCELLED
    job.progress_message = "Cancelled by user."
    job.progress_percent = 100
    job.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    return job


def _check_cancelled(job_id: int, db_factory) -> None:
    if is_job_cancelled(job_id, db_factory):
        raise ScrapeJobCancelled()


def _job_enrichment_flags(job: ScrapeJob) -> tuple[bool, bool]:
    """Return (skip_website_resolution, skip_job_signals) for a scrape job."""
    mode = getattr(job, "enrichment_mode", None) or "fast"
    if mode == "quality":
        return False, False
    return settings.skip_website_resolution, settings.skip_job_signals


async def run_scrape_job(job_id: int, db_factory) -> None:
    db: Session = db_factory()
    leads_created = 0
    try:
        job = db.get(ScrapeJob, job_id)
        if not job:
            logger.error("Scrape job %s not found", job_id)
            return

        if job.cancel_requested or job.status == ScrapeJobStatus.CANCELLED:
            job.status = ScrapeJobStatus.CANCELLED
            job.progress_message = "Cancelled before start."
            job.progress_percent = 100
            job.completed_at = datetime.utcnow()
            db.commit()
            return

        job.status = ScrapeJobStatus.RUNNING
        job.progress_message = "Starting discovery..."
        job.progress_percent = 2
        db.commit()

        def update_progress(msg: str, percent: int | None = None) -> None:
            if is_job_cancelled(job_id, db_factory):
                raise ScrapeJobCancelled()
            pct = percent if percent is not None else percent_from_message(msg, "running")
            try:
                fresh = db_factory()
                try:
                    row = fresh.get(ScrapeJob, job_id)
                    if row and row.status == ScrapeJobStatus.RUNNING:
                        row.progress_message = msg
                        row.progress_percent = pct
                        fresh.commit()
                finally:
                    fresh.close()
            except ScrapeJobCancelled:
                raise
            except Exception:
                logger.exception("Failed to update progress for job %s", job_id)

        skip_website_resolution, skip_job_signals = _job_enrichment_flags(job)

        companies = await discover_companies(
            industry=job.industry,
            city=job.city,
            state=job.state,
            keyword_override=job.keyword_override,
            industry_label=job.industry_label,
            max_results=settings.max_companies_per_job,
            progress_callback=update_progress,
            should_cancel=lambda: is_job_cancelled(job_id, db_factory),
            skip_website_resolution=skip_website_resolution,
        )

        _check_cancelled(job_id, db_factory)

        job = db.get(ScrapeJob, job_id)
        if not job or job.status == ScrapeJobStatus.CANCELLED:
            return

        job.progress_message = f"Found {len(companies)} companies. Enriching..."
        job.progress_percent = 50
        db.commit()

        total = max(len(companies), 1)
        thresholds = load_icp_config().get("thresholds", {})
        min_persist = thresholds.get("min_persist", 25)

        for idx, company in enumerate(companies, start=1):
            _check_cancelled(job_id, db_factory)
            pct = min(99, round(50 + (idx / total) * 49))
            update_progress(
                f"Enriching {idx}/{total}: {company.company_name}",
                pct,
            )

            enrichment = await enrich_company(company.website, company.company_name)
            job_keywords: list[str] = []
            if not skip_job_signals:
                job_signals = await scan_job_signals(
                    company.company_name, company.website or enrichment.website
                )
                for sig in job_signals:
                    job_keywords.extend(sig.matched_signals)
                    enrichment.evidence.extend(
                        [
                            {
                                "type": "job_signal",
                                "keyword": kw,
                                "snippet": sig.snippet[:200],
                                "source_url": sig.source_url,
                            }
                            for kw in sig.matched_signals
                        ]
                    )

            score = score_lead(
                company_name=company.company_name,
                industry=job.industry,
                enrichment=enrichment,
                job_signal_keywords=job_keywords,
                state=company.state or job.state,
                has_website=bool(company.website or enrichment.website),
                positive_keywords_extra=parse_keyword_override(
                    job.positive_keywords_override
                ),
                negative_keywords_extra=parse_keyword_override(
                    job.negative_keywords_override
                ),
            )

            email = enrichment.emails[0] if enrichment.emails else None
            phone = (
                enrichment.phones[0]
                if enrichment.phones
                else company.phone
            )

            has_contact = bool(email or phone)
            if (
                not score.disqualified
                and score.fit_score < min_persist
                and not has_contact
            ):
                continue

            lead = Lead(
                scrape_job_id=job.id,
                assigned_to_user_id=job.created_by_user_id,
                company_name=company.company_name,
                industry=job.industry,
                website=company.website or enrichment.website,
                phone=phone,
                email=email,
                contact_name=enrichment.contact_name,
                contact_title=enrichment.contact_title,
                city=company.city or job.city,
                state=company.state or job.state,
                address=company.address,
                portal_detected=enrichment.portal_detected,
                portal_type=enrichment.portal_type,
                portal_urls=enrichment.portal_urls,
                platform_signals=enrichment.platform_signals,
                employee_estimate=enrichment.employee_estimate,
                fit_score=score.fit_score,
                lead_tier=score.lead_tier,
                practice_fit=score.practice_fit,
                pain_signals=score.pain_signals,
                score_rationale=score.score_rationale,
                evidence=enrichment.evidence,
                source_url=company.source_url,
                status=LeadStatus.NOT_A_FIT if score.disqualified else LeadStatus.NEW,
                disqualified=score.disqualified,
                disqualify_reason=score.disqualify_reason,
            )
            db.add(lead)
            leads_created += 1
            db.commit()

        job = db.get(ScrapeJob, job_id)
        if job and job.status == ScrapeJobStatus.RUNNING:
            job.status = ScrapeJobStatus.COMPLETED
            job.companies_found = leads_created
            job.progress_message = f"Completed. {leads_created} leads created."
            job.progress_percent = 100
            job.completed_at = datetime.utcnow()
            db.commit()
    except ScrapeJobCancelled:
        job = db.get(ScrapeJob, job_id)
        if job and job.status != ScrapeJobStatus.CANCELLED:
            job.status = ScrapeJobStatus.CANCELLED
            job.companies_found = leads_created
            job.progress_message = (
                f"Cancelled. {leads_created} lead{'s' if leads_created != 1 else ''} saved."
            )
            job.progress_percent = 100
            job.completed_at = datetime.utcnow()
            db.commit()
        logger.info("Scrape job %s cancelled (%s leads saved)", job_id, leads_created)
    except Exception as exc:
        logger.exception("Scrape job %s failed", job_id)
        tb = traceback.format_exc()
        job = db.get(ScrapeJob, job_id)
        if job:
            job.status = ScrapeJobStatus.FAILED
            job.error_message = str(exc) or f"{type(exc).__name__}: see server logs"
            job.progress_message = "Job failed."
            job.progress_percent = 100
            job.completed_at = datetime.utcnow()
            db.commit()
        logger.error("Traceback for job %s:\n%s", job_id, tb)
    finally:
        db.close()


def _run_scrape_job_sync(job_id: int, db_factory) -> None:
    """Run scrape in a dedicated event loop (Windows/uvicorn-safe)."""
    with _worker_lock:
        asyncio.run(run_scrape_job(job_id, db_factory))


async def schedule_scrape_job(job_id: int, db_factory) -> None:
    await asyncio.to_thread(_run_scrape_job_sync, job_id, db_factory)
