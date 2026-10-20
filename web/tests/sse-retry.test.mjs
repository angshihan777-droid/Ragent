// 验证 SSE 在「连接正常但没收到 done」时会重连，并从第二次连接拿到终态。
// 用本地 HTTP server 模拟，不依赖真实后端或模型。
import http from "node:http";
import { readStream } from "../src/sse.js";

let hits = 0;
const server = http.createServer((req, res) => {
  hits += 1;
  res.writeHead(200, { "Content-Type": "text/event-stream" });
  if (hits === 1) {
    res.write('event: step\ndata: {"step":{"key":"1","node":"decide","status":"running"}}\n\n');
    res.end();
    return;
  }
  res.write('event: done\ndata: {"status":"done","content":"ok"}\n\n');
  res.end();
});

await new Promise((resolve) => server.listen(0, resolve));
const port = server.address().port;
const started = Date.now();
const result = await readStream(
  `http://127.0.0.1:${port}/stream`,
  () => {},
  () => {},
  () => {},
  undefined,
  { retries: 2 },
);
server.close();
console.log(JSON.stringify({ result, hits, elapsedMs: Date.now() - started }));
if (result.content !== "ok" || hits !== 2) process.exit(1);
