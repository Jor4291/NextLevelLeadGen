from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from backend.auth import (
    create_access_token,
    ensure_admin_user,
    get_current_user,
    hash_password,
    require_admin,
    verify_password,
)
from backend.config_loader import (
    add_custom_industry,
    get_industry_options,
    get_metro_options,
    get_brand_config,
    load_icp_config,
    slugify_industry_id,
)
from backend.icp_scoring_config import (
    get_scoring_settings,
    reset_scoring_overrides,
    update_scoring_settings,
)
from backend.database import SessionLocal, get_db, init_db
from backend.integrations.email_campaign import (
    get_default_templates,
    render_template,
    send_campaign_email,
)
from backend.integrations.google_sheets import export_leads_to_sheet, is_sheets_configured
from backend.jobs.job_progress import percent_from_message
from backend.jobs.scrape_runner import (
    cancel_all_active_jobs,
    cleanup_stale_jobs,
    request_job_cancel,
    schedule_scrape_job,
)
from backend.lead_filters import lead_counts_by_job, resolve_latest_scrape_job_id
from backend.models import (
    EmailCampaign,
    EmailCampaignStatus,
    Lead,
    LeadStatus,
    ScrapeJob,
    ScrapeJobStatus,
    User,
    UserRole,
)
from backend.scoring.icp_scorer import compute_lead_tier
from backend.scrape_readiness import scrape_readiness
from backend.settings import ROOT_DIR, settings

logger = logging.getLogger(__name__)

