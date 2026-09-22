<script setup>
// 侧栏：工作台导航、项目→多会话树，底部模型配置入口。
// 每个项目下挂多条会话；新建项目走弹窗(引导填名称+上传首批资料)。
import { ref, watch } from "vue";
import { useRouter } from "vue-router";
import { store } from "../store.js";
import { api } from "../api.js";
import NewProjectModal from "./NewProjectModal.vue";
import NewThreadModal from "./NewThreadModal.vue";

defineEmits(["collapse"]);
const router = useRouter();
const expanded = ref({});
const loadingProjects = ref({});
const docsBusy = ref({});      // 每个项目资料区的忙碌态（上传/删除/改名）
const renaming = ref({});       // 正在改名的资料 id -> 新标题
const uploaders = ref({});      // 每个项目的隐藏 file input 引用
const error = ref("");
watch(() => store.currentProjectId, id => { if (id) expanded.value[id] = true; }, { immediate: true });
async function attempt(action) {
  error.value = "";
  try { await action(); } catch (e) { error.value = e.message; }
}
async function toggleProject(id) {
  expanded.value[id] = !expanded.value[id];
  if (!expanded.value[id]) return;
  loadingProjects.value[id] = true;
  try { await Promise.all([store.loadProjectThreads(id), store.loadProjectDocuments(id)]); }
  finally { loadingProjects.value[id] = false; }
}
async function newThread(projectId) {
  await store.selectProject(projectId);
  if (store.currentProjectId !== projectId || store.projectLoading) return;
  showNewThread.value = true;
}
const showNewProject = ref(false);
const showNewThread = ref(false);

async function pickProject(id) {
  await store.selectProject(id);
  router.push("/chat");
}
async function pickThread(projectId, id) {
  await store.selectProject(projectId);
  if (store.currentProjectId !== projectId) return;
  await store.selectThread(id);
  router.push("/chat");
}
async function onProjectCreated(projectId) {
  showNewProject.value = false;
  await store.loadProjects();
  await store.selectProject(projectId);
  if (store.threads.length) await store.selectThread(store.threads[0].id);
  router.push("/chat");
}
async function onThreadCreated(threadId) {
  showNewThread.value = false;
  await store.loadProjectDetail();
  await store.selectThread(threadId);
  router.push("/chat");
}
async function removeProject(id, name) {
  if (!confirm('删除项目「' + name + '」？其会话与资料会一并删除，不可恢复。')) return;
  await api.deleteProject(id);
  await store.loadProjects();
}
async function removeThread(projectId, id, title) {
  if (!confirm('删除会话「' + title + '」？该会话的对话记录会一并删除，不可恢复。')) return;
  await api.deleteThread(id);
  if (projectId === store.currentProjectId) await store.loadProjectDetail();
  else await store.loadProjectThreads(projectId);
}

// ---- 左栏内联资料增删改：不跳页，直接在项目下管理文件 ----
const ACCEPT = ".pdf,.docx,.md,.markdown,.txt";
function pickFiles(projectId) {
  uploaders.value[projectId]?.click();
}
async function onFiles(projectId, event) {
  const files = Array.from(event.target.files || []);
  event.target.value = "";
  if (!files.length || docsBusy.value[projectId]) return;
  docsBusy.value[projectId] = true;
  const failures = [];
  try {
    for (const file of files) {
      try {
        if (!/\.(pdf|docx|md|markdown|txt)$/i.test(file.name) || file.size > 20 * 1024 * 1024)
          throw new Error("仅支持 PDF/DOCX/MD/TXT，单文件≤20MB");
        await api.uploadDocument(projectId, file);
      } catch (e) { failures.push(file.name + "：" + e.message); }
    }
    await store.loadProjectDocuments(projectId);
    if (failures.length) error.value = failures.join("；");
  } finally { docsBusy.value[projectId] = false; }
}
async function removeDoc(projectId, doc) {
  if (docsBusy.value[projectId]) return;
  if (!confirm('删除资料「' + doc.title + '」？正文与检索索引会一并删除，不可恢复。')) return;
  docsBusy.value[projectId] = true;
  try { await api.deleteDocument(doc.id); await store.loadProjectDocuments(projectId); }
  finally { docsBusy.value[projectId] = false; }
}
function startRename(doc) { renaming.value[doc.id] = doc.title; }
function cancelRename(doc) { delete renaming.value[doc.id]; }
async function commitRename(projectId, doc) {
  const next = (renaming.value[doc.id] || "").trim();
  if (!next || next === doc.title) { delete renaming.value[doc.id]; return; }
  docsBusy.value[projectId] = true;
  try {
    // 改名需带上正文与 revision（乐观锁），先取详情再整体回写标题
    const detail = await api.getDocument(doc.id);
    await api.updateDocument(doc.id, { title: next, content: detail.content, revision: detail.revision });
    delete renaming.value[doc.id];
    await store.loadProjectDocuments(projectId);
  } catch (e) { error.value = "改名失败：" + e.message; }
  finally { docsBusy.value[projectId] = false; }
}
</script>

