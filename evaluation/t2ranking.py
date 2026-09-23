"""T2Ranking retrieval evaluation against the real RAG pipeline.

Isolated from the application database: creates a temporary database, applies the
application schema, ingests a frozen sample of the public T2Ranking dev split through
the production ingest path, then measures vector-only vs. two-stage retrieval.

Run inside the API container:
    docker compose exec -T api env PYTHONPATH=/app python /tmp/t2r/eval_t2ranking.py
"""
import asyncio
import hashlib
import importlib.metadata
import json
import math
import random
import statistics
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg

from app.agent.embedding import embed_query
from app.agent.rerank import rerank
from app.config import get_settings
from app.repositories import documents
from app.services import rag

DATA = Path("/tmp/t2r")
QRELS = DATA / "qrels.retrieval.dev.tsv"
QUERIES = DATA / "queries.dev.tsv"
COLLECTION = DATA / "collection_prefix.tsv"
BM25 = DATA / "dev.bm25.tsv"
OUT = DATA / "results_t2ranking.json"

PID_CAP = 500000
N_QUERIES = 300
N_CORPUS = 2000
MIN_POS, MAX_POS = 3, 8
# Hard negatives: BM25 retrieved these for the same query but the editors did not
# judge them relevant. Lexically close, semantically wrong -- the case reranking exists for.
# A query is only eligible if its positives AND its hard negatives all fall inside the
# locally available pid range, so every selected query competes in a fully populated pool.
BM25_RANK_MIN, BM25_RANK_MAX = 4, 40
SEED = 20260922
CONFIGS = [("vector_top3", 3, False), ("pipeline_20_rerank3", 20, True)]

RESULT = {"started_at": datetime.now(timezone.utc).isoformat(), "checks": [], "failures": []}


def check(name, condition, **evidence):
    RESULT["checks"].append({"name": name, "passed": bool(condition), **evidence})
    print(f'{"PASS" if condition else "FAIL"}: {name}', flush=True)
    if not condition:
        RESULT["failures"].append(name)


def load_qrels():
    by_query = defaultdict(list)
    for line in QRELS.open(encoding="utf-8"):
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 2 or parts[0] == "qid":
            continue
        by_query[parts[0]].append(int(parts[1]))
    return by_query


def load_queries():
    text = {}
    for line in QUERIES.open(encoding="utf-8"):
        parts = line.rstrip("\n").split("\t", 1)
        if len(parts) < 2 or parts[0] == "qid":
            continue
        text[parts[0]] = parts[1]
    return text


def load_collection(needed):
    """Stream both local collection parts; keep only wanted pids."""
    found = {}
    for path in (COLLECTION, DATA / "collection_rest.tsv"):
        if not path.exists():
            continue
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                pid, tab, text = line.partition("\t")
                if pid.isdigit() and int(pid) in needed:
                    found[int(pid)] = text.rstrip("\n")
                    if len(found) == len(needed):
                        return found
    return found


def load_bm25_hard_negatives(selected_qids):
    """Per query, the passages BM25 ranked highly but qrels never marked relevant."""
    by_query = defaultdict(list)
    wanted = {q for q in selected_qids}
    with BM25.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            qid, _, rest = line.partition("\t")
            if qid not in wanted:
                continue
            pid, _, rank = rest.partition("\t")
            if pid.isdigit() and rank.strip().isdigit():
                r = int(rank)
                if BM25_RANK_MIN <= r <= BM25_RANK_MAX:
                    by_query[qid].append(int(pid))
    return by_query


def select_queries(qrels, texts, hard):
    """Queries whose positives and hard negatives are all available locally."""
    rng = random.Random(SEED)
    pool = [(q, p) for q, p in qrels.items()
            if q in texts and MIN_POS <= len(p) <= MAX_POS and max(p) < PID_CAP
            and len(hard.get(q, [])) >= MIN_POS]
    pool.sort()
    rng.shuffle(pool)
    return pool[:N_QUERIES]


async def retrieve_deep(pool, project_id, question, recall_size, top_k):
    """Same two-stage shape as rag.retrieve, but with a configurable recall depth."""
    query_embedding = await embed_query(question)
    async with pool.acquire() as conn:
        rows = await documents.search_chunks_with_doc(conn, project_id, query_embedding, recall_size)
    if not rows:
        return []
    rows_by_content = defaultdict(deque)
    for row in rows:
        rows_by_content[row["content"]].append(row)
    ranked = await rerank(question, [r["content"] for r in rows], top_k)
    hits = []
    for content in ranked:
        row = rows_by_content[content].popleft()
        hits.append({"document_id": str(row["document_id"]), "title": row["title"], "content": content,
                     "similarity": float(row["similarity"]) if row["similarity"] is not None else None})
    return hits


async def vector_only(pool, project_id, question, top_k):
    query_embedding = await embed_query(question)
    async with pool.acquire() as conn:
        rows = await documents.search_chunks_with_doc(conn, project_id, query_embedding, top_k)
    return [{"document_id": str(r["document_id"]), "title": r["title"], "content": r["content"], "similarity": None} for r in rows]


