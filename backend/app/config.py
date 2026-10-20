"""应用配置：全部从环境变量读取，避免把地址、密码写死在代码里。"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# 队列分组键 (user_id, agent_id, thread_id) 里的 agent 维度：产品只有一个知识库 Agent，
# 用户不选 Agent，故写成常量。user 维度已在 P1 换成 Cookie 身份，不再是常量
# （原 FIXED_USER_ID = "u1" 已删除：它让所有人的请求落进同一个 FIFO 分组，
# 两个浏览器并发提问会互相排队，不只是数据可见性的问题）。
KNOWLEDGE_AGENT_ID = "knowledge-base"

# 存量数据的归属身份：加 owner_id 之前建的项目全部归到它名下，
# 之后通过「切换身份」入口认领回来。和 schema.sql 里的回填值必须一致。
LEGACY_OWNER_ID = "legacy-u1"

# ---- 身份 Cookie ----
# 身份就是这个 Cookie 里的一个 uuid4，没有密码、没有找回：这是「隔离」不是「鉴权」。
# 为什么走 Cookie 而不是 header + localStorage：
#   1. httpOnly 是 header 方案拿不到的 —— 放 localStorage 任何 XSS 都能直接读走凭证，
#      而本项目凭证泄露即等于全部数据泄露；
#   2. header 要求每个调用点都记得带（含 uploadDocument 的裸 fetch、流式 fetch），漏一处
#      就凭空多出一个匿名身份，Cookie 由浏览器统一携带，前端调用点不用逐个改；
#   3. 不进 URL，也就不进日志、浏览器历史与 Referer。
OWNER_COOKIE_NAME = "ragent_oid"
# 400 天是 Chrome 对 Max-Age 的上限，设更大也会被截到 400 天，索性就写真实生效值。
OWNER_COOKIE_MAX_AGE = 400 * 24 * 3600

# ---- 触发式增量摘要的两个阈值：管的是两件不同的事，别当成大小两条触发线 ----
#
# 触发阈值：决定「要不要做摘要」。未被摘要覆盖的历史累计超过任一条即触发一次增量摘要。
# 两条并列是因为两种会话形态都要防住：长文贴一次就爆字符，碎聊则是轮次多而字符少。
SUMMARY_TRIGGER_CHARS = 8000
SUMMARY_TRIGGER_TURNS = 10
#
# 保留阈值：决定「近窗留多大」。最近这几轮永不摘要、永远原样进模型。
# 它不是摘要的触发下限，而是精度缓冲区：追问（「那第二点呢」）依赖近期原文的指代关系，
# 一旦被压缩成摘要，指代就找不回来了。
KEEP_RECENT_TURNS = 4

# 连续失败到这个次数就熔断该会话的摘要，只走原文截断，
# 不每轮再去撞一个必然失败的模型调用（白烧一次往返延迟）。
SUMMARY_MAX_CONSECUTIVE_FAILURES = 3


class Settings(BaseSettings):
    # pydantic v2 写法：用 model_config 代替旧的 class Config
    model_config = SettingsConfigDict(env_file=".env")

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
    # 请求超时（秒）。OpenAI 兼容服务在繁忙时会持续发空行保活，读超时必须放宽到覆盖
    # 排队时间，否则真正的响应还没到就先超时了。DeepSeek 实测排队可超过 2 分钟。
    llm_request_timeout: int = 180
    # 推理强度（low / high / max）。留空表示不传这个字段，交给服务端默认。
    # 为什么默认 low：DeepSeek V4 系列是推理模型，服务端默认 high —— 实测同一句「你好」
    # 默认档要 41 秒，low 档 0.7 秒；一次问答要调 2~3 次模型，默认档累积就是分钟级等待。
    # 换成别的服务商时把它设为空串即可回到「不传该字段」的行为。
    llm_reasoning_effort: str = "low"

    # RAG embedding：走本地 fastembed(ONNX)，不依赖外部 API。
    # 只暴露模型名一个配置项，本地模型无需 base_url/key。
    embedding_model: str = "BAAI/bge-small-zh-v1.5"

    # RAG rerank：两阶段检索的精排模型，同样走本地 fastembed(cross-encoder)。
    rerank_model: str = "BAAI/bge-reranker-base"

    # 单身份每分钟允许的提问次数。进程内滑动窗口；多副本部署需换成 Redis。
    rate_limit_per_minute: int = 10

    # 成本估算单价（元 / 1K tokens）。默认 0 表示不估算，前端显示「未配置」，
    # 避免把某家服务商的价格硬编码进代码。
    cost_input_per_1k: float = 0.0
    cost_output_per_1k: float = 0.0


@lru_cache
def get_settings() -> Settings:
    """缓存单例，避免每次请求重复解析环境变量。"""
    return Settings()
