"""Isolated retrieval and recovery evidence; run only as documented in README.md."""
import asyncio
import hashlib
import importlib.metadata
import json
import statistics
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from unittest.mock import patch

import asyncpg
import redis.asyncio as redislib
from langchain_core.messages import HumanMessage

from app import queue, worker
from app.agent import graph
from app.agent.embedding import embed_query
from app.agent.structured import invoke_json
from app.config import get_settings
from app.repositories import documents, messages, runs
from app.services import rag, requests, sse, threads
from corpus import DOCS, QUERIES, NO_ANSWER

RESULT = {"started_at": datetime.now(timezone.utc).isoformat(), "harness_sha256": hashlib.sha256(Path(__file__).read_text(encoding="utf-8").encode("utf-8")).hexdigest(), "checks": [], "failures": []}
REQUEST_IDS = []


def check(name, condition, **evidence):
    RESULT["checks"].append({"name": name, "passed": bool(condition), **evidence})
    print(f'{"PASS" if condition else "FAIL"}: {name}', flush=True)
    if not condition:
        RESULT["failures"].append(name)


async def snapshot(conn):
    # Fingerprints/counts only: no content or credentials in the artifact.
    return {
        "counts": {table: await conn.fetchval(f'SELECT count(*) FROM {table}')
                   for table in ("projects", "threads", "documents", "chunks", "messages", "agent_run_requests")},
        "document_fingerprints": [dict(r) for r in await conn.fetch(
            "SELECT id::text, md5(content) AS md5 FROM documents ORDER BY id")],
    }


async def new_case(pool, project, question="验证恢复", thread=None):
    if thread is None:
        thread = str((await threads.create_thread(pool, project, "隔离评测"))["id"])
    req = await requests.create_request(pool, REDIS, thread, question)
    REQUEST_IDS.append(req["request_id"])
    async with pool.acquire() as conn:
        run = await conn.fetchrow("SELECT id FROM agent_runs WHERE request_id=$1", req["request_id"])
    return thread, req["request_id"], run["id"] if run else None


async def info_claim(pool, run_id, owner):
    async with pool.acquire() as conn:
        assert await runs.claim_run(conn, run_id, owner)
        return await runs.get_run_with_group(conn, run_id)


async def answer_count(pool, request):
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT count(*) FROM messages WHERE request_id=$1 AND role='assistant'", request)


