"""文档路由：保持薄，只收发参数，切块/向量化/落库在 rag service。"""
import asyncio
import hashlib
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.db import get_pool
from app.schemas import DocumentOut, IngestDocumentIn, IngestDocumentOut
from app.services import attachments, rag, projects

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=IngestDocumentOut, status_code=201)
async def ingest_document(
    body: IngestDocumentIn,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """文档入库：切块→向量化→落库（归属 body.project_id），返回文档 id 和块数。"""
    if await projects.get_project(pool, body.project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    if not body.content.strip() or not body.title.strip():
        raise HTTPException(status_code=400, detail="标题和正文不能为空")
    document_id, chunk_count = await rag.ingest_document(
        pool, body.project_id, body.title, body.content
    )
    return IngestDocumentOut(document_id=document_id, chunk_count=chunk_count)


@router.post("/upload", response_model=IngestDocumentOut, status_code=201)
async def upload_document(
    project_id: UUID = Form(...),
    file: UploadFile = File(...),
    title: str | None = Form(None),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """上传文件入库：支持 PDF/Word(.docx)/Markdown/纯文本，解析成文本后走同一条入库链路。

    路由保持薄：只收 multipart、解析成纯文本、把不支持类型/空文本收成 400，
    切块向量化落库仍复用 rag.ingest_document，不另起一套逻辑。
    标题缺省用文件名，方便检索命中时溯源到具体来源文件。
    """
    if await projects.get_project(pool, project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    raw = await file.read(20 * 1024 * 1024 + 1)
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件大小不能超过 20 MB")
    try:
        blocks = await asyncio.to_thread(attachments.parse_file, file.filename, raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    doc_title = (title or "").strip() or (file.filename or "未命名文件")
    document_id, chunk_count = await rag.ingest_document(
        pool, project_id, doc_title, blocks=blocks, source_hash=hashlib.sha256(raw).hexdigest()
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
