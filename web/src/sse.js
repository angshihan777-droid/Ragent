// 读一次请求的 SSE 流：边收 token 边回调实时追加，收到 done 就 resolve 结果。
// 决策：用 fetch + ReadableStream 而非 EventSource。
// 面试理由：EventSource 只能 GET 且流结束后会自动重连、重复触发；
// 我们的链路是「先 POST 拿 id 再 GET stream」，用 reader 能读完 done 就主动收手，不重连。
export async function readStream(url, onToken, onSources, onStep, signal) {
  const res = await fetch(url, { signal });
  if (!res.ok) throw new Error("SSE 连接失败: " + res.status);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  // 逐块读取，按 SSE 的空行分隔切出完整事件；token 边到边追加，done 收尾返回
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const lines = block.split("\n");
      // 忽略 ": keepalive" 心跳注释行（无 event/data）
      const dataLine = lines.find((l) => l.startsWith("data:"));
      if (!dataLine) continue;
      const data = JSON.parse(dataLine.slice(5).trim());
      if (lines.some((l) => l === "event: step")) {
        // 过程链条：某节点开始(running)/完成(done)，回调给右栏更新步骤进度
        if (onStep) onStep(data.step);
        continue;
      }
      if (lines.some((l) => l === "event: sources")) {
        // 检索命中：先于正文到达，回调给页面展示「本次检索到了什么」
        if (onSources) onSources(data.sources);
        continue;
      }
      if (lines.some((l) => l === "event: token")) {
        // 回复增量：实时回调给页面追加，不结束流
        onToken(data.token);
        continue;
      }
      if (lines.some((l) => l === "event: done")) {
        // 终态：主动收手，返回完整结果供页面兜底落地
        reader.cancel();
        return data;
      }
    }
  }
  throw new Error("流已结束但未收到结果");
}
