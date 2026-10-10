// 统一封装后端调用：把 API 契约收在一处，页面组件只管调用不拼 URL。
// 面试理由：接口地址/错误处理集中管理，改后端契约时只动这一个文件。
//
// 地址来源优先级：VITE_API_BASE > 同源相对路径。
// 决策：不再硬编码 localhost:8000——那样一部署到静态托管就会去连访问者本机的 8000 端口，
// 必然失败。开发态由 vite 代理把 /api 转发到后端，生产态可通过环境变量指向真实地址。
const BASE = (import.meta.env.VITE_API_BASE ?? "/api").replace(/\/$/, "");

async function toJson(res) {
  // 后端出错时 detail 里有中文原因，透出来方便前端展示，而不是吞掉只报状态码
  if (!res.ok) {
    let detail = res.status + "";
    try {
      const body = await res.json();
      if (body?.detail) detail = Array.isArray(body.detail) ? body.detail.map(item => item.msg).join("；") : body.detail;
    } catch (_) {}
    throw new Error(detail);
  }
  // 204 无内容（删除）时不解析 body
  if (res.status === 204) return null;
  return res.json();
}

// 身份放在 httpOnly Cookie 里，跨源请求默认不带 Cookie，所以每个出口都要 credentials: "include"。
// 收在 get/send 两个函数里就是为了不用在几十个调用点上各写一遍——唯一的例外是
// uploadDocument 的裸 fetch（multipart 不能用 send），那里单独补一份。
const CREDENTIALS = "include";

function get(path) {
  return fetch(BASE + path, { credentials: CREDENTIALS }).then(toJson);
}
function send(method, path, body) {
  return fetch(BASE + path, {
    method,
    credentials: CREDENTIALS,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).then(toJson);
}

export const api = {
  // ---- 项目 / 会话 ----
  listProjects: () => get("/projects"),
  createProject: (name, description) => send("POST", "/projects", { name, description }),
  deleteProject: (id) => send("DELETE", "/projects/" + id),

  listThreads: (projectId) => get("/projects/" + projectId + "/threads"),
  createThread: (projectId, title) =>
    send("POST", "/projects/" + projectId + "/threads", { title }),
  listThreadMessages: (threadId) => get("/threads/" + threadId + "/messages"),
  deleteThread: (threadId) => send("DELETE", "/threads/" + threadId),

  // ---- 资料（按项目） ----
  listDocuments: (projectId) => get("/documents?project_id=" + projectId),
  ingestDocument: (projectId, title, content) =>
    send("POST", "/documents", { project_id: projectId, title, content }),
  // 文件入库：PDF/Word/Markdown/txt，走 multipart，后端解析成文本再切块向量化
  uploadDocument: (projectId, fileObj, title) => {
    const fd = new FormData();
    fd.append("project_id", projectId);
    fd.append("file", fileObj);
    if (title) fd.append("title", title);
    // 这处是全文件唯一不走 send() 的请求（multipart 不能自己设 Content-Type），
    // credentials 必须手动补：漏了就是「上传返回 404 项目不存在」
    return fetch(BASE + "/documents/upload", { method: "POST", credentials: CREDENTIALS, body: fd }).then(toJson);
  },
  getDocument: (id) => get("/documents/" + id),
  updateDocument: (id, body) => send("PUT", "/documents/" + id, body),
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

  // ---- 身份（§3.7 身份可迁移） ----
  // Cookie 是 httpOnly 的，前端读不到，只能问后端「我是谁」
  getIdentity: () => get("/config/identity"),
  switchIdentity: (owner_id) => send("POST", "/config/identity", { owner_id }),
};
