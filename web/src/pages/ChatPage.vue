<script setup>
// 对话页：中间对话窗口 + 右侧「执行计划 / 命中资料」实时面板(与左栏合成三栏)。
// 发送走「POST 拿 id → SSE 流式」：token 实时追加，step 点亮计划进度，sources 填命中资料。
import { ref, computed, watch, nextTick } from "vue";
import { store } from "../store.js";
import { api } from "../api.js";
import { readStream } from "../sse.js";
import MessageBubble from "../components/MessageBubble.vue";

const messages = ref([]);      // {role, content, pending, error, sources}
const input = ref("");
const sending = ref(false);
const listEl = ref(null);

// 右栏：Tab（执行计划/命中资料）+ 本轮计划步骤 + 命中资料 + 溯源查看
const tab = ref("plan");       // "plan" | "sources"
const steps = ref([]);         // [{key,label,icon,status}] status: pending|running|done
const sources = ref([]);       // [{title,content}]
const tracing = ref(null);     // 点击溯源时展开的那条 {title,content}
const runState = ref("idle");  // idle | running | done | error

const thread = computed(() => store.currentThread);
const agent = computed(() => store.agentOf(thread.value));

// 后端 step 的 key → 展示用图标（emoji，零依赖，观感贴近参考稿）
const STEP_ICONS = { retrieve: "📚", agent: "🧠", tools: "🛠️", answer: "✍️" };

// 进入本轮先按「是否检索」铺开计划：检索(可选)→模型思考→生成回答。
// 工具调用是否发生取决于模型，所以不预置，收到 tools 事件时再插到「生成回答」前。
function buildPlan(useRag) {
  const plan = [];
  if (useRag) plan.push({ key: "retrieve", label: "检索知识库", icon: STEP_ICONS.retrieve, status: "pending" });
  plan.push({ key: "agent", label: "模型思考", icon: STEP_ICONS.agent, status: "pending" });
  plan.push({ key: "answer", label: "生成回答", icon: STEP_ICONS.answer, status: "pending" });
  return plan;
}

// 底部进度：已完成步数 / 总步数 + 百分比
const progress = computed(() => {
  const total = steps.value.length || 1;
  const done = steps.value.filter((s) => s.status === "done").length;
  return { done, total: steps.value.length, pct: Math.round((done / total) * 100) };
});
const runningLabel = computed(() => steps.value.find((s) => s.status === "running")?.label || "");

async function scrollToBottom() {
  await nextTick();
  if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight;
}

function resetPanel() {
  steps.value = []; sources.value = []; tracing.value = null; runState.value = "idle"; tab.value = "plan";
}

watch(
  () => store.currentThreadId,
  async (id) => {
    messages.value = []; resetPanel();
    if (!id) return;
    const history = await api.listThreadMessages(id);
    messages.value = history.map((m) => ({ role: m.role, content: m.content }));
    await scrollToBottom();
  },
  { immediate: true }
);

function send() {
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  sendText(text);
}

// 收到后端 step 事件：把对应计划步骤点亮为 running/done。
// tools 未预置——首次出现时插到「生成回答」前，保持计划清单顺序自然。
function applyStep(step) {
  let node = steps.value.find((s) => s.key === step.key);
  if (!node && step.key === "tools") {
    node = { key: "tools", label: "调用工具", icon: STEP_ICONS.tools, status: "pending" };
    const at = steps.value.findIndex((s) => s.key === "answer");
    steps.value.splice(at < 0 ? steps.value.length : at, 0, node);
  }
  if (!node) return;
  // 某步开始 running 时，把它前面还没结束的步骤补成 done（事件粒度粗时也不留半截）
  if (step.status === "running") {
    for (const s of steps.value) {
      if (s.key === step.key) break;
      if (s.status !== "done") s.status = "done";
    }
  }
  node.status = step.status;
}

