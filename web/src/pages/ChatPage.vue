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
const { messages, input, sending, listEl, historyError, historyLoading, steps, sources,
  tracing, runState, thread, creatingThread, startConversation, send, sendText } = useConversation();
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
          <div class="titles"><div class="breadcrumb">{{ store.currentProject?.name }} <span>/ 知识库对话</span></div><h1>{{ thread.title }}</h1></div>
          <div class="head-actions"><button class="quiet" :disabled="creatingThread || sending" @click="startConversation">＋ 新对话</button><button class="quiet" :aria-expanded="!panelCollapsed" @click="panelCollapsed = !panelCollapsed">{{ panelCollapsed ? '展开右栏' : '收起右栏' }}</button></div>
        </header>
        <div ref="listEl" class="list" aria-live="polite" :aria-busy="historyLoading">
          <div class="message-content">
            <p v-if="historyLoading" class="empty">加载对话…</p><p v-if="historyError" role="alert">{{ historyError }}</p>
            <div v-if="!historyLoading && !messages.length" class="conversation-empty"><span>✦</span><h2>有什么想从资料中了解的？</h2><p>我会按需检索当前项目，并把依据展示在右侧。</p></div>
            <MessageBubble v-for="(m, i) in messages" :key="i" :role="m.role" :content="m.content" :pending="m.pending" :error="m.error" :sources="m.sources || []" :retryable="!!m.error && i === messages.length - 1 && !sending && messages[i-1]?.role === 'user'" @retry="sendText(messages[i-1].content)" @trace="tracing = $event" />
          </div>
        </div>
        <div class="input-zone"><ChatComposer v-model="input" :busy="sending" :disabled="historyLoading" :project-name="store.currentProject?.name" @send="send" /></div>
      </section>
      <ResizeHandle v-if="!panelCollapsed" v-model="panelWidth" :min="280" :max="480" reverse label="调整右栏宽度" />
      <aside v-if="!panelCollapsed" class="right-rail" :style="{ width: panelWidth + 'px' }"><ExecutionPanel :steps="steps" :sources="sources" :run-state="runState" :thread="thread" :project-name="store.currentProject?.name" @trace="tracing = $event" /></aside>
      <SourceDialog v-if="tracing" :source="tracing" @close="tracing = null" />
    </template>
  </div>
</template>
<style scoped>
.chat-wrap { min-height: 0; display: flex; height: 100%; width: 100%; background: var(--panel); }
.chat { display: flex; flex-direction: column; height: 100%; flex: 1; min-width: 0; overflow: hidden; }
.chat-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 18px 26px; border-bottom: 1px solid var(--line); }
.titles { min-width: 0; }.breadcrumb { font-size: 11px; color: var(--muted); }.breadcrumb span { color: var(--faint); }h1 { margin: 5px 0 0; font-size: 16px; font-weight: 550; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.head-actions { display: flex; gap: 4px; flex-shrink: 0; }.head-actions button { font-size: 12px; padding: 7px; }
.list { min-height: 0; flex: 1; overflow-y: auto; padding: 24px 30px; }.message-content { max-width: 820px; margin: auto; }.empty { text-align: center; color: var(--muted); }
.conversation-empty { text-align: center; margin: 10vh auto 40px; color: var(--muted); font-size: 13px; line-height: 1.8; }.conversation-empty span { color: var(--accent); font-size: 30px; }.conversation-empty h2 { color: var(--ink); font-size: 21px; font-weight: 500; }
.input-zone { padding: 0 28px 15px; }.right-rail { flex-shrink: 0; max-width: 40%; min-width: 260px; height: 100%; }
@media (max-width: 760px) { .chat-wrap { flex-direction: column; overflow: auto; }.chat { flex: 1 0 65dvh; height: auto; }.chat-head { padding: 14px; }.list { padding: 18px 16px; }.input-zone { padding: 0 14px 12px; }.right-rail { width: 100% !important; max-width: none; min-width: 0; height: auto; }.breadcrumb { max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; } }
</style>
