"""下载并构建 CMRC2018 评测集：把公开中文阅读理解数据集复用为 RAG 检索评测。

为什么用公开数据集：自造语料会被质疑"数据和答案都你自己编、挑好看的"。CMRC2018
是哈工大讯飞发布的公开数据集，语料(维基百科段落)、问题、答案标注都由第三方给定，
可追溯、可复现；且为中文，与线上使用的中文 embedding 模型同一套，评测分数能直接
代表线上真实检索能力。

如何复用：CMRC2018 原任务是"给定段落找答案"，这里复用成"检索"——把所有不重复
段落当作知识库，每个问题的正确来源(gold)= 它自带的那段 context。检索评测即：
向量检索能否在整个语料库里把问题对应的那段捞到 top-k。这是常见且合理的复用。

跑法：docker compose exec worker python -m app.eval.build_dataset
产物：app/eval/data/cmrc_eval.json（语料段落 + 标注问题），rag_eval.py 直接读它。
"""
import json
import os
import time

import requests

# 目标规模：语料 60~100 段、问题 100~150 条。太小分数虚高，太大本地 CPU rerank 跑太久。
TARGET_PASSAGES = 150
MAX_QUESTIONS_PER_PASSAGE = 2  # 每段最多取 2 问，避免题目扎堆在少数长段落上
OUT_PATH = os.path.join(os.path.dirname(__file__), "data", "cmrc_eval.json")

# HuggingFace datasets-server 分页 rows API：无需装 datasets/pyarrow，requests 即可拉。
ROWS_API = "https://datasets-server.huggingface.co/rows"
DATASET = "hfl/cmrc2018"
SPLIT = "validation"
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
    for attempt in range(3):
        resp = requests.get(ROWS_API, params=params, timeout=30)
        if resp.status_code == 200:
            return [x["row"] for x in resp.json()["rows"]]
        time.sleep(2)
    resp.raise_for_status()
    return []


def build() -> dict:
    """按顺序扫描验证集，去重段落建语料，每段取前若干问，直到凑够目标规模。

    单正例约束：CMRC2018 每个问题只出自一段 context，所以 gold 唯一、天然无歧义。
    段落用稳定序号(P0、P1...)当标题，问题记录它归属的段落序号。
    """
    passages: list[str] = []
    index_of: dict[str, int] = {}  # context 原文 -> 段落序号，用于去重
    per_passage_count: dict[int, int] = {}
    questions: list[dict] = []

    offset = 0
    while len(passages) < TARGET_PASSAGES:
        rows = _fetch_page(offset)
        if not rows:
            break
        offset += PAGE
        for row in rows:
            ctx = row["context"].strip()
            q = row["question"].strip()
            if ctx not in index_of:
                # 段落数已达标就不再新建段落，只在已有段落上补问题
                if len(passages) >= TARGET_PASSAGES:
                    continue
                index_of[ctx] = len(passages)
                passages.append(ctx)
                per_passage_count[index_of[ctx]] = 0
            pid = index_of[ctx]
            # 每段限流，避免题目集中在少数段落，保证问题覆盖面
            if per_passage_count[pid] >= MAX_QUESTIONS_PER_PASSAGE:
                continue
            per_passage_count[pid] += 1
            questions.append({"question": q, "gold": pid})

    # 语料：段落序号 -> 标题(P{i})+正文
    corpus = [{"title": f"P{i}", "content": passages[i]} for i in range(len(passages))]
    dataset = [
        {"question": item["question"], "gold_title": f"P{item['gold']}"}
        for item in questions
    ]
    return {"corpus": corpus, "questions": dataset}


def main() -> None:
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    data = build()
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(
        f"已写入 {OUT_PATH}：语料 {len(data['corpus'])} 段 / 问题 {len(data['questions'])} 条"
    )


if __name__ == "__main__":
    main()
