"""add users.is_super_admin and backfill from org_memberships

Revision ID: c7a3e41b09d2
Revises: dff2b08909b4
Create Date: 2026-09-10 00:00:00.000000+00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "c7a3e41b09d2"
down_revision = "3f7e6329f9ca"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_super_admin",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE users
               SET is_super_admin = true
             WHERE id IN (
                   SELECT user_id
                     FROM org_memberships
                    WHERE role = 'super_admin'
             )
            """
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_super_admin")
