# Ragent Harness 改造

| 状态 | 已完成内容 | 验证 |
|---|---|---|
| ✅ 已完成 | 安全防护、Token 统计与成本配置、检索容错、worker 健康检查、SSE 断线重连、CI | 后端 146 passed；前端 SSE 测试与构建通过 |
| ✅ 已完成 | 修复限流器内存增长（超过 2048 个身份时清理过期键）；统计接口改用只读 `get_cost_prices`，GET 不再创建配置行 | 后端 148 passed |
| ✅ 已完成 | 每步耗时 + trace_id：`step` 事件记录 `duration_ms`，前端执行面板显示；trace_id 使用 request_id | 后端 149 passed；前端构建通过 |
| ✅ 已完成 | 20 题检索回归 + CI 门禁：临时 PG、真实 embedding/rerank，阈值 Hit@1 ≥ 0.85、MRR@3 ≥ 0.90、Recall@3 ≥ 0.95 | 实测 20 题：Hit@1 = 1.0、MRR@3 = 1.0、Recall@3 = 1.0 |
| ✅ 已完成 | LangGraph PostgresSaver 断点续传：API/worker 启动时初始化，同一 request 中断后从最后 checkpoint 续跑，已完成节点不重跑 | 集成探针：cancel 后 `next=('b',)`，resume 后 `y=2`，节点 a 只执行 1 次 |
| ✅ 已完成 | 引用一致性检查（轻量幻觉检测）：逐句比对带 `[S#]` 的结论与被引片段词面重叠，低重叠追加「未找到足够依据」警告 | 6 个单测；后端 158 passed、2 skipped |
| ✅ 已完成 | Redis 原子滑动窗口限流（Lua，Redis 故障回退进程内）+ `audit_logs` 记录限流与注入拦截 | 实测第 11 次 429；`audit_logs` 写入 `retry_after=60` 与 `rule_id` |
| ✅ 已完成 | 生产化 Docker：非 root 用户、镜像不带 `--reload`、api/worker healthcheck；新增 `docs/ADR.md` 记录 5 个关键取舍 | 容器 healthy，uid=10001；`/ready` 返回 200 |
| ✅ 已完成 | 介绍页新增「工程能力」动画区（安全 / Token / 故障恢复 / 断点续传）；主演示加入 Token 成本与 SSE 断线重连；对话图补 `verify`；桌面与移动端布局收紧 | 1280 与 600 宽度预览通过；标签 / 重播 / 自动播放正常；控制台无 error |
