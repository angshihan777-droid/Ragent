// 统一封装后端调用：把 API 契约收在一处，页面组件只管调用不拼 URL。
// 面试理由：接口地址/错误处理集中管理，改后端契约时只动这一个文件。
const BASE = "http://localhost:8000";

async function toJson(res) {
  // 后端出错时 detail 里有中文原因，透出来方便前端展示，而不是吞掉只报状态码
  if (!res.ok) {
    let detail = res.status + "";
    try {
      const body = await res.json();
      if (body && body.detail) detail = body.detail;
    } catch (_) {}
    throw new Error(detail);
  }
  // 204 无内容（删除）时不解析 body
  if (res.status === 204) return null;
  return res.json();
}

function get(path) {
  return fetch(BASE + path).then(toJson);
}
function send(method, path, body) {
  return fetch(BASE + path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).then(toJson);
}

export const api = {
  // ---- 项目 / Agent / 会话 ----
  listProjects: () => get("/projects"),
  createProject: (name, description) => send("POST", "/projects", { name, description }),
  deleteProject: (id) => send("DELETE", "/projects/" + id),

  listAgents: (projectId) => get("/projects/" + projectId + "/agents"),
  createAgent: (projectId, payload) => send("POST", "/projects/" + projectId + "/agents", payload),

  listThreads: (projectId) => get("/projects/" + projectId + "/threads"),
  createThread: (projectId, agentId, title) =>
    send("POST", "/projects/" + projectId + "/threads", { agent_id: agentId, title }),
  listThreadMessages: (threadId) => get("/threads/" + threadId + "/messages"),
  deleteThread: (threadId) => send("DELETE", "/threads/" + threadId),

  // ---- 资料（按项目） ----
  listDocuments: (projectId) => get("/documents?project_id=" + projectId),
  ingestDocument: (projectId, title, content) =>
    send("POST", "/documents", { project_id: projectId, title, content }),
  deleteDocument: (id) => send("DELETE", "/documents/" + id),

  // ---- 提问 ----
  // 落库拿 request_id 立即返回，不等执行
  createRequest: (thread_id, content) => send("POST", "/requests", { thread_id, content }),
  streamUrl: (request_id) => BASE + "/requests/" + request_id + "/stream",

  // ---- LLM 配置 ----
  getLLMConfig: () => get("/config/llm"),
  saveLLMConfig: (base_url, model, api_key) =>
    send("PUT", "/config/llm", { base_url, model, api_key: api_key || null }),
  listModels: (base_url, api_key) =>
    send("POST", "/config/llm/models", { base_url, api_key: api_key || null }),
};
