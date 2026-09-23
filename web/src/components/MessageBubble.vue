<script setup>
import { computed } from 'vue';
import { renderInline } from '../md.js';
import Icon from './Icon.vue';
defineEmits(['trace', 'retry']);
const props = defineProps({ role: String, content: { type: String, default: '' }, pending: Boolean, error: Boolean, retryable: Boolean, sources: { type: Array, default: () => [] } });
const html = computed(() => renderInline(props.content));
</script>
<template>
  <div class="row" :class="role"><div class="col">
    <div v-if="role === 'assistant'" class="author"><span class="avatar"><Icon name="sparkles" :size="14" /></span> 知识库助手</div>
    <div class="bubble" :class="{ error }">
      <span v-if="pending" class="dots">正在处理<i></i><i></i><i></i></span>
      <div v-else class="text" v-html="html"></div>
    </div>
    <button v-if="error && retryable" class="retry quiet" @click="$emit('retry')"><Icon name="refresh" :size="14" /> 重新提问</button>
    <details v-if="sources.length" class="sources">
      <summary>{{ sources.length }} 条参考资料</summary>
      <button v-for="(s, i) in sources" :key="i" class="src-item" @click="$emit('trace', s)">
        <span class="truncate">{{ s.title || '未知来源' }}</span><Icon name="arrow-up-right" :size="13" />
      </button>
    </details>
  </div></div>
</template>
<style scoped>
.row { display: flex; margin: 0 0 var(--s-6); align-items: flex-start; }
.row.user { justify-content: flex-end; }
.col { display: flex; flex-direction: column; min-width: 0; max-width: 100%; }
.user .col { max-width: 85%; }
.author { font-size: var(--fs-xs); color: var(--muted); display: flex; align-items: center; gap: var(--s-2); margin-bottom: var(--s-2); }
.avatar { display: grid; place-items: center; width: 24px; height: 24px; border-radius: var(--r-sm); background: var(--brand-soft); color: var(--brand); }

.bubble { line-height: 1.8; font-size: var(--fs-body); overflow-wrap: anywhere; }
.user .bubble { background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--r-lg); padding: var(--s-2) var(--s-4); white-space: pre-wrap; }
.assistant .bubble { color: var(--text); }
.bubble.error { background: var(--danger-soft); border: 1px solid var(--danger-line); border-radius: var(--r-md); padding: var(--s-3) var(--s-4); color: var(--danger-ink); }
.retry { align-self: flex-start; margin-top: var(--s-2); font-size: var(--fs-xs); }

.dots { color: var(--muted); font-size: var(--fs-sm); }
.dots i { display: inline-block; width: 3px; height: 3px; margin-left: 2px; border-radius: 50%; background: currentColor; animation: blink 1.4s infinite both; }
.dots i:nth-child(2) { animation-delay: 0.2s; }
.dots i:nth-child(3) { animation-delay: 0.4s; }
@keyframes blink { 0%, 80%, 100% { opacity: 0.2; } 40% { opacity: 1; } }

/* Markdown 块级元素：首尾元素不带外边距，避免气泡内出现多余留白 */
.text :deep(> *:first-child) { margin-top: 0; }
.text :deep(> *:last-child) { margin-bottom: 0; }
.text :deep(p) { margin: 0 0 var(--s-3); }
.text :deep(h3), .text :deep(h4) { margin: var(--s-4) 0 var(--s-2); font-size: var(--fs-body); }
.text :deep(ul), .text :deep(ol) { margin: 0 0 var(--s-3); padding-left: var(--s-5); }
.text :deep(li) { margin-bottom: var(--s-1); }
.text :deep(code) { background: var(--surface-3); padding: 1px 5px; border-radius: var(--r-sm); font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: 0.88em; }
.text :deep(pre) { background: var(--n-800); color: var(--n-50); padding: var(--s-3) var(--s-4); border-radius: var(--r-md); overflow-x: auto; margin: 0 0 var(--s-3); }
.text :deep(pre code) { background: none; padding: 0; color: inherit; font-size: var(--fs-sm); line-height: 1.7; }
.text :deep(blockquote) { margin: 0 0 var(--s-3); padding: var(--s-1) 0 var(--s-1) var(--s-3); border-left: 2px solid var(--brand-line); color: var(--muted); }
.text :deep(a) { color: var(--brand-ink); text-decoration: underline; text-underline-offset: 2px; }
.text :deep(hr) { border: 0; border-top: 1px solid var(--border); margin: var(--s-4) 0; }
.text :deep(em) { font-style: italic; }

.sources { margin-top: var(--s-3); font-size: var(--fs-xs); color: var(--muted); }
.sources summary { cursor: pointer; padding: var(--s-1) 0; }
.src-item { display: flex; align-items: center; justify-content: space-between; gap: var(--s-2); width: 100%; margin-top: var(--s-1); padding: var(--s-2) var(--s-3); background: var(--surface-2); border: 1px solid var(--border); color: var(--text); font-size: var(--fs-xs); text-align: left; font-weight: 400; }
.src-item:hover:not(:disabled) { background: var(--brand-soft); border-color: var(--brand-line); color: var(--brand-ink); }
</style>
