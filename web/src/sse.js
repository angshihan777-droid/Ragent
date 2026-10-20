// 读一次请求的 SSE 流：边收 token 边回调实时追加，收到 done 就 resolve 结果。
// 决策：用 fetch + ReadableStream 而非 EventSource。
// 面试理由：EventSource 只能 GET 且会自动重连、重复触发；我们的链路是
// 「先 POST 拿 id 再 GET stream」，由这里做受控重连：只在网络错误 / 5xx /
// 流未收到 done 时重试，且重试不带 EventSource 的隐式副作用。
//
// credentials: "include" 是身份隔离的必要条件：身份存在 httpOnly Cookie 里，
// 跨源（dev 下 5173 → 8000）的 fetch 默认不带 Cookie，漏了这一项的表现是
// 「提问成功但流里是另一个身份的上下文」或直接 404，而不是显式报错。
// 注意不是 withCredentials——那是 XHR/EventSource 的写法，对 fetch 无效。
const RETRY_DELAYS_MS = [600, 1500];

function abortableSleep(ms, signal) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    if (!signal) return;
    const onAbort = () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    if (signal.aborted) return onAbort();
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

async function readOnce(url, onToken, onSources, onStep, signal) {
  const res = await fetch(url, { signal, credentials: "include" });
  if (!res.ok) {
    const error = new Error("SSE 连接失败: " + res.status);
    // 4xx 是身份/资源问题，重试没有意义；5xx 与 429 才值得等下一轮。
    error.retryable = res.status >= 500 || res.status === 429;
    throw error;
  }
  if (!res.body) {
    const error = new Error("SSE 响应没有可读流");
    error.retryable = true;
    throw error;
  }
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
  const error = new Error("流已结束但未收到结果");
  error.retryable = true;
  throw error;
}

export async function readStream(url, onToken, onSources, onStep, signal, options = {}) {
  const retries = options.retries ?? RETRY_DELAYS_MS.length;
  for (let attempt = 0; ; attempt++) {
    try {
      return await readOnce(url, onToken, onSources, onStep, signal);
    } catch (error) {
      if (signal?.aborted || error.retryable === false || attempt >= retries) throw error;
      if (options.onReconnect) options.onReconnect(attempt + 1);
      const delay = RETRY_DELAYS_MS[Math.min(attempt, RETRY_DELAYS_MS.length - 1)];
      await abortableSleep(delay, signal);
    }
  }
}
