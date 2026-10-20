# Architecture Decision Records

## ADR-001：每个请求单独 checkpoint

**Context**：worker 可能在任意节点崩溃；同一会话的多个请求不能互相读到对方的中间状态。

**Decision**：`PostgresSaver` 的 `thread_id` 使用 `app_thread_id:request_id`，而不是只使用会话 id。应用层的历史查询仍使用真实会话 id。

**Consequences**：

- 同一请求重试会从最后一个完成的节点续跑，已完成节点不重复执行。
- 新请求天然隔离，不会继承上一轮的 `sources` / `rounds`。
- checkpoint 行数随请求增长，需要定期清理已完成请求的 checkpoint。
- 续跑时 `usage` 只累计本次剩余模型调用；中断前已经发生的 Token 不会重复计入，成本会略低于实际消耗。

**Alternatives**：只用会话 id 做 checkpoint——会把不同请求的状态串在一起；不持久化状态——worker 崩溃就整轮重跑。

## ADR-002：SSE 只做实时通道，PostgreSQL 是终态权威

**Context**：Redis 推送可能丢失，用户也可能在生成中途刷新页面。

**Decision**：SSE 负责增量体验；每 2 秒从 PostgreSQL 对账终态；前端对网络错误/5xx/未收到 `done` 做受控重连，重连后以 `done` 的完整正文覆盖。

**Consequences**：

- 断线后能补读完整回答，不会停在「正在处理」。
- 前端可能短暂看到部分正文，终态到达后被权威正文覆盖。
- 不能依赖 Redis 消息做计费或审计，真相以数据库为准。

## ADR-003：Redis FIFO + 租约/心跳保证至少一次执行

**Context**：多 worker 并发时，同一会话必须串行，且 worker 崩溃后任务不能永久丢失。

**Decision**：按 `(user_id, agent_id, thread_id)` 分组 FIFO；执行权通过 `lease_owner` + 心跳获取；reaper 回收超时租约并重投。

**Consequences**：

- 至少一次执行，重复投递由 `claim_run` 的原子状态转换挡住。
- 外部模型调用不是 exactly-once，重试可能重复计费。
- 需要 `attempts` 上限防止毒消息卡死队列。

## ADR-004：两阶段检索，rerank 超时可降级

**Context**：向量召回快但粗，cross-encoder 精排准但慢；检索链路不能因为精排卡住而整体失败。

**Decision**：向量召回 20 个候选，cross-encoder 取 top-3；embedding 3 秒、召回 5 秒、rerank 8 秒；只有 rerank 超时降级为召回顺序。

**Consequences**：

- 精排故障时仍能返回可用结果，并在日志中留下 degrade 记录。
- embedding/召回失败明确报「检索失败」，不伪装成「没有资料」。
- 降级结果的质量低于正常精排，评测需要区分两条路径。

## ADR-005：身份隔离与配置按 owner 存储

**Context**：API Key 和项目数据不能跨用户共享；成本单价也不能是全局唯一值。

**Decision**：浏览器 Cookie / Bearer 令牌最终收敛为 `owner_id`；项目、会话、资料、模型配置和成本单价都按 owner 隔离；统计接口只读当前 owner。

**Consequences**：

- 不同身份之间互不可见，成本统计不会混算。
- Cookie 是隔离标识而不是强鉴权；正式对外仍需接入登录体系。
- 新身份首次读配置时由环境变量播种，之后以数据库为准。
