<script setup>
import { computed, ref, shallowRef, watch, onBeforeUnmount } from "vue";
import { store } from "../store.js";
import { api } from "../api.js";
import { useDocuments } from "../composables/useDocuments.js";
import DocumentList from "./DocumentList.vue";
import DocumentEditor from "./DocumentEditor.vue";
import Icon from "./Icon.vue";
const props = defineProps({ allProjects: Boolean });
const filter = shallowRef("");
const search = shallowRef("");
const projectId = computed(() => props.allProjects ? filter.value : store.currentProjectId);
const scope = computed(() => {
  if (props.allProjects && !projectId.value) return store.projects;
  return store.projects.filter(project => project.id === projectId.value);
});
const { documents, loading, error, reload } = useDocuments(scope);
const shown = computed(() => documents.value.filter(doc => doc.title.toLowerCase().includes(search.value.trim().toLowerCase())));
const picker = ref(null);
const busy = shallowRef(false);
const message = shallowRef("");
const editor = shallowRef(null);
let generation = 0;
watch(projectId, () => { generation++; message.value = ""; error.value = ""; editor.value = null; });
onBeforeUnmount(() => { generation++; });
async function open(doc, mode) {
  if (busy.value) return;
  const current = generation; busy.value = true; error.value = "";
  try { const detail = await api.getDocument(doc.id); if (current === generation) editor.value = { document: detail, mode }; }
  catch (e) { if (current === generation) error.value = e.message; }
  finally { busy.value = false; }
}
async function remove(doc) {
  if (busy.value || !confirm(`删除资料「${doc.title}」？正文和检索索引会一起删除，不可恢复。`)) return;
  const current = generation; busy.value = true; error.value = ""; message.value = "";
  try {
    await api.deleteDocument(doc.id);
    if (current === generation) {
      await reload();
      if (current === generation) message.value = "资料已删除，检索索引已同步移除。";
    }
  } catch (e) { if (current === generation) error.value = "删除失败：" + e.message; }
  finally { busy.value = false; }
}
async function upload(event) {
  const files = Array.from(event.target.files || []); event.target.value = "";
  if (!files.length || busy.value || !projectId.value) return;
  const id = projectId.value, current = generation;
  busy.value = true; error.value = "";
  let completed = 0;
  const failures = [];
  try {
    for (const file of files) {
      if (current === generation) message.value = `上传并入库中：${file.name}`;
      try {
        if (!/\.(pdf|docx|md|markdown|txt)$/i.test(file.name) || file.size > 20 * 1024 * 1024) throw new Error("仅支持 PDF、DOCX、MD、TXT，单文件最大 20 MB");
        await api.uploadDocument(id, file); completed++;
      } catch (e) { failures.push(`${file.name}：${e.message}`); }
    }
    if (current === generation) {
      await reload();
      if (current !== generation) return;
      message.value = `已入库 ${completed} 个文件。`;
      if (failures.length) error.value = failures.join("；") + "。重新选择失败文件即可重试。";
    }
  } finally { busy.value = false; }
}
async function saved() { editor.value = null; message.value = "资料已保存，检索索引已更新。"; await reload(); }
</script>
<template>
  <section class="manager">
    <header class="heading">
      <h1>{{ allProjects ? '知识库图书馆' : (store.currentProject?.name ? store.currentProject.name + ' · 项目资料' : '项目资料') }}</h1>
      <p>上传、查看、编辑或删除资料，修改会同步更新检索索引。</p>
    </header>
    <div class="toolbar">
      <select v-if="allProjects" v-model="filter" aria-label="按项目筛选" :disabled="busy"><option value="">全部项目</option><option v-for="project in store.projects" :key="project.id" :value="project.id">{{ project.name }}</option></select>
      <div class="search-wrap">
        <Icon name="search" :size="15" />
        <input v-model="search" class="search" placeholder="搜索资料标题" aria-label="搜索资料标题" />
      </div>
      <div class="tools">
        <button class="secondary" :disabled="busy || !projectId" @click="editor = { mode: 'create' }"><Icon name="file-plus" :size="15" />新建文本</button>
        <button class="btn-brand" :disabled="busy || !projectId" @click="picker.click()"><Icon name="upload" :size="15" />{{ busy ? '处理中…' : '上传资料' }}</button>
      </div>
      <input ref="picker" hidden type="file" accept=".pdf,.docx,.md,.markdown,.txt" multiple @change="upload" />
    </div>
    <p class="hint">{{ projectId ? '支持 PDF、Markdown、Word（.docx）和 TXT，单文件最大 20 MB。' : '选择具体项目后可上传资料；全部项目下也可直接查看、编辑和删除。' }}</p>
    <p v-if="message" class="notice" role="status"><Icon name="check" :size="15" />{{ message }}</p>
    <div v-if="error" class="error-box" role="alert"><span>{{ error }}</span><button class="secondary" :disabled="busy || loading" @click="reload">刷新列表</button></div>
    <div class="list-head"><span>{{ shown.length }} 份资料</span><button class="quiet" :disabled="busy || loading" @click="reload"><Icon name="refresh" :size="14" />刷新</button></div>
    <DocumentList :documents="shown" :loading="loading" :busy="busy" :show-project="allProjects" @view="doc => open(doc, 'view')" @edit="doc => open(doc, 'edit')" @delete="remove" />
    <DocumentEditor v-if="editor" :document="editor.document" :mode="editor.mode" :project-id="projectId || undefined" @close="editor = null" @saved="saved" />
  </section>
</template>
<style scoped>
.manager { width: 100%; max-width: 1040px; margin: 0 auto; padding: var(--s-7) var(--s-6); box-sizing: border-box; }
.heading h1 { margin: 0; font-size: var(--fs-display); letter-spacing: -.02em; }
.heading p { margin: var(--s-2) 0 var(--s-6); color: var(--muted); font-size: var(--fs-sm); line-height: 1.7; }
.toolbar { display: flex; gap: var(--s-3); align-items: center; flex-wrap: wrap; }
.toolbar select { width: auto; min-width: 160px; max-width: 240px; }
.search-wrap { position: relative; flex: 1; min-width: 180px; display: flex; align-items: center; }
.search-wrap > svg { position: absolute; left: var(--s-3); color: var(--faint); pointer-events: none; }
.search { width: 100%; padding-left: calc(var(--s-3) * 2 + 15px); }
.tools { display: flex; gap: var(--s-2); }
.tools button { white-space: nowrap; }
.hint { font-size: var(--fs-xs); color: var(--faint); line-height: 1.7; margin: var(--s-3) 0 var(--s-5); }
.notice { margin: 0 0 var(--s-4); }
.error-box { display: flex; align-items: center; justify-content: space-between; gap: var(--s-3); margin-bottom: var(--s-4); flex-wrap: wrap; }
.error-box button { padding: var(--s-2) var(--s-3); font-size: var(--fs-xs); }
.list-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--s-3); font-size: var(--fs-sm); color: var(--muted); }
.list-head button { padding: var(--s-2) var(--s-3); font-size: var(--fs-xs); }
@media (max-width: 600px) {
  .manager { padding: var(--s-5) var(--s-4); }
  .tools { width: 100%; }
  .tools button { flex: 1; justify-content: center; }
  .toolbar select { max-width: 100%; width: 100%; }
}
</style>
