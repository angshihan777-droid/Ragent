# 故障记录

## 2026-10-15：提问后一直「正在处理…」，且速度极慢

### 现象

- 发出问题后气泡停在「正在处理…」，最终出现「本轮执行未完成，请稍后重试」。
- 偶尔能跑完，但一次简单的「你好」要等分钟级。
- 点击「停止生成」没有反应。
- 切换页面后正在生成的回答会中断。

### 原因（四个叠在一起，逐个才排干净）

**1. 代码缺陷：worker 启动即失败（本次排查中自己引入的）**

给模型客户端加超时配置时改坏了 `app/agent/graph.py`：

- 用了 `get_settings()` 却没 `from app.config import get_settings` → `NameError`；
- `ChatOpenAI(...)` 里 `model=` 写了两次 → `SyntaxError: keyword argument repeated`。

worker 进程导入这个模块就崩，任务永远卡在 `pending`。这两个错误只在运行时暴露，
静态读代码时那几行看起来完全正常。

**2. 读超时太短（60 秒）**

`ChatOpenAI(timeout=60)` 是原始配置。OpenAI 兼容服务在繁忙时，非流式请求会**在拿到结果前
持续发送空行**来保持连接（流式请求对应 SSE 的 `: keep-alive` 注释）；排队时间可以超过 60 秒，
于是客户端在真正的响应到达之前就先超时了。

这里要澄清一个常见误判：**不是「解析器没跳过空行」**。`openai` SDK 和 `httpx` 本来就会正确
跳过多余空白、一直读到有效 JSON，空行不会导致解析失败。真正的失败点是读超时。

**3. 推理档位：服务端默认 high，一次问候 41 秒**

`deepseek-flash` / `deepseek-v4-pro` 是推理模型，服务端默认档位是 `high`。实测同一句
「只回复两个字：你好」：

| 档位 | 耗时 |
|---|---|
| 默认（high） | 41.2s |
| `reasoning_effort=low` | **0.7s** |

一次问答要调 2~3 次模型（决策、可选补查、生成），默认档累积起来就是分钟级等待。

**4. 排查时看不到堆栈**

`app/worker.py` 原来只记 `type(exc).__name__`，日志里只有一行 `exception=ValueError`，
没有 traceback，等于把根因丢掉了。

### 改正

| 改动 | 文件 |
|---|---|
| 补齐 `get_settings` 导入、去掉重复的 `model=` 参数 | `backend/app/agent/graph.py` |
| 超时改为可配置、默认 180s；httpx 的 read 超时同步放宽 | `backend/app/config.py`、`graph.py` |
| 新增推理强度配置：环境变量兜底 + 每个身份可覆盖 | `config.py`、`schema.sql`、`repositories/llm_config.py`、`services/llm_config.py` |
| 配置接口与前端页面暴露「推理强度」下拉 | `schemas.py`、`routers/config.py`、`web/src/api.js`、`web/src/pages/ConfigPage.vue` |
| 异常改记 `log.exception`，保留完整堆栈 | `backend/app/worker.py` |
| 切换页面不再中断生成（`<keep-alive>`） | `web/src/App.vue` |
| 停止按钮立即回到可发送状态 | `web/src/composables/useConversation.js` |

### 验证

```bash
# 1. 纯逻辑单测
cd backend && python -m pytest -q          # 90 passed

# 2. 端到端冒烟（真实 HTTP + 真实 worker + 真实模型）
docker compose cp backend/scripts/e2e_smoke.py api:/app/e2e_smoke.py
docker compose exec -T api python /app/e2e_smoke.py
#    -> [通过] 整条链路 OK，总耗时 4.9s
```

### 两个需要知道的边界

- **「停止生成」只中断前端读取**：服务端那次 run 仍会跑完并落库（数据库才是结果的权威来源），
  刷新或切回会话会看到已经完成的回答。要真正取消服务端执行，需要额外的取消信号机制。
- **模型配置按身份隔离**：换浏览器 / 换身份后要在「模型配置」页重新填一次密钥，
  这是有意设计（共用密钥等于让别人花掉你的额度）。
