<script setup>
import { store } from "../store.js";
import { useConversation } from "../composables/useConversation.js";
import { usePreference } from "../composables/usePreference.js";
import ChatWelcome from "../components/ChatWelcome.vue";
import ChatComposer from "../components/ChatComposer.vue";
import MessageBubble from "../components/MessageBubble.vue";
import SourceDialog from "../components/SourceDialog.vue";
import ResizeHandle from "../components/ResizeHandle.vue";
import ExecutionPanel from "../components/ExecutionPanel.vue";
import Icon from "../components/Icon.vue";
const { messages, input, sending, listEl, historyError, historyLoading, steps, sources,
  tracing, runState, thread, creatingThread, startConversation, send, sendText,
  stop, stickToBottom, onListScroll, jumpToBottom } = useConversation();
const panelWidth = usePreference("ragent.panelWidth", 320);
panelWidth.value = Math.min(480, Math.max(280, panelWidth.value));
const panelCollapsed = usePreference("ragent.panelCollapsed", false);
</script>
<template>
  <div class="chat-wrap">
    <ChatWelcome v-if="!thread" :project-name="store.currentProject?.name" :available="!!store.currentProjectId" :busy="creatingThread" :error="historyError" @start="startConversation" />
    <template v-else>
      <section class="chat">
        <header class="chat-head">
          <div class="titles">
            <div class="breadcrumb truncate">{{ store.currentProject?.name }} <span>/ 知识库对话</span></div>
            <h1 class="truncate">{{ thread.title }}</h1>
          </div>
          <div class="head-actions">
            <button class="quiet" :disabled="creatingThread || sending" @click="startConversation"><Icon name="plus" :size="15" /> 新对话</button>
            <button class="quiet" :aria-expanded="!panelCollapsed" @click="panelCollapsed = !panelCollapsed">
              <Icon name="panel-left" :size="15" /> {{ panelCollapsed ? '展开右栏' : '收起右栏' }}
            </button>
          </div>
        </header>
        <div class="list-wrap">
          <div ref="listEl" class="list" :aria-busy="historyLoading" @scroll.passive="onListScroll">
            <div class="message-content">
              <p v-if="historyLoading" class="empty" role="status">加载对话…</p>
              <p v-if="historyError" class="error-box" role="alert">{{ historyError }}</p>
              <div v-if="!historyLoading && !messages.length" class="conversation-empty">
                <span class="ce-mark"><Icon name="sparkles" :size="22" /></span>
                <h2>有什么想从资料中了解的？</h2>
                <p>我会按需检索当前项目，并把依据展示在右侧。</p>
              </div>
              <MessageBubble v-for="(m, i) in messages" :key="i" :role="m.role" :content="m.content" :pending="m.pending" :error="m.error" :sources="m.sources || []" :retryable="!!m.error && i === messages.length - 1 && !sending && messages[i-1]?.role === 'user'" @retry="sendText(messages[i-1].content)" @trace="tracing = $event" />
            </div>
          </div>
          <button v-if="!stickToBottom && messages.length" class="jump secondary" aria-label="回到最新消息" @click="jumpToBottom">
            <Icon name="arrow-down" :size="16" />
          </button>
        </div>
        <div class="input-zone"><ChatComposer v-model="input" :busy="sending" :disabled="historyLoading" :project-name="store.currentProject?.name" @send="send" @stop="stop" /></div>
      </section>
      <ResizeHandle v-if="!panelCollapsed" v-model="panelWidth" :min="280" :max="480" reverse label="调整右栏宽度" />
      <aside v-if="!panelCollapsed" class="right-rail" :style="{ width: panelWidth + 'px' }"><ExecutionPanel :steps="steps" :sources="sources" :run-state="runState" :thread="thread" :project-name="store.currentProject?.name" @trace="tracing = $event" /></aside>
      <SourceDialog v-if="tracing" :source="tracing" @close="tracing = null" />
    </template>
  </div>
</template>
<style scoped>
.chat-wrap { min-height: 0; display: flex; height: 100%; width: 100%; background: var(--surface); }
.chat { display: flex; flex-direction: column; height: 100%; flex: 1; min-width: 0; overflow: hidden; }
.chat-head { display: flex; align-items: center; justify-content: space-between; gap: var(--s-3); padding: var(--s-3) var(--s-5); border-bottom: 1px solid var(--border); }
.titles { min-width: 0; }
.breadcrumb { font-size: var(--fs-xs); color: var(--muted); }
.breadcrumb span { color: var(--faint); }
h1 { margin: 2px 0 0; font-size: var(--fs-title); }
.head-actions { display: flex; gap: var(--s-1); flex-shrink: 0; }
.head-actions button { font-size: var(--fs-xs); }

.list-wrap { position: relative; flex: 1; min-height: 0; display: flex; }
.list { flex: 1; min-height: 0; overflow-y: auto; padding: var(--s-5) var(--s-6); }
.message-content { max-width: 780px; margin: auto; }
.empty { text-align: center; color: var(--muted); font-size: var(--fs-sm); }
.jump { position: absolute; bottom: var(--s-4); left: 50%; transform: translateX(-50%); width: 34px; height: 34px; padding: 0; border-radius: var(--r-full); box-shadow: var(--shadow-md); }

.conversation-empty { text-align: center; margin: 12vh auto var(--s-6); color: var(--muted); font-size: var(--fs-sm); line-height: 1.8; }
.ce-mark { display: inline-grid; place-items: center; width: 44px; height: 44px; border-radius: var(--r-lg); background: var(--brand-soft); color: var(--brand); margin-bottom: var(--s-3); }
.conversation-empty h2 { color: var(--ink); font-size: 22px; margin-bottom: var(--s-2); }
.conversation-empty p { margin: 0; }

.input-zone { padding: 0 var(--s-6) var(--s-4); }
.right-rail { flex-shrink: 0; max-width: 40%; min-width: 260px; height: 100%; }
@media (max-width: 760px) {
  .chat-wrap { flex-direction: column; overflow: auto; }
  .chat { flex: 1 0 65dvh; height: auto; }
  .chat-head { padding: var(--s-3); }
  .list { padding: var(--s-4); }
  .input-zone { padding: 0 var(--s-3) var(--s-3); }
  .right-rail { width: 100% !important; max-width: none; min-width: 0; height: auto; }
  .breadcrumb { max-width: 140px; }
}
</style>
