import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class LeadStatus(str, enum.Enum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    NOT_A_FIT = "not_a_fit"
    EXPORTED = "exported"
    APPROVED_FOR_EMAIL = "approved_for_email"


class ScrapeJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EnrichmentMode(str, enum.Enum):
    FAST = "fast"
    QUALITY = "quality"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    BDR = "bdr"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.BDR)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    industry: Mapped[str] = mapped_column(String(64), nullable=False)
    city: Mapped[str | None] = mapped_column(String(128))
    state: Mapped[str | None] = mapped_column(String(8))
    keyword_override: Mapped[str | None] = mapped_column(String(256))
    positive_keywords_override: Mapped[str | None] = mapped_column(Text)
    negative_keywords_override: Mapped[str | None] = mapped_column(Text)
    enrichment_mode: Mapped[str] = mapped_column(String(16), default="quality")
    status: Mapped[ScrapeJobStatus] = mapped_column(
        Enum(ScrapeJobStatus), default=ScrapeJobStatus.PENDING
    )
    progress_message: Mapped[str | None] = mapped_column(Text)
    companies_found: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    leads: Mapped[list["Lead"]] = relationship(back_populates="scrape_job")


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scrape_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("scrape_jobs.id"), nullable=True
    )
    assigned_to_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )

    company_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    industry: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    website: Mapped[str | None] = mapped_column(String(512))
    phone: Mapped[str | None] = mapped_column(String(64))
    email: Mapped[str | None] = mapped_column(String(256))
    contact_name: Mapped[str | None] = mapped_column(String(256))
    contact_title: Mapped[str | None] = mapped_column(String(256))
    city: Mapped[str | None] = mapped_column(String(128))
    state: Mapped[str | None] = mapped_column(String(8))
    address: Mapped[str | None] = mapped_column(String(512))
    portal_detected: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    portal_type: Mapped[str | None] = mapped_column(String(32))
    portal_urls: Mapped[list | None] = mapped_column(JSON, default=list)
    platform_signals: Mapped[list | None] = mapped_column(JSON, default=list)
    employee_estimate: Mapped[int | None] = mapped_column(Integer)
    fit_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    lead_tier: Mapped[str | None] = mapped_column(String(1), index=True)
    practice_fit: Mapped[str | None] = mapped_column(String(64))
    pain_signals: Mapped[list | None] = mapped_column(JSON, default=list)
    score_rationale: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[list | None] = mapped_column(JSON, default=list)
    source_url: Mapped[str | None] = mapped_column(String(1024))
    status: Mapped[LeadStatus] = mapped_column(
        Enum(LeadStatus), default=LeadStatus.NEW, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)
    disqualified: Mapped[bool] = mapped_column(Boolean, default=False)
    disqualify_reason: Mapped[str | None] = mapped_column(Text)
    exported_at: Mapped[datetime | None] = mapped_column(DateTime)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    scrape_job: Mapped[ScrapeJob | None] = relationship(back_populates="leads")


class EmailCampaignStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    FAILED = "failed"


class EmailCampaign(Base):
    __tablename__ = "email_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[EmailCampaignStatus] = mapped_column(
        Enum(EmailCampaignStatus), default=EmailCampaignStatus.DRAFT
    )
    leads_sent: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
