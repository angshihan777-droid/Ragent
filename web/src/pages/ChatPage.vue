<script setup>
// 对话页：中间对话窗口 + 右侧「过程链条 / 命中资料」实时面板(与左栏合成三栏)。
// 发送走「POST 拿 id → SSE 流式」：token 实时追加，step 更新右栏进度，sources 填命中资料。
import { ref, computed, watch, nextTick } from "vue";
import { store } from "../store.js";
import { api } from "../api.js";
import { readStream } from "../sse.js";
import MessageBubble from "../components/MessageBubble.vue";

const messages = ref([]);      // {role, content, pending, error, sources}
const input = ref("");
const sending = ref(false);
const listEl = ref(null);

// 右栏实时态：本轮的过程步骤 + 命中资料 + 正在查看的溯源资料
const steps = ref([]);         // [{key,label,status}]
const sources = ref([]);       // [{title,content}]
const tracing = ref(null);     // 点击溯源时展开的那条 {title,content}

const thread = computed(() => store.currentThread);
const agent = computed(() => store.agentOf(thread.value));

async function scrollToBottom() {
  await nextTick();
  if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight;
}

watch(
  () => store.currentThreadId,
  async (id) => {
    messages.value = []; steps.value = []; sources.value = []; tracing.value = null;
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

function upsertStep(step) {
  // 同一节点先 running 后 done：按 key 原地更新状态，不重复堆叠
  const found = steps.value.find((s) => s.key === step.key);
  if (found) found.status = step.status;
  else steps.value.push({ ...step });
}

async function sendText(text) {
  if (sending.value || !thread.value) return;
  sending.value = true;
  // 新一轮：清空右栏上一轮的过程与命中，从头展示
  steps.value = []; sources.value = []; tracing.value = null;
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
        reply.content += token;
        scrollToBottom();
      },
      (hits) => {
        // 命中资料先于正文到达：填右栏「命中资料」，也留一份在气泡上
        sources.value = hits;
        reply.sources = hits;
        scrollToBottom();
      },
      (step) => upsertStep(step)
    );
    reply.pending = false;
    if (result.status === "done") {
      if (!reply.content) reply.content = result.content || "(空回复)";
    } else {
      reply.error = true;
      reply.content = "执行失败: " + (result.error || "未知错误");
    }
  } catch (e) {
    reply.pending = false;
    reply.error = true;
    reply.content = "请求出错: " + e.message;
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

      <!-- 右栏：过程链条 + 命中资料(可点击溯源) -->
      <aside class="process">
        <div class="p-sec">
          <div class="p-title">执行过程</div>
          <ul v-if="steps.length" class="steps">
            <li v-for="s in steps" :key="s.key" :class="s.status">
              <span class="ico">
                <span v-if="s.status === 'running'" class="spin"></span>
                <span v-else class="check">✓</span>
              </span>
              <span class="lbl">{{ s.label }}</span>
            </li>
          </ul>
          <p v-else class="p-empty">发送问题后，这里实时显示助手正在进行的步骤。</p>
        </div>

        <div class="p-sec">
          <div class="p-title">命中资料 <span v-if="sources.length" class="cnt">{{ sources.length }}</span></div>
          <ul v-if="sources.length" class="srcs">
            <li v-for="(s, i) in sources" :key="i" @click="tracing = s">
              <div class="src-t">{{ s.title }}</div>
              <div class="src-p">{{ s.content.slice(0, 60) }}…</div>
            </li>
          </ul>
          <p v-else class="p-empty">检索命中的资料会列在这里，点击可查看原文溯源。</p>
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
</style>
