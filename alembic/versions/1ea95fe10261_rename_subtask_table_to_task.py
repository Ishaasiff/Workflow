"""rename subtask table to task

Revision ID: 1ea95fe10261
Revises: ff4c39a1e1ef
Create Date: 2026-09-16 15:16:18.257848

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1ea95fe10261'
down_revision: Union[str, Sequence[str], None] = 'ff4c39a1e1ef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _rename_constraint(name: str, new_name: str) -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(f'ALTER TABLE task RENAME CONSTRAINT "{name}" TO "{new_name}"')
    )


def upgrade() -> None:
    """Upgrade schema."""
    op.rename_table("subtask", "task")
    _rename_constraint("subtask_pkey", "task_pkey")
    _rename_constraint("subtask_project_id_fkey", "task_project_id_fkey")
    _rename_constraint("subtask_status_id_fkey", "task_status_id_fkey")
    _rename_constraint("subtask_created_by_fkey", "task_created_by_fkey")
    _rename_constraint("subtask_parent_task_id_fkey", "task_parent_task_id_fkey")
    _rename_constraint("subtask_updated_by_fkey", "task_updated_by_fkey")


def downgrade() -> None:
    """Downgrade schema."""
    _rename_constraint("task_pkey", "subtask_pkey")
    _rename_constraint("task_project_id_fkey", "subtask_project_id_fkey")
    _rename_constraint("task_status_id_fkey", "subtask_status_id_fkey")
    _rename_constraint("task_created_by_fkey", "subtask_created_by_fkey")
    _rename_constraint("task_parent_task_id_fkey", "subtask_parent_task_id_fkey")
    _rename_constraint("task_updated_by_fkey", "subtask_updated_by_fkey")
    op.rename_table("task", "subtask")