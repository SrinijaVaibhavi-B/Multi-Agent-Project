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
    """User-facing tracker — only applied jobs live here."""
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
    review_items: Mapped[list["ReviewQueue"]] = relationship(back_populates="job")


class JobPipeline(Base):
    """Internal agent state — discovery, dedup, ATS metadata, queue status."""
    __tablename__ = "job_pipeline"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    # null job_id = discovered but not yet applied
    ats_platform: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dedup_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    pipeline_status: Mapped[str] = mapped_column(String(32), nullable=False, default="discovered")
    # pipeline_status values: discovered / queued / applying / applied / skipped / failed
    date_discovered: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    raw_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    fit_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    job: Mapped["Job | None"] = relationship(back_populates="pipeline")


class ReviewQueue(Base):
    __tablename__ = "review_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    screenshot_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    job: Mapped["Job | None"] = relationship(back_populates="review_items")


class AnswerBank(Base):
    __tablename__ = "answer_bank"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    answer_value: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
