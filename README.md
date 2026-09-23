# Ragent · 项目知识库助手

面向项目资料的单知识库问答 Agent。LangGraph 先判断"该不该查"再决定检索，pgvector 向量召回叠加 cross-encoder 重排，三元组 FIFO 串行加租约恢复，保证并发下不乱序、不丢任务。

- 技术栈：FastAPI · LangGraph · PostgreSQL/pgvector · Redis · Vue 3
- 在线演示：<https://ragent.ashia.icu/>
- 介绍页：见本仓库 GitHub Pages

每个项目拥有独立资料与多个会话；只有一个知识库 Agent，没有人设选择，也没有手动 RAG 开关。开箱是干净的：无默认项目、示例资料、演示工具或内置密钥。

## 特性

- **先决策再检索**：模型先判断问题能否直接回答，只有需要证据时才走检索，避免无谓查询。
- **两阶段检索**：向量召回 20 个候选，cross-encoder 重排取 3 个；最多两轮，相同查询或无新证据不重试。
- **流式且可对齐**：回答逐 token 通过 `model.astream → Redis → 前端`推送；done 事件另带一份落库后的权威正文，断线重连或刷新后与数据库保持一致。
- **可靠执行**：请求落库后进入 FIFO 队列，执行身份固定为 `knowledge-base`，worker 维护租约、心跳与超时恢复。
- **多格式入库**：支持 `.pdf / .docx / .md / .markdown / .txt`，单文件最大 20 MB，保留标题路径、页码与块序号。

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

## 评测

产品运行时不加载测试/演示资料。`evaluation/` 单独保留合成检索语料、隔离故障注入脚本和真实运行记录；评测使用临时数据库及独立 Redis 队列，不向真实项目插入资料。复现方式见 `evaluation/README.md`，结果与限制见 `evaluation/REPORT.md`。

## 生产注意事项

当前是本地单用户应用。生产发布前需自行配置鉴权、HTTPS 和网络访问边界。
