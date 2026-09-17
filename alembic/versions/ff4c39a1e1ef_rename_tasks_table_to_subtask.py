"""rename tasks table to subtask

Revision ID: ff4c39a1e1ef
Revises: 7f4a5b6c8d2e
Create Date: 2026-09-16 15:07:08.493636

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'ff4c39a1e1ef'
down_revision: Union[str, Sequence[str], None] = '7f4a5b6c8d2e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _rename_constraint(name: str, new_name: str) -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(f'ALTER TABLE subtask RENAME CONSTRAINT "{name}" TO "{new_name}"')
    )


def upgrade() -> None:
    """Upgrade schema."""
    op.rename_table("tasks", "subtask")
    _rename_constraint("tasks_pkey", "subtask_pkey")
    _rename_constraint("tasks_project_id_fkey", "subtask_project_id_fkey")
    _rename_constraint("tasks_status_id_fkey", "subtask_status_id_fkey")
    _rename_constraint("tasks_created_by_fkey", "subtask_created_by_fkey")
    _rename_constraint("tasks_parent_task_id_fkey", "subtask_parent_task_id_fkey")
    _rename_constraint("fk_tasks_updated_by_users", "subtask_updated_by_fkey")


def downgrade() -> None:
    """Downgrade schema."""
    _rename_constraint("subtask_pkey", "tasks_pkey")
    _rename_constraint("subtask_project_id_fkey", "tasks_project_id_fkey")
    _rename_constraint("subtask_status_id_fkey", "tasks_status_id_fkey")
    _rename_constraint("subtask_created_by_fkey", "tasks_created_by_fkey")
    _rename_constraint("subtask_parent_task_id_fkey", "tasks_parent_task_id_fkey")
    _rename_constraint("subtask_updated_by_fkey", "fk_tasks_updated_by_users")
    op.rename_table("subtask", "tasks")