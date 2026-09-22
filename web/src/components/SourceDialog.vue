<script setup>
import { onMounted, ref } from "vue";
defineProps({ source: { type: Object, required: true } });
const emit = defineEmits(["close"]);
const dialog = ref(null);
onMounted(() => dialog.value.showModal());
</script>
<template>
  <dialog ref="dialog" class="source-dialog" aria-labelledby="source-title" @close="emit('close')" @click="event => { if (event.target === dialog) dialog.close(); }">
    <div class="trace-head"><h2 id="source-title">{{ source.title || '未知来源' }}</h2><button class="quiet" aria-label="关闭原文" autofocus @click="dialog.close()">×</button></div>
    <div class="trace-body">{{ source.content }}</div>
  </dialog>
</template>
<style scoped>
.source-dialog { width: 680px; max-width: calc(100vw - 40px); max-height: 85dvh; padding: 0; border: 1px solid var(--border); border-radius: 16px; background: var(--panel); color: var(--text); box-shadow: var(--shadow); }
.source-dialog::backdrop { background: rgba(15,15,25,.32); }
.trace-head { position: sticky; top: 0; background: var(--panel); display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 16px 20px; border-bottom: 1px solid var(--line); }
h2 { margin: 0; font-size: 16px; overflow-wrap: anywhere; }
.trace-body { padding: 20px; white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.7; }
</style>
