<script setup>
// 对话页：基于当前选中的会话(store.currentThread)提问并流式接收回答。
// 切换会话时从后端拉历史消息回放；发送走「POST 拿 id → SSE 流式追加」。
import { ref, computed, watch, nextTick } from "vue";
import { store } from "../store.js";
import { api } from "../api.js";
import { readStream } from "../sse.js";
import MessageBubble from "../components/MessageBubble.vue";

const messages = ref([]); // {role, content, pending, error}
const input = ref("");
const sending = ref(false);
const listEl = ref(null);

const thread = computed(() => store.currentThread);
const agent = computed(() => store.agentOf(thread.value));

async function scrollToBottom() {
  await nextTick();
  if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight;
}

// 切换会话即加载它的历史消息；没有选中会话则清空
watch(
  () => store.currentThreadId,
  async (id) => {
    messages.value = [];
    if (!id) return;
    const history = await api.listThreadMessages(id);
    messages.value = history.map((m) => ({ role: m.role, content: m.content }));
    await scrollToBottom();
  },
  { immediate: true }
);

// 预设的演示问题：命中 demo 项目的请假制度资料，一键即可看到 RAG 检索效果
const DEMO_QUESTION = "请年假需要提前几天申请？可以带薪吗？";

function send() {
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  sendText(text);
}

function runDemo() {
  // 一键演示：直接发预设问题，走和手动提问完全相同的链路
  sendText(DEMO_QUESTION);
}

async function sendText(text) {
  if (sending.value || !thread.value) return;
  sending.value = true;
  messages.value.push({ role: "user", content: text });
  // 先占一个「思考中」气泡，SSE token 到达时原地追加；sources 命中时填到气泡上方
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
      (sources) => {
        // 检索命中先于正文到达：填进气泡，用户能看到「这次检索了什么」
        reply.sources = sources;
        scrollToBottom();
      }
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
  <div class="chat">
    <div v-if="!thread" class="placeholder">
      <p>先在左侧选择或新建一个会话，就能开始对话。</p>
    </div>
    <template v-else>
      <header class="chat-head">
        <div class="titles">
          <div class="t">{{ thread.title }}</div>
          <div class="sub">
            {{ store.currentProject?.name }} · {{ agent?.name }}
            <span class="rag" :class="{ on: agent?.use_rag }">
              {{ agent?.use_rag ? "RAG 检索" : "不检索" }}
            </span>
          </div>
        </div>
        <!-- 一键演示：仅对会检索的助手显示，点一下自动问预设问题、展示检索命中 -->
        <button
          v-if="agent?.use_rag"
          class="demo"
          :disabled="sending"
          @click="runDemo"
        >一键演示</button>
      </header>

      <div ref="listEl" class="list">
        <p v-if="messages.length === 0" class="empty">
          问点什么吧。{{ agent?.use_rag ? "这个助手会先检索本项目资料再回答。" : "这个助手不检索资料，自由发挥。" }}
        </p>
        <MessageBubble
          v-for="(m, i) in messages"
          :key="i"
          :role="m.role"
          :content="m.content"
          :pending="m.pending"
          :error="m.error"
          :sources="m.sources || []"
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
    </template>
  </div>
</template>

<style scoped>
.chat { display: flex; flex-direction: column; height: 100vh; max-width: 860px; width: 100%; margin: 0 auto; padding: 20px 28px; box-sizing: border-box; }
.placeholder { margin: auto; color: var(--muted); }
.chat-head { display: flex; align-items: center; justify-content: space-between; padding-bottom: 14px; border-bottom: 1px solid var(--border); }
.demo { white-space: nowrap; background: var(--primary-soft); color: var(--primary); border: 1px solid #e8d3c7; padding: 7px 15px; border-radius: 9px; font-size: 13px; font-weight: 600; }
.demo:hover:not(:disabled) { background: #f0ddd2; }
.titles .t { font-size: 18px; font-weight: 600; }
.titles .sub { font-size: 13px; color: var(--muted); margin-top: 4px; display: flex; align-items: center; gap: 8px; }
.rag { font-size: 11px; padding: 2px 9px; border-radius: 999px; background: rgba(0,0,0,0.05); color: var(--muted); }
.rag.on { background: var(--primary-soft); color: var(--primary); }
.list { flex: 1; overflow-y: auto; padding: 16px 4px; }
.empty { color: var(--muted); text-align: center; margin-top: 40px; }
.composer { display: flex; gap: 12px; align-items: flex-end; padding-top: 12px; border-top: 1px solid var(--border); }
.composer textarea { flex: 1; }
.composer button { white-space: nowrap; height: 44px; }
</style>
