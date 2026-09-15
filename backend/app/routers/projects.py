"""项目/Agent/会话路由：保持薄，只收发参数，业务在对应 service。

嵌套路径 /projects/{id}/agents、/projects/{id}/threads 表达「归属关系」，
让前端按项目拉取它名下的 Agent 与会话，语义清晰。
"""
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from app.db import get_pool
from app.schemas import (
    AgentOut,
    CreateAgentIn,
    CreateProjectIn,
    CreateThreadIn,
    ProjectOut,
    ThreadOut,
)
from app.services import agents as agent_service
from app.services import projects as project_service
from app.services import threads as thread_service

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(body: CreateProjectIn, pool: asyncpg.Pool = Depends(get_pool)):
    """新建项目。"""
    return await project_service.create_project(pool, body.name, body.description)


@router.get("", response_model=list[ProjectOut])
async def list_projects(pool: asyncpg.Pool = Depends(get_pool)):
    """列出全部项目，供左侧项目栏展示。"""
    return await project_service.list_projects(pool)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: UUID, pool: asyncpg.Pool = Depends(get_pool)):
    """硬删项目及其全部关联数据；不存在返回 404。"""
    ok = await project_service.delete_project(pool, project_id)
    if not ok:
        raise HTTPException(status_code=404, detail="project not found")


@router.post("/{project_id}/agents", response_model=AgentOut, status_code=201)
async def create_agent(
    project_id: UUID, body: CreateAgentIn, pool: asyncpg.Pool = Depends(get_pool)
):
    """在项目下新建 Agent。"""
    return await agent_service.create_agent(
        pool, project_id, body.name, body.persona, body.system_prompt, body.use_rag
    )


@router.get("/{project_id}/agents", response_model=list[AgentOut])
async def list_agents(project_id: UUID, pool: asyncpg.Pool = Depends(get_pool)):
    """列出项目下全部 Agent。"""
    return await agent_service.list_agents(pool, project_id)


@router.post("/{project_id}/threads", response_model=ThreadOut, status_code=201)
async def create_thread(
    project_id: UUID, body: CreateThreadIn, pool: asyncpg.Pool = Depends(get_pool)
):
    """在项目下新建会话并绑定 Agent。"""
    return await thread_service.create_thread(
        pool, project_id, body.agent_id, body.title
    )


@router.get("/{project_id}/threads", response_model=list[ThreadOut])
async def list_threads(project_id: UUID, pool: asyncpg.Pool = Depends(get_pool)):
    """列出项目下全部会话，最新在前。"""
    return await thread_service.list_threads(pool, project_id)
