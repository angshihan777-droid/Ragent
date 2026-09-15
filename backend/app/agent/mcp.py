"""M9 MCP：从外部 MCP server 拉取工具，和本地 Skill 一起交给模型。

为什么要有 MCP：Skill 是「同进程的本地函数」，MCP 是「独立进程/服务暴露的工具」。
真实项目里天气、数据库、搜索等能力常由别的团队/服务提供，MCP 是接它们的标准协议——
Agent 不用关心工具怎么实现，只按统一协议发现和调用。这就是接入生态的意义。

为什么用 MultiServerMCPClient：langchain 官方适配器，把 MCP 工具直接转成 LangChain 工具，
和本地 Skill 用同一套 bind_tools/ToolNode 机制，图不用为「工具来源」分叉。
"""
import sys

from langchain_mcp_adapters.client import MultiServerMCPClient

# server 配置：用 stdio 传输拉起本地 mcp_server 子进程。
# 只配一个 server、一个工具，够演示即可——多 server 管理是重型平台的事，当前无需求。
_SERVERS = {
    "ragent-tools": {
        # 用当前 Python 解释器跑，保证子进程和 worker 用同一套依赖/环境。
        "command": sys.executable,
        "args": ["-m", "app.agent.mcp_server"],
        "transport": "stdio",
    },
}

# 进程级缓存：MCP 工具要异步拉取(还要拉起子进程握手)，拉一次缓存复用，
# 避免每个请求都重连重握手。worker 是长驻进程，缓存生命周期跟随进程。
_MCP_TOOLS: list = []


async def preload_mcp_tools() -> None:
    """首次用图前拉取并缓存 MCP 工具。失败则记为空，不阻断本地 Skill 可用。

    失败降级说明：MCP 是可选增强能力，server 拉不起来时 Agent 仍能用本地 Skill 作答，
    不能因为一个外部工具源不可用就让整条链路挂掉。降级是结构化的(清空缓存)，不是假装成功。
    """
    global _MCP_TOOLS
    try:
        client = MultiServerMCPClient(_SERVERS)
        _MCP_TOOLS = await client.get_tools()
    except Exception as e:
        # 打到 worker 日志，便于排查；同时保持工具清单为空，链路继续。
        print(f"[mcp] 加载 MCP 工具失败，降级为仅本地 Skill: {e}", flush=True)
        _MCP_TOOLS = []


async def get_mcp_tools() -> list:
    """给 agent 节点用：返回已缓存的 MCP 工具。"""
    return _MCP_TOOLS


def get_cached_mcp_tools() -> list:
    """给图构建(ToolNode)用：同步取已缓存的 MCP 工具。"""
    return _MCP_TOOLS