async def recovery(pool, project):
    # Actual PG/Redis; deterministic agent avoids provider variance in recovery tests.
    async def deterministic_agent(*args):
        await asyncio.sleep(0.05)
        yield "token", "隔离恢复验证回答"

    _, request, run = await new_case(pool, project)
    with patch.object(worker, "stream_agent", deterministic_agent):
        await asyncio.gather(*(worker._handle_run(pool, REDIS, run) for _ in range(8)))
    count = await answer_count(pool, request)
    check("eight_duplicate_deliveries_one_reply", count == 1, replies=count)

    _, request, run = await new_case(pool, project)
    info = await info_claim(pool, run, "old-owner")
    async with pool.acquire() as conn:
        await conn.execute("UPDATE agent_runs SET heartbeat_at=now()-interval '30 seconds' WHERE id=$1", run)
    recovered = await worker.recover_once(pool, REDIS)
    await info_claim(pool, run, "new-owner")
    stale, _ = await worker.finalize_run(pool, info, "old-owner", "done", result=("stale", [], []))
    fresh, _ = await worker.finalize_run(pool, info, "new-owner", "done", result=("fresh", [], []))
    check("expired_lease_fences_old_owner", run in recovered and not stale and fresh and await answer_count(pool, request) == 1,
          injection="backdated heartbeat (not OS process kill)", stale_committed=stale, replacement_committed=fresh)

    class OfflineDelivery:
        async def lpush(self, *args):
            raise redislib.ConnectionError("injected delivery loss")
    thread = str((await threads.create_thread(pool, project, "投递失败"))["id"])
    req = await requests.create_request(pool, OfflineDelivery(), thread, "数据库已提交但Redis投递失败")
    REQUEST_IDS.append(req["request_id"])
    async with pool.acquire() as conn:
        run = await conn.fetchval("SELECT id FROM agent_runs WHERE request_id=$1", req["request_id"])
        await conn.execute("UPDATE agent_runs SET created_at=now()-interval '30 seconds' WHERE id=$1", run)
    recovered = await worker.recover_once(pool, REDIS)
    with patch.object(worker, "stream_agent", deterministic_agent):
        await worker._handle_run(pool, REDIS, run)
    check("committed_request_survives_initial_enqueue_loss", run in recovered and await answer_count(pool, req["request_id"]) == 1)

    # Start the SSE subscriber before completion; intentionally never publish done.
    _, request, run = await new_case(pool, project)
    info = await info_claim(pool, run, "sse-owner")
    async def collect(redis):
        return [event async for event in sse.stream_request(pool, redis, request)]
    task = asyncio.create_task(collect(REDIS))
    await asyncio.sleep(0.2)
    start = time.perf_counter()
    await worker.finalize_run(pool, info, "sse-owner", "done", result=("durable answer", [], []))
    events = await asyncio.wait_for(task, 6)
    elapsed = time.perf_counter() - start
    check("lost_done_notification_reconciles", any('"content": "durable answer"' in e for e in events), seconds=round(elapsed, 3))
    class OfflinePubsub:
        async def subscribe(self, *args):
            raise redislib.ConnectionError("injected subscribe failure")
        async def aclose(self):
            pass
    class OfflineRedis:
        def pubsub(self):
            return OfflinePubsub()
    events = await asyncio.wait_for(collect(OfflineRedis()), 4)
    check("sse_subscription_failure_reads_database", any('"content": "durable answer"' in e for e in events))

    thread, request, run = await new_case(pool, project)
    _, second, _ = await new_case(pool, project, thread=thread)
    async def failing_agent(*args):
        raise TimeoutError("provider timeout secret-body")
        yield
    with patch.object(worker, "stream_agent", failing_agent):
        await worker._handle_run(pool, REDIS, run)
    history = await threads.list_thread_messages(pool, thread)
    async with pool.acquire() as conn:
        second_run = await conn.fetchval("SELECT id FROM agent_runs WHERE request_id=$1", second)
    check("failure_persisted_safely_and_fifo_advances", any(m["error"] and "超时" in m["content"] and "secret" not in m["content"] for m in history) and second_run is not None)
    with patch.object(worker, "stream_agent", deterministic_agent):
        await worker._handle_run(pool, REDIS, second_run)

    _, request, run = await new_case(pool, project)
    info = await info_claim(pool, run, "rollback-owner")
    async def broken_insert(*args, **kwargs):
        raise RuntimeError("injected crash between run completion and message insert")
    with patch.object(messages, "insert_message", broken_insert):
        try:
            await worker.finalize_run(pool, info, "rollback-owner", "done", result=("answer", [], []))
        except RuntimeError:
            pass
    async with pool.acquire() as conn:
        state = await runs.get_run(conn, run)
    before_count = await answer_count(pool, request)
    committed, _ = await worker.finalize_run(pool, info, "rollback-owner", "done", result=("answer", [], []))
    check("result_transaction_rolls_back_and_retries", state["status"] == "running" and before_count == 0 and committed and await answer_count(pool, request) == 1)


