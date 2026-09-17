"""add tasks.updated_by

Revision ID: 7f4a5b6c8d2e
Revises: e4f1a9c2b7d3
Create Date: 2026-09-16 00:00:00.000000+00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "7f4a5b6c8d2e"
down_revision = "e4f1a9c2b7d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("updated_by", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_tasks_updated_by_users",
        "tasks",
        "users",
        ["updated_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_tasks_updated_by_users", "tasks", type_="foreignkey")
    op.drop_column("tasks", "updated_by")