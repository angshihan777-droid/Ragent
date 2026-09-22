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
  try { await store.loadProjectThreads(id); } finally { loadingProjects.value[id] = false; }
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
</script>

<template>
  <aside class="sidebar">
    <div class="brand"><span class="brand-mark">R</span><span>Ragent<small>知识工作台</small></span><button class="quiet collapse" aria-label="收起左栏" @click="$emit('collapse')">‹</button></div>

    <nav class="primary-nav" aria-label="工作台导航">
      <RouterLink to="/chat" @click="store.currentThreadId = null"><span>⊕</span> 新对话</RouterLink>
      <RouterLink to="/intro"><span>✦</span> 使用介绍</RouterLink>
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
.primary-nav { display: grid; gap: 5px; margin-bottom: 22px; }.primary-nav a { display: flex; align-items: center; gap: 10px; text-decoration: none; color: var(--text); padding: 11px 13px; border-radius: 8px; font-size: 13px; }.primary-nav a span { font-size: 18px; width: 20px; }.primary-nav a:hover { background: #edf1ee; }.primary-nav .router-link-active { background: var(--accent-soft); color: var(--accent-d); font-weight: 550; }
.section-head { display: flex; align-items: center; justify-content: space-between; color: var(--faint); font-size: 11px; padding: 0 10px 10px; }.mini { background: transparent; color: var(--muted); width: 23px; height: 23px; border-radius: 6px; padding: 0; font-size: 17px; }.mini:hover { color: var(--accent); background: var(--accent-soft); }
.project-tree, .thread-tree { list-style: none; margin: 0; padding: 0; }.project-tree { padding-bottom: 20px; }.project-node { margin-bottom: 8px; }.project-row, .thread-row { display: flex; align-items: center; gap: 2px; border-radius: 7px; }.project-row.active { background: #edf1ee; }.thread-row.active { background: var(--accent-soft); }.thread-row.active .name { color: var(--accent-d); }.thread-tree { margin: 5px 0 10px 17px; padding-left: 9px; border-left: 1px solid var(--border); }.name { flex: 1; min-width: 0; text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding: 9px 5px; font-size: 12px; }.expander { padding: 5px 7px; }.del { padding: 5px; color: var(--muted); }.del:hover { color: #ad3737; }.empty { padding: 8px 6px; font-size: 11px; color: var(--faint); }.nav-error { color: #a83232; font-size: 12px; }
.footer { margin-top: auto; padding: 15px 5px 2px; border-top: 1px solid var(--line); }.settings-link { display: flex; align-items: center; justify-content: space-between; gap: 8px; color: var(--text); text-decoration: none; font-size: 12px; padding: 8px 3px; }.settings-link small { color: var(--faint); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 110px; font-size: 10px; }.workspace-label { font-size: 10px; color: var(--faint); padding: 12px 3px 2px; }
</style>
