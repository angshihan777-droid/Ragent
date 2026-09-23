# T2Ranking 检索评测报告

在公开数据集 **T2Ranking**（清华大学 THUIR + 腾讯 QQ 浏览器，SIGIR 2023，Apache-2.0）上评测本项目的检索链路。
脚本：[`evaluation/t2ranking.py`](t2ranking.py) ｜ 原始结果：[`evaluation/results/t2ranking.json`](results/t2ranking.json)

## 一、怎么跑的

不是 mock，是把 T2Ranking 的段落**真的喂进生产入库通道**，再用生产检索函数查：

- 建一个临时数据库（`ragent_eval_<随机>`），跑 `app/schema.sql`，评测结束在 `finally` 里 `DROP DATABASE`。全程不碰业务库。
- 段落经 `rag.ingest_document()` 入库 —— 和用户上传文档走的是同一条切分、向量化路径。
- 查询经 `documents.search_chunks_with_doc()` + `app.agent.rerank.rerank()` —— 和生产 `rag.retrieve()` 同一套函数。

固定随机种子 `20260922`，语料 SHA256 `149a3c13…f77ca`，换台机器能复现同一批段落。

| 项目 | 值 |
|---|---|
| 数据集 | THUIR/T2Ranking dev split |
| 语料 | 1,991 段落 / 5,771 chunks |
| 查询 | 300 条（每条 3–8 个正确答案） |
| 正确答案总数 | 1,241 |
| Embedding | BAAI/bge-small-zh-v1.5（ONNX） |
| Reranker | BAAI/bge-reranker-base（ONNX） |
| 干扰项 | 759 个 **BM25 难负例**（BM25 排第 4–40 名，但人工判定不相关） |

**为什么用 BM25 难负例**：第一版我用随机段落当干扰项（猫、菜谱、游戏），向量模型闭着眼都能排对，Hit@1 直接 0.96，什么也证明不了。改用 BM25 难负例后 —— 这些段落字面和问题高度重合、语义却不相关 —— 才真正测出东西。

**评测单位**：chunk → 回溯到源段落 pid。检索是 chunk 级的，指标按段落去重后计算。

## 二、结果

| 配置 | R@3 | MRR@3 | nDCG@3 | Hit@1 | p50 | p95 |
|---|---|---|---|---|---|---|
| 向量 top-3 | 0.6736 | 0.9372 | 0.8757 | 0.9033 | 26.7 ms | 38.8 ms |
| 召回 20 → 重排 → top-3 | 0.6796 | 0.9506 | 0.8831 | 0.9167 | 2376.3 ms | 3570.2 ms |

> 诚实标注：脚本里的 `recall_at_10` 字段等同于 R@3 —— 因为检索时只取回 3 个 chunk，第 4 名之后不存在，截断发生在计算之前。报告里用 R@3，不要引用那个字段当 Recall@10。

入库耗时 211.9 s（1,991 段落，单线程走生产通道）。

## 三、重排到底有没有用

**分查询配对比较（Hit@1，n=300）：**

| 指标 | 值 |
|---|---|
| 平均提升 | +0.0133（约 +1.3 个百分点） |
| 配对 t | 0.71 |
| Bootstrap 95% CI | [-0.0233, +0.0500] |
| CI 是否排除 0 | **否** |
| 重排更好 / 更差 / 持平 | 18 / 14 / 268 |

**结论：重排的收益在统计上不显著。** 置信区间横跨 0，符号检验是 18 胜 14 负 —— 跟抛硬币没区别。它把 Hit@1 从 90.3% 抬到 91.7%，代价是延迟涨了 **89 倍**。

失败面拆解：

- 向量 Hit@1 已经排错：29 / 300
- 重排后仍排错：25 / 300
- 两个系统都错：11 / 300 ← 真正的难点，重排救不回来
- 只有重排能救对：约 4 条

也就是说，重排能改善的空间本来就只剩 29 条，它救回 4 条、弄坏若干条，净赚 4。

## 四、怎么解读

**1. Hit@1 90% 不等于"这系统很准"，是这个任务偏简单。**
1,991 个段落里挑 3 个，池子只有对手的千分之几。真实场景是百万级文档库，指标会难看很多。报告里必须写清楚池子规模。

**2. MRR 0.94 vs Hit@1 0.90 —— 差距说明"正确答案基本都在，只是位置偶尔不对"。**
R@3 只有 0.67，但有 77 条查询在 top-3 里把 3–8 个正确答案全捞齐了。召回瓶颈才是主要矛盾，不是排序。

**3. 89 倍延迟换 1.3 个百分点，不建议上生产。**
`bge-reranker-base` 是 CPU 上跑的 ONNX，一次重排 20 篇约 2.3 秒。要么换更小的模型，要么改成对 top-3 之后的候选重排，要么只在低置信度查询上触发。

**4. 这个数字不能和 C-MTEB 排行榜直接比。**
T2Ranking 就是 C-MTEB 的 `T2Retrieval` 任务。`bge` 系列很可能在训练时见过它 —— 存在数据泄漏。公开榜上同类模型分数普遍低于本文。面试时主动说出来，比被问出来强。

## 五、已知局限

- **段落池 1,991 而非目标 2,000**：9 个 pid 在 collection 文件边界处缺失（`all_positive_passages_present` 通过，所有正确答案都在）。
- **只有 300 条查询**：CI 宽度约 ±0.037，能发现 4 个百分点以上的差异，更小的效应量需要更多查询。
- **单次运行**：延迟是单次测量，未做重复取中位数，机器负载会影响 p95。
- **只测检索**：不含 LLM 生成、答案质量、LangGraph 多轮改写路径。

## 六、复现

```bash
docker cp evaluation/t2ranking.py ragent-api-1:/tmp/t2r/eval_t2ranking.py
docker exec ragent-api-1 sh -c "cd /tmp/t2r && PYTHONPATH=/app python eval_t2ranking.py"
```

需要 `/tmp/t2r/` 下四个数据文件：`qrels.retrieval.dev.tsv`、`queries.dev.tsv`、`collection_prefix.tsv`、`collection_rest.tsv`、`dev.bm25.tsv`（均来自 HuggingFace `THUIR/T2Ranking` 的 `data/` 目录）。