app = FastAPI(
    title=f"{get_brand_config().get('display_name', 'Next Level Studio')} Lead Generator",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Pydantic schemas ---


class ScrapeJobCreate(BaseModel):
    industry: str
    industry_label: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    keyword_override: Optional[str] = None
    enrichment_mode: str = "fast"
    positive_keywords_override: Optional[str] = None
    negative_keywords_override: Optional[str] = None


class IndustryCreate(BaseModel):
    label: str = Field(min_length=1, max_length=128)


class LeadUpdate(BaseModel):
    status: Optional[LeadStatus] = None
    notes: Optional[str] = None
    fit_score: Optional[float] = None
    disqualified: Optional[bool] = None
    disqualify_reason: Optional[str] = None
    contact_name: Optional[str] = None
    contact_title: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    assigned_to_user_id: Optional[int] = None


class ExportRequest(BaseModel):
    lead_ids: list[int] = Field(default_factory=list)
    sheet_id: Optional[str] = None
    include_low_tier: bool = False
    include_no_contact: bool = False


class EmailCampaignCreate(BaseModel):
    name: str
    subject: str
    body_template: str


class SendEmailRequest(BaseModel):
    lead_ids: list[int]
    subject: str
    body_template: str
    campaign_name: Optional[str] = "Manual Send"


class SettingsUpdate(BaseModel):
    google_sheet_id: Optional[str] = None


class ScoringSettingsUpdate(BaseModel):
    scoring_weights: Optional[dict[str, float | int]] = None
    negative_weights: Optional[dict[str, float | int]] = None
    thresholds: Optional[dict[str, float | int]] = None
    employee_bands: Optional[dict[str, float | int]] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(min_length=1, max_length=128)


# --- Helpers ---


def _user_id(user: User) -> int | None:
    uid = getattr(user, "id", None)
    return uid if isinstance(uid, int) and uid > 0 else None


def user_to_dict(user: User) -> dict:
    return {
        "id": _user_id(user),
        "email": user.email,
        "name": user.name,
        "role": user.role.value,
        "is_active": user.is_active,
    }


def _user_name_map(db: Session, user_ids: set[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    rows = db.query(User).filter(User.id.in_(user_ids)).all()
    return {u.id: u.name for u in rows}


def lead_to_dict(lead: Lead, user_names: dict[int, str] | None = None) -> dict:
    pain_signals = lead.pain_signals or []
    thresholds = load_icp_config().get("thresholds", {})
    tier = lead.lead_tier or compute_lead_tier(lead.fit_score, thresholds)
    assigned_id = lead.assigned_to_user_id
    return {
        "id": lead.id,
        "scrape_job_id": lead.scrape_job_id,
        "company_name": lead.company_name,
        "industry": lead.industry,
        "website": lead.website,
        "phone": lead.phone,
        "email": lead.email,
        "contact_name": lead.contact_name,
        "contact_title": lead.contact_title,
        "city": lead.city,
        "state": lead.state,
        "address": lead.address,
        "portal_detected": lead.portal_detected,
        "portal_type": lead.portal_type,
        "portal_urls": lead.portal_urls or [],
        "platform_signals": lead.platform_signals or [],
        "employee_estimate": lead.employee_estimate,
        "fit_score": lead.fit_score,
        "lead_tier": tier,
        "pain_signal_count": len(pain_signals),
        "practice_fit": lead.practice_fit,
        "pain_signals": pain_signals,
        "score_rationale": lead.score_rationale,
        "evidence": lead.evidence or [],
        "source_url": lead.source_url,
        "status": lead.status.value,
        "notes": lead.notes,
        "disqualified": lead.disqualified,
        "disqualify_reason": lead.disqualify_reason,
        "exported_at": lead.exported_at.isoformat() if lead.exported_at else None,
        "scraped_at": lead.scraped_at.isoformat() if lead.scraped_at else None,
        "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
        "assigned_to_user_id": assigned_id,
        "assigned_to_name": user_names.get(assigned_id) if assigned_id and user_names else None,
    }


def job_to_dict(
    job: ScrapeJob,
    user_names: dict[int, str] | None = None,
    lead_count: int | None = None,
) -> dict:
    creator_id = job.created_by_user_id
    payload = {
        "id": job.id,
        "industry": job.industry,
        "industry_label": getattr(job, "industry_label", None),
        "city": job.city,
        "state": job.state,
        "keyword_override": job.keyword_override,
        "enrichment_mode": getattr(job, "enrichment_mode", None) or "fast",
        "positive_keywords_override": getattr(job, "positive_keywords_override", None),
        "negative_keywords_override": getattr(job, "negative_keywords_override", None),
        "status": job.status.value,
        "progress_message": job.progress_message,
        "progress_percent": job.progress_percent
        if job.progress_percent
        else percent_from_message(
            job.progress_message or "", job.status.value
        ),
        "companies_found": job.companies_found,
        "error_message": job.error_message,
        "cancel_requested": job.cancel_requested,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "created_by_user_id": creator_id,
        "created_by_name": user_names.get(creator_id) if creator_id and user_names else None,
    }
    if lead_count is not None:
        payload["lead_count"] = lead_count
    return payload


@app.on_event("startup")
def on_startup() -> None:
    if settings.auth_required and settings.jwt_secret == "change-me-in-production":
        raise RuntimeError(
            "JWT_SECRET must be set to a secure value when AUTH_REQUIRED=true"
        )
    init_db()
    db = SessionLocal()
    try:
        ensure_admin_user(db)
        count = cleanup_stale_jobs(db)
        if count:
            logger.info("Cleaned up %s stale scrape job(s) on startup", count)
    finally:
        db.close()


# --- API routes ---


@app.get("/api/health")
def health():
    ready, notes = scrape_readiness()
    brand = get_brand_config()
    return {
        "status": "ok",
        "service": f"{brand.get('display_name', 'Lead Generator')} Lead Generator",
        "scrape_ready": ready,
        "scrape_notes": notes,
        "auth_required": settings.auth_required,
    }


@app.post("/api/auth/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")
    token = create_access_token(user.id, user.email, user.role.value)
    return {"access_token": token, "token_type": "bearer", "user": user_to_dict(user)}


@app.post("/api/auth/register")
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    if not settings.allow_registration:
        raise HTTPException(status_code=403, detail="Registration is disabled")
    email = payload.email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        email=email,
        name=payload.name.strip(),
        password_hash=hash_password(payload.password),
        role=UserRole.BDR,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id, user.email, user.role.value)
    return {"access_token": token, "token_type": "bearer", "user": user_to_dict(user)}


@app.get("/api/auth/me")
def auth_me(user: User = Depends(get_current_user)):
    return user_to_dict(user)


@app.get("/api/users")
def list_users(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = (
        db.query(User)
        .filter(User.is_active.is_(True))
        .order_by(User.name)
        .all()
    )
    return [user_to_dict(u) for u in rows]


def _scrape_readiness() -> tuple[bool, list[str]]:
    return scrape_readiness()


@app.get("/api/config")
def get_config(user: User = Depends(get_current_user)):
    scrape_ready, scrape_notes = _scrape_readiness()
    return {
        "brand": get_brand_config(),
        "industries": get_industry_options(),
        "metros": get_metro_options(),
        "icp": load_icp_config(),
        "sheets_configured": is_sheets_configured(),
        "google_sheet_id": settings.google_sheet_id,
        "email_configured": bool(settings.resend_api_key),
        "scrape_ready": scrape_ready,
        "scrape_notes": scrape_notes,
        "auth_required": settings.auth_required,
    }


@app.post("/api/settings")
def update_settings(
    payload: SettingsUpdate,
    user: User = Depends(get_current_user),
):
    if payload.google_sheet_id is not None:
        settings.google_sheet_id = payload.google_sheet_id
    return {
        "google_sheet_id": settings.google_sheet_id,
        "sheets_configured": is_sheets_configured(),
    }


@app.get("/api/icp/scoring")
def get_icp_scoring_settings(user: User = Depends(get_current_user)):
    return get_scoring_settings()


@app.post("/api/icp/scoring")
def save_icp_scoring_settings(
    payload: ScoringSettingsUpdate,
    user: User = Depends(get_current_user),
):
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No scoring fields to update")
    try:
        return update_scoring_settings(updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/icp/scoring/reset")
def reset_icp_scoring_settings(user: User = Depends(get_current_user)):
    return reset_scoring_overrides()


@app.post("/api/industries")
def create_industry(
    payload: IndustryCreate,
    user: User = Depends(get_current_user),
):
    try:
        return add_custom_industry(payload.label)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/scrape-jobs")
def create_scrape_job(
    payload: ScrapeJobCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    industry_id = slugify_industry_id(payload.industry)
    if not industry_id:
        raise HTTPException(status_code=400, detail="Industry is required")

    industry_label = (payload.industry_label or payload.industry).strip() or None
    industry_cfg = load_icp_config().get("industries", {}).get(industry_id, {})
    if not industry_label and industry_cfg.get("label"):
        industry_label = industry_cfg["label"]

    if payload.enrichment_mode not in ("fast", "quality"):
        raise HTTPException(status_code=400, detail="enrichment_mode must be 'fast' or 'quality'")

    active_count = (
        db.query(ScrapeJob)
        .filter(ScrapeJob.status.in_([ScrapeJobStatus.PENDING, ScrapeJobStatus.RUNNING]))
        .count()
    )
    if active_count > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                "A scrape job is already in progress. "
                "Cancel it or wait for it to finish before starting another."
            ),
        )

    job = ScrapeJob(
        industry=industry_id,
        industry_label=industry_label,
        city=payload.city,
        state=payload.state,
        keyword_override=payload.keyword_override,
        enrichment_mode=payload.enrichment_mode,
        positive_keywords_override=payload.positive_keywords_override,
        negative_keywords_override=payload.negative_keywords_override,
        created_by_user_id=_user_id(user),
        status=ScrapeJobStatus.PENDING,
        progress_message="Queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(schedule_scrape_job, job.id, SessionLocal)

    return job_to_dict(job, _user_name_map(db, {job.created_by_user_id} if job.created_by_user_id else set()))


@app.get("/api/scrape-jobs")
def list_scrape_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    jobs = db.query(ScrapeJob).order_by(ScrapeJob.created_at.desc()).all()
    creator_ids = {j.created_by_user_id for j in jobs if j.created_by_user_id}
    names = _user_name_map(db, creator_ids)
    counts = lead_counts_by_job(db, [j.id for j in jobs])
    return [job_to_dict(j, names, lead_count=counts.get(j.id, 0)) for j in jobs]


@app.get("/api/scrape-jobs/{job_id}")
def get_scrape_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.get(ScrapeJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_to_dict(job, _user_name_map(db, {job.created_by_user_id} if job.created_by_user_id else set()))


@app.post("/api/scrape-jobs/{job_id}/cancel")
def cancel_scrape_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.get(ScrapeJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        job = request_job_cancel(job_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return job_to_dict(job, _user_name_map(db, {job.created_by_user_id} if job.created_by_user_id else set()))


@app.post("/api/scrape-jobs/cancel-all")
def cancel_all_scrape_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    count = cancel_all_active_jobs(db)
    return {"cancelled_count": count, "message": f"Cancelled {count} job(s). Restart the API if jobs were stuck."}


@app.get("/api/leads")
def list_leads(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    min_score: Optional[float] = Query(None),
    industry: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    tier: Optional[str] = Query(None),
    practice_fit: Optional[str] = Query(None),
    hot_only: Optional[bool] = Query(None),
    has_email: Optional[bool] = Query(None),
    has_phone: Optional[bool] = Query(None),
    has_contact: Optional[bool] = Query(None),
    has_portal: Optional[bool] = Query(None),
    not_exported: Optional[bool] = Query(None),
    assigned_to_me: Optional[bool] = Query(None),
    assigned_to_user_id: Optional[int] = Query(None),
    scrape_job_id: Optional[int] = Query(None),
    latest_scrape: Optional[bool] = Query(None),
    include_disqualified: Optional[bool] = Query(False),
):
    job_filter_id = scrape_job_id
    if latest_scrape:
        job_filter_id = resolve_latest_scrape_job_id(db)
        if job_filter_id is None:
            return []

    if job_filter_id is not None:
        q = db.query(Lead).filter(Lead.scrape_job_id == job_filter_id)
        q = q.order_by(Lead.scraped_at.desc(), Lead.fit_score.desc())
    else:
        q = db.query(Lead).order_by(Lead.fit_score.desc(), Lead.scraped_at.desc())
    thresholds = load_icp_config().get("thresholds", {})
    hot_threshold = thresholds.get("hot", 65)

    if not include_disqualified:
        q = q.filter(Lead.disqualified.is_(False))
    if min_score is not None:
        q = q.filter(Lead.fit_score >= min_score)
    if industry:
        q = q.filter(Lead.industry == industry)
    if status:
        q = q.filter(Lead.status == LeadStatus(status))
    if tier:
        q = q.filter(Lead.lead_tier == tier.upper())
    if practice_fit:
        q = q.filter(Lead.practice_fit == practice_fit)
    if has_email:
        q = q.filter(Lead.email.isnot(None), Lead.email != "")
    if has_phone:
        q = q.filter(Lead.phone.isnot(None), Lead.phone != "")
    if has_contact:
        q = q.filter(
            (Lead.email.isnot(None) & (Lead.email != ""))
            | (Lead.phone.isnot(None) & (Lead.phone != ""))
        )
    if has_portal:
        q = q.filter(Lead.portal_detected.is_(True))
    if not_exported:
        q = q.filter(Lead.exported_at.is_(None))
    if hot_only:
        q = q.filter(Lead.fit_score >= hot_threshold)
        q = q.filter(
            (Lead.email.isnot(None) & (Lead.email != ""))
            | (Lead.phone.isnot(None) & (Lead.phone != ""))
        )
        q = q.filter(Lead.pain_signals.isnot(None))
        q = q.filter(Lead.lead_tier == "A")
    if assigned_to_me:
        uid = _user_id(user)
        if uid:
            q = q.filter(Lead.assigned_to_user_id == uid)
    if assigned_to_user_id is not None:
        q = q.filter(Lead.assigned_to_user_id == assigned_to_user_id)

    leads = q.all()
    assign_ids = {l.assigned_to_user_id for l in leads if l.assigned_to_user_id}
    names = _user_name_map(db, assign_ids)
    return [lead_to_dict(l, names) for l in leads]


@app.get("/api/leads/{lead_id}")
def get_lead(
    lead_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead_to_dict(
        lead,
        _user_name_map(db, {lead.assigned_to_user_id} if lead.assigned_to_user_id else set()),
    )


@app.patch("/api/leads/{lead_id}")
def update_lead(
    lead_id: int,
    payload: LeadUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(lead, field, value)
    lead.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(lead)
    return lead_to_dict(
        lead,
        _user_name_map(db, {lead.assigned_to_user_id} if lead.assigned_to_user_id else set()),
    )


@app.post("/api/leads/export")
def export_leads(
    payload: ExportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Lead)
    if payload.lead_ids:
        q = q.filter(Lead.id.in_(payload.lead_ids))
    else:
        q = q.filter(Lead.disqualified.is_(False), Lead.exported_at.is_(None))
        if not payload.include_low_tier:
            q = q.filter(Lead.lead_tier.in_(["A", "B", "C"]))
        if not payload.include_no_contact:
            q = q.filter(
                (Lead.email.isnot(None) & (Lead.email != ""))
                | (Lead.phone.isnot(None) & (Lead.phone != ""))
            )

    leads = q.order_by(Lead.fit_score.desc()).all()
    if not leads:
        raise HTTPException(status_code=400, detail="No leads to export")

    try:
        result = export_leads_to_sheet(leads, sheet_id=payload.sheet_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    now = datetime.utcnow()
    for lead in leads:
        lead.exported_at = now
        lead.status = LeadStatus.EXPORTED
    db.commit()

    return result


@app.get("/api/email/templates")
def email_templates(user: User = Depends(get_current_user)):
    return get_default_templates()


@app.post("/api/email/campaigns")
def create_email_campaign(
    payload: EmailCampaignCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    campaign = EmailCampaign(
        name=payload.name,
        subject=payload.subject,
        body_template=payload.body_template,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return {
        "id": campaign.id,
        "name": campaign.name,
        "subject": campaign.subject,
        "status": campaign.status.value,
    }


@app.post("/api/email/send")
def send_email_campaign(
    payload: SendEmailRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    leads = db.query(Lead).filter(Lead.id.in_(payload.lead_ids)).all()
    if not leads:
        raise HTTPException(status_code=400, detail="No leads found")

    campaign = EmailCampaign(
        name=payload.campaign_name or "Manual Send",
        subject=payload.subject,
        body_template=payload.body_template,
    )
    db.add(campaign)
    db.flush()

    sent = 0
    errors = []
    for lead in leads:
        if not lead.email:
            errors.append({"lead_id": lead.id, "error": "No email"})
            continue
        try:
            subject = render_template(payload.subject, lead)
            body = render_template(payload.body_template, lead)
            send_campaign_email(lead, subject, body)
            lead.status = LeadStatus.CONTACTED
            sent += 1
        except Exception as exc:
            errors.append({"lead_id": lead.id, "error": str(exc)})

    campaign.leads_sent = sent
    campaign.status = EmailCampaignStatus.SENT if sent else EmailCampaignStatus.FAILED
    campaign.sent_at = datetime.utcnow()
    db.commit()

    return {"sent": sent, "errors": errors, "campaign_id": campaign.id}


@app.get("/api/stats")
def stats(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    thresholds = load_icp_config().get("thresholds", {})
    qualified_min = thresholds.get("qualified", 50)
    hot_min = thresholds.get("hot", 65)
    total = db.query(Lead).count()
    qualified = db.query(Lead).filter(Lead.fit_score >= qualified_min).count()
    hot_leads = db.query(Lead).filter(
        Lead.lead_tier == "A",
        Lead.disqualified.is_(False),
    ).count()
    with_email = db.query(Lead).filter(Lead.email.isnot(None), Lead.email != "").count()
    with_phone = db.query(Lead).filter(Lead.phone.isnot(None), Lead.phone != "").count()
    exported = db.query(Lead).filter(Lead.exported_at.isnot(None)).count()
    return {
        "total_leads": total,
        "qualified_leads": qualified,
        "hot_leads": hot_leads,
        "thresholds": thresholds,
        "with_email": with_email,
        "with_phone": with_phone,
        "exported": exported,
    }


# Serve frontend in production build
frontend_dist = ROOT_DIR / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
