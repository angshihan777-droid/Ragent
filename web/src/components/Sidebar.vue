<script setup>
// 侧栏：工作台导航、项目→多会话树，底部模型配置入口。
// 每个项目下挂多条会话；新建项目走弹窗(引导填名称+上传首批资料)。
import { ref, watch } from "vue";
import { useRouter } from "vue-router";
import { store } from "../store.js";
import { api } from "../api.js";
import NewProjectModal from "./NewProjectModal.vue";
import NewThreadModal from "./NewThreadModal.vue";
import Icon from "./Icon.vue";

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
    <div class="brand">
      <span class="brand-mark">R</span>
      <span class="brand-text">Ragent<small>知识工作台</small></span>
      <button class="quiet collapse" aria-label="收起左栏" @click="$emit('collapse')"><Icon name="chevron-left" :size="18" /></button>
    </div>

    <nav class="primary-nav" aria-label="工作台导航">
      <RouterLink to="/chat" @click="store.currentThreadId = null"><Icon name="message-plus" /> 新对话</RouterLink>
      <RouterLink to="/documents"><Icon name="files" /> 项目资料</RouterLink>
      <RouterLink to="/library"><Icon name="library" /> 知识库图书馆</RouterLink>
      <a class="nav-link" href="https://angshihan777-droid.github.io/Ragent/" target="_blank" rel="noopener"><Icon name="book" /> 使用介绍</a>
    </nav>
    <div class="section-head">
      <span>项目</span>
      <button class="quiet mini" title="新建项目" aria-label="新建项目" @click="showNewProject = true"><Icon name="plus" :size="15" /></button>
    </div>
    <p v-if="error" class="nav-error" role="alert">{{ error }}</p>
    <ul class="project-tree" aria-label="项目与会话">
      <li v-for="p in store.projects" :key="p.id" class="project-node">
        <div class="project-row" :class="{ active: p.id === store.currentProjectId }">
          <button class="quiet expander" :aria-label="(expanded[p.id] ? '收起项目 ' : '展开项目 ') + p.name" :aria-expanded="!!expanded[p.id]" @click="attempt(() => toggleProject(p.id))">
            <Icon :name="expanded[p.id] ? 'chevron-down' : 'chevron-right'" :size="14" />
          </button>
          <button class="quiet name" :title="p.name" @click="attempt(() => pickProject(p.id))"><Icon name="folder" :size="14" /><span class="truncate">{{ p.name }}</span></button>
          <button class="quiet mini" :aria-label="'在 ' + p.name + ' 新建会话'" :disabled="store.projectLoading" @click="attempt(() => newThread(p.id))"><Icon name="plus" :size="14" /></button>
          <button class="quiet del" :aria-label="'删除项目 ' + p.name" @click="attempt(() => removeProject(p.id, p.name))"><Icon name="x" :size="14" /></button>
        </div>
        <ul v-if="expanded[p.id]" class="thread-tree" :aria-label="p.name + ' 的会话'">
          <li v-if="loadingProjects[p.id]" class="empty">加载会话…</li>
          <li v-for="t in store.threadsByProject[p.id] || []" :key="t.id" class="thread-row" :class="{ active: p.id === store.currentProjectId && t.id === store.currentThreadId }">
            <button class="quiet name" :title="t.title" :aria-current="p.id === store.currentProjectId && t.id === store.currentThreadId ? 'page' : undefined" @click="attempt(() => pickThread(p.id, t.id))"><span class="truncate">{{ t.title }}</span></button>
            <button class="quiet del" :aria-label="'删除会话 ' + t.title" @click="attempt(() => removeThread(p.id, t.id, t.title))"><Icon name="x" :size="13" /></button>
          </li>
          <li v-if="!loadingProjects[p.id] && !store.threadsByProject[p.id]?.length" class="empty">暂无会话，点项目旁 + 新建</li>
        </ul>
      </li>
      <li v-if="!store.projects.length" class="empty">还没有项目，点 + 新建</li>
    </ul>

    <div class="footer">
      <RouterLink to="/config" class="settings-link">
        <span class="sl-label"><Icon name="settings" :size="15" /> 模型配置</span>
        <small :class="{ unset: !store.llm.model }">{{ store.llm.model || '未配置' }}</small>
      </RouterLink>
      <div class="workspace-label">个人工作空间 · 单知识库助手</div>
    </div>

    <NewProjectModal v-if="showNewProject" @created="onProjectCreated" @close="showNewProject = false" />
    <NewThreadModal v-if="showNewThread" @created="onThreadCreated" @close="showNewThread = false" />
  </aside>
