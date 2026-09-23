<script setup>
import Icon from "./Icon.vue";
defineProps({ documents: { type: Array, required: true }, busy: Boolean, loading: Boolean, showProject: Boolean });
defineEmits(["view", "edit", "delete"]);
</script>
<template>
  <div v-if="loading" class="card-empty" role="status">正在加载资料…</div>
  <ul v-else-if="documents.length" class="documents">
    <li v-for="doc in documents" :key="doc.id" class="document">
      <span class="doc-icon" aria-hidden="true"><Icon name="book" :size="16" /></span>
      <div class="info">
        <button class="title truncate" :disabled="busy" @click="$emit('view', doc)">{{ doc.title }}</button>
        <div class="meta"><span v-if="showProject">{{ doc.project_name }} · </span>{{ doc.chunk_count }} 个检索片段</div>
      </div>
      <div class="actions">
        <button class="quiet" :disabled="busy" :aria-label="'查看资料 ' + doc.title" @click="$emit('view', doc)"><Icon name="eye" :size="15" /><span>查看</span></button>
        <button class="quiet" :disabled="busy" :aria-label="'编辑资料 ' + doc.title" @click="$emit('edit', doc)"><Icon name="pencil" :size="15" /><span>编辑</span></button>
        <button class="quiet del" :disabled="busy" :aria-label="'删除资料 ' + doc.title" @click="$emit('delete', doc)"><Icon name="trash" :size="15" /></button>
      </div>
    </li>
  </ul>
  <div v-else class="card-empty">
    <Icon name="library" :size="22" />
    <p>暂无资料</p>
    <small>上传文件或新建文本资料后，助手就可以按需检索。</small>
  </div>
</template>
<style scoped>
.documents { list-style: none; margin: 0; padding: 0; border: 1px solid var(--border); border-radius: var(--r-lg); background: var(--surface); overflow: hidden; }
.document { display: flex; gap: var(--s-3); align-items: center; padding: var(--s-4) var(--s-5); transition: background .12s var(--ease); }
.document:hover { background: var(--surface-2); }
.document + .document { border-top: 1px solid var(--border-soft); }
.doc-icon { flex-shrink: 0; width: 30px; height: 30px; display: grid; place-content: center; border-radius: var(--r-md); background: var(--brand-soft); color: var(--brand-ink); }
.info { flex: 1; min-width: 0; }
.title { display: block; max-width: 100%; background: transparent; color: var(--ink); padding: 0; text-align: left; font-weight: 600; font-size: var(--fs-body); }
.title:hover:not(:disabled) { background: transparent; color: var(--brand-ink); text-decoration: underline; text-underline-offset: 2px; }
.meta { margin-top: 3px; font-size: var(--fs-xs); color: var(--muted); }
.actions { display: flex; gap: var(--s-1); flex-shrink: 0; opacity: 0; transition: opacity .12s var(--ease); }
.document:hover .actions, .actions:focus-within { opacity: 1; }
.actions button { padding: var(--s-2) var(--s-2); font-size: var(--fs-xs); }
.del:hover:not(:disabled) { background: var(--danger-soft); color: var(--danger-ink); }
.card-empty p { margin: var(--s-3) 0 var(--s-1); font-size: var(--fs-body); color: var(--text); font-weight: 500; }
.card-empty small { font-size: var(--fs-sm); }
@media (max-width: 720px) {
  .actions { opacity: 1; }
  .actions button span { display: none; }
}
@media (max-width: 600px) {
  .document { align-items: flex-start; }
  .doc-icon { display: none; }
}
</style>
