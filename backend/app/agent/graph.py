"""LangGraph 主图：先检索知识库(RAG)，再让大模型带着「工具(Skill/MCP)」作答。

为什么用 LangGraph：RAG、Skill、MCP 都是挂在图上的节点/工具，
把「模型↔工具」的循环搭成图后，加能力只是往工具清单里加一项，不用改 worker。

为什么是「循环」而不是一条直线：带工具的对话是多轮的——模型可能先要求调工具、
拿到结果后再作答，甚至连续调多次。用 agent→tools→agent 的条件循环表达这个过程。
"""
from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent import mcp
from app.agent.skills import LOCAL_SKILLS
from app.services import llm_config as llm_config_service
from app.services import rag


class AgentState(TypedDict):
    """图在节点间传递的状态。

    messages 用 add_messages 归并：工具调用是「往对话里追加消息」的过程，
    这个 reducer 保证每次节点返回的新消息是追加而不是覆盖历史。
    sources 是本次检索命中的资料原文，单独存一份用于对外展示「这次确实检索了什么」，
    默认 reducer（覆盖）即可，检索只发生在入口一次。
    """
    messages: Annotated[list[AnyMessage], add_messages]
    sources: list[str]


async def _build_llm(pool) -> ChatOpenAI:
    """构造 OpenAI 兼容客户端：配置从数据库读(生效配置)，而不是进程启动时的环境变量。

    为什么每次从库读：配置页改了地址/密钥/模型要立刻对 worker 生效，
    而 api 与 worker 是两个进程、不共享内存，数据库是唯一共享真相。
    """
    cfg = await llm_config_service.get_effective_config(pool)
    return ChatOpenAI(
        base_url=cfg["base_url"],
        api_key=cfg["api_key"],
        model=cfg["model"],
        temperature=0,
    )


async def _retrieve_node(state: AgentState, config: RunnableConfig) -> AgentState:
    """检索节点：按会话 Agent 的配置决定是否检索，命中则把资料塞成 SystemMessage。

    pool/project_id/use_rag 不是图状态、是运行期依赖，通过 config.configurable 注入——
    这样图结构保持纯粹，worker/测试各自传自己的连接池与会话上下文。

    use_rag=False（如「通用助手」）直接跳过检索，与「知识库助手」肉眼对照 RAG 效果；
    检索范围按 project_id 圈定，只在本项目的资料里找，不串到别的项目。
    """
    cfg = config["configurable"]
    # 先放 Agent 人设(system_prompt)，再放检索资料，最后才是用户问题，顺序影响模型理解
    system_msgs = []
    if cfg["system_prompt"]:
        system_msgs.append(SystemMessage(content=cfg["system_prompt"]))
    # use_rag=False（如「通用助手」）跳过检索；检索按 project_id 圈定本项目资料
    sources: list[str] = []
    if cfg["use_rag"]:
        pool = cfg["pool"]
        # 取用户问题原文（此时 messages 里只有一条 HumanMessage）
        question = state["messages"][-1].content
        chunks = await rag.retrieve(pool, cfg["project_id"], question)
        if chunks:
            sources = chunks  # 命中的原文单独留一份，供对外展示「检索到了什么」
            context = "\n\n".join(chunks)
            system_msgs.append(SystemMessage(
                content=f"参考资料:\n{context}\n\n请优先根据上面的参考资料回答用户问题。"
            ))
    if not system_msgs:
        return {"sources": sources}
    # 把系统消息插到最前面：模型按「人设→资料→用户问题」的顺序读取
    return {"messages": system_msgs + state["messages"], "sources": sources}


async def _agent_node(state: AgentState, config: RunnableConfig) -> AgentState:
    """智能体节点：模型带着工具清单作答，可能直接回答、也可能要求调用工具。

    工具清单 = 本地 Skill + MCP 远程工具。MCP 工具要异步从 server 拉取，
    故在运行期取（带缓存），而不是图构建时——图是同步编译的。
    """
    pool = config["configurable"]["pool"]
    tools = LOCAL_SKILLS + await mcp.get_mcp_tools()
    llm = (await _build_llm(pool)).bind_tools(tools)
    # 用 ainvoke(异步)避免阻塞 worker 事件循环(心跳/reaper 同循环)。
    resp = await llm.ainvoke(state["messages"])
    return {"messages": [resp]}


def _build_tool_node() -> ToolNode:
    """构建执行工具的节点：把「模型要调的工具」真正跑起来，结果回填进对话。

    这里要提供完整工具清单(含 MCP)，ToolNode 按名字派发。MCP 工具在进程启动后
    首次用图时已被 preload_mcp_tools 拉好并缓存，故此处同步取缓存即可。
    """
    return ToolNode(LOCAL_SKILLS + mcp.get_cached_mcp_tools())


def _build_graph():
    """编译图：START→retrieve→agent，agent 视情况走 tools 再回 agent，或结束。

    tools_condition：模型这轮若发起了 tool_calls 就去 tools 节点执行，
    否则说明已给出最终答案，直接 END。tools 执行完回到 agent 让模型据结果续答。
    """
    g = StateGraph(AgentState)
    g.add_node("retrieve", _retrieve_node)
    g.add_node("agent", _agent_node)
    g.add_node("tools", _build_tool_node())
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "agent")
    g.add_conditional_edges("agent", tools_condition)
    g.add_edge("tools", "agent")
    return g.compile()


# 图在首次用到时才编译：MCP 工具需先异步拉取并缓存，才能正确构建 tools 节点。
_GRAPH = None


async def stream_agent(question: str, pool, project_id, use_rag: bool, system_prompt: str):
    """对外入口：给问题和连接池，逐 token 产出模型回复片段。worker 调这个。

    为什么改成流式：整段答案要等模型写完才回，用户等得久；
    改用 astream_events 监听模型的 token 事件，边生成边吐，前端可实时追加。
    只产出有正文的增量：带工具调用的那一轮 content 为空，会被自然过滤，
    真正的最终答案才有文本 token。累加成完整回复由调用方(worker)负责落库。
    首次调用时先把 MCP 工具拉好并缓存，再编译图；之后复用同一张图。
    pool 经 configurable 透传给检索节点，图本身不持有连接。

    产出用「带类型标签的元组」而不是裸字符串：("sources", [...]) 是本次检索命中的
    资料原文（对外展示「这次确实检索了什么」），("token", str) 是回复增量。
    worker 靠标签区分两类事件转发，不用脆弱的字符串解析。
    """
    global _GRAPH
    if _GRAPH is None:
        await mcp.preload_mcp_tools()
        _GRAPH = _build_graph()
    async for event in _GRAPH.astream_events(
        {"messages": [HumanMessage(content=question)]},
        # 经 configurable 注入运行期上下文：连接池 + 本会话 Agent 的检索/人设配置
        config={"configurable": {
            "pool": pool,
            "project_id": project_id,
            "use_rag": use_rag,
            "system_prompt": system_prompt,
        }},
        version="v2",
    ):
        kind = event["event"]
        # 检索节点结束：把命中资料先于正文吐出，前端可在答案上方展示「检索到了什么」
        if kind == "on_chain_end" and event.get("name") == "retrieve":
            hits = event["data"]["output"].get("sources") or []
            if hits:
                yield ("sources", hits)
            continue
        # on_chat_model_stream 是模型吐字事件；chunk.content 有内容才是可展示的回复增量
        if kind == "on_chat_model_stream":
            token = event["data"]["chunk"].content
            if token:
                yield ("token", token)
