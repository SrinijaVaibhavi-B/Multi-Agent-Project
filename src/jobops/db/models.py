from datetime import datetime, timezone
from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Job(Base):
    """User-facing tracker — one row per applied job."""
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    job_title: Mapped[str] = mapped_column(String(255), nullable=False)
    job_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    date_applied: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="applied")
    # status values: applied / screening / interviewing / offer / rejected
    job_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    resume_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    pipeline: Mapped["JobPipeline | None"] = relationship(back_populates="job", uselist=False)
    status_history: Mapped[list["StatusHistory"]] = relationship(back_populates="job", order_by="StatusHistory.changed_at")
    review_items: Mapped[list["ReviewQueue"]] = relationship(back_populates="job")
    outreach: Mapped[list["Outreach"]] = relationship(back_populates="job")


class JobPipeline(Base):
    """Internal agent state — one row per discovered job, linked to jobs once applied."""
    __tablename__ = "job_pipeline"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    ats_platform: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dedup_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    pipeline_status: Mapped[str] = mapped_column(String(32), nullable=False, default="discovered")
    # pipeline_status values: discovered / queued / applying / applied / skipped / failed
    date_discovered: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    raw_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    fit_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    resume_drive_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    apply_result: Mapped[str | None] = mapped_column(Text, nullable=True)

    job: Mapped["Job | None"] = relationship(back_populates="pipeline")
    review_items: Mapped[list["ReviewQueue"]] = relationship(back_populates="pipeline")


class StatusHistory(Base):
    """Immutable log of every status change on a job — never update, only insert."""
    __tablename__ = "status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)  # null on first entry
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    changed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # changed_by: inbox_monitor / apply_agent / manual

    job: Mapped["Job"] = relationship(back_populates="status_history")


class ReviewQueue(Base):
    """Items needing manual review — linked to pipeline (pre-apply) or job (post-apply)."""
    __tablename__ = "review_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    pipeline_id: Mapped[int | None] = mapped_column(ForeignKey("job_pipeline.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # reason values: captcha / unknown_step / legal_question / verifier_failed / fit_review
    screenshot_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    job: Mapped["Job | None"] = relationship(back_populates="review_items")
    pipeline: Mapped["JobPipeline | None"] = relationship(back_populates="review_items")


class Outreach(Base):
    """Recruiter outreach log — one row per message sent."""
    __tablename__ = "outreach"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    recruiter_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recruiter_email: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    message_subject: Mapped[str | None] = mapped_column(String(512), nullable=True)
    message_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    reply_received: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reply_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reply_body: Mapped[str | None] = mapped_column(Text, nullable=True)

    job: Mapped["Job | None"] = relationship(back_populates="outreach")


class AnswerBank(Base):
    """Pre-filled answers to legal/EEO questions. Never guessed by LLM."""
    __tablename__ = "answer_bank"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    answer_value: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # category values: legal / eeo / preferences / personal
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
