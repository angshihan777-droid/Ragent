"""极简本地 MCP server：用 stdio 协议对外提供工具，演示「Agent 接入外部工具服务」。

为什么自己起一个本地 server：MCP 的价值是「工具跑在独立进程里，Agent 通过标准协议调用」，
和本地 Skill(同进程函数)形成对比。用本地 stdio server 而不是连公网 server，
是为了离线、确定性、可自测——面试时能稳定复现，不受外部服务可用性影响。

为什么用 FastMCP + stdio：FastMCP 是 mcp 官方 SDK 的高层封装，一个装饰器就注册工具；
stdio 传输让父进程(worker)用「启动子进程 + 读写标准输入输出」的方式通信，无需开端口。
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ragent-tools")


@mcp.tool()
def get_weather(city: str) -> str:
    """查询指定城市今天的天气。

    Args:
        city: 城市名，例如 "北京"
    """
    # 返回固定值：作为「确定性外部工具」的演示。真实场景这里会调天气 API，
    # 用固定值是为了让自测可断言——模型答案里出现这个值，就证明工具真被调用了。
    return f"{city}今天晴，气温 26 度，东南风 3 级。"


if __name__ == "__main__":
    # 以 stdio 传输运行：worker 会用 python -m app.agent.mcp_server 拉起本进程。
    mcp.run(transport="stdio")
