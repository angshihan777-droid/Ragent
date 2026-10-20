# Ragent · 项目知识库助手

面向项目资料的单知识库问答 Agent。LangGraph 先判断"该不该查"再决定检索，pgvector 向量召回叠加 cross-encoder 重排，三元组 FIFO 串行加租约恢复，保证并发下不乱序、不丢任务。

- 技术栈：FastAPI · LangGraph · PostgreSQL/pgvector · Redis · Vue 3
- 在线演示：<https://ragent.ashia.icu/>
- 介绍页：见本仓库 GitHub Pages

每个项目拥有独立资料与多个会话；只有一个知识库 Agent，没有人设选择，也没有手动 RAG 开关。开箱是干净的：无默认项目、示例资料、演示工具或内置密钥。

## 特性

- **先决策再检索，但判据是客观事实**：该不该查资料，看的是「项目里有没有资料」，不是「问题像不像常识」。项目非空时，凡涉及某个主题、概念、命令或做法的提问一律先检索再回答——避免出现「资料里明明写着，却凭模型常识直接答」；只有问候寒暄、改写用户本次粘贴的文本、以及问助手自身这三类才直接回答。项目为空时不会空跑一次检索。
- **两阶段检索**：向量召回 20 个候选，cross-encoder 重排取 3 个；最多两轮，相同查询或无新证据不重试。
- **流式且可对齐**：回答逐 token 通过 `model.astream → Redis → 前端`推送；done 事件另带一份落库后的权威正文，断线重连或刷新后与数据库保持一致。
- **可靠执行**：请求落库后进入 FIFO 队列，执行身份固定为 `knowledge-base`，worker 维护租约、心跳与超时恢复。
- **多格式入库**：支持 `.pdf / .docx / .md / .markdown / .txt`，单文件最大 20 MB，保留标题路径、页码与块序号。

## Harness 能力（当前实现）

| 能力 | 实现 | 边界 |
|---|---|---|
| 输入防护 | Prompt 注入检测（NFKC / 去零宽 / 中英文规则），命中直接 400 且不落库 | 只拦已知的指令覆盖与提示词套取话术，防不住语义改写 |
| 限流 | 按身份每分钟 10 次，Redis 原子滑动窗口（Lua）；Redis 故障回退进程内；超限 429 + `Retry-After` | 多副本共享 Redis 计数 |
| 安全审计 | `audit_logs` 记录 `rate_limited` 与 `prompt_injection_blocked`，只存规则编号、长度、重试秒数 | 不记录用户原文 |
| Token 账本 | `agent_runs.usage` 汇总输入/输出/调用次数，右侧执行面板显示本轮消耗，「使用统计」页按 7/30 天聚合 | 只统计当前身份；单价在「模型配置」页按身份填写后估算 |
| 检索容错 | embedding 3s、召回 5s、rerank 8s 分段超时；rerank 超时降级为召回顺序 | embedding/召回失败明确报「检索失败」，不伪装成「没资料」 |
| 回归测试 | `pytest -q` 覆盖注入、限流、统计、检索降级，全部不依赖 PG/Redis/模型 | 纯逻辑测试，不替代端到端评测 |
| 运行可靠性 | worker 每 5 秒刷新 Redis 心跳（15 秒 TTL）；`/ready` 返回 worker 状态、排队/执行中数量和最早排队时长；前端每 15 秒轮询并在 worker 掉线时显示提示 | 心跳按进程；多副本部署共享同一个 Redis |
| 持续集成 | GitHub Actions 跑后端 `pytest` 与前端 `npm test` + `npm run build` | 需要仓库启用 Actions |
| 断点续传 | LangGraph `PostgresSaver` 持久化每个请求的图状态；worker 重启后从最后 checkpoint 续跑，已完成节点不重复执行 | 需要 `langgraph-checkpoint-postgres` 与 psycopg；checkpoint 表随启动创建 |
| 引用一致性 | 逐句检查带 `[S#]` 的结论与被引片段词面重叠；低重叠追加警告 | 词面检查，不是语义级幻觉检测 |
| 生产镜像 | 非 root（uid 10001）；镜像不带 `--reload`，开发热重载由 compose 的 command 提供；api/worker 均有 healthcheck | 生产部署仍需 HTTPS 与真实登录体系 |

关键取舍见 [`docs/ADR.md`](docs/ADR.md)。

## 快速开始

```bash
# 1. 启动后端三件套（api / worker / postgres / redis）
docker compose up --build -d

# 2. 启动前端
cd web
npm install
npm run dev
```

打开前端后：

1. 进入「模型配置」页，填写任意 OpenAI 兼容服务信息（自定义地址 / DeepSeek 等）。模型需支持 JSON object 输出（`response_format`），结构化结果由后端严格校验。
2. 创建项目并上传 PDF、Markdown、DOCX 或 TXT，进入自动创建的首个会话开始提问。

## 配置

密钥与模型信息可以两种方式提供，二选一：

- 复制 `.env.example` 为 `backend/.env` 并填写；
- 或全部留空，改在应用「模型配置」页填写。

```env
DATABASE_URL=postgresql://ragent:ragent@postgres:5432/ragent
REDIS_URL=redis://redis:6379/0
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
```

数据库与 Redis 在 compose 中已给默认值，本地直接跑无需改动。