<template>
  <aside class="sidebar">
    <div class="brand"><span class="brand-mark">R</span><span>Ragent<small>知识工作台</small></span><button class="quiet collapse" aria-label="收起左栏" @click="$emit('collapse')">‹</button></div>

    <nav class="primary-nav" aria-label="工作台导航">
      <RouterLink to="/chat" @click="store.currentThreadId = null"><span>⊕</span> 新对话</RouterLink>
      <a class="nav-link" href="/intro.html" target="_blank" rel="noopener"><span>✦</span> 使用介绍</a>
      <RouterLink to="/documents"><span>▧</span> 项目资料</RouterLink>
      <RouterLink to="/library"><span>▦</span> 知识库图书馆</RouterLink>
    </nav>
    <div class="section-head">
      <span>项目</span>
      <button class="mini" title="新建项目" @click="showNewProject = true">+</button>
    </div>
    <p v-if="error" class="nav-error" role="alert">{{ error }}</p>
    <ul class="project-tree" aria-label="项目与会话">
      <li v-for="p in store.projects" :key="p.id" class="project-node">
        <div class="project-row" :class="{ active: p.id === store.currentProjectId }">
          <button class="quiet expander" :aria-label="(expanded[p.id] ? '收起项目 ' : '展开项目 ') + p.name" :aria-expanded="!!expanded[p.id]" @click="attempt(() => toggleProject(p.id))">{{ expanded[p.id] ? '▾' : '▸' }}</button>
          <button class="quiet name" :title="p.name" @click="attempt(() => pickProject(p.id))">{{ p.name }}</button>
          <button class="quiet mini" :aria-label="'在 ' + p.name + ' 新建会话'" :disabled="store.projectLoading" @click="attempt(() => newThread(p.id))">+</button>
          <button class="quiet del" :aria-label="'删除项目 ' + p.name" @click="attempt(() => removeProject(p.id, p.name))">×</button>
        </div>
        <ul v-if="expanded[p.id]" class="thread-tree" :aria-label="p.name + ' 的会话'">
          <li v-if="loadingProjects[p.id]" class="empty">加载会话…</li>
          <li v-for="t in store.threadsByProject[p.id] || []" :key="t.id" class="thread-row" :class="{ active: p.id === store.currentProjectId && t.id === store.currentThreadId }">
            <button class="quiet name" :title="t.title" :aria-current="p.id === store.currentProjectId && t.id === store.currentThreadId ? 'page' : undefined" @click="attempt(() => pickThread(p.id, t.id))">{{ t.title }}</button>
            <button class="quiet del" :aria-label="'删除会话 ' + t.title" @click="attempt(() => removeThread(p.id, t.id, t.title))">×</button>
          </li>
          <li v-if="!loadingProjects[p.id] && !store.threadsByProject[p.id]?.length" class="empty">暂无会话，点项目旁 + 新建</li>
        </ul>
        <div v-if="expanded[p.id]" class="docs-block">
          <div class="docs-head">
            <span>资料</span>
            <button class="quiet mini" :disabled="docsBusy[p.id]" :title="'上传资料到 ' + p.name" @click="pickFiles(p.id)">＋</button>
            <input :ref="el => uploaders[p.id] = el" hidden type="file" :accept="ACCEPT" multiple @change="e => onFiles(p.id, e)" />
          </div>
          <ul class="doc-tree">
            <li v-for="d in store.docsByProject[p.id] || []" :key="d.id" class="doc-row">
              <template v-if="renaming[d.id] !== undefined">
                <input class="doc-rename" v-model="renaming[d.id]" :aria-label="'重命名 ' + d.title" @keyup.enter="commitRename(p.id, d)" @keyup.esc="cancelRename(d)" @blur="commitRename(p.id, d)" />
              </template>
              <template v-else>
                <span class="doc-name" :title="d.title + '（' + d.chunk_count + ' 块）'" @dblclick="startRename(d)">▤ {{ d.title }}</span>
                <button class="quiet doc-act" :aria-label="'重命名 ' + d.title" @click="startRename(d)">✎</button>
                <button class="quiet del" :aria-label="'删除资料 ' + d.title" @click="removeDoc(p.id, d)">×</button>
              </template>
            </li>
            <li v-if="docsBusy[p.id]" class="empty">处理中…</li>
            <li v-else-if="!(store.docsByProject[p.id] || []).length" class="empty">暂无资料，点＋上传 PDF/Word/MD</li>
          </ul>
        </div>
      </li>
      <li v-if="!store.projects.length" class="empty">还没有项目，点 + 新建</li>
    </ul>

    <div class="footer">
      <RouterLink to="/config" class="settings-link"><span>⚙ 模型配置</span><small>{{ store.llm.model || '未配置' }}</small></RouterLink>
      <div class="workspace-label">个人工作空间 · 单知识库助手</div>
    </div>

    <NewProjectModal v-if="showNewProject" @created="onProjectCreated" @close="showNewProject = false" />
    <NewThreadModal v-if="showNewThread" @created="onThreadCreated" @close="showNewThread = false" />
  </aside>
