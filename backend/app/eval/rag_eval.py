"""企业级 RAG 检索评测：在隔离的临时项目上，对照「纯向量」与「向量+rerank」。

跑法：docker compose exec worker python -m app.eval.rag_eval

流程：建临时评测项目 → 入库易混淆语料 → 跑两套检索方案 → 打印指标对照与分类短板 → 删项目。
指标(多档位 k=1/3/5/10)：
  Recall@k —— 正确文档是否落在 top-k(命中率)。
  MRR      —— 正确文档首次出现名次的倒数均值(排得多靠前)。
  nDCG@k   —— 带位置折扣的排序质量，越接近 1 越好。
延迟：整体与「召回/精排」分阶段的 p50/p95，量化 rerank 的准确率提升 vs 时间代价。
聚焦检索质量：答案生成质量需 LLM 裁判且要配密钥，本脚本不做，保持离线可复现。
"""
import asyncio
import math
import time

import asyncpg

from app.agent.embedding import embed_query
from app.agent.rerank import rerank
from app.config import get_settings
from app.eval.dataset import CORPUS, GOLDEN_SET
from app.repositories import documents, projects
from app.services import rag

# 报告这些档位的指标；RECALL_SIZE 决定召回候选数(rerank 的输入池)。
K_LIST = [1, 3, 5, 10]
MAX_K = max(K_LIST)


def _recall_at_k(ranked: list[str], gold: str, k: int) -> float:
    """Recall@k：正确文档出现在前 k 个即记 1(单正例场景等价于 Hit@k)。"""
    return 1.0 if gold in ranked[:k] else 0.0


def _rr(ranked: list[str], gold: str) -> float:
    """Reciprocal Rank：正确文档首次出现名次的倒数，未命中记 0。"""
    for idx, title in enumerate(ranked, start=1):
        if title == gold:
            return 1.0 / idx
    return 0.0


def _ndcg_at_k(ranked: list[str], gold: str, k: int) -> float:
    """nDCG@k：单正例下 IDCG=1，命中位置 i 的 DCG=1/log2(i+1)，未命中记 0。"""
    for idx, title in enumerate(ranked[:k], start=1):
        if title == gold:
            return 1.0 / math.log2(idx + 1)
    return 0.0


def _percentile(values: list[float], pct: float) -> float:
    """取百分位延迟(如 p95)：小样本用最近秩法，足够稳定直观。"""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, math.ceil(pct / 100 * len(ordered)) - 1)
    return ordered[rank]


async def _dedup_titles(rows) -> list[str]:
    """把命中的块按原顺序去重成文档标题列表：同一文档多个块只保留最靠前的名次。"""
    seen, titles = set(), []
    for r in rows:
        t = r["title"]
        if t not in seen:
            seen.add(t)
            titles.append(t)
    return titles


async def _vector_only(conn, project_id, question: str):
    """纯向量检索：召回 MAX_K 个块 → 去重成文档排名。返回(排名, 各阶段耗时ms)。"""
    t0 = time.perf_counter()
    qe = await embed_query(question)
    t1 = time.perf_counter()
    rows = await documents.search_chunks_with_doc(conn, project_id, qe, MAX_K)
    t2 = time.perf_counter()
    titles = await _dedup_titles(rows)
    return titles, {"embed": (t1 - t0) * 1000, "recall": (t2 - t1) * 1000, "rerank": 0.0}


async def _vector_rerank(conn, project_id, question: str):
    """两阶段：召回 RECALL_SIZE 块 → rerank 精排 → 去重成文档排名。返回(排名, 各阶段耗时ms)。"""
    t0 = time.perf_counter()
    qe = await embed_query(question)
    t1 = time.perf_counter()
    rows = await documents.search_chunks_with_doc(
        conn, project_id, qe, rag.RECALL_SIZE
    )
    t2 = time.perf_counter()
    # rerank 只认原文，排完再映射回标题；保留分数顺序
    title_of = {r["content"]: r["title"] for r in rows}
    candidates = [r["content"] for r in rows]
    ranked_chunks = await rerank(question, candidates, len(candidates))
    t3 = time.perf_counter()
    ranked_rows = [{"title": title_of[c]} for c in ranked_chunks]
    titles = await _dedup_titles(ranked_rows)
    return titles, {
        "embed": (t1 - t0) * 1000,
        "recall": (t2 - t1) * 1000,
        "rerank": (t3 - t2) * 1000,
    }


