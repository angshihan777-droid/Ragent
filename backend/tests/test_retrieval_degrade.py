"""检索分段超时：rerank 降级、embedding/召回失败向上抛。"""
import asyncio

import pytest

from app.services import rag


class _Acquire:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc):
        return False


class _Pool:
    def acquire(self):
        return _Acquire()


def _rows():
    return [
        {
            "content": "first", "title": "doc-a", "document_id": "d1",
            "chunk_id": "c1", "similarity": 0.9, "metadata": {},
        },
        {
            "content": "second", "title": "doc-a", "document_id": "d1",
            "chunk_id": "c2", "similarity": 0.8, "metadata": {},
        },
    ]


def test_rerank_timeout_falls_back_to_recall_order(monkeypatch):
    async def fake_embed(_question):
        return [0.1, 0.2]

    async def fake_search(_conn, _project_id, _embedding, _limit):
        return _rows()

    async def slow_rerank(_question, _candidates, _top_k):
        await asyncio.sleep(0.2)
        return ["second", "first"]

    monkeypatch.setattr(rag, "embed_query", fake_embed)
    monkeypatch.setattr(rag.documents, "search_chunks_with_doc", fake_search)
    monkeypatch.setattr(rag, "rerank", slow_rerank)
    monkeypatch.setattr(rag, "RERANK_TIMEOUT_SECONDS", 0.01)

    hits = asyncio.run(rag.retrieve(_Pool(), "p1", "question"))
    assert [hit["chunk_id"] for hit in hits] == ["c1", "c2"]


def test_embedding_failure_propagates(monkeypatch):
    async def failing_embed(_question):
        raise RuntimeError("model unavailable")

    async def must_not_search(*_args, **_kwargs):
        raise AssertionError("embedding 失败时不应继续查库")

    monkeypatch.setattr(rag, "embed_query", failing_embed)
    monkeypatch.setattr(rag.documents, "search_chunks_with_doc", must_not_search)

    with pytest.raises(RuntimeError, match="model unavailable"):
        asyncio.run(rag.retrieve(_Pool(), "p1", "question"))


def test_search_timeout_propagates(monkeypatch):
    async def fake_embed(_question):
        return [0.1]

    async def slow_search(*_args, **_kwargs):
        await asyncio.sleep(0.2)
        return _rows()

    monkeypatch.setattr(rag, "embed_query", fake_embed)
    monkeypatch.setattr(rag.documents, "search_chunks_with_doc", slow_search)
    monkeypatch.setattr(rag, "SEARCH_TIMEOUT_SECONDS", 0.01)

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(rag.retrieve(_Pool(), "p1", "question"))
