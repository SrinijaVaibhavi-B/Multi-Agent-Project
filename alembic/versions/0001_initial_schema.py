"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-06-11 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("job_title", sa.String(255), nullable=False),
        sa.Column("job_url", sa.String(2048), nullable=False),
        sa.Column("ats_platform", sa.String(64), nullable=True),
        sa.Column("external_job_id", sa.String(255), nullable=True),
        sa.Column("dedup_hash", sa.String(64), nullable=False),
        sa.Column("date_discovered", sa.DateTime(timezone=True), nullable=False),
        sa.Column("date_applied", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("raw_description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedup_hash"),
    )
    op.create_table(
        "review_queue",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("screenshot_path", sa.String(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved", sa.Boolean(), nullable=False),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "answer_bank",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_key", sa.String(255), nullable=False),
        sa.Column("answer_value", sa.Text(), nullable=False),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("question_key"),
    )


def downgrade() -> None:
    op.drop_table("answer_bank")
    op.drop_table("review_queue")
    op.drop_table("jobs")
