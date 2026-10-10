"""文档路由：保持薄，只收发参数，切块/向量化/落库在 rag service。

归属校验：路径上带 document_id 的挂 require_owned_document；project_id 来自
body / Form / query 三种位置的，用 assert_owned_project 在函数里显式验一次。
资料正文与项目同属一条归属链（documents.project_id → projects.owner_id），不另挂 owner 列。
"""
import asyncio
import hashlib
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.db import get_pool
from app.deps import assert_owned_project, get_owner_id, require_owned_document
from app.schemas import DocumentOut, DocumentDetailOut, UpdateDocumentIn, IngestDocumentIn, IngestDocumentOut
from app.services import attachments, rag

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=IngestDocumentOut, status_code=201)
async def ingest_document(
    body: IngestDocumentIn,
    owner_id: str = Depends(get_owner_id),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """文档入库：切块→向量化→落库（归属 body.project_id），返回文档 id 和块数。"""
    # 项目不存在与不归自己合并成同一个 404：入库前就挡住，别把向量化算力花在别人项目上
    await assert_owned_project(pool, body.project_id, owner_id)
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
    owner_id: str = Depends(get_owner_id),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """上传文件入库：支持 PDF/Word(.docx)/Markdown/纯文本，解析成文本后走同一条入库链路。

    路由保持薄：只收 multipart、解析成纯文本、把不支持类型/空文本收成 400，
    切块向量化落库仍复用 rag.ingest_document，不另起一套逻辑。
    标题缺省用文件名，方便检索命中时溯源到具体来源文件。
    """
    # 归属校验刻意放在 file.read() 之前：越权请求不该先把 20 MB 读进内存，
    # 否则任何人拿一个别人的 project_id 就能反复打满这台机器的内存带宽。
    await assert_owned_project(pool, project_id, owner_id)
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
    owner_id: str = Depends(get_owner_id),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """列出某项目的资料（标题+块数），供资料管理页展示。

    这里的 project_id 在 query 上，不校验就是一个「换个 id 就能看别人资料标题」的枚举接口。
    """
    await assert_owned_project(pool, project_id, owner_id)
    return await rag.list_documents(pool, project_id)

@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: UUID = Depends(require_owned_document),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """删一篇资料（chunks 级联删除）。"""
    if not await rag.delete_document(pool, document_id):
        raise HTTPException(status_code=404, detail="资料不存在或已被删除")


@router.get("/{document_id}", response_model=DocumentDetailOut)
async def get_document(
    document_id: UUID = Depends(require_owned_document),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """读一篇资料正文，供资料编辑页回显。"""
    document = await rag.get_document(pool, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="资料不存在或已被删除")
    return document


@router.put("/{document_id}", response_model=DocumentDetailOut)
async def update_document(
    body: UpdateDocumentIn,
    document_id: UUID = Depends(require_owned_document),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """改一篇资料（乐观并发，revision 不匹配回 409）。

    body 写在最前面是 Python 的形参规则要求：带默认值的 Depends 只能排在无默认值的参数之后。
    """
    try:
        document = await rag.update_document(pool, document_id, body.title, body.content, body.revision)
    except rag.DocumentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if document is None:
        raise HTTPException(status_code=404, detail="资料不存在或已被删除")
    return document