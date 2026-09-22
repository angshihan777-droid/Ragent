<script setup>
// 资料管理页：按当前项目列出资料，支持新增与删除（CRUD 的增删查）。
// 资料归属项目，同项目多会话共享，所以这里以 store.currentProject 为上下文。
import { ref, computed, watch } from "vue";
import { store } from "../store.js";
import { api } from "../api.js";

const docs = ref([]);
const title = ref("");
const content = ref("");
const busy = ref(false);
const msg = ref("");
const msgType = ref("");

const projectId = computed(() => store.currentProjectId);

function flash(type, text) { msgType.value = type; msg.value = text; }

let loadVersion = 0;
async function load() {
  const version = ++loadVersion;
  const id = projectId.value;
  docs.value = [];
  if (!id) return;
  try {
    const result = await api.listDocuments(id);
    if (version === loadVersion) docs.value = result;
  } catch (e) { if (version === loadVersion) flash("err", e.message); }
}
watch(projectId, () => { msg.value = ""; title.value = ""; content.value = ""; load(); }, { immediate: true });
async function upload(event) {
  const files = Array.from(event.target.files || []);
  event.target.value = "";
  if (!files.length || busy.value || !projectId.value) return;
  const id = projectId.value;
  busy.value = true;
  const failures = [];
  let done = 0;
  try {
    for (const file of files) {
      if (projectId.value === id) flash("ok", `上传并入库中：${file.name}`);
      try { await api.uploadDocument(id, file); done++; }
      catch (e) { failures.push(`${file.name}：${e.message}`); }
    }
    if (projectId.value === id) {
      flash(failures.length ? "err" : "ok", `已入库 ${done} 个文件。${failures.join("；")}`);
      await load();
    }
  } finally { busy.value = false; }
}

async function add() {
  if (!title.value.trim() || !content.value.trim() || busy.value || !projectId.value) return;
  const project = projectId.value;
  busy.value = true; msg.value = "";
  try {
    const r = await api.ingestDocument(project, title.value.trim(), content.value.trim());
    if (projectId.value !== project) return;
    flash("ok", "入库成功，切成 " + r.chunk_count + " 块。");
    title.value = ""; content.value = "";
    await load();
  } catch (e) {
    if (projectId.value === project) flash("err", "入库失败: " + e.message);
  } finally {
    busy.value = false;
  }
}

async function remove(id, t) {
  if (busy.value || !confirm('删除资料「' + t + '」？')) return;
  const project = projectId.value;
  busy.value = true;
  try {
    await api.deleteDocument(id);
    if (projectId.value === project) await load();
  } catch (e) {
    if (projectId.value === project) flash("err", "删除失败：" + e.message);
  } finally { busy.value = false; }
}
</script>

<template>
  <div class="page">
    <div v-if="!projectId" class="placeholder">先在左侧选择一个项目，再管理它的资料。</div>
    <template v-else>
      <h2>资料管理 · {{ store.currentProject?.name }}</h2>
      <p class="hint">资料归属当前项目，项目内所有会话共享这份资料，由知识库助手按需检索。</p>

      <div class="card">
        <label for="document-files">上传资料（PDF / Markdown / Word .docx / TXT，单文件最大 20 MB）</label>
        <input id="document-files" type="file" accept=".pdf,.docx,.md,.markdown,.txt" multiple :disabled="busy" @change="upload" />
        <p class="hint">扫描 PDF 请先 OCR；也可以在下方直接粘贴正文。</p>
        <label>标题</label>
        <input v-model="title" placeholder="例如：请假制度" />
        <label>正文</label>
        <textarea v-model="content" rows="8" placeholder="粘贴文档正文，会自动切块向量化..." />
        <div class="actions">
          <button :disabled="busy || !title.trim() || !content.trim()" @click="add">
            {{ busy ? "入库中" : "入库" }}
          </button>
        </div>
        <div v-if="msg" :class="msgType">{{ msg }}</div>
      </div>

      <h3>已有资料（{{ docs.length }}）</h3>
      <ul class="docs">
        <li v-for="d in docs" :key="d.id">
          <div class="meta">
            <span class="dt">{{ d.title }}</span>
            <span class="dc">{{ d.chunk_count }} 块</span>
          </div>
          <button class="del" :disabled="busy" @click="remove(d.id, d.title)">删除</button>
        </li>
        <li v-if="docs.length === 0" class="empty">还没有资料，先在上面添加。</li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.page { max-width: 760px; margin: 0 auto; padding: 28px; }
.placeholder { color: var(--muted); margin-top: 40px; text-align: center; }
h2 { margin: 0 0 4px; }
h3 { margin: 28px 0 10px; font-size: 15px; }
.hint { color: var(--muted); margin: 0 0 20px; font-size: 14px; }
.card { background: #fff; border: 1px solid var(--border); border-radius: 12px; box-shadow: var(--shadow-sm); padding: 22px; }
label { display: block; margin: 12px 0 6px; font-size: 14px; font-weight: 500; }
.actions { margin-top: 16px; }
.docs { list-style: none; margin: 0; padding: 0; }
.docs li { display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; border: 1px solid var(--border); border-radius: 12px; margin-bottom: 8px; background: var(--panel2); }
.meta { display: flex; align-items: center; gap: 10px; }
.dt { font-weight: 500; }
.dc { font-size: 12px; color: var(--muted); background: rgba(120,120,140,0.14); padding: 1px 8px; border-radius: 999px; }
.del { background: #fef2f2; color: #b91c1c; }
.del:hover { background: #fee2e2; }
.empty { justify-content: center; color: var(--muted); }
.ok { margin-top: 14px; padding: 10px 12px; background: var(--accent-soft); border: 1px solid rgba(16,163,127,0.35); border-radius: 10px; color: var(--accent-d); font-size: 14px; }
.err { margin-top: 14px; padding: 10px 12px; background: rgba(224,92,92,0.12); border: 1px solid rgba(224,92,92,0.35); border-radius: 10px; color: #c0392b; font-size: 14px; }
</style>
