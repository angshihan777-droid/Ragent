"""重排评测：在 T2Reranking 每题自带的候选池上，对照「纯向量排序」与「向量+rerank」。

跑法：docker compose exec worker python -m app.eval.rag_eval

数据来自公开中文重排基准 T2Reranking(见 build_dataset.py)：每个 query 自带一批候选
段落——正例(能回答)与人工标注的强负例(看着相关其实答非所问)。评测即在这批候选里
比较两种排序：
  纯向量    —— 用 embedding 算 query 与各候选的余弦相似度排序(bi-encoder，快而粗)。
  向量+rerank —— 再用 cross-encoder 对候选逐对精排(慢而准)。
这正是本项目两阶段检索里「重排」这一步真正要干的事，强负例最能体现 rerank 的价值。

多正例指标(一个 query 可能有多个正例)：
  MRR    —— 第一个正例出现名次的倒数均值(第一条对不对)。
  MAP    —— 平均精度均值，综合衡量正例整体是否都排在前面(重排标准指标)。
  nDCG@k —— 带位置折扣的排序质量，IDCG 按真实正例数计算(多正例下上界不再恒为 1)。
  Recall@k —— top-k 里命中的正例数 / 该题正例总数。
延迟：整体与 rerank 阶段的 p50/p95，量化 rerank 的准确率提升 vs 时间代价。
纯离线可复现，不需 LLM 密钥。
"""
import asyncio
import math
import time

from app.agent.embedding import embed_texts
from app.agent.rerank import rerank
from app.eval.dataset import EVAL_SET

K_LIST = [1, 3, 5, 10]


def _cosine(a: list[float], b: list[float]) -> float:
    """余弦相似度：向量未必已归一化，这里显式除以模长。"""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _rr(ranked: list[str], golds: set[str]) -> float:
    """Reciprocal Rank：第一个正例出现名次的倒数，未命中记 0。"""
    for idx, c in enumerate(ranked, start=1):
        if c in golds:
            return 1.0 / idx
    return 0.0


def _ap(ranked: list[str], golds: set[str]) -> float:
    """Average Precision：每命中一个正例就累计当前精度，除以正例总数。"""
    if not golds:
        return 0.0
    hit, precision_sum = 0, 0.0
    for idx, c in enumerate(ranked, start=1):
        if c in golds:
            hit += 1
            precision_sum += hit / idx
    return precision_sum / len(golds)


def _ndcg_at_k(ranked: list[str], golds: set[str], k: int) -> float:
    """nDCG@k：二元相关性，命中位置 i 贡献 1/log2(i+1)；IDCG 按 min(正例数,k) 个理想命中。"""
    dcg = 0.0
    for idx, c in enumerate(ranked[:k], start=1):
        if c in golds:
            dcg += 1.0 / math.log2(idx + 1)
    ideal = min(len(golds), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal + 1))
    return dcg / idcg if idcg else 0.0


def _recall_at_k(ranked: list[str], golds: set[str], k: int) -> float:
    """Recall@k：top-k 命中的正例数 / 正例总数。"""
    if not golds:
        return 0.0
    return sum(1 for c in ranked[:k] if c in golds) / len(golds)


def _percentile(values: list[float], pct: float) -> float:
    """取百分位延迟(如 p95)：小样本用最近秩法，足够稳定直观。"""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, math.ceil(pct / 100 * len(ordered)) - 1)
    return ordered[rank]


async def _vector_only(query: str, candidates: list[str]) -> tuple[list[str], float]:
    """纯向量排序：一次性编码 query 与全部候选，按余弦相似度降序排列。

    时序：把 [query] + candidates 拼成一批送 embed_texts，只调一次模型省开销。
    返回 (排好序的候选原文, 本题总耗时毫秒)。
    """
    t0 = time.perf_counter()
    vecs = await embed_texts([query] + candidates)
    q_vec, cand_vecs = vecs[0], vecs[1:]
    scored = sorted(
        zip(candidates, cand_vecs),
        key=lambda x: _cosine(q_vec, x[1]),
        reverse=True,
    )
    ranked = [c for c, _ in scored]
    return ranked, (time.perf_counter() - t0) * 1000