def per_query_hit1(records, method, k=3):
    """Hit@1 as a 0/1 vector, so configurations can be compared query by query."""
    out = []
    for row in records:
        rel = set(row["relevant"])
        ranked = row[method][:k]
        out.append(1.0 if (ranked and ranked[0] in rel) else 0.0)
    return out


def bootstrap_ci(deltas, rng, rounds=5000):
    """Percentile bootstrap over queries. deltas > 0 means the second system wins."""
    n = len(deltas)
    means = []
    for _ in range(rounds):
        means.append(sum(deltas[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    lo = means[int(0.025 * rounds)]
    hi = means[min(rounds - 1, int(0.975 * rounds))]
    return round(lo, 4), round(hi, 4)


def significance(records, rng):
    """Paired comparison of vector-only vs. reranked, on the same queries."""
    base = per_query_hit1(records, "vector_top3")
    pipe = per_query_hit1(records, "pipeline_20_rerank3")
    deltas = [b - a for a, b in zip(base, pipe)]
    n = len(deltas)
    mean = statistics.mean(deltas)
    if n > 1 and statistics.stdev(deltas) > 0:
        t = mean / (statistics.stdev(deltas) / math.sqrt(n))
    else:
        t = 0.0
    wins = sum(1 for d in deltas if d > 0)
    losses = sum(1 for d in deltas if d < 0)
    ties = n - wins - losses
    lo, hi = bootstrap_ci(deltas, rng)
    return {"n_queries": n, "mean_delta_hit1": round(mean, 4),
            "paired_t": round(t, 2), "bootstrap_95_ci": [lo, hi],
            "ci_excludes_zero": lo > 0 or hi < 0,
            "rerank_better": wins, "rerank_worse": losses, "tied": ties}


def score(records, method, k):
    recall, mrr, ndcg, hit = [], [], [], []
    for row in records:
        rel = set(row["relevant"])
        ranked = row[method][:k]
        hits = [1 if p in rel else 0 for p in ranked]
        recall.append(sum(hits) / len(rel))
        mrr.append(next((1 / (i + 1) for i, h in enumerate(hits) if h), 0))
        dcg = sum(h / math.log2(i + 2) for i, h in enumerate(hits))
        idcg = sum(1 / math.log2(i + 2) for i in range(min(len(rel), k)))
        ndcg.append(dcg / idcg if idcg else 0)
        hit.append(hits[0] if hits else 0)
    lat = [r[method + "_ms"] for r in records]
    lat_sorted = sorted(lat)
    p95 = lat_sorted[min(len(lat_sorted) - 1, int(0.95 * len(lat_sorted)))]
    return {"recall": statistics.mean(recall), "mrr": statistics.mean(mrr),
            "ndcg": statistics.mean(ndcg), "hit1": statistics.mean(hit),
            "p50_ms": round(statistics.median(lat), 1), "p95_ms": round(p95, 1)}


async def main():
    admin = await asyncpg.connect(get_settings().database_url)
    qrels, texts = load_qrels(), load_queries()
    hard = load_bm25_hard_negatives(set(qrels))
    selected = select_queries(qrels, texts, hard)
    check("enough_queries_selected", len(selected) == N_QUERIES,
          selected=len(selected), requested=N_QUERIES, pid_cap=PID_CAP,
          positives_per_query=f"{MIN_POS}-{MAX_POS}")

    rng = random.Random(SEED)
    positives = sorted({p for _, ps in selected for p in ps})
    # Distractors = BM25 hard negatives for the same queries, then random fill.
    hard_flat = sorted({p for q, _ in selected for p in hard.get(q, [])} - set(positives))
    rng.shuffle(hard_flat)
    taken = set(positives)
    negatives = []
    for pid in hard_flat:
        if len(negatives) >= N_CORPUS - len(positives):
            break
        if pid not in taken:
            taken.add(pid)
            negatives.append(pid)
    n_hard = len(negatives)
    while len(negatives) < N_CORPUS - len(positives):
        cand = rng.randrange(1, PID_CAP)
        if cand not in taken:
            taken.add(cand)
            negatives.append(cand)
    wanted = sorted(set(positives) | set(negatives))
    RESULT["distractors"] = {"bm25_hard_negatives": n_hard,
                             "random": len(negatives) - n_hard,
                             "bm25_rank_range": [BM25_RANK_MIN, BM25_RANK_MAX],
                             "queries_with_hard_negatives": len(hard)}

    print(f"streaming collection for {len(wanted)} pids ({len(positives)} positives)...", flush=True)
    t0 = time.perf_counter()
    collection = load_collection(set(wanted))
    print(f"collection read in {time.perf_counter() - t0:.1f}s, found {len(collection)}", flush=True)
    check("all_positive_passages_present", all(p in collection for p in positives),
          missing=len([p for p in positives if p not in collection]))

    usable = [(q, [p for p in ps if p in collection]) for q, ps in selected]
    usable = [(q, ps) for q, ps in usable if ps]
    check("selected_queries_usable_after_load", len(usable) >= N_QUERIES * 0.9, usable=len(usable))
    pids = [p for p in positives if p in collection] + [p for p in negatives if p in collection]

    name = "ragent_eval_" + uuid.uuid4().hex
    parsed = urlsplit(get_settings().database_url)
    dsn = urlunsplit(parsed._replace(path="/" + name))
    pool = None
    created = False
    corpus_sha = hashlib.sha256(
        ("\n".join(f"{p}\t{collection[p]}" for p in sorted(pids))).encode("utf-8")).hexdigest()
    RESULT["dataset"] = {
        "name": "THUIR/T2Ranking", "split": "dev (qrels.retrieval.dev.tsv)",
        "license": "apache-2.0", "pid_cap": PID_CAP,
        "passages": len(pids), "positives": len([p for p in pids if p in set(positives)]),
        "queries": len(usable), "seed": SEED,
        "corpus_sha256": corpus_sha,
        "embedding": get_settings().embedding_model, "reranker": get_settings().rerank_model,
        "versions": {p: importlib.metadata.version(p) for p in ("fastembed", "asyncpg", "tokenizers")},
    }
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
        created = True
        pool = await asyncpg.create_pool(dsn, min_size=2, max_size=12)
        async with pool.acquire() as conn:
            await conn.execute(Path("/app/app/schema.sql").read_text(encoding="utf-8"))
            project = await conn.fetchval("INSERT INTO projects(name) VALUES('T2Ranking 评测') RETURNING id")

        print(f"ingesting {len(pids)} passages through rag.ingest_document...", flush=True)
        t0 = time.perf_counter()
        pid_of_doc = {}
        for i, pid in enumerate(pids, 1):
            doc, _ = await rag.ingest_document(pool, project, str(pid), collection[pid])
            pid_of_doc[str(doc)] = pid
            if i % 200 == 0:
                print(f"  {i}/{len(pids)} ({time.perf_counter() - t0:.0f}s)", flush=True)
        ingest_seconds = time.perf_counter() - t0
        async with pool.acquire() as conn:
            n_chunks = await conn.fetchval("SELECT count(*) FROM chunks")
        print(f"ingest done: {ingest_seconds:.0f}s, {n_chunks} chunks", flush=True)

        records = []
        for qid, rel_pids in usable:
            question = texts[qid]
            rel = set(rel_pids)
            row = {"qid": qid, "question": question, "relevant": sorted(rel)}
            for label, recall_size, do_rerank in CONFIGS:
                t = time.perf_counter()
                if do_rerank:
                    hits = await retrieve_deep(pool, project, question, recall_size, 3)
                else:
                    hits = await vector_only(pool, project, question, recall_size)
                ms = (time.perf_counter() - t) * 1000
                row[label] = [pid_of_doc.get(h["document_id"]) for h in hits]
                row[label + "_ms"] = round(ms, 2)
            records.append(row)
            if len(records) % 10 == 0:
                print(f"  queried {len(records)}/{len(usable)}", flush=True)

        RESULT["retrieval"] = {
            "ingest_seconds": round(ingest_seconds, 1), "chunks": n_chunks,
            "unit": "chunk -> source passage pid; metrics over top-K chunks, truncated once at K",
            "metrics": {label: {**score(records, label, 3), "recall_at_10": score(records, label, 10)["recall"]}
                        for label, _, _ in CONFIGS},
            "records": records,
        }
        base = RESULT["retrieval"]["metrics"]["vector_top3"]
        pipe = RESULT["retrieval"]["metrics"]["pipeline_20_rerank3"]
        RESULT["significance"] = significance(records, random.Random(SEED))
        check("rerank_improves_mrr_over_vector_only", pipe["mrr"] > base["mrr"],
              vector=round(base["mrr"], 4), pipeline=round(pipe["mrr"], 4))
        check("rerank_costs_latency", pipe["p50_ms"] > base["p50_ms"],
              vector_p50=base["p50_ms"], pipeline_p50=pipe["p50_ms"])
        print("significance:", json.dumps(RESULT["significance"], ensure_ascii=False), flush=True)
    except Exception as exc:
        RESULT["failures"].append(type(exc).__name__)
        print("Evaluation stopped:", type(exc).__name__, flush=True)
        import traceback
        traceback.print_tb(exc.__traceback__)
    finally:
        if pool:
            await pool.close()
        if created:
            await admin.execute(f'DROP DATABASE "{name}"')
        check("temporary_database_removed", not await admin.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", name))
        await admin.close()
        RESULT["completed_at"] = datetime.now(timezone.utc).isoformat()
        OUT.write_text(json.dumps(RESULT, ensure_ascii=False, indent=2), encoding="utf-8")
        print("wrote", OUT, flush=True)
    if RESULT["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
