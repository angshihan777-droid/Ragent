"""端到端冒烟：在一个全新的身份上跑通「建项目 → 建会话 → 提问 → 落回答」整条链路。

为什么单独放一个脚本而不是塞进 pytest：tests/ 那套是纯逻辑单测，不连库、不连模型；
而这条链路的价值恰恰在于「真的连了才可能发现」——路由契约、队列投递、worker 认领、
模型调用、结果落库，任何一环断掉都只有真跑一遍才看得出来。两者目标不同，所以分开。

用法（在 api 容器里跑，脚本需要能读库拿到一份可用的模型密钥）：
    docker compose cp backend/scripts/e2e_smoke.py api:/app/e2e_smoke.py
    docker compose exec -T api python /app/e2e_smoke.py

（必须放在 /app 下而不是 /tmp：脚本要 import app 包，而 python 只把「脚本所在目录」
加进 sys.path，放 /tmp 会直接 ModuleNotFoundError。）

可用环境变量覆盖：E2E_SOURCE_OWNER（从哪个身份借配置）、E2E_QUESTION、E2E_TIMEOUT。

退出码：0 = 整条链路通过；非 0 = 失败，并在 stdout 说明卡在哪一步。
"""
import asyncio
import os
import sys
import time
import uuid

import asyncpg
import httpx

from app.config import get_settings

BASE = os.environ.get("E2E_BASE", "http://localhost:8000")
# 从哪个身份「借」一份可用的模型配置（地址 + 密钥）。默认取库里第一个配好密钥的身份，
# 这样可以不给脚本传密钥，也不会把密钥写进命令行历史。
SOURCE_OWNER = os.environ.get("E2E_SOURCE_OWNER", "")
DEADLINE_SECONDS = float(os.environ.get("E2E_TIMEOUT", "300"))
QUESTION = os.environ.get("E2E_QUESTION", "你好")


def log(step: str, msg: str = "") -> None:
    print(f"[{step}] {msg}".rstrip(), flush=True)


def fail(step: str, msg: str) -> None:
    print(f"[FAIL:{step}] {msg}", file=sys.stderr, flush=True)
    raise SystemExit(1)


def check(step: str, condition: bool, msg: str) -> None:
    if not condition:
        fail(step, msg)
    log(step, "ok  " + msg)


async def load_source_config() -> dict:
    """从库里取一份可用的模型配置，供本次测试的身份复制使用。"""
    settings = get_settings()
    conn = await asyncpg.connect(dsn=settings.database_url)
    try:
        if SOURCE_OWNER:
            row = await conn.fetchrow(
                "SELECT base_url, api_key, model, reasoning_effort FROM llm_config"
                " WHERE owner_id = $1",
                SOURCE_OWNER,
            )
        else:
            # 挑第一个真正配了密钥的身份：没密钥的行是刚播种还没填的，拿它测必然失败
            row = await conn.fetchrow(
                "SELECT base_url, api_key, model, reasoning_effort FROM llm_config"
                " WHERE api_key <> '' ORDER BY updated_at DESC LIMIT 1"
            )
    finally:
        await conn.close()
    if row is None or not row["api_key"]:
        fail("config", "库里没有任何配好 API Key 的身份，请先在「模型配置」页填一次")
    return dict(row)


async def cleanup(owner: str, project_id: str | None, cookie: dict) -> None:
    """清掉本次跑出来的测试数据，反复跑不会在库里留垃圾。

    只删自己刚建的东西：项目按 id 删（级联清掉会话/资料/消息/run），
    模型配置按本次随机身份删。任何一步失败都只告警，不改退出码——测试结论已经定了。
    """
    try:
        if project_id:
            async with httpx.AsyncClient(base_url=BASE, cookies=cookie) as c:
                await c.delete(f"/projects/{project_id}")
        settings = get_settings()
        conn = await asyncpg.connect(dsn=settings.database_url)
        try:
            await conn.execute("DELETE FROM llm_config WHERE owner_id = $1", owner)
        finally:
            await conn.close()
        log("cleanup", "ok  已清理测试数据")
    except Exception as exc:  # noqa: BLE001 — 清理失败不该掩盖测试结论
        log("cleanup", f"warn 清理失败（不影响结论）: {type(exc).__name__}: {exc}")


async def main() -> int:
    started = time.time()
    source = await load_source_config()
    log("config", f"借用模型 {source['model']} / 推理强度 {source['reasoning_effort']!r}")

    owner = f"e2e-{uuid.uuid4().hex[:12]}"
    cookie = {"ragent_oid": owner}
    project_id = None

    async with httpx.AsyncClient(base_url=BASE, cookies=cookie, timeout=30.0) as c:
        # 1. 这个新身份先配好模型（真实链路里等价于用户在配置页填一次）
        r = await c.put(
            "/config/llm",
            json={
                "base_url": source["base_url"],
                "model": source["model"],
                "api_key": source["api_key"],
                "reasoning_effort": source["reasoning_effort"] or "low",
            },
        )
        check("配置", r.status_code == 200, f"写入模型配置 HTTP {r.status_code}")
        view = r.json()
        check("配置", view.get("reasoning_effort") == (source["reasoning_effort"] or "low"),
              f"推理强度已回显为 {view.get('reasoning_effort')!r}")

        try:
            # 2. 建项目（同时会带上一个默认会话）
            r = await c.post("/projects", json={"name": "e2e 冒烟", "description": "自动生成"})
            check("建项目", r.status_code == 201, f"HTTP {r.status_code}")
            project_id = r.json()["id"]

            r = await c.get(f"/projects/{project_id}/threads")
            check("建会话", r.status_code == 200 and len(r.json()) >= 1, "新项目自带一个会话")
            thread_id = r.json()[0]["id"]

            # 3. 提问：接口立刻返回 request_id，执行在 worker 侧异步进行
            t_ask = time.time()
            r = await c.post("/requests", json={"thread_id": thread_id, "content": QUESTION})
            check("提问", r.status_code == 201, f"HTTP {r.status_code} body={r.text[:120]}")
            request_id = r.json()["request_id"]

            # 4. 轮询到终态。这里只看数据库口径的状态，不等 SSE——
            #    前端断线、切页都不该影响「结果有没有落库」这件事。
            status = "queued"
            while time.time() - started < DEADLINE_SECONDS:
                r = await c.get(f"/requests/{request_id}")
                if r.status_code != 200:
                    fail("轮询", f"查询请求失败 HTTP {r.status_code} {r.text[:120]}")
                status = r.json()["status"]
                if status in ("done", "failed"):
                    break
                await asyncio.sleep(1.0)
            else:
                fail("执行", f"{DEADLINE_SECONDS:.0f}s 内未到终态，当前 {status}")

            check("执行", status == "done", f"终态 {status}，耗时 {time.time() - t_ask:.1f}s")

            # 5. 回答必须真的落进了会话，且不是空壳
            r = await c.get(f"/threads/{thread_id}/messages")
            check("落库", r.status_code == 200, f"HTTP {r.status_code}")
            msgs = r.json()
            roles = [m["role"] for m in msgs]
            check("落库", roles == ["user", "assistant"], f"消息序列 {roles}")
            answer = msgs[-1]["content"]
            check("落库", bool(answer.strip()), f"回答非空：{answer.strip()[:60]!r}")
        finally:
            await cleanup(owner, project_id, cookie)

    log("通过", f"整条链路 OK，总耗时 {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
