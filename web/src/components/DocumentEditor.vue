<script setup>
import { ref, shallowRef, onMounted } from "vue";
import { api } from "../api.js";
import Icon from "./Icon.vue";
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
      <header class="head">
        <h2 id="document-editor-title">{{ editing ? (document ? '编辑资料' : '新建文本资料') : '查看资料' }}</h2>
        <button type="button" class="quiet icon-btn" aria-label="关闭资料" :disabled="busy" @click="close"><Icon name="x" :size="18" /></button>
      </header>
      <div class="body-wrap">
        <template v-if="editing">
          <label for="doc-title">标题</label><input id="doc-title" v-model="title" maxlength="500" required :disabled="busy" />
          <label for="doc-content">正文</label><textarea id="doc-content" v-model="content" rows="15" required :disabled="busy"></textarea>
          <p class="hint">保存后自动更新检索索引。修改正文将作为文本资料重新切分，不保留原文件页码；仅改标题会保留来源结构。</p>
        </template>
        <template v-else>
          <h3 class="doc-title">{{ title }}</h3>
          <p class="hint doc-meta"><Icon name="book" :size="14" />入库正文 · {{ document.chunk_count }} 个检索片段</p>
          <pre class="body">{{ content }}</pre>
        </template>
        <p v-if="error" class="error-box" role="alert">{{ error }}</p>
      </div>
      <footer class="actions">
        <button class="secondary" type="button" :disabled="busy" @click="close">{{ editing ? '取消' : '关闭' }}</button>
        <button v-if="editing" class="btn-brand" :disabled="busy || !title.trim() || !content.trim()">{{ busy ? '保存并更新索引…' : '保存资料' }}</button>
        <button v-else type="button" @click="editing = true"><Icon name="pencil" :size="15" />编辑资料</button>
      </footer>
    </form>
  </dialog>
</template>
<style scoped>
.editor { width: min(760px, calc(100vw - var(--s-5) * 2)); max-height: 88dvh; box-sizing: border-box; padding: 0; border: 1px solid var(--border); border-radius: var(--r-xl); background: var(--surface); color: var(--ink); box-shadow: var(--shadow-lg); overflow: hidden; }
.editor::backdrop { background: rgba(23, 23, 26, .34); backdrop-filter: blur(2px); }
.editor form { display: flex; flex-direction: column; max-height: 88dvh; }
.head { display: flex; justify-content: space-between; align-items: center; gap: var(--s-4); padding: var(--s-5); border-bottom: 1px solid var(--border-soft); }
.head h2 { font-size: var(--fs-title); margin: 0; }
.icon-btn { padding: var(--s-2); border-radius: var(--r-md); }
.body-wrap { padding: var(--s-5); overflow: auto; flex: 1; }
label { display: block; margin: var(--s-4) 0 var(--s-2); font-size: var(--fs-sm); font-weight: 500; color: var(--text); }
label:first-child { margin-top: 0; }
textarea { resize: vertical; min-height: 220px; font-size: var(--fs-sm); line-height: 1.75; }
.hint { color: var(--faint); font-size: var(--fs-xs); line-height: 1.7; margin: var(--s-3) 0 0; }
.doc-title { margin: 0; font-size: var(--fs-title); overflow-wrap: anywhere; }
.doc-meta { display: flex; align-items: center; gap: var(--s-1); margin: var(--s-2) 0 var(--s-4); }
.body { white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; font-size: var(--fs-sm); line-height: 1.85; color: var(--text); margin: 0; border-top: 1px solid var(--border-soft); padding-top: var(--s-4); }
.error-box { margin-top: var(--s-4); }
.actions { display: flex; justify-content: flex-end; gap: var(--s-2); padding: var(--s-4) var(--s-5); border-top: 1px solid var(--border-soft); background: var(--surface-2); }
</style>