async def _vector_rerank(query: str, candidates: list[str]) -> tuple[list[str], float, float]:
    """向量+rerank：A 方案候选池小，直接用 cross-encoder 全量精排。

    时序：rerank 内部对每个「query+候选」逐对打分再降序，返回排好序的原文。
    返回 (排好序的候选原文, 本题总耗时毫秒, rerank 阶段耗时毫秒)。
    """
    t0 = time.perf_counter()
    ranked = await rerank(query, candidates, len(candidates))
    total_ms = (time.perf_counter() - t0) * 1000
    # A 方案不含向量召回，总耗时即 rerank 耗时
    return ranked, total_ms, total_ms


async def _evaluate(method) -> dict:
    """跑一种方法过全部题目，累加多正例指标与延迟。

    method 是 _vector_only 或 _vector_rerank；后者多返回一个 rerank 耗时。
    """
    recall = {k: 0.0 for k in K_LIST}
    ndcg = {k: 0.0 for k in K_LIST}
    rr_sum, ap_sum = 0.0, 0.0
    total_ms_list: list[float] = []
    rerank_ms_list: list[float] = []
    is_rerank = method is _vector_rerank

    for item in EVAL_SET:
        query = item["query"]
        candidates = item["candidates"]
        golds = set(item["golds"])
        if is_rerank:
            ranked, total_ms, rerank_ms = await method(query, candidates)
            rerank_ms_list.append(rerank_ms)
        else:
            ranked, total_ms = await method(query, candidates)
        total_ms_list.append(total_ms)
        for k in K_LIST:
            recall[k] += _recall_at_k(ranked, golds, k)
            ndcg[k] += _ndcg_at_k(ranked, golds, k)
        rr_sum += _rr(ranked, golds)
        ap_sum += _ap(ranked, golds)

    n = len(EVAL_SET)
    result = {
        "recall": {k: recall[k] / n for k in K_LIST},
        "ndcg": {k: ndcg[k] / n for k in K_LIST},
        "mrr": rr_sum / n,
        "map": ap_sum / n,
        "p50": _percentile(total_ms_list, 50),
        "p95": _percentile(total_ms_list, 95),
    }
    if is_rerank:
        result["rerank_p50"] = _percentile(rerank_ms_list, 50)
    return result


def _pct(x: float) -> str:
    """把 0~1 的比率格式化成百分比字符串。"""
    return f"{x * 100:.1f}%"


def _gain(before: float, after: float) -> str:
    """提升量：rerank 后相对纯向量的绝对百分点变化。"""
    return f"+{(after - before) * 100:.1f}pt"


def _print_report(v: dict, r: dict) -> None:
    """打印对照报告：纯向量 vs 向量+rerank，逐指标给提升。"""
    print()
    print(f"重排评测报告 (T2Reranking / 问题 {len(EVAL_SET)} 条)")
    print("=" * 60)
    print(f"{'指标':<12}{'纯向量':>12}{'向量+rerank':>14}{'提升':>12}")
    print("-" * 60)
    for k in K_LIST:
        print(f"{'Recall@' + str(k):<12}{_pct(v['recall'][k]):>12}"
              f"{_pct(r['recall'][k]):>14}{_gain(v['recall'][k], r['recall'][k]):>12}")
    print(f"{'MRR':<12}{v['mrr']:>12.3f}{r['mrr']:>14.3f}"
          f"{'+' + format(r['mrr'] - v['mrr'], '.3f'):>12}")
    print(f"{'MAP':<12}{v['map']:>12.3f}{r['map']:>14.3f}"
          f"{'+' + format(r['map'] - v['map'], '.3f'):>12}")
    for k in K_LIST:
        print(f"{'nDCG@' + str(k):<12}{v['ndcg'][k]:>12.3f}"
              f"{r['ndcg'][k]:>14.3f}{'+' + format(r['ndcg'][k] - v['ndcg'][k], '.3f'):>12}")
    print("-" * 60)
    print("延迟(每题)")
    print(f"  纯向量      p50 {v['p50']:.1f}ms   p95 {v['p95']:.1f}ms")
    print(f"  向量+rerank p50 {r['p50']:.1f}ms   p95 {r['p95']:.1f}ms"
          f"  (rerank p50 {r['rerank_p50']:.1f}ms)")
    print("=" * 60)


async def main() -> None:
    """纯内存离线评测：不建项目、不入库、不连 PG，只跑 embedding 与 rerank。"""
    print(f"加载评测集：{len(EVAL_SET)} 题")
    print("跑「纯向量」...")
    v = await _evaluate(_vector_only)
    print("跑「向量+rerank」(首次会加载 reranker 模型)...")
    r = await _evaluate(_vector_rerank)
    _print_report(v, r)


if __name__ == "__main__":
    asyncio.run(main())