</template>

<style scoped>
.sidebar { width: 264px; flex-shrink: 0; background: #f7f9f8; border-right: 1px solid var(--line); display: flex; flex-direction: column; padding: 24px 14px 14px; min-height: 0; overflow: auto; }
.brand { display: flex; align-items: center; gap: 10px; padding: 0 8px 27px; font-size: 21px; font-weight: 650; color: var(--ink); }.brand small { display: block; font-weight: 400; font-size: 10px; color: var(--muted); letter-spacing: 1px; margin-top: 3px; }.brand-mark { display: grid; place-items: center; width: 36px; height: 36px; border-radius: 11px; background: var(--accent); color: #fff; }.collapse { margin-left: auto; font-size: 21px; padding: 3px 8px; }
.primary-nav { display: grid; gap: 5px; margin-bottom: 22px; }.primary-nav a { display: flex; align-items: center; gap: 10px; text-decoration: none; color: var(--text); padding: 11px 13px; border-radius: 8px; font-size: 13px; }.primary-nav a span { font-size: 18px; width: 20px; }.primary-nav a:hover { background: #edf1ee; }.primary-nav .router-link-active { background: var(--accent-soft); color: var(--accent-d); font-weight: 650; }
.section-head { display: flex; align-items: center; justify-content: space-between; color: var(--faint); font-size: 11px; padding: 0 10px 10px; }.mini { background: transparent; color: var(--muted); width: 23px; height: 23px; border-radius: 6px; padding: 0; font-size: 17px; }.mini:hover { color: var(--accent); background: var(--accent-soft); }
.project-tree, .thread-tree { list-style: none; margin: 0; padding: 0; }.project-tree { padding-bottom: 20px; }.project-node { margin-bottom: 8px; }.project-row, .thread-row { display: flex; align-items: center; gap: 2px; border-radius: 7px; }.project-row.active { background: #edf1ee; }.thread-row.active { background: var(--accent-soft); }.thread-row.active .name { color: var(--accent-d); }.thread-tree { margin: 5px 0 10px 17px; padding-left: 9px; border-left: 1px solid var(--border); }.name { flex: 1; min-width: 0; text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding: 9px 5px; font-size: 12px; }.expander { padding: 5px 7px; }.del { padding: 5px; color: var(--muted); }.del:hover { color: #ad3737; }.empty { padding: 8px 6px; font-size: 11px; color: var(--faint); }.nav-error { color: #a83232; font-size: 12px; }
.docs-block { margin: 2px 0 12px 17px; padding-left: 9px; border-left: 1px solid var(--border); }
.docs-head { display: flex; align-items: center; gap: 4px; color: var(--faint); font-size: 10.5px; font-weight: 700; letter-spacing: .5px; padding: 4px 6px 2px; text-transform: uppercase; }
.docs-head span { flex: 1; }
.doc-tree { list-style: none; margin: 0; padding: 0; }
.doc-row { display: flex; align-items: center; gap: 2px; border-radius: 7px; }
.doc-row:hover { background: #eef2f0; }
.doc-name { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding: 7px 5px; font-size: 12px; color: var(--muted); cursor: default; }
.doc-act { padding: 5px; color: var(--faint); font-size: 12px; }
.doc-act:hover { color: var(--accent-d); }
.doc-rename { flex: 1; padding: 5px 7px; font-size: 12px; border: 1px solid var(--accent); border-radius: 6px; }
.footer { margin-top: auto; padding: 15px 5px 2px; border-top: 1px solid var(--line); }.settings-link { display: flex; align-items: center; justify-content: space-between; gap: 8px; color: var(--text); text-decoration: none; font-size: 12px; padding: 8px 3px; }.settings-link small { color: var(--faint); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 110px; font-size: 10px; }.workspace-label { font-size: 10px; color: var(--faint); padding: 12px 3px 2px; }
</style>