## 服务间鉴权（访问令牌）

浏览器侧仍是 Cookie 身份（那是隔离，不是鉴权）。服务调用方——外部 Agent 平台、脚本、CI——走 **Bearer 令牌**。两者最终收敛成同一个 `owner_id`，后面的归属校验只认这一个值，不关心它是从哪来的。

```bash
# 在 backend 目录下执行，读 .env 里的 DATABASE_URL
python -m app.tokens create --owner svc-opsmind --name opsmind-mcp
python -m app.tokens list
python -m app.tokens revoke --id <uuid>

# 容器里签发（不暴露数据库端口，这是本地最常用的方式）
docker compose exec api python -m app.tokens create --owner svc-opsmind --name opsmind-mcp
```

```bash
curl -H "Authorization: Bearer rag_xxx" http://localhost:8000/projects
```

- 明文令牌只在签发那一刻打印一次，库里只存 `sha256`；撤销是写 `revoked_at` 而不是物理删除，便于审计。
- 令牌映射到一个 `owner_id`，该身份的项目、会话、资料、模型配置与浏览器身份**完全隔离**，互相不可见。
- **不带 `Authorization` 头时行为与改造前完全一致**，前端无需任何改动。
- 令牌无效或已撤销返回 `401`；资源不归该身份返回 `404`（与「无权限」同一口径，避免拿 id 做存在性探测）。

## 对话图

```text
准备上下文 → 理解问题与决策
               ├─ 直接回答 / 澄清 → 回答 → 引用结构检查 → 结束
               └─ 检索与重排 → 证据检查
                                  ├─ 足够 → 回答
                                  ├─ 有可补查缺口 → 改写查询 → 检索与重排
                                  └─ 无法补足 / 到达上限 → 有限回答
```

- 检索最多两轮；相同查询、无新增证据或基础设施故障不会无限重试。
- 检索范围由后端注入项目 ID。资料不是指令，历史回复不是新的文档证据。
- 历史只取当前请求之前成功完成的问答，最多 12 轮、12000 字符预算。
- 引用结构检查只检查来源编号，不代表已验证所有语义；匹配度是向量余弦相似度，不是答案正确率。

## RAG 入库与检索

- PDF 按页提取并记录页码；无文本页显式拒绝，需先 OCR。
- Markdown 保留标题路径与代码块边界；DOCX 按正文顺序读取段落/表格，表格行带表头。
- 结构化块按实际 embedding tokenizer 切分，目标最多 384 tokens（含标题），长块最多重叠 48 tokens，句子边界优先。
- 保存标题路径、页码（若已知）、块序号和相对合并块的文本偏移。
- embedding 与重排模型缓存使用共享 Docker 卷，重建容器不重复下载权重。

重建索引（备份数据库、暂停写入后执行）：

```powershell
docker compose exec api python -m app.reindex
```

按文档原子替换索引并记录版本，重复执行不会重复重建。

## 界面

左栏项目 → 多会话，中间对话，右栏上下双卡片：执行过程 / 命中资料与匹配度。两侧可折叠与调整宽度。打开应用或切换项目默认显示空白对话入口，不自动打开旧会话；历史保留在左栏，需手动选择。

项目资料页与知识库图书馆共用资料管理组件，均可搜索、查看入库正文、编辑及删除。编辑使用版本校验避免覆盖他人修改，向量生成成功后才原子替换正文和索引。

## 目录结构

```text
Ragent/
├─ backend/            FastAPI + LangGraph + worker
├─ web/                Vue 3 前端
├─ evaluation/         隔离的检索评测（合成语料、故障注入、真实运行记录）
├─ docs/               文档
├─ index.html          产品介绍页（GitHub Pages）
└─ docker-compose.yml  开发拓扑：一条命令拉起三件套
```

## 测试

纯逻辑单元测试（不连数据库、Redis 和模型）：

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest -q
```

横向扩容 worker：`docker compose up -d --scale worker=3`。每个 worker 进程内默认并发 4 个 run，同一会话仍严格串行。

## 评测

产品运行时不加载测试/演示资料。`evaluation/` 单独保留合成检索语料、隔离故障注入脚本和真实运行记录；评测使用临时数据库及独立 Redis 队列，不向真实项目插入资料。复现方式见 `evaluation/README.md`，结果与限制见 `evaluation/REPORT.md`。

## 生产注意事项

当前是本地应用。服务间调用已支持 Bearer 令牌（见「服务间鉴权（访问令牌）」），生产发布前仍需自行配置 HTTPS、令牌轮换与网络访问边界。

多用户隔离的性质需要说清楚：浏览器首次访问时后端下发一个 httpOnly Cookie 作为身份标识，项目、会话、资料、消息、模型配置都按这个标识隔离，不同浏览器之间互相看不到对方的数据。但**浏览器这条路仍是隔离，不是鉴权**——身份标识本身就是唯一凭据，等同于密码，谁拿到谁就是那个用户，没有口令校验也没有登录态过期。因此配置页的身份标识不要截图外发，正式对外服务仍需接入真实登录体系（账号密码 / OAuth / SSO），把当前的标识降级为登录成功后才下发的会话标识。服务调用方请走上一节的访问令牌，那条路是有凭据校验的。
