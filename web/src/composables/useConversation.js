import { ref, reactive, computed, watch, nextTick, onBeforeUnmount } from "vue";
import { store } from "../store.js";
import { api } from "../api.js";
import { readStream } from "../sse.js";

export function useConversation() {
const messages = ref([]);      // {role, content, pending, error, sources}
const input = ref("");
const sending = ref(false);
const listEl = ref(null);
// 流式期间是否自动贴底。用户一旦往上翻就交还滚动控制权，
// 否则每来一个 token 都被拽回底部，根本没法回看前文。
const stickToBottom = ref(true);
const NEAR_BOTTOM = 80;
function onListScroll() {
  const el = listEl.value;
  if (!el) return;
  stickToBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM;
}

let viewVersion = 0;
let streamController;
const historyError = ref("");
const historyLoading = ref(false);
onBeforeUnmount(() => { viewVersion++; streamController?.abort(); });
const steps = ref([]);         // [{key,label,icon,status}] status: pending|running|done
const sources = ref([]);       // [{title,content}]
const tracing = ref(null);     // 点击溯源时展开的那条 {title,content}
const runState = ref("idle");  // idle | running | done | error

const thread = computed(() => store.currentThread);
const creatingThread = ref(false);
async function startConversation() {
  if (!store.currentProjectId || creatingThread.value) return;
  const projectId = store.currentProjectId;
  creatingThread.value = true; historyError.value = "";
  try {
    const created = await api.createThread(projectId, "新会话");
    if (store.currentProjectId !== projectId) return;
    await store.loadProjectDetail();
    if (store.currentProjectId === projectId) await store.selectThread(created.id);
  } catch (e) { if (store.currentProjectId === projectId) historyError.value = e.message; }
  finally { creatingThread.value = false; }
}

const STEP_ICONS = { context: "01", decide: "02", retrieve: "03", evidence: "04", rewrite: "05", answer: "06", validate: "07" };

async function scrollToBottom(force = false) {
  if (!force && !stickToBottom.value) return;
  await nextTick();
  if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight;
}
// 供"回到底部"浮标调用：强制贴底并重新开启跟随。
function jumpToBottom() {
  stickToBottom.value = true;
  scrollToBottom(true);
}

function resetPanel() {
  steps.value = []; sources.value = []; tracing.value = null; runState.value = "idle";
}

watch(
  () => store.currentThreadId,
  async (id) => {
    const version = ++viewVersion;
    streamController?.abort();
    sending.value = false;
    input.value = "";
    messages.value = []; resetPanel(); historyError.value = "";
    stickToBottom.value = true;
    historyLoading.value = !!id;
    if (!id) return;
    try {
      const history = await api.listThreadMessages(id);
      if (version !== viewVersion) return;
      messages.value = history.map(m => ({ role: m.role, content: m.content, error: !!m.error, sources: m.sources || [] }));
      const latest = [...history].reverse().find(m => m.role === "assistant");
      if (latest) {
        sources.value = latest.sources || [];
        steps.value = (latest.steps || []).map(step => ({ ...step, icon: STEP_ICONS[step.node] || "·" }));
        runState.value = latest.error ? "error" : "done";
      }
      await scrollToBottom(true);
    } catch (e) {
      if (version === viewVersion) historyError.value = "加载对话失败：" + e.message;
    } finally {
      if (version === viewVersion) historyLoading.value = false;
    }
  },
  { immediate: true }
);

function send() {
  const text = input.value.trim();
  if (!text || sending.value || historyLoading.value || !thread.value) return;
  input.value = "";
  sendText(text);
}

// 主动中断本轮生成：abort 掉 SSE 读取，把占位气泡落成"已停止"。
// 已有的 AbortController 原来只在切换会话/卸载时用，这里暴露给 UI。
function stop() {
  if (!sending.value) return;
  streamController?.abort();
}

// run_id 标识每次节点执行，补检索不会覆盖第一轮步骤。
function applyStep(step) {
  const node = steps.value.find(s => s.key === step.key);
  if (node) Object.assign(node, step);
  else steps.value.push({ ...step, icon: STEP_ICONS[step.node] || "·" });
}

async function sendText(text) {
  if (sending.value || !thread.value) return;
  sending.value = true;
  const version = viewVersion;
  const threadId = thread.value.id;
  const controller = new AbortController();
  streamController = controller;
  // 新一轮：清空上一轮的步骤与来源
  steps.value = [];
  sources.value = []; tracing.value = null; runState.value = "running";
  messages.value.push({ role: "user", content: text });
  const reply = reactive({ role: "assistant", content: "", pending: true, error: false, sources: [] });
  messages.value.push(reply);
  // 自己发的消息一定要贴底，不受之前的手动上翻影响。
  stickToBottom.value = true;
  await scrollToBottom(true);

  try {
    const { request_id } = await api.createRequest(threadId, text);
    if (version !== viewVersion) return;
    const result = await readStream(
      api.streamUrl(request_id),
      (token) => {
        if (version !== viewVersion) return;
        if (reply.pending) reply.pending = false;
        reply.content += token;
        scrollToBottom();
      },
      (hits) => {
        if (version !== viewVersion) return;
        // 命中资料先于正文到达：填右栏「命中资料」，也留一份在气泡上
        sources.value = hits;
        reply.sources = hits;
        scrollToBottom();
      },
      (step) => { if (version === viewVersion) applyStep(step); },
      controller.signal
    );
    if (version !== viewVersion) return;
    reply.pending = false;
    if (result.status === "done") {
      reply.content = result.content || reply.content || "(空回复)";
      runState.value = "done";
    } else {
      reply.error = true;
      reply.content = result.error || "本轮执行未完成，请稍后重试。";
      runState.value = "error";
    }
  } catch (e) {
    if (version !== viewVersion) return;
    reply.pending = false;
    if (e.name === "AbortError") {
      // 用户主动停止：保留已生成的内容，不当成错误红框。
      reply.content = reply.content ? reply.content + "\n\n_（已停止生成）_" : "已停止生成。";
      runState.value = "done";
    } else {
      reply.error = true;
      reply.content = "请求出错: " + e.message;
      runState.value = "error";
    }
  } finally {
    if (version === viewVersion) {
      // 收尾：没有 running 状态残留的转圈图标。失败标红，中断标未完成。
      const leftover = runState.value === "error" ? "error" : "idle";
      for (const step of steps.value) if (step.status === "running") step.status = leftover;
      sending.value = false;
      await scrollToBottom();
    }
  }
}

return { messages, input, sending, listEl, historyError, historyLoading, steps, sources, tracing, runState, thread, creatingThread, startConversation, send, sendText, stop, stickToBottom, onListScroll, jumpToBottom };
}
