<script setup>
// 对话页：中间对话窗口 + 右侧上下双卡片（执行过程 / 命中资料与匹配度）。
// 发送走「POST 拿 id → SSE 流式」：token 实时追加，step 点亮计划进度，sources 填命中资料。
import { ref, reactive, computed, watch, nextTick, onBeforeUnmount } from "vue";
import { store } from "../store.js";
import { api } from "../api.js";
import { readStream } from "../sse.js";
import SourceDialog from "../components/SourceDialog.vue";
import ResizeHandle from "../components/ResizeHandle.vue";
import ExecutionPanel from "../components/ExecutionPanel.vue";
import { usePreference } from "../composables/usePreference.js";
import MessageBubble from "../components/MessageBubble.vue";

const messages = ref([]);      // {role, content, pending, error, sources}
const input = ref("");
const sending = ref(false);
const listEl = ref(null);

const panelWidth = usePreference("ragent.panelWidth", 340);
panelWidth.value = Math.min(480, Math.max(280, panelWidth.value));
const panelCollapsed = usePreference("ragent.panelCollapsed", false);
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

const STEP_ICONS = { context: "💬", decide: "🧭", retrieve: "📚", evidence: "🔎", rewrite: "↻", answer: "✍️", validate: "✓" };

async function scrollToBottom() {
  await nextTick();
  if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight;
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
    historyLoading.value = !!id;
    if (!id) return;
    try {
      const history = await api.listThreadMessages(id);
      if (version !== viewVersion) return;
      messages.value = history.map(m => ({ role: m.role, content: m.content, sources: m.sources || [] }));
      const latest = [...history].reverse().find(m => m.role === "assistant");
      if (latest) {
        sources.value = latest.sources || [];
        steps.value = (latest.steps || []).map(step => ({ ...step, icon: STEP_ICONS[step.node] || "·" }));
        runState.value = "done";
      }
      await scrollToBottom();
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
  await scrollToBottom();

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
      reply.content = "执行失败: " + (result.error || "未知错误");
      runState.value = "error";
    }
  } catch (e) {
    if (version !== viewVersion) return;
    reply.pending = false;
    reply.error = true;
    reply.content = "请求出错: " + e.message;
    runState.value = "error";
  } finally {
    if (version === viewVersion) {
      if (runState.value === "error") for (const step of steps.value) if (step.status === "running") step.status = "error";
      sending.value = false;
      await scrollToBottom();
    }
  }
}
</script>
<template>
  <div class="chat-wrap">
    <div v-if="!thread" class="placeholder">
      <p>先在左侧选择或新建一个会话，就能开始对话。</p>
    </div>
    <template v-else>
      <!-- 中栏：对话窗口 -->
      <section class="chat">
        <header class="chat-head">
          <div class="titles">
            <div class="t">{{ thread.title }}</div>
            <div class="sub">
              {{ store.currentProject?.name }} · 知识库助手
              <span class="rag on">自主检索</span>
            </div>
          </div>
          <button class="quiet panel-toggle" :aria-expanded="!panelCollapsed" @click="panelCollapsed = !panelCollapsed">{{ panelCollapsed ? '展开右栏' : '收起右栏' }}</button>
        </header>

        <div ref="listEl" class="list">
          <p v-if="historyLoading" class="empty">加载对话…</p>
          <p v-if="historyError" role="alert">{{ historyError }}</p>
          <p v-if="messages.length === 0" class="empty">
            问点什么吧。助手会按需检索本项目资料，检查证据后回答。
          </p>
          <MessageBubble
            v-for="(m, i) in messages"
            :key="i"
            :role="m.role"
            :content="m.content"
            :pending="m.pending"
            :error="m.error"
            :sources="m.sources || []"
            @trace="tracing = $event"
          />
        </div>

        <div class="composer">
          <textarea
            v-model="input"
            rows="2"
            placeholder="输入问题，回车发送（Shift+回车换行）"
            @keydown.enter.exact.prevent="send"
          />
          <button :disabled="sending || historyLoading || !input.trim()" @click="send">
            {{ sending ? "发送中" : "发送" }}
          </button>
        </div>
      </section>

      <ResizeHandle v-if="!panelCollapsed" v-model="panelWidth" :min="280" :max="480" reverse label="调整右栏宽度" />
      <aside v-if="!panelCollapsed" class="right-rail" :style="{ width: panelWidth + 'px' }">
        <ExecutionPanel :steps="steps" :sources="sources" :run-state="runState" :thread="thread"
          :project-name="store.currentProject?.name"  @trace="tracing = $event" />
      </aside>

      <SourceDialog v-if="tracing" :source="tracing" @close="tracing = null" />
    </template>
  </div>
</template>

<style scoped>
.chat-wrap { min-height: 0; display: flex; height: 100%; width: 100%; }
.chat { overflow: hidden; display: flex; flex-direction: column; height: 100%; flex: 1; min-width: 0; padding: 20px 28px; box-sizing: border-box; }
.placeholder { margin: auto; color: var(--muted); }
.chat-head { display: flex; align-items: center; justify-content: space-between; padding: 4px 4px 14px; border-bottom: 1px solid var(--line); }
.titles .t { font-size: 18px; font-weight: 600; }
.titles .sub { font-size: 13px; color: var(--muted); margin-top: 4px; display: flex; align-items: center; gap: 8px; }
.rag { font-size: 11px; padding: 2px 9px; border-radius: 999px; background: rgba(0,0,0,0.05); color: var(--muted); }
.rag.on { background: var(--accent-soft); color: var(--accent); }
.list { min-height: 0; flex: 1; overflow-y: auto; padding: 16px 4px; }
.empty { color: var(--muted); text-align: center; margin-top: 40px; }
.composer { display: flex; gap: 12px; align-items: flex-end; padding: 12px 4px 4px; border-top: 1px solid var(--line); }
.composer textarea { flex: 1; }
.composer button { white-space: nowrap; height: 44px; }
.right-rail { flex-shrink: 0; max-width: 40%; min-width: 260px; height: 100%; }
.titles { min-width: 0; }
.titles .t { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.titles .sub { flex-wrap: wrap; }
.panel-toggle { font-size: 12px; flex-shrink: 0; }
.composer textarea { min-width: 0; max-height: 28dvh; }
@media (max-width: 760px) {
  .chat-wrap { flex-direction: column; overflow: auto; }
  .chat { flex: 1 0 60dvh; padding: 14px; height: auto; }
  .right-rail { width: 100% !important; max-width: none; min-width: 0; height: auto; }
}
</style>