</template>

<style scoped>
.sidebar { width: 264px; flex-shrink: 0; background: var(--surface-2); border-right: 1px solid var(--border); display: flex; flex-direction: column; padding: var(--s-4) var(--s-3) var(--s-3); min-height: 0; overflow: auto; }

.brand { display: flex; align-items: center; gap: var(--s-3); padding: var(--s-2) var(--s-2) var(--s-5); }
.brand-text { font-size: var(--fs-body); font-weight: 600; color: var(--ink); line-height: 1.2; }
.brand-text small { display: block; font-weight: 400; font-size: var(--fs-xs); color: var(--muted); letter-spacing: 0.04em; margin-top: 2px; }
.brand-mark { display: grid; place-items: center; width: 32px; height: 32px; border-radius: var(--r-md); background: var(--brand); color: #fff; font-size: var(--fs-body); font-weight: 600; flex-shrink: 0; }
.collapse { margin-left: auto; padding: var(--s-1); }

.primary-nav { display: grid; gap: 2px; margin-bottom: var(--s-5); }
.primary-nav a { display: flex; align-items: center; gap: var(--s-3); text-decoration: none; color: var(--text); padding: var(--s-2) var(--s-3); border-radius: var(--r-md); font-size: var(--fs-sm); transition: background var(--ease), color var(--ease); }
.primary-nav a:hover { background: var(--surface-3); color: var(--ink); }
.primary-nav .router-link-active { background: var(--brand-soft); color: var(--brand-ink); font-weight: 500; }

.section-head { display: flex; align-items: center; justify-content: space-between; color: var(--faint); font-size: var(--fs-xs); font-weight: 500; letter-spacing: 0.04em; padding: 0 var(--s-2) var(--s-2); }
.mini { width: 24px; height: 24px; border-radius: var(--r-sm); padding: 0; }
.mini:hover:not(:disabled) { color: var(--brand-ink); background: var(--brand-soft); }

.project-tree, .thread-tree { list-style: none; margin: 0; padding: 0; }
.project-tree { padding-bottom: var(--s-4); }
.project-node { margin-bottom: 2px; }
.project-row, .thread-row { display: flex; align-items: center; gap: 1px; border-radius: var(--r-md); }
.project-row:hover, .thread-row:hover { background: var(--surface-3); }
.project-row.active { background: var(--surface-3); }
.thread-row.active { background: var(--brand-soft); }
.thread-row.active .name { color: var(--brand-ink); font-weight: 500; }
.thread-tree { margin: 2px 0 var(--s-2) var(--s-4); padding-left: var(--s-2); border-left: 1px solid var(--border); }
.name { flex: 1; min-width: 0; justify-content: flex-start; gap: var(--s-2); text-align: left; padding: 7px var(--s-2); font-size: var(--fs-sm); }
.expander { padding: var(--s-1); }
.del { padding: var(--s-1); opacity: 0; transition: opacity var(--ease), color var(--ease); }
.project-row:hover .del, .thread-row:hover .del, .del:focus-visible { opacity: 1; }
.del:hover:not(:disabled) { color: var(--danger); background: var(--danger-soft); }
.empty { padding: var(--s-2); font-size: var(--fs-xs); color: var(--faint); line-height: 1.6; }
.nav-error { color: var(--danger); font-size: var(--fs-xs); padding: 0 var(--s-2) var(--s-2); margin: 0; }

.footer { margin-top: auto; padding-top: var(--s-3); border-top: 1px solid var(--border); }
.settings-link { display: flex; align-items: center; justify-content: space-between; gap: var(--s-2); color: var(--text); text-decoration: none; font-size: var(--fs-sm); padding: var(--s-2); border-radius: var(--r-md); transition: background var(--ease); }
.settings-link:hover { background: var(--surface-3); }
.sl-label { display: inline-flex; align-items: center; gap: var(--s-2); }
.settings-link small { color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 96px; font-size: var(--fs-xs); }
.settings-link small.unset { color: var(--danger); }
.workspace-label { font-size: var(--fs-xs); color: var(--faint); padding: var(--s-2) var(--s-2) 0; }
</style>
