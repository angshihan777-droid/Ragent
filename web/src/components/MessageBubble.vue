<script setup>
import { computed } from 'vue';
import { renderInline } from '../md.js';
defineEmits(['trace', 'retry']);
const props = defineProps({ role: String, content: { type: String, default: '' }, pending: Boolean, error: Boolean, retryable: Boolean, sources: { type: Array, default: () => [] } });
const html = computed(() => renderInline(props.content));
</script>
<template>
  <div class="row" :class="role"><div class="col">
    <div v-if="role === 'assistant'" class="author"><span>✦</span> 知识库助手</div>
    <div class="bubble" :class="{ error }"><span v-if="pending" class="dots">正在处理…</span><span v-else class="text" v-html="html"></span></div>
    <button v-if="error && retryable" class="retry quiet" @click="$emit('retry')">↻ 重新提问</button>
    <details v-if="sources.length" class="sources"><summary>{{ sources.length }} 条参考资料</summary><button v-for="(s, i) in sources" :key="i" class="src-item" @click="$emit('trace', s)">{{ s.title || '未知来源' }} · 查看原文</button></details>
  </div></div>
</template>
<style scoped>
.row { display: flex; margin: 0 0 28px; align-items: flex-start; }.row.user { justify-content: flex-end; }.col { display: flex; flex-direction: column; min-width: 0; max-width: 100%; }.user .col { max-width: 85%; }.author { font-size: 12px; color: var(--muted); display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }.author span { display: grid; place-items: center; width: 25px; height: 25px; border-radius: 8px; background: var(--accent-soft); color: var(--accent); font-size: 18px; }
.bubble { line-height: 1.9; font-size: 14px; white-space: pre-wrap; overflow-wrap: anywhere; }.user .bubble { background: var(--panel2); border: 1px solid var(--line); border-radius: 12px; padding: 10px 16px; }.assistant .bubble { padding-left: 2px; }.bubble.error { background: #fff8f5; border: 1px solid #f3ded4; border-radius: 10px; padding: 12px 16px; color: #9c4e38; }.retry { align-self: flex-start; margin-top: 8px; font-size: 12px; }
.sources { margin-top: 14px; font-size: 12px; color: var(--muted); }.sources summary { cursor: pointer; }.src-item { display: block; margin-top: 6px; padding: 6px 10px; background: var(--accent-soft); color: var(--accent-d); font-size: 12px; text-align: left; }.src-item:hover { background: #d5efe0; }.text :deep(code) { background: var(--panel2); padding: 2px 5px; border-radius: 4px; }.text :deep(strong) { font-weight: 600; }.dots { color: var(--muted); }
</style>
