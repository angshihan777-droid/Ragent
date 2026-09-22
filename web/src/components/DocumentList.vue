<script setup>
defineProps({ documents: { type: Array, required: true }, busy: Boolean, loading: Boolean, showProject: Boolean });
defineEmits(["view", "edit", "delete"]);
</script>
<template>
  <p v-if="loading" class="empty" role="status">正在加载资料…</p>
  <ul v-else-if="documents.length" class="documents">
    <li v-for="doc in documents" :key="doc.id" class="document">
      <div class="info">
        <button class="title" :disabled="busy" @click="$emit('view', doc)">{{ doc.title }}</button>
        <div class="meta"><span v-if="showProject">{{ doc.project_name }} · </span>{{ doc.chunk_count }} 个检索片段</div>
      </div>
      <div class="actions">
        <button class="quiet" :disabled="busy" :aria-label="'查看资料 ' + doc.title" @click="$emit('view', doc)">查看</button>
        <button class="quiet" :disabled="busy" :aria-label="'编辑资料 ' + doc.title" @click="$emit('edit', doc)">编辑</button>
        <button class="danger" :disabled="busy" :aria-label="'删除资料 ' + doc.title" @click="$emit('delete', doc)">删除</button>
      </div>
    </li>
  </ul>
  <div v-else class="empty">暂无资料。上传文件或新建文本资料后，助手就可以按需检索。</div>
</template>
<style scoped>
.documents { list-style: none; margin: 0; padding: 0; border: 1px solid var(--border); border-radius: 12px; background: var(--panel); overflow: hidden; }
.document { display: flex; gap: 16px; align-items: center; padding: 17px 20px; }
.document + .document { border-top: 1px solid var(--line); }
.info { flex: 1; min-width: 0; }.title { background: transparent; color: var(--ink); padding: 0; text-align: left; overflow-wrap: anywhere; font-weight: 600; }.title:hover:not(:disabled) { background: transparent; color: var(--accent-d); }
.meta { margin-top: 7px; font-size: 12px; color: var(--muted); }
.actions { display: flex; gap: 6px; flex-shrink: 0; }.actions button { padding: 7px 10px; font-size: 13px; }.quiet { background: transparent; color: var(--muted); }.quiet:hover:not(:disabled) { background: var(--panel2); color: var(--ink); }.danger { background: #fff4f4; color: #ad3737; }.danger:hover:not(:disabled) { background: #fee2e2; }
.empty { padding: 52px 20px; text-align: center; color: var(--muted); font-size: 14px; line-height: 1.8; border: 1px dashed var(--border); border-radius: 12px; }
@media (max-width: 600px) { .document { align-items: flex-start; flex-direction: column; }.actions { align-self: flex-end; } }
</style>
