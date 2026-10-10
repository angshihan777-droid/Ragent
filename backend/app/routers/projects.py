"""项目与会话接口。

归属校验统一走 deps 里的依赖：路径上带 project_id 的端点挂 require_owned_project，
列表/创建这类没有资源 id 的端点直接把 owner_id 传进 service 让 SQL 带上过滤条件。
"""
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from app.db import get_pool
from app.deps import get_owner_id, require_owned_project
from app.schemas import (
    CreateProjectIn,
    CreateThreadIn,
    ProjectOut,
    ThreadOut,
)
from app.services import projects as project_service
from app.services import threads as thread_service

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(
    body: CreateProjectIn,
    owner_id: str = Depends(get_owner_id),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """新建项目，归属当前身份。"""
    return await project_service.create_project(pool, owner_id, body.name, body.description)


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    owner_id: str = Depends(get_owner_id),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """列出当前身份的项目，供左侧项目栏展示。

    过滤放在 SQL 而不是前端：前端筛等于先把别人的数据发到浏览器，那不叫隔离。
    """
    return await project_service.list_projects(pool, owner_id)


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: UUID = Depends(require_owned_project),
    owner_id: str = Depends(get_owner_id),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """硬删项目及其全部关联数据；不存在或不归自己都返回 404。"""
    ok = await project_service.delete_project(pool, project_id, owner_id)
    if not ok:
        raise HTTPException(status_code=404, detail="project not found")


@router.post("/{project_id}/threads", response_model=ThreadOut, status_code=201)
async def create_thread(
    body: CreateThreadIn,
    project_id: UUID = Depends(require_owned_project),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """在项目下新建知识库会话。项目存在性与归属都由依赖一次校验完。"""
    return await thread_service.create_thread(pool, project_id, body.title)


@router.get("/{project_id}/threads", response_model=list[ThreadOut])
async def list_threads(
    project_id: UUID = Depends(require_owned_project),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """列出项目下全部会话，最新在前。"""
    return await thread_service.list_threads(pool, project_id)