"""应用配置：全部从环境变量读取，避免把地址、密码写死在代码里。"""
from functools import lru_cache

from pydantic_settings import BaseSettings

# 精简版：单用户、无登录，故 user 写成常量。
# 固定执行身份保留队列契约；产品没有 Agent 配置或选择。
FIXED_USER_ID = "u1"
KNOWLEDGE_AGENT_ID = "knowledge-base"


class Settings(BaseSettings):
    # PostgreSQL 连接串，compose 内通过服务名 postgres 互联
    database_url: str = "postgresql://ragent:ragent@postgres:5432/ragent"
    # Redis 连接串：运行队列与请求事件通道
    redis_url: str = "redis://redis:6379/0"

    # LLM 接入：只保留一套 OpenAI 兼容配置。DeepSeek 本身就是 OpenAI 兼容接口，
    # 自定义服务/DeepSeek 都靠 base_url 区分，不为每家各写一套客户端。
    # 默认全空、不内置任何服务地址或密钥：克隆后由用户在「模型配置」页自行填写。
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    # RAG embedding：走本地 fastembed(ONNX)，不依赖外部 API。
    # 只暴露模型名一个配置项，本地模型无需 base_url/key。
    embedding_model: str = "BAAI/bge-small-zh-v1.5"

    # RAG rerank：两阶段检索的精排模型，同样走本地 fastembed(cross-encoder)。
    rerank_model: str = "BAAI/bge-reranker-base"

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    """缓存单例，避免每次请求重复解析环境变量。"""
    return Settings()