async def retrieval(pool, project):
    ids = {}
    start = time.perf_counter()
    for key, (title, content) in DOCS.items():
        doc, _ = await rag.ingest_document(pool, project, title, content)
        ids[str(doc)] = key
    ingest_seconds = time.perf_counter() - start
    records = []
    for qid, question, relevant in QUERIES:
        start = time.perf_counter()
        vec = await embed_query(question)
        async with pool.acquire() as conn:
            rows = await documents.search_chunks_with_doc(conn, project, vec, 3)
        baseline_ms = (time.perf_counter() - start) * 1000
        start = time.perf_counter()
        hits = await rag.retrieve(pool, project, question)
        rerank_ms = (time.perf_counter() - start) * 1000
        ranked = lambda rows: list(dict.fromkeys(ids[str(r["document_id"])] for r in rows))
        records.append({"id": qid, "question": question, "relevant": relevant,
                        "vector": ranked(rows), "rerank": ranked(hits),
                        "vector_ms": round(baseline_ms, 2), "rerank_ms": round(rerank_ms, 2)})
    def metrics(method):
        recall, mrr, hit = [], [], []
        for row in records:
            relevant = set(row["relevant"])
            ranked = row[method]
            recall.append(len(relevant.intersection(ranked)) / len(relevant))
            mrr.append(next((1 / (i+1) for i, key in enumerate(ranked) if key in relevant), 0))
            hit.append(int(bool(ranked) and ranked[0] in relevant))
        return {"recall_at_3": statistics.mean(recall), "mrr_at_3": statistics.mean(mrr), "hit_at_1": statistics.mean(hit),
                "median_ms": statistics.median(r[method + "_ms"] for r in records)}
    probes = []
    for question in NO_ANSWER:
        hits = await rag.retrieve(pool, project, question)
        probes.append({"question": question, "ranked": [ids[h["document_id"]] for h in hits], "interpretation": "top-k is not a no-answer classifier"})
    RESULT["retrieval"] = {"corpus_sha256": hashlib.sha256(Path(__file__).with_name("corpus.py").read_text(encoding="utf-8").encode("utf-8")).hexdigest(),
        "documents": len(DOCS), "queries": len(QUERIES), "unit": "document IDs deduplicated within top-3 chunks",
        "ingest_seconds": round(ingest_seconds, 2), "first_rerank_ms_includes_model_load": records[0]["rerank_ms"],
        "vector": metrics("vector"), "rerank": metrics("rerank"), "records": records, "no_answer_probes": probes}
    # Index mutation and project isolation use actual embeddings.
    async with pool.acquire() as conn:
        other = await conn.fetchval("INSERT INTO projects(name) VALUES('隔离域') RETURNING id")
    check("project_retrieval_isolation", await rag.retrieve(pool, other, QUERIES[0][1]) == [])
    doc, _ = await rag.ingest_document(pool, other, "可变资料.md", "系统验证口令为北风九号")
    detail = await rag.get_document(pool, doc)
    await rag.update_document(pool, doc, "可变资料.md", "系统验证口令为南山七号", detail["revision"])
    conflict = False
    try:
        await rag.update_document(pool, doc, "可变资料.md", "不应覆盖", detail["revision"])
    except rag.DocumentConflict:
        conflict = True
    hits = await rag.retrieve(pool, other, "系统验证口令")
    check("document_edit_replaces_index_and_rejects_stale_revision", conflict and all("北风" not in h["content"] for h in hits) and any("南山七号" in h["content"] for h in hits))
    await rag.delete_document(pool, doc)
    check("document_delete_cascades_index", await rag.retrieve(pool, other, "系统验证口令") == [])


