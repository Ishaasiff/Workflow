import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers import project_controller as project_fn
from app.controllers.auth_controller import (
    AuthContext,
    assert_project_access,
    require_org_admin,
    require_org_member,
)
from app.core.plans import PlanLimitError
from app.database import get_db
from app.models.project_schemas import (
    ProgressOut,
    ProjectCreateRequest,
    ProjectMemberAddRequest,
    ProjectMemberOut,
    ProjectOut,
    ProjectRoleUpdateRequest,
    ProjectUpdateRequest,
    StatusCreateRequest,
    StatusOut,
    StatusUpdateRequest,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(
    payload: ProjectCreateRequest,
    ctx: AuthContext = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await project_fn.create_project(
            db, ctx.org_id, ctx.user_id, payload.name, payload.description
        )
    except PlanLimitError as e:
        raise HTTPException(status_code=402, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    ctx: AuthContext = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
):
    return await project_fn.list_projects(db, ctx)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: uuid.UUID,
    ctx: AuthContext = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
):
    await assert_project_access(ctx, db, project_id)
    try:
        return await project_fn.get_project(db, project_id, ctx.org_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdateRequest,
    ctx: AuthContext = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
):
    await project_fn.assert_project_manager(db, ctx, project_id)
    try:
        return await project_fn.update_project(
            db,
            project_id,
            ctx.org_id,
            ctx.user_id,
            payload.name if "name" in payload.model_fields_set else None,
            payload.description if "description" in payload.model_fields_set else None,
            payload.status if "status" in payload.model_fields_set else None,
        )
    except PlanLimitError as e:
        raise HTTPException(status_code=402, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: uuid.UUID,
    ctx: AuthContext = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        await project_fn.delete_project(db, project_id, ctx.org_id, ctx.user_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return None


@router.get("/{project_id}/members", response_model=list[ProjectMemberOut])
async def list_members(
    project_id: uuid.UUID,
    ctx: AuthContext = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
):
    await assert_project_access(ctx, db, project_id)
    try:
        return await project_fn.list_members(db, project_id, ctx.org_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/{project_id}/members", response_model=ProjectMemberOut, status_code=201)
async def add_member(
    project_id: uuid.UUID,
    payload: ProjectMemberAddRequest,
    ctx: AuthContext = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
):
    await project_fn.assert_project_manager(db, ctx, project_id)
    try:
        return await project_fn.add_member(
            db, project_id, ctx.org_id, payload.user_id, payload.role, ctx.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.patch("/{project_id}/members/{user_id}", response_model=ProjectMemberOut)
async def update_member_role(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: ProjectRoleUpdateRequest,
    ctx: AuthContext = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
):
    await project_fn.assert_project_manager(db, ctx, project_id)
    try:
        return await project_fn.update_member_role(
            db, project_id, ctx.org_id, user_id, payload.role, ctx.user_id
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete("/{project_id}/members/{user_id}", status_code=204)
async def remove_member(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    ctx: AuthContext = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
):
    await project_fn.assert_project_manager(db, ctx, project_id)
    try:
        await project_fn.remove_member(db, project_id, ctx.org_id, user_id, ctx.user_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return None


@router.get("/{project_id}/progress", response_model=ProgressOut)
async def get_progress(
    project_id: uuid.UUID,
    ctx: AuthContext = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
):
    await assert_project_access(ctx, db, project_id)
    try:
        return await project_fn.get_progress(db, project_id, ctx.org_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/{project_id}/statuses", response_model=list[StatusOut])
async def list_statuses(
    project_id: uuid.UUID,
    ctx: AuthContext = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
):
    await assert_project_access(ctx, db, project_id)
    try:
        return await project_fn.list_statuses(db, project_id, ctx.org_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/{project_id}/statuses", response_model=StatusOut, status_code=201)
async def create_status(
    project_id: uuid.UUID,
    payload: StatusCreateRequest,
    ctx: AuthContext = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
):
    await project_fn.assert_project_manager(db, ctx, project_id)
    try:
        return await project_fn.create_status(
            db, project_id, ctx.org_id, ctx.user_id, payload.name, payload.color, payload.order
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.patch("/{project_id}/statuses/{status_id}", response_model=StatusOut)
async def update_status(
    project_id: uuid.UUID,
    status_id: uuid.UUID,
    payload: StatusUpdateRequest,
    ctx: AuthContext = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
):
    await project_fn.assert_project_manager(db, ctx, project_id)
    try:
        return await project_fn.update_status(
            db,
            project_id,
            ctx.org_id,
            status_id,
            ctx.user_id,
            payload.name,
            payload.color,
            payload.order,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete("/{project_id}/statuses/{status_id}")
async def delete_status(
    project_id: uuid.UUID,
    status_id: uuid.UUID,
    ctx: AuthContext = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
):
    await project_fn.assert_project_manager(db, ctx, project_id)
    try:
        return await project_fn.delete_status(
            db, project_id, ctx.org_id, status_id, ctx.user_id
        )
    except project_fn.StatusInUseError as e:
        raise HTTPException(
            status_code=409,
            detail=f"{e.count} tasks are assigned to this status; reassign or delete them first",
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))