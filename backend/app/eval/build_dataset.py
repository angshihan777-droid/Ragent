"""下载并构建 T2Reranking 评测集：把公开中文重排基准复用为本项目的重排评测。

为什么用公开数据集：自造语料会被质疑"数据和答案都你自己编、挑好看的"。T2Reranking
是 C-MTEB 收录的公开中文重排(reranking)基准，query、正例段落、负例段落都由第三方
标注给定，可追溯、可复现；中文，与线上使用的中文 embedding 模型同一套。

数据结构：每个 query 自带一批候选段落——正例(能回答)与人工标注的强负例(看着相关
其实答非所问)。评测即在这批候选里比较两种排序：纯向量相似度 vs 向量召回后再 rerank，
正是本项目两阶段检索里"重排"这一步真正要干的事，强负例最能体现 rerank 的价值。

多正例：一个 query 可能有多个正例段落，因此指标按多正例口径计算(见 rag_eval.py)。

跑法：docker compose exec worker python -m app.eval.build_dataset
产物：app/eval/data/t2rerank_eval.json，rag_eval.py 直接读它。
"""
import json
import os
import time

import requests

# 目标题量：取 dev 集前 N 个 query。每题候选池是自带的正/负例，不依赖外部大语料。
TARGET_QUERIES = 300
OUT_PATH = os.path.join(os.path.dirname(__file__), "data", "t2rerank_eval.json")

# HuggingFace datasets-server 分页 rows API：无需装 datasets/pyarrow，requests 即可拉。
ROWS_API = "https://datasets-server.huggingface.co/rows"
DATASET = "C-MTEB/T2Reranking"
SPLIT = "dev"
PAGE = 100


def _fetch_page(offset: int) -> list[dict]:
    """拉一页原始样例；带简单重试，datasets-server 偶发 5xx。"""
    params = {
        "dataset": DATASET,
        "config": "default",
        "split": SPLIT,
        "offset": offset,
        "length": PAGE,
    }
    for _ in range(3):
        resp = requests.get(ROWS_API, params=params, timeout=30)
        if resp.status_code == 200:
            return [x["row"] for x in resp.json()["rows"]]
        time.sleep(2)
    resp.raise_for_status()
    return []


def build() -> list[dict]:
    """取前 TARGET_QUERIES 个 query，每题保留其自带的正例、负例候选池。

    过滤：跳过没有正例或没有负例的题(无法构成有意义的排序对比)。
    去重：同一题内候选段落可能重复，去重同时记录哪些是正例(gold)。
    """
    items: list[dict] = []
    offset = 0
    while len(items) < TARGET_QUERIES:
        rows = _fetch_page(offset)
        if not rows:
            break
        offset += PAGE
        for row in rows:
            positives = [p.strip() for p in row["positive"] if p.strip()]
            negatives = [n.strip() for n in row["negative"] if n.strip()]
            if not positives or not negatives:
                continue
            pos_set = set(positives)
            # 候选池 = 正例 + 负例，去重并保留顺序；gold 是其中的正例集合
            seen, candidates, golds = set(), [], []
            for c in positives + negatives:
                if c in seen:
                    continue
                seen.add(c)
                candidates.append(c)
                if c in pos_set:
                    golds.append(c)
            items.append(
                {
                    "query": row["query"].strip(),
                    "candidates": candidates,
                    "golds": golds,
                }
            )
            if len(items) >= TARGET_QUERIES:
                break
    return items


def main() -> None:
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    data = build()
    n_cand = sum(len(x["candidates"]) for x in data)
    n_gold = sum(len(x["golds"]) for x in data)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(
        f"已写入 {OUT_PATH}：{len(data)} 题 / 候选 {n_cand} 段 / 正例 {n_gold} 段 "
        f"(平均每题候选 {n_cand/len(data):.1f}、正例 {n_gold/len(data):.1f})"
    )


if __name__ == "__main__":
    main()
