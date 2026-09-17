import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers import task_controller as task_fn
from app.controllers.auth_controller import (
    AuthContext,
    assert_project_access,
    get_current_user,
    is_project_manager,
    require_org_member,
)
from app.database import get_db
from app.models.tasks import TaskPriority
from app.models.task_schemas import (
    TaskActivityListResponse,
    TaskCreateRequest,
    TaskListResponse,
    TaskOut,
    TaskUpdateRequest,
    SubtaskCreateRequest,
    AssigneeUpdateRequest,
)

router = APIRouter(tags=["tasks"])


@router.post(
    "/projects/{project_id}/tasks", response_model=TaskOut, status_code=201
)
async def create_task(
    project_id: uuid.UUID,
    payload: TaskCreateRequest,
    ctx: AuthContext = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
):
    if not await is_project_manager(ctx, db, project_id):
        raise HTTPException(
            status_code=403, detail="only project manager can create tasks"
        )
    try:
        return await task_fn.create_task(
            db,
            ctx,
            project_id,
            payload.title,
            payload.description,
            payload.status_id,
            payload.priority,
            payload.due_date,
            payload.estimated_hours,
            payload.assignee_ids,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/projects/{project_id}/tasks", response_model=TaskListResponse
)
async def list_tasks(
    project_id: uuid.UUID,
    ctx: AuthContext = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
    status: uuid.UUID | None = Query(default=None),
    assignee: uuid.UUID | None = Query(default=None),
    priority: TaskPriority | None = Query(default=None),
    search: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    await assert_project_access(ctx, db, project_id)
    return await task_fn.list_tasks(
        db, ctx, project_id, status, assignee, priority, search, offset, limit
    )


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(
    task_id: uuid.UUID,
    ctx: AuthContext = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await task_fn.get_task(db, ctx, task_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdateRequest,
    ctx: AuthContext = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await task_fn.update_task(
            db,
            ctx,
            task_id,
            payload.model_fields_set,
            payload.title if "title" in payload.model_fields_set else None,
            payload.description
            if "description" in payload.model_fields_set
            else None,
            payload.status_id
            if "status_id" in payload.model_fields_set
            else None,
            payload.priority
            if "priority" in payload.model_fields_set
            else None,
            payload.due_date
            if "due_date" in payload.model_fields_set
            else None,
            payload.estimated_hours
            if "estimated_hours" in payload.model_fields_set
            else None,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(
    task_id: uuid.UUID,
    ctx: AuthContext = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
):
    try:
        task = await task_fn._get_task(db, task_id)
        project = await task_fn._get_project_for_org(db, task.project_id, ctx.org_id)
        if not await is_project_manager(ctx, db, project.id):
            raise HTTPException(
                status_code=403,
                detail="only project manager can delete tasks",
            )
        await task_fn.delete_task(db, ctx, task_id)
    except task_fn.SubtaskInUseError as e:
        raise HTTPException(
            status_code=409,
            detail=f"task has {e.count} subtasks; remove them first",
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return None


@router.post(
    "/tasks/{task_id}/subtasks", response_model=TaskOut, status_code=201
)
async def create_subtask(
    task_id: uuid.UUID,
    payload: SubtaskCreateRequest,
    ctx: AuthContext = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
):
    try:
        task = await task_fn._get_task(db, task_id)
        project = await task_fn._get_project_for_org(db, task.project_id, ctx.org_id)
        if not await is_project_manager(ctx, db, project.id):
            raise HTTPException(
                status_code=403,
                detail="only project manager can create subtasks",
            )
        return await task_fn.create_subtask(
            db,
            ctx,
            task_id,
            payload.title,
            payload.description,
            payload.status_id,
            payload.priority,
            payload.due_date,
            payload.estimated_hours,
            payload.assignee_ids,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tasks/{task_id}/subtasks", response_model=list[TaskOut])
async def list_subtasks(
    task_id: uuid.UUID,
    ctx: AuthContext = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
):
    task_obj = await task_fn._get_task(db, task_id)
    await assert_project_access(ctx, db, task_obj.project_id)
    try:
        return await task_fn.list_subtasks(db, ctx, task_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.patch("/tasks/{task_id}/assignees", response_model=TaskOut)
async def update_assignees(
    task_id: uuid.UUID,
    payload: AssigneeUpdateRequest,
    ctx: AuthContext = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
):
    try:
        task_obj = await task_fn._get_task(db, task_id)
        project = await task_fn._get_project_for_org(
            db, task_obj.project_id, ctx.org_id
        )
        if not await is_project_manager(ctx, db, project.id):
            raise HTTPException(
                status_code=403,
                detail="only project manager can update assignees",
            )
        return await task_fn.update_assignees(db, ctx, task_id, payload.assignee_ids)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tasks/{task_id}/activity", response_model=TaskActivityListResponse)
async def list_task_activity(
    task_id: uuid.UUID,
    ctx: AuthContext = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    try:
        return await task_fn.list_task_activity(db, ctx, task_id, offset, limit)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/tasks", response_model=TaskListResponse)
async def list_my_tasks(
    ctx: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    status: uuid.UUID | None = Query(default=None),
    priority: TaskPriority | None = Query(default=None),
    search: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    return await task_fn.list_my_tasks(
        db, ctx, status, priority, search, offset, limit
    )
