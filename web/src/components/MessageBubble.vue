<script setup>
// 单条消息气泡：按角色区分左右与配色。抽成小组件让聊天列表只管排列、不管样式。
import { computed } from "vue";
import { renderInline } from "../md.js";

const props = defineProps({
  role: { type: String, required: true }, // "user" | "assistant"
  content: { type: String, default: "" },
  pending: { type: Boolean, default: false }, // 助手回复等待中时显示「思考中」
  error: { type: Boolean, default: false },
  sources: { type: Array, default: () => [] }, // 本次 RAG 检索命中的资料原文，展示「检索到了什么」
});

// 把模型输出的 Markdown 渲染成 HTML（已在 md.js 里先转义再套标签，安全可控）
const html = computed(() => renderInline(props.content));
</script>

<template>
  <div class="row" :class="role">
    <div class="col">
      <!-- 检索命中提示：让 RAG 不是黑盒，点开能看到这次到底检索到哪些资料原文 -->
      <details v-if="sources.length" class="sources">
        <summary>本次检索到 {{ sources.length }} 条资料</summary>
        <div v-for="(s, i) in sources" :key="i" class="src-item">{{ s }}</div>
      </details>
      <div class="bubble" :class="{ error }">
        <span v-if="pending" class="dots">思考中<i>.</i><i>.</i><i>.</i></span>
        <span v-else class="text" v-html="html"></span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.row { display: flex; margin: 10px 0; }
.row.user { justify-content: flex-end; }
.row.assistant { justify-content: flex-start; }
.bubble {
  padding: 10px 14px;
  border-radius: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.col { display: flex; flex-direction: column; max-width: 78%; }
.row.user .col { align-items: flex-end; }
.sources { margin-bottom: 6px; font-size: 12px; background: var(--panel2); border: 1px solid var(--border); border-radius: 10px; padding: 7px 11px; }
.sources summary { cursor: pointer; color: var(--primary); font-weight: 600; }
.src-item { margin-top: 6px; padding: 7px 9px; background: #fff; border: 1px solid var(--line); border-radius: 8px; color: var(--muted); line-height: 1.55; cursor: pointer; transition: 0.12s; }
.src-item:hover { border-color: var(--accent); }
.src-item-t { font-weight: 600; color: var(--ink); font-size: 12px; margin-bottom: 3px; }
.src-item-c { white-space: pre-wrap; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.user .bubble { background: var(--panel2); color: var(--ink); border: 1px solid var(--border); border-bottom-right-radius: 4px; }
.assistant .bubble { background: var(--card); border: 1px solid var(--border); border-bottom-left-radius: 4px; }
.row { align-items: flex-start; }
.bubble.error { background: rgba(224,92,92,0.12); border-color: rgba(224,92,92,0.4); color: #c0392b; }
.text :deep(code) { background: rgba(148,163,184,0.18); padding: 1px 5px; border-radius: 4px; font-size: 0.92em; }
.text :deep(strong) { font-weight: 700; }
.dots i { animation: blink 1.4s infinite both; }
.dots i:nth-child(2) { animation-delay: 0.2s; }
.dots i:nth-child(3) { animation-delay: 0.4s; }
@keyframes blink { 0%, 80%, 100% { opacity: 0; } 40% { opacity: 1; } }
</style>
