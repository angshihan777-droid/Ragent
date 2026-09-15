"""本地 rerank 客户端：对召回的候选块做精排，供 RAG 两阶段检索用。

为什么要 rerank：向量检索(bi-encoder)把问题和文档分别编码再算距离，快但粗，
容易把"字面像但答非所问"的块排前面。rerank 用 cross-encoder 把「问题+块」
拼在一起送进模型打分，精准得多——这就是业界标准的「先召回、后精排」两阶段检索。

为什么仍用 fastembed：embedding 已经在用它，reranker 只是同库的另一个类(TextCrossEncoder)，
一样本地 ONNX、离线免费，不引新依赖。
"""
import asyncio

from fastembed.rerank.cross_encoder import TextCrossEncoder

from app.config import get_settings

# 进程级懒加载单例：模型加载慢(读 ONNX 权重)，首次用到时加载一次并复用。
_MODEL: TextCrossEncoder | None = None


def _get_model() -> TextCrossEncoder:
    """首次调用时加载 reranker 模型，之后复用同一实例。"""
    global _MODEL
    if _MODEL is None:
        _MODEL = TextCrossEncoder(model_name=get_settings().rerank_model)
    return _MODEL


def _rerank_sync(query: str, docs: list[str]) -> list[float]:
    """同步为每个候选块打分：分数越高越相关。"""
    return list(_get_model().rerank(query, docs))


async def rerank(query: str, docs: list[str], top_k: int) -> list[str]:
    """对候选块精排，返回分数最高的 top_k 块原文。

    并发关键：打分是 CPU 密集的同步调用，丢到线程池执行，
    不阻塞事件循环(心跳、SSE 都在同一循环上跑)，与 embedding 一致。
    候选为空直接返回空；候选不足 top_k 就有多少返回多少。
    """
    if not docs:
        return []
    scores = await asyncio.to_thread(_rerank_sync, query, docs)
    # 按分数从高到低排序，取前 top_k 的原文
    ranked = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
    return [doc for doc, _ in ranked[:top_k]]
