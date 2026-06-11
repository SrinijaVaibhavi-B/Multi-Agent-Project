"""split jobs into tracker + pipeline tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Recreate jobs as clean tracker table
    op.drop_table("jobs")
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("job_title", sa.String(255), nullable=False),
        sa.Column("job_url", sa.String(2048), nullable=False),
        sa.Column("date_applied", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="applied"),
        sa.Column("job_description", sa.Text, nullable=True),
        sa.Column("resume_used", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_table(
        "job_pipeline",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("job_id", sa.Integer, sa.ForeignKey("jobs.id"), nullable=True),
        sa.Column("ats_platform", sa.String(64), nullable=True),
        sa.Column("external_job_id", sa.String(255), nullable=True),
        sa.Column("dedup_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("pipeline_status", sa.String(32), nullable=False, server_default="discovered"),
        sa.Column("date_discovered", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_description", sa.Text, nullable=True),
        sa.Column("fit_score", sa.Integer, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("job_pipeline")
    op.drop_table("jobs")