async function sendText(text) {
  if (sending.value || !thread.value) return;
  sending.value = true;
  // 新一轮：按当前 Agent 是否检索铺开计划，从头展示
  steps.value = buildPlan(!!agent.value?.use_rag);
  sources.value = []; tracing.value = null; runState.value = "running"; tab.value = "plan";
  messages.value.push({ role: "user", content: text });
  const reply = { role: "assistant", content: "", pending: true, error: false, sources: [] };
  messages.value.push(reply);
  await scrollToBottom();

  try {
    const { request_id } = await api.createRequest(thread.value.id, text);
    const result = await readStream(
      api.streamUrl(request_id),
      (token) => {
        if (reply.pending) reply.pending = false;
        // 首个 token 到达＝开始生成回答：点亮「生成回答」并收尾前面的步骤
        applyStep({ key: "answer", status: "running" });
        reply.content += token;
        scrollToBottom();
      },
      (hits) => {
        // 命中资料先于正文到达：填右栏「命中资料」，也留一份在气泡上
        sources.value = hits;
        reply.sources = hits;
        scrollToBottom();
      },
      (step) => applyStep(step)
    );
    reply.pending = false;
    if (result.status === "done") {
      if (!reply.content) reply.content = result.content || "(空回复)";
      // 收尾：所有步骤置 done，进度拉满
      for (const s of steps.value) s.status = "done";
      runState.value = "done";
    } else {
      reply.error = true;
      reply.content = "执行失败: " + (result.error || "未知错误");
      runState.value = "error";
    }
  } catch (e) {
    reply.pending = false;
    reply.error = true;
    reply.content = "请求出错: " + e.message;
    runState.value = "error";
  } finally {
    sending.value = false;
    await scrollToBottom();
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
              {{ store.currentProject?.name }} · {{ agent?.name }}
              <span class="rag" :class="{ on: agent?.use_rag }">
                {{ agent?.use_rag ? "检索知识库" : "不检索" }}
              </span>
            </div>
          </div>
        </header>

        <div ref="listEl" class="list">
          <p v-if="messages.length === 0" class="empty">
            问点什么吧。{{ agent?.use_rag ? "助手会先检索本项目资料再回答。" : "该助手不检索资料，自由发挥。" }}
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
          <button :disabled="sending || !input.trim()" @click="send">
            {{ sending ? "发送中" : "发送" }}
          </button>
        </div>
      </section>

      <!-- 右栏：执行计划(Tab) + 命中资料(可点击溯源) -->
      <aside class="process">
        <div class="tabs">
          <button :class="{ on: tab === 'plan' }" @click="tab = 'plan'">
            <span class="tab-ico">⚡</span> 执行计划
          </button>
          <button :class="{ on: tab === 'sources' }" @click="tab = 'sources'">
            <span class="tab-ico">📄</span> 命中资料
            <span v-if="sources.length" class="tab-cnt">{{ sources.length }}</span>
          </button>
        </div>

        <!-- 执行计划：任务进度 + 计划清单(当前步转圈/已完成打勾) + 底部进度 -->
        <div v-show="tab === 'plan'" class="panel">
          <div class="prog-head">
            <span class="prog-label">任务进度</span>
            <span class="badge" :class="runState">
              <span v-if="runState === 'running'" class="badge-dot"></span>
              {{ runState === 'running' ? '运行中' : runState === 'done' ? '已完成' : runState === 'error' ? '执行失败' : '待发送' }}
            </span>
          </div>

          <div v-if="steps.length" class="plan-title">
            <span class="pt-ico">🗂️</span>
            <div class="pt-txt">
              <div class="pt-name">{{ thread.title }}</div>
              <div class="pt-sub">{{ store.currentProject?.name }} · {{ agent?.name }}</div>
            </div>
          </div>

          <ul v-if="steps.length" class="steps">
            <li v-for="s in steps" :key="s.key" :class="s.status">
              <span class="ico">
                <span v-if="s.status === 'running'" class="spin"></span>
                <span v-else-if="s.status === 'done'" class="check">✓</span>
                <span v-else class="dot"></span>
              </span>
              <span class="s-emoji">{{ s.icon }}</span>
              <span class="lbl">{{ s.label }}</span>
            </li>
          </ul>
          <p v-else class="p-empty">发送问题后，这里会铺开本轮的执行计划，并实时点亮每一步进度。</p>

          <div v-if="steps.length" class="prog-foot">
            <span>{{ progress.done }} / {{ progress.total }} 步</span>
            <div class="bar"><div class="bar-in" :style="{ width: progress.pct + '%' }"></div></div>
            <span>{{ progress.pct }}%</span>
          </div>
        </div>

        <!-- 命中资料：检索到的资料卡片，点击溯源看原文 -->
        <div v-show="tab === 'sources'" class="panel">
          <ul v-if="sources.length" class="srcs">
            <li v-for="(s, i) in sources" :key="i" @click="tracing = s">
              <div class="src-t">{{ s.title }}</div>
              <div class="src-p">{{ s.content.slice(0, 72) }}…</div>
            </li>
          </ul>
          <p v-else class="p-empty">检索命中的资料会列在这里，点击任意一条可查看原文溯源。</p>
        </div>
      </aside>

      <!-- 溯源弹层：查看命中资料的完整原文 -->
      <div v-if="tracing" class="trace-mask" @click.self="tracing = null">
        <div class="trace">
          <div class="trace-head">
            <span class="trace-title">{{ tracing.title }}</span>
            <button class="trace-x" @click="tracing = null">×</button>
          </div>
          <div class="trace-body">{{ tracing.content }}</div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.chat-wrap { display: flex; height: 100vh; width: 100%; }
.chat { display: flex; flex-direction: column; height: 100vh; flex: 1; min-width: 0; padding: 20px 28px; box-sizing: border-box; }
.placeholder { margin: auto; color: var(--muted); }
.chat-head { display: flex; align-items: center; justify-content: space-between; padding: 4px 4px 14px; border-bottom: 1px solid var(--line); }
.demo { white-space: nowrap; background: var(--accent-soft); color: var(--accent); border: 1px solid var(--border); padding: 7px 15px; border-radius: 9px; font-size: 13px; font-weight: 600; }
.demo:hover:not(:disabled) { background: var(--accent-soft); }
.titles .t { font-size: 18px; font-weight: 600; }
.titles .sub { font-size: 13px; color: var(--muted); margin-top: 4px; display: flex; align-items: center; gap: 8px; }
.rag { font-size: 11px; padding: 2px 9px; border-radius: 999px; background: rgba(0,0,0,0.05); color: var(--muted); }
.rag.on { background: var(--accent-soft); color: var(--accent); }
.list { flex: 1; overflow-y: auto; padding: 16px 4px; }
.empty { color: var(--muted); text-align: center; margin-top: 40px; }
.composer { display: flex; gap: 12px; align-items: flex-end; padding: 12px 4px 4px; border-top: 1px solid var(--line); }
.composer textarea { flex: 1; }
.composer button { white-space: nowrap; height: 44px; }
</style>/* 右栏：执行计划面板 */
.process { width: 340px; flex-shrink: 0; border-left: 1px solid var(--line); background: var(--panel2); overflow-y: auto; padding: 16px 14px; box-sizing: border-box; }
.tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--line); margin-bottom: 16px; }
.tabs button { flex: 1; display: inline-flex; align-items: center; justify-content: center; gap: 6px; background: transparent; border: none; box-shadow: none; padding: 10px 6px; font-size: 13.5px; font-weight: 600; color: var(--muted); border-bottom: 2px solid transparent; border-radius: 0; cursor: pointer; }
.tabs button:hover { color: var(--ink); background: transparent; }
.tabs button.on { color: var(--accent); border-bottom-color: var(--accent); }
.tabs .tab-ico { font-size: 13px; }
.tabs .tab-cnt { background: var(--accent-soft); color: var(--accent); border-radius: 999px; font-size: 11px; padding: 0 7px; }
.panel { background: #fff; border: 1px solid var(--border); border-radius: 14px; box-shadow: var(--shadow-sm); padding: 16px 16px 14px; }
.prog-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.prog-label { font-size: 13px; color: var(--muted); }
.badge { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600; padding: 3px 11px; border-radius: 999px; background: rgba(0,0,0,0.05); color: var(--muted); }
.badge.running { background: var(--accent-soft); color: var(--accent); }
.badge.done { background: var(--ok-soft, rgba(16,163,127,.1)); color: var(--accent-d); }
.badge.error { background: rgba(224,92,92,0.12); color: #c0392b; }
.badge-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; animation: pulse 1.2s ease-in-out infinite; }
@keyframes pulse { 0%,100% { opacity: 0.35; } 50% { opacity: 1; } }
.plan-title { display: flex; align-items: flex-start; gap: 10px; padding: 4px 0 14px; }
.pt-ico { font-size: 18px; line-height: 1.3; }
.pt-name { font-size: 14px; font-weight: 700; color: var(--ink); }
.pt-sub { font-size: 12px; color: var(--muted); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 240px; }
.steps { list-style: none; margin: 0; padding: 6px 0; border-top: 1px solid var(--line); }
.steps li { display: flex; align-items: center; gap: 9px; padding: 9px 8px; border-radius: 9px; font-size: 13.5px; color: var(--faint); }
.steps li.done { color: var(--text); }
.steps li.running { color: var(--accent); font-weight: 600; background: var(--accent-soft); }
.steps .ico { width: 16px; height: 16px; flex-shrink: 0; display: grid; place-items: center; }
.steps .check { color: var(--accent); font-size: 13px; }
.steps .dot { width: 8px; height: 8px; border: 1.5px solid var(--border); border-radius: 50%; }
.steps .spin { width: 13px; height: 13px; border: 2px solid var(--accent-soft); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.steps .s-emoji { font-size: 14px; }
.steps .lbl { flex: 1; }
.prog-foot { display: flex; align-items: center; gap: 10px; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--line); font-size: 12px; color: var(--muted); }
.prog-foot .bar { flex: 1; height: 6px; background: var(--line); border-radius: 999px; overflow: hidden; }
.prog-foot .bar-in { height: 100%; background: var(--accent); border-radius: 999px; transition: width 0.35s ease; }
.p-empty { font-size: 13px; color: var(--muted); line-height: 1.6; margin: 8px 2px; }
.srcs { list-style: none; margin: 0; padding: 0; }
.srcs li { padding: 10px 12px; border: 1px solid var(--border); border-radius: 10px; margin-bottom: 8px; background: #fff; cursor: pointer; transition: 0.12s; }
.srcs li:hover { border-color: var(--accent); box-shadow: var(--shadow-sm); }
.src-t { font-size: 13px; font-weight: 600; color: var(--ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.src-p { font-size: 12px; color: var(--muted); margin-top: 4px; line-height: 1.5; }

