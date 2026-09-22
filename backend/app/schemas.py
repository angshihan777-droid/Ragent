"""HTTP 出入参模型：只定义当前接口真正用到的字段，不预留扩展位。"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class CreateRequestIn(BaseModel):
    """发起一次提问：前端只需给会话标识和问题内容。"""
    thread_id: str
    content: str = Field(min_length=1, max_length=16000)


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


# ---- 项目 / 会话----

class CreateProjectIn(BaseModel):
    """新建项目：名称必填，描述可选。"""
    name: str = Field(min_length=1, max_length=120)
    description: str = ""

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        if not value.strip():
            raise ValueError("项目名称不能为空")
        return value.strip()


class ProjectOut(BaseModel):
    """项目返回体。"""
    id: UUID
    name: str
    description: str
    created_at: datetime


class CreateThreadIn(BaseModel):
    """在项目内新建知识库会话。"""
    title: str = "新会话"


class ThreadOut(BaseModel):
    """会话返回体。"""
    id: UUID
    project_id: UUID
    title: str
    created_at: datetime


class MessageOut(BaseModel):
    """历史消息返回体，用于切换会话时回放对话。"""
    id: UUID
    role: str
    content: str
    error: bool = False
    sources: list[dict] = Field(default_factory=list)
    steps: list[dict] = Field(default_factory=list)
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


class DocumentDetailOut(DocumentOut):
    project_id: UUID
    content: str
    revision: UUID


class UpdateDocumentIn(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1)
    revision: UUID

    @field_validator("title", "content")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("标题和正文不能为空")
        return value
