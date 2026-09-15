"""内置 demo 数据：首次启动(库里没有任何项目时)播种一个演示项目。

为什么要 demo：让验收者一进来就有「项目 + 多 Agent + 资料」可玩，
直接对照「知识库助手(检索)」和「通用助手(不检索)」的 RAG 效果。
密钥绝不内置：只种项目/Agent/资料，模型密钥仍为空，由用户在配置页自行填写。
幂等：只在库里一个项目都没有时播种，重启不会重复插入。
"""
import asyncpg

from app.repositories import agents, projects
from app.services import rag

# demo 资料：几篇「公司制度」假资料，用于演示 RAG 检索命中，也方便演示「资料删除」。
# 多放几篇：删掉一篇后还剩别的，检索对照不至于断档。
_DEMO_DOCS = [
    (
        "示例资料：请假制度",
        "公司请假制度规定：员工请年假需提前三个工作日在系统提交申请，"
        "并由直属主管审批通过后生效。病假需在当天上午十点前通知主管，"
        "并在三日内补交医院证明。事假一年累计不得超过十个工作日。"
        "调休需在加班后一个月内使用完毕，逾期作废。",
    ),
    (
        "示例资料：报销制度",
        "公司报销制度规定：员工报销需在费用发生后十五个工作日内提交发票，"
        "超过三十天的发票财务不予受理。单笔金额超过五千元需分管副总审批。"
        "差旅费报销须附行程单与住宿发票，交通费凭票实报。",
    ),
    (
        "示例资料：考勤制度",
        "公司考勤制度规定：工作日上班时间为上午九点至下午六点，弹性打卡区间为八点半到九点半。"
        "迟到超过三十分钟按半天事假计。每月累计迟到三次以上，当月绩效扣减。"
        "远程办公需提前一天向主管报备。",
    ),
]


async def seed_demo_if_empty(pool: asyncpg.Pool) -> None:
    """库里没有任何项目时，播种一个 demo 项目 + 3 个 Agent + 若干篇资料。"""
    async with pool.acquire() as conn:
        existing = await projects.list_projects(conn)
        if existing:
            return  # 已有项目，说明不是首次启动，不重复播种
        proj = await projects.insert_project(
            conn, "示例项目", "内置演示：对照知识库助手与通用助手的 RAG 效果"
        )
        project_id = proj["id"]
        # 默认 Agent 放第一个：知识库问答助手（检索、只据资料答）
        await agents.insert_agent(
            conn, project_id, "知识库问答助手",
            "严谨的资料检索员",
            "你是严谨的知识库助手。只根据检索到的参考资料回答，"
            "资料里没有就直说「资料里没有相关内容」，并在答案末尾标注依据的资料。",
            True,
        )
        await agents.insert_agent(
            conn, project_id, "通用聊天助手",
            "自由发挥的通用助手",
            "你是通用聊天助手，可以自由发挥回答任何问题，无需依赖检索资料。",
            False,
        )
        await agents.insert_agent(
            conn, project_id, "面试八股讲解官",
            "结构化讲解的面试导师",
            "你是面试讲解官。按「是什么 / 为什么 / 怎么做」三段式结构化讲解，"
            "结合检索到的资料把概念讲透。",
            True,
        )
    # 资料入库走正规 RAG 流程（切块+向量化+落库），保证 demo 检索真的能命中
    for title, content in _DEMO_DOCS:
        await rag.ingest_document(pool, project_id, title, content)
