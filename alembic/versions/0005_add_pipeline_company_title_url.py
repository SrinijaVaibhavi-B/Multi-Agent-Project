"""add company_name, job_title, job_url to job_pipeline

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("job_pipeline", sa.Column("company_name", sa.String(255), nullable=True))
    op.add_column("job_pipeline", sa.Column("job_title", sa.String(255), nullable=True))
    op.add_column("job_pipeline", sa.Column("job_url", sa.String(2048), nullable=True))


def downgrade() -> None:
    op.drop_column("job_pipeline", "job_url")
    op.drop_column("job_pipeline", "job_title")
    op.drop_column("job_pipeline", "company_name")
