"""drop organizations.slug

Revision ID: e4f1a9c2b7d3
Revises: c7a3e41b09d2
Create Date: 2026-09-11 00:00:00.000000+00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "e4f1a9c2b7d3"
down_revision = "c7a3e41b09d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("organizations", "slug")


def downgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("slug", sa.String(), nullable=True),
    )
