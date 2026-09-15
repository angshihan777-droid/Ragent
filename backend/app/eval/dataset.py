"""评测集加载器：读取 build_dataset.py 从 CMRC2018 生成的 cmrc_eval.json。

为什么单独一个加载器：语料与标注来自公开数据集(见 build_dataset.py)，不再手工编写。
这里只负责把 json 读成 rag_eval.py 需要的两个结构，保持评测脚本与数据来源解耦。

CORPUS       : list[(title, content)]      —— 入库的语料段落。
GOLDEN_SET   : list[(question, gold_title)] —— 每题及其唯一正确来源段落(单正例)。
"""
import json
import os

_DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "cmrc_eval.json")

if not os.path.exists(_DATA_PATH):
    raise FileNotFoundError(
        f"未找到 {_DATA_PATH}，请先运行 python -m app.eval.build_dataset 下载并构建评测集"
    )

with open(_DATA_PATH, "r", encoding="utf-8") as _f:
    _data = json.load(_f)

CORPUS = [(item["title"], item["content"]) for item in _data["corpus"]]
GOLDEN_SET = [(item["question"], item["gold_title"]) for item in _data["questions"]]
