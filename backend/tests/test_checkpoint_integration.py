"""断点续传集成测试：需要真实 PostgreSQL，默认跳过。

CI 的 retrieval-eval job 会设置 TEST_POSTGRES_URL 后运行。
用一个小图模拟「节点 a 完成、节点 b 执行中被杀」，验证恢复时 a 不重跑、b 继续跑完。
"""
import asyncio
import os
import uuid
from typing import TypedDict

import pytest

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_POSTGRES_URL"),
    reason="需要 TEST_POSTGRES_URL 指向可用的 PostgreSQL",
)


class State(TypedDict, total=False):
    x: int
    y: int


def test_checkpoint_resumes_without_rerunning_completed_node():
    dsn = os.environ["TEST_POSTGRES_URL"]
    thread = "probe-" + uuid.uuid4().hex
    counts = {"a": 0, "b": 0}

    async def scenario():
        async def node_a(_state):
            counts["a"] += 1
            await asyncio.sleep(0.05)
            return {"x": 1}

        async def node_b(_state):
            counts["b"] += 1
            await asyncio.sleep(2)
            return {"y": 2}

        builder = StateGraph(State)
        builder.add_node("a", node_a)
        builder.add_node("b", node_b)
        builder.add_edge(START, "a")
        builder.add_edge("a", "b")
        builder.add_edge("b", END)

        async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
            await saver.setup()
            graph = builder.compile(checkpointer=saver)
            cfg = {"configurable": {"thread_id": thread}}

            async def run():
                async for _ in graph.astream({"x": 0, "y": 0}, config=cfg):
                    pass

            task = asyncio.create_task(run())
            await asyncio.sleep(0.4)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

            before = await graph.aget_state(cfg)
            assert before.next == ("b",)

            async for _ in graph.astream(None, config=cfg):
                pass
            after = await graph.aget_state(cfg)
            assert after.values.get("y") == 2
            assert counts["a"] == 1
            await saver.adelete_thread(thread)

    asyncio.run(scenario())
