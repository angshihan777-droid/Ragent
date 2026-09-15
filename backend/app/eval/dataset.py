"""评测集加载器：读取 build_dataset.py 从 T2Reranking 生成的 t2rerank_eval.json。

为什么单独一个加载器：语料与标注来自公开数据集(见 build_dataset.py)，不再手工编写。
这里只负责把 json 读成 rag_eval.py 需要的结构，保持评测脚本与数据来源解耦。

EVAL_SET : list[dict]，每题 {query, candidates(候选段落), golds(其中的正例段落)}。
"""
import json
import os

_DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "t2rerank_eval.json")

if not os.path.exists(_DATA_PATH):
    raise FileNotFoundError(
        f"未找到 {_DATA_PATH}，请先运行 python -m app.eval.build_dataset 下载并构建评测集"
    )

with open(_DATA_PATH, "r", encoding="utf-8") as _f:
    EVAL_SET = json.load(_f)
