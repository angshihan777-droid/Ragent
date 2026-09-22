"""本地 embedding 客户端：把文本转成向量，供 RAG 存储与检索用。

为什么本地跑：kuaipao/DeepSeek 都不提供 embedding 接口，本地 fastembed(ONNX)
离线、免费、稳定，还省掉外部 API 的网络抖动与配额限制。
"""
import asyncio

from fastembed import TextEmbedding

from app.config import get_settings

# 进程级懒加载单例：模型加载慢(要读 ONNX 权重)，只在首次用到时加载一次并复用。
_MODEL: TextEmbedding | None = None


def _get_model() -> TextEmbedding:
    """首次调用时加载模型，之后复用同一实例。"""
    global _MODEL
    if _MODEL is None:
        _MODEL = TextEmbedding(model_name=get_settings().embedding_model)
    return _MODEL


def _embed_sync(texts: list[str]) -> list[list[float]]:
    """同步批量编码：fastembed 返回生成器，这里收成列表。"""
    return [vec.tolist() for vec in _get_model().embed(texts)]


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """把多段文本转成向量列表。

    并发关键：编码是 CPU 密集的同步调用，丢到线程池执行，
    不阻塞 worker/api 的事件循环(心跳、SSE 都在同一循环上跑)。
    """
    return await asyncio.to_thread(_embed_sync, texts)


async def embed_query(text: str) -> list[float]:
    """检索用：把单条查询转成一条向量。"""
    vecs = await embed_texts([text])
    return vecs[0]


def _prepare_chunks_sync(blocks, title):
    from tokenizers import Tokenizer
    from app.services.chunking import split_blocks, TARGET_TOKENS
    # 克隆实际 embedding tokenizer，禁用截断；不改变共享推理模型的 tokenizer。
    original = _get_model().model.tokenizer
    tokenizer = Tokenizer.from_str(original.to_str())
    limit = (original.truncation or {}).get("max_length", 512)
    tokenizer.no_truncation()
    tokenizer.no_padding()
    return split_blocks(blocks, tokenizer, title, min(TARGET_TOKENS, limit - 8))


async def prepare_chunks(blocks, title):
    return await asyncio.to_thread(_prepare_chunks_sync, blocks, title)
