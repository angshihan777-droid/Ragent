"""20 题检索回归：在临时数据库里跑真实 embedding + rerank，低于阈值就退出 1。

这是 CI 门禁，不是通用 benchmark。语料是冻结的合成数据，不碰应用数据库。
运行方式：
    PYTHONPATH=backend python evaluation/regression.py
"""
import asyncio
import json
import os
from pathlib import Path
import statistics
import sys
import uuid

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import get_settings  # noqa: E402
from app.services import rag  # noqa: E402
from corpus import DOCS, QUERIES  # noqa: E402

MIN_HIT_AT_1 = 0.85
MIN_MRR_AT_3 = 0.90
MIN_RECALL_AT_3 = 0.95


def schema_path() -> Path:
    configured = os.getenv("SCHEMA_PATH")
    candidates = [Path(configured)] if configured else []
    candidates += [ROOT / "backend" / "app" / "schema.sql", Path("/app/app/schema.sql")]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("找不到 schema.sql；设置 SCHEMA_PATH")


def score(records: list[dict]) -> dict:
    recall, mrr, hit = [], [], []
    for row in records:
        relevant = set(row["relevant"])
        ranked = row["ranked"]
        recall.append(len(relevant.intersection(ranked)) / len(relevant))
        mrr.append(next((1 / (i + 1) for i, key in enumerate(ranked) if key in relevant), 0.0))
        hit.append(int(bool(ranked) and ranked[0] in relevant))
    return {
        "queries": len(records),
        "recall_at_3": round(statistics.mean(recall), 4),
        "mrr_at_3": round(statistics.mean(mrr), 4),
        "hit_at_1": round(statistics.mean(hit), 4),
    }


async def main() -> int:
    settings = get_settings()
    admin = await asyncpg.connect(settings.database_url)
    name = "ragent_reg_" + uuid.uuid4().hex
    parsed = settings.database_url.rsplit("/", 1)[0]
    dsn = f"{parsed}/{name}"
    pool = None
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4)
        async with pool.acquire() as conn:
            await conn.execute(schema_path().read_text(encoding="utf-8"))
            project = await conn.fetchval(
                "INSERT INTO projects(name, owner_id) VALUES('回归评测', 'eval') RETURNING id"
            )

        ids: dict[str, str] = {}
        for key, (title, content) in DOCS.items():
            doc, _ = await rag.ingest_document(pool, project, title, content)
            ids[str(doc)] = key

        records = []
        for qid, question, relevant in QUERIES:
            hits = await rag.retrieve(pool, project, question)
            ranked = list(dict.fromkeys(ids[str(h["document_id"])] for h in hits))
            records.append({"id": qid, "question": question, "relevant": relevant, "ranked": ranked})

        result = score(records)
        failures = []
        if result["hit_at_1"] < MIN_HIT_AT_1:
            failures.append(f"hit_at_1 {result['hit_at_1']} < {MIN_HIT_AT_1}")
        if result["mrr_at_3"] < MIN_MRR_AT_3:
            failures.append(f"mrr_at_3 {result['mrr_at_3']} < {MIN_MRR_AT_3}")
        if result["recall_at_3"] < MIN_RECALL_AT_3:
            failures.append(f"recall_at_3 {result['recall_at_3']} < {MIN_RECALL_AT_3}")

        output = {
            "metrics": result,
            "thresholds": {
                "hit_at_1": MIN_HIT_AT_1,
                "mrr_at_3": MIN_MRR_AT_3,
                "recall_at_3": MIN_RECALL_AT_3,
            },
            "failures": failures,
            "records": records,
        }
        out_dir = Path(__file__).with_name("results")
        out_dir.mkdir(exist_ok=True)
        (out_dir / "regression.json").write_text(
            json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps({"metrics": result, "failures": failures}, ensure_ascii=False))
        return 1 if failures else 0
    finally:
        if pool is not None:
            await pool.close()
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}"')
        await admin.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
