"""Offline contract tests: model inference and database I/O are mocked, not the mapping logic."""
import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class RetrievalSourceTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.modules = patch.dict(sys.modules, {
            "asyncpg": types.SimpleNamespace(Pool=object, Connection=object, Record=dict),
            "app.agent.embedding": types.SimpleNamespace(embed_query=AsyncMock(), embed_texts=AsyncMock()),
            "app.agent.rerank": types.SimpleNamespace(rerank=AsyncMock()),
        })
        cls.modules.start()
        cls.rag = importlib.import_module("app.services.rag")

    @classmethod
    def tearDownClass(cls):
        cls.modules.stop()

    async def retrieve(self, rows, ranked):
        connection = AsyncMock()
        pool = types.SimpleNamespace(acquire=lambda: connection)
        with patch.object(self.rag.documents, "search_chunks_with_doc", AsyncMock(return_value=rows)), \
             patch.object(self.rag, "embed_query", AsyncMock(return_value=[1.0, 0.0])), \
             patch.object(self.rag, "rerank", AsyncMock(return_value=ranked)):
            return await self.rag.retrieve(pool, "project", "question")

    async def test_duplicate_text_retains_distinct_sources_and_scores(self):
        rows = [
            {"content": "same", "title": "one", "document_id": 1, "chunk_id": 11, "similarity": .8},
            {"content": "same", "title": "two", "document_id": 2, "chunk_id": 22, "similarity": .7},
        ]
        hits = await self.retrieve(rows, ["same", "same"])
        self.assertEqual([h["title"] for h in hits], ["one", "two"])
        self.assertEqual([h["similarity"] for h in hits], [.8, .7])
        self.assertEqual([h["chunk_id"] for h in hits], ["11", "22"])

    async def test_missing_invalid_negative_and_roundoff_scores(self):
        values = [None, float("nan"), -0.3, 1.0000000001]
        rows = [{"content": str(i), "title": "doc", "document_id": i, "chunk_id": i, "similarity": value} for i, value in enumerate(values)]
        hits = await self.retrieve(rows, [str(i) for i in range(len(values))])
        self.assertEqual([h["similarity"] for h in hits], [None, None, -.3, 1.0])

    async def test_no_hits(self):
        self.assertEqual(await self.retrieve([], []), [])

    async def test_sql_exposes_cosine_similarity_with_project_filter(self):
        connection = AsyncMock()
        await self.rag.documents.search_chunks_with_doc(connection, "project", [1.0, 0.0], 3)
        sql, project, vector, limit = connection.fetch.call_args.args
        self.assertIn("1 - (c.embedding <=> $2::vector) AS similarity", sql)
        self.assertIn("WHERE d.project_id = $1", sql)
        self.assertEqual((project, vector, limit), ("project", "[1.0,0.0]", 3))


if __name__ == "__main__":
    unittest.main()
