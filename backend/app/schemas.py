"""HTTP 出入参模型：只定义当前接口真正用到的字段，不预留扩展位。"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class CreateRequestIn(BaseModel):
    """发起一次提问：前端只需给会话标识和问题内容。"""
    thread_id: str
    content: str


class CreateRequestOut(BaseModel):
    """落库即返回：把请求 id 和状态立刻给前端，不等真正执行。"""
    request_id: UUID
    message_id: UUID
    status: str


class RequestOut(BaseModel):
    """查询请求当前状态时的返回体。"""
    id: UUID
    thread_id: str
    status: str
    created_at: datetime


class IngestDocumentIn(BaseModel):
    """文档入库入参：资料归属项目，给项目 id、标题和正文，切块向量化由后端做。"""
    project_id: UUID
    title: str
    content: str


class IngestDocumentOut(BaseModel):
    """入库结果：文档 id 和切出的块数，方便前端确认存了多少。"""
    document_id: UUID
    chunk_count: int


class DocumentOut(BaseModel):
    """资料列表项：只回标题和块数，不回正文，列表页够用。"""
    id: UUID
    title: str
    chunk_count: int
    created_at: datetime


# ---- 项目 / Agent / 会话（M11 项目分区 + 多 Agent）----

class CreateProjectIn(BaseModel):
    """新建项目：名称必填，描述可选。"""
    name: str
    description: str = ""


class ProjectOut(BaseModel):
    """项目返回体。"""
    id: UUID
    name: str
    description: str
    created_at: datetime


class CreateAgentIn(BaseModel):
    """在项目内新建 Agent：人设与系统提示可选，use_rag 决定是否检索知识库。"""
    name: str
    persona: str = ""
    system_prompt: str = ""
    use_rag: bool = True


class AgentOut(BaseModel):
    """Agent 返回体。"""
    id: UUID
    project_id: UUID
    name: str
    persona: str
    system_prompt: str
    use_rag: bool
    created_at: datetime


class CreateThreadIn(BaseModel):
    """在项目内新建会话：绑定一个 Agent，标题可选。"""
    agent_id: UUID
    title: str = "新会话"


class ThreadOut(BaseModel):
    """会话返回体。"""
    id: UUID
    project_id: UUID
    agent_id: UUID
    title: str
    created_at: datetime


class MessageOut(BaseModel):
    """历史消息返回体，用于切换会话时回放对话。"""
    id: UUID
    role: str
    content: str
    created_at: datetime


class LLMConfigView(BaseModel):
    """给前端看的 LLM 配置：密钥只回「是否已设置」，不回显明文。"""
    base_url: str
    model: str
    key_set: bool


class SaveLLMConfigIn(BaseModel):
    """保存 LLM 配置：api_key 为空表示「不改密钥」，保留库里原值。"""
    base_url: str
    model: str
    api_key: str | None = None


class ListModelsIn(BaseModel):
    """拉模型列表入参：api_key 为空则用库里已存的密钥去拉。"""
    base_url: str
    api_key: str | None = None


class ListModelsOut(BaseModel):
    """拉取到的可选模型 id 列表，供前端下拉选择。"""
    models: list[str]