async def provider(pool, project, cfg):
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO llm_config(id,base_url,api_key,model) VALUES(1,$1,$2,$3) ON CONFLICT(id) DO UPDATE SET base_url=$1,api_key=$2,model=$3", cfg["base_url"], cfg["api_key"], cfg["model"])
    model = await graph._build_llm(pool)
    RESULT["provider"] = {"model": cfg["model"], "old_forced_tool": None}
    try:
        await model.with_structured_output(graph.Decision, method="function_calling").ainvoke([HumanMessage(content="你好，请判断是否需要检索")])
        RESULT["provider"]["old_forced_tool"] = "accepted (provider behavior differs from original reproduction)"
    except Exception as exc:
        RESULT["provider"]["old_forced_tool"] = {"type": type(exc).__name__, "thinking_tool_choice_rejected": "Thinking mode does not support this tool_choice" in str(exc)}
    decision = await invoke_json(model, graph.Decision, [HumanMessage(content="你好，请判断是否需要检索")])
    evidence_prompt = "问题：星河公司正式员工每年享有几天带薪年假？证据：星河公司正式员工每年享有十五天带薪年假。只判断上述问题是否被这条证据覆盖。"
    evidence = await invoke_json(model, graph.Evidence, [HumanMessage(content=evidence_prompt)])
    check("live_provider_json_decision_and_evidence", decision.action in ("direct", "clarify", "retrieve") and evidence.sufficient,
          decision=decision.model_dump(), evidence=evidence.model_dump(), evidence_prompt=evidence_prompt)
    for name, question in [("greeting", "你好"), ("grounded", "根据星河员工年假规则，正式员工每年享有几天带薪年假？")]:
        thread, request, run = await new_case(pool, project, question)
        start = time.perf_counter()
        await asyncio.wait_for(worker._handle_run(pool, REDIS, run), 240)
        async with pool.acquire() as conn:
            reply = await messages.get_assistant_reply(conn, request)
        nodes = [s["node"] for s in json.loads(reply["steps"])] if reply else []
        answer = reply["content"] if reply else ""
        valid = bool(answer) and (("retrieve" not in nodes) if name == "greeting" else ("retrieve" in nodes and "[S" in answer and ("十五" in answer or "15" in answer)))
        check("live_graph_" + name, valid, nodes=nodes, answer=answer, seconds=round(time.perf_counter()-start, 2))


async def main():
    global REDIS
    settings = get_settings()
    admin = await asyncpg.connect(settings.database_url)
    RESULT["before"] = await snapshot(admin)
    cfg = await admin.fetchrow("SELECT base_url,api_key,model FROM llm_config WHERE id=1")
    name = "ragent_eval_" + uuid.uuid4().hex
    parsed = urlsplit(settings.database_url)
    dsn = urlunsplit(parsed._replace(path="/" + name))
    queue.QUEUE_KEY = "ragent:eval:" + name + ":runs"
    worker.QUEUE_KEY = queue.QUEUE_KEY
    REDIS = redislib.from_url(settings.redis_url, socket_connect_timeout=3, socket_timeout=5)
    pool = None
    created = False
    RESULT["environment"] = {"database": name, "embedding": settings.embedding_model, "reranker": settings.rerank_model,
        "versions": {p: importlib.metadata.version(p) for p in ("langgraph", "langchain-openai", "fastembed", "asyncpg")}}
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
        created = True
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=10)
        async with pool.acquire() as conn:
            await conn.execute(Path("/app/app/schema.sql").read_text())
            project = await conn.fetchval("INSERT INTO projects(name) VALUES('隔离评测') RETURNING id")
        await recovery(pool, project)
        await retrieval(pool, project)
        if cfg and cfg["api_key"]:
            await provider(pool, project, cfg)
        else:
            RESULT["failures"].append("live_provider_missing_configuration")
    except Exception as exc:
        # Exception bodies may contain provider secrets; type only in artifacts.
        RESULT["failures"].append(type(exc).__name__)
        print("Evaluation stopped:", type(exc).__name__, flush=True)
        import traceback
        traceback.print_tb(exc.__traceback__)
    finally:
        if pool:
            await pool.close()
        if created:
            await admin.execute(f'DROP DATABASE "{name}"')
        keys = [queue.QUEUE_KEY]
        from app.events import request_channel
        keys += [request_channel(r) + ":trace" for r in REQUEST_IDS]
        await REDIS.delete(*keys)
        await REDIS.aclose()
        RESULT["after"] = await snapshot(admin)
        check("real_database_unchanged", RESULT["before"] == RESULT["after"])
        check("temporary_database_removed", not await admin.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", name))
        await admin.close()
        RESULT["completed_at"] = datetime.now(timezone.utc).isoformat()
        Path(__file__).with_name("results").mkdir(exist_ok=True)
        Path(__file__).with_name("results").joinpath("latest.json").write_text(json.dumps(RESULT, ensure_ascii=False, indent=2), encoding="utf-8")
    if RESULT["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
