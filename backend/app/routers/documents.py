"""文档路由：保持薄，只收发参数，切块/向量化/落库在 rag service。"""
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends

from app.db import get_pool
from app.schemas import DocumentOut, IngestDocumentIn, IngestDocumentOut
from app.services import rag

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=IngestDocumentOut, status_code=201)
async def ingest_document(
    body: IngestDocumentIn,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """文档入库：切块→向量化→落库（归属 body.project_id），返回文档 id 和块数。"""
    document_id, chunk_count = await rag.ingest_document(
        pool, body.project_id, body.title, body.content
    )
    return IngestDocumentOut(document_id=document_id, chunk_count=chunk_count)


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    project_id: UUID,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """列出某项目的资料（标题+块数），供资料管理页展示。"""
    return await rag.list_documents(pool, project_id)


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: UUID,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """删一篇资料（chunks 级联删除）。"""
    await rag.delete_document(pool, document_id)
