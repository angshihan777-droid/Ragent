<script setup>
import { onMounted, ref } from "vue";
import Icon from "./Icon.vue";
defineProps({ source: { type: Object, required: true } });
const emit = defineEmits(["close"]);
const dialog = ref(null);
onMounted(() => dialog.value.showModal());
</script>
<template>
  <dialog ref="dialog" class="source-dialog" aria-labelledby="source-title" @close="emit('close')" @click="event => { if (event.target === dialog) dialog.close(); }">
    <header class="trace-head">
      <div class="head-text">
        <span class="kicker">原文片段</span>
        <h2 id="source-title">{{ source.title || '未知来源' }}</h2>
      </div>
      <button class="quiet icon-btn" aria-label="关闭原文" autofocus @click="dialog.close()"><Icon name="x" :size="18" /></button>
    </header>
    <div class="trace-meta">
      <span v-if="source.citation_id" class="badge-brand badge">引用 [{{ source.citation_id }}]</span>
      <span v-if="source.metadata?.page_start" class="badge">第 {{ source.metadata.page_start }} 页</span>
      <span v-if="source.metadata?.heading_path?.length" class="path">{{ source.metadata.heading_path.join(' / ') }}</span>
    </div>
    <div class="trace-body">{{ source.content }}</div>
  </dialog>
</template>
<style scoped>
.source-dialog { width: min(680px, calc(100vw - var(--s-5) * 2)); max-height: 85dvh; padding: 0; border: 1px solid var(--border); border-radius: var(--r-xl); background: var(--surface); color: var(--text); box-shadow: var(--shadow-lg); overflow: auto; }
.source-dialog::backdrop { background: rgba(23, 23, 26, .34); backdrop-filter: blur(2px); }
.trace-head { position: sticky; top: 0; z-index: 1; background: var(--surface); display: flex; align-items: flex-start; justify-content: space-between; gap: var(--s-4); padding: var(--s-5) var(--s-5) var(--s-4); border-bottom: 1px solid var(--border-soft); }
.head-text { min-width: 0; }
.kicker { display: block; font-size: var(--fs-xs); color: var(--faint); letter-spacing: .04em; text-transform: uppercase; margin-bottom: var(--s-1); }
h2 { margin: 0; font-size: var(--fs-title); line-height: 1.4; overflow-wrap: anywhere; }
.icon-btn { padding: var(--s-2); border-radius: var(--r-md); }
.trace-meta { display: flex; flex-wrap: wrap; align-items: center; gap: var(--s-2); padding: var(--s-4) var(--s-5) 0; }
.path { font-size: var(--fs-xs); color: var(--muted); overflow-wrap: anywhere; }
.trace-body { padding: var(--s-4) var(--s-5) var(--s-6); white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.8; font-size: var(--fs-body); color: var(--text); }
</style>