async def _evaluate(conn, project_id, method):
    """对整份黄金集跑一种方法，聚合各档位指标、延迟分布与分类命中。"""
    n = len(GOLDEN_SET)
    recall = {k: 0.0 for k in K_LIST}
    ndcg = {k: 0.0 for k in K_LIST}
    rr_sum = 0.0
    total_ms, rerank_ms = [], []
    for question, gold in GOLDEN_SET:
        titles, timing = await method(conn, project_id, question)
        for k in K_LIST:
            recall[k] += _recall_at_k(titles, gold, k)
            ndcg[k] += _ndcg_at_k(titles, gold, k)
        rr_sum += _rr(titles, gold)
        total_ms.append(timing["embed"] + timing["recall"] + timing["rerank"])
        rerank_ms.append(timing["rerank"])
    return {
        "recall": {k: recall[k] / n for k in K_LIST},
        "ndcg": {k: ndcg[k] / n for k in K_LIST},
        "mrr": rr_sum / n,
        "p50": _percentile(total_ms, 50),
        "p95": _percentile(total_ms, 95),
        "rerank_p50": _percentile(rerank_ms, 50),
    }


def _print_report(v: dict, r: dict) -> None:
    """打印对照报告：指标表 + 延迟 + 分类短板。"""
    n = len(GOLDEN_SET)
    print(f"\n{'='*56}")
    print(f"RAG 检索评测报告  (语料 {len(CORPUS)} 段 / 问题 {n} 条)")
    print(f"{'='*56}\n")

    def row(label, vv, rr, fmt):
        delta = rr - vv
        sign = "+" if delta >= 0 else ""
        print(f"{label:<14}{fmt(vv):>12}{fmt(rr):>16}{sign+fmt(delta):>14}")

    pct = lambda x: f"{x:.1%}"
    num = lambda x: f"{x:.3f}"
    print(f"{'指标':<14}{'纯向量':>12}{'向量+rerank':>16}{'提升':>14}")
    print("-" * 56)
    for k in K_LIST:
        row(f"Recall@{k}", v["recall"][k], r["recall"][k], pct)
    row("MRR", v["mrr"], r["mrr"], num)
    for k in K_LIST:
        row(f"nDCG@{k}", v["ndcg"][k], r["ndcg"][k], num)

    print("\n延迟(单次检索):")
    print(f"  纯向量        p50={v['p50']:.1f}ms  p95={v['p95']:.1f}ms")
    print(f"  向量+rerank   p50={r['p50']:.1f}ms  p95={r['p95']:.1f}ms  (其中 rerank p50={r['rerank_p50']:.1f}ms)")

    print()


async def main() -> None:
    settings = get_settings()
    pool = await asyncpg.create_pool(dsn=settings.database_url)
    project_id = None
    try:
        # 1) 建隔离的临时评测项目，避免污染 demo 数据
        async with pool.acquire() as conn:
            proj = await projects.insert_project(
                conn, "__eval__", "RAG 评测临时项目，跑完自动删除"
            )
            project_id = proj["id"]
        # 2) 入库易混淆语料(走正规切块+向量化流程)
        print(f"入库评测语料 {len(CORPUS)} 段...", flush=True)
        for title, content in CORPUS:
            await rag.ingest_document(pool, project_id, title, content)
        # 3) 两套方案各跑一遍
        print("评测中(首次会加载 rerank 模型，稍候)...", flush=True)
        async with pool.acquire() as conn:
            v = await _evaluate(conn, project_id, _vector_only)
            r = await _evaluate(conn, project_id, _vector_rerank)
        _print_report(v, r)
    finally:
        # 4) 删临时项目(chunks/documents 靠外键级联清除)，评测不留痕
        if project_id is not None:
            async with pool.acquire() as conn:
                await conn.execute("DELETE FROM projects WHERE id = $1", project_id)
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
