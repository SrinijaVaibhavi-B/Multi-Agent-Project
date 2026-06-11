"""add resume_used to jobs

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("resume_used", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "resume_used")
