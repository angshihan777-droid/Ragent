<script setup>
import { ref, shallowRef, onMounted } from "vue";
import { api } from "../api.js";
const props = defineProps({ document: Object, projectId: String, mode: { type: String, default: "view" } });
const emit = defineEmits(["close", "saved"]);
const dialog = ref(null);
const editing = shallowRef(props.mode !== "view");
const title = shallowRef(props.document?.title || "");
const content = shallowRef(props.document?.content || "");
const busy = shallowRef(false);
const error = shallowRef("");
onMounted(() => dialog.value.showModal());
function close() { if (!busy.value) emit("close"); }
async function save() {
  if (busy.value || !title.value.trim() || !content.value.trim()) return;
  busy.value = true; error.value = "";
  try {
    if (props.document) await api.updateDocument(props.document.id, { title: title.value.trim(), content: content.value, revision: props.document.revision });
    else await api.ingestDocument(props.projectId, title.value.trim(), content.value);
    emit("saved");
  } catch (e) { error.value = e.message; }
  finally { busy.value = false; }
}
</script>
<template>
  <dialog ref="dialog" class="editor" aria-labelledby="document-editor-title" @cancel.prevent="close" @click="event => event.target === dialog && close()">
    <form @submit.prevent="save">
      <header class="head"><h2 id="document-editor-title">{{ editing ? (document ? '编辑资料' : '新建文本资料') : '查看资料' }}</h2><button type="button" class="quiet" aria-label="关闭资料" :disabled="busy" @click="close">×</button></header>
      <template v-if="editing">
        <label for="doc-title">标题</label><input id="doc-title" v-model="title" maxlength="500" required :disabled="busy" />
        <label for="doc-content">正文</label><textarea id="doc-content" v-model="content" rows="15" required :disabled="busy"></textarea>
        <p class="hint">保存后自动更新检索索引。修改正文将作为文本资料重新切分，不保留原文件页码；仅改标题会保留来源结构。</p>
      </template>
      <template v-else><h3 class="doc-title">{{ title }}</h3><p class="hint">入库正文 · {{ document.chunk_count }} 个检索片段</p><pre class="body">{{ content }}</pre></template>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <footer class="actions"><button class="quiet" type="button" :disabled="busy" @click="close">{{ editing ? '取消' : '关闭' }}</button><button v-if="editing" :disabled="busy || !title.trim() || !content.trim()">{{ busy ? '保存并更新索引…' : '保存资料' }}</button><button v-else type="button" @click="editing = true">编辑资料</button></footer>
    </form>
  </dialog>
</template>
<style scoped>
.editor { width: min(760px, calc(100vw - 32px)); max-height: 88dvh; box-sizing: border-box; padding: 24px; border: 1px solid var(--border); border-radius: 16px; background: var(--panel); color: var(--ink); box-shadow: var(--shadow); }.editor::backdrop { background: rgba(30,35,34,.38); }
.head { display: flex; justify-content: space-between; align-items: center; gap: 16px; }.head h2 { font-size: 18px; margin: 0; }.head button { font-size: 22px; padding: 4px 10px; }
label { display: block; margin: 18px 0 8px; font-size: 13px; }textarea { resize: vertical; min-height: 220px; }.hint { color: var(--muted); font-size: 12px; line-height: 1.7; }.doc-title { overflow-wrap: anywhere; }.body { white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; font-size: 14px; line-height: 1.85; max-height: 55dvh; overflow: auto; border-top: 1px solid var(--line); padding-top: 18px; }.actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px; }.quiet { color: var(--muted); background: var(--panel2); }.quiet:hover:not(:disabled) { background: var(--line); }.error { color: #ad3737; font-size: 13px; }
</style>
