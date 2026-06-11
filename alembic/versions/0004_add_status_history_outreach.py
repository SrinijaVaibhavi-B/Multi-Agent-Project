"""add status_history, outreach; fix review_queue pipeline FK

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "status_history",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("job_id", sa.Integer, sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("from_status", sa.String(32), nullable=True),
        sa.Column("to_status", sa.String(32), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changed_by", sa.String(64), nullable=True),
    )
    op.create_table(
        "outreach",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("job_id", sa.Integer, sa.ForeignKey("jobs.id"), nullable=True),
        sa.Column("recruiter_name", sa.String(255), nullable=True),
        sa.Column("recruiter_email", sa.String(255), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("message_subject", sa.String(512), nullable=True),
        sa.Column("message_body", sa.Text, nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reply_received", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("reply_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reply_body", sa.Text, nullable=True),
    )
    op.add_column("review_queue", sa.Column("pipeline_id", sa.Integer, sa.ForeignKey("job_pipeline.id"), nullable=True))


def downgrade() -> None:
    op.drop_column("review_queue", "pipeline_id")
    op.drop_table("outreach")
    op.drop_table("status_history")
