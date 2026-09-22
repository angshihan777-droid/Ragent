# UI 改造验证

## 日常检查

在仓库根目录执行：

```powershell
npm test --prefix web
python -m unittest discover -s backend/tests -v
npm run build --prefix web
```

前端单测覆盖匹配度边界、项目切换竞态/会话记忆、SSE 事件透传。
后端单测替换数据库和模型调用，检查来源 ID、重复文本归属、相似度与 SQL 契约，不下载模型、不调用 LLM。

## 浏览器回归

先启动 `npm run dev --prefix web -- --host 127.0.0.1`。
测试需要 Playwright（本机安装或工具运行时自带），默认使用无头 Chromium。
如使用自带运行时，将 `PLAYWRIGHT_MODULE` 设为该运行时 `playwright` 包的绝对路径；如本机安装 Edge，可用：

```powershell
$env:BROWSER_CHANNEL = 'msedge'
npm run test:ui --prefix web
```

可选环境变量：`TEST_URL`（默认 `http://127.0.0.1:5173`）、`SCREENSHOT_PATH`（截图绝对路径）。

浏览器测试拦截全部后端请求，**不会新增或删除真实资料/会话，也不会消费 LLM 配额**。覆盖：

- 右栏上下双卡片同时显示，无 Tab；执行状态、完成进度、失败状态。
- 项目下多会话、跨项目切换、新建/删除会话、返回对话。
- 左右栏鼠标拖拽、键盘调宽、宽度记忆、收起/展开。
- 主按钮与轻量按钮 hover 色、原文弹窗与 Escape 关闭。
- 历史/请求迟到时不串会话；缺失匹配度不伪造。
- 390px 窄屏不横向溢出，无浏览器运行错误。

## 匹配度契约

`source.similarity` 是 pgvector 余弦相似度（范围 -1 至 1），前端以百分比展示，
不是重排模型分数或回答正确率。重排仍决定结果顺序。
旧后端缺少该字段时显示“暂未提供”。来源事件同时携带 `document_id` 和 `chunk_id`。
无需数据库迁移；已运行的 worker 要重启才能加载新的来源字段。

执行过程与来源沿用本轮 SSE 临时状态，刷新/重新进入会话不恢复历史来源；聊天历史仍从后端读取。
