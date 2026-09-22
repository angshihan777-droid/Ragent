<script setup>
// 侧栏：顶部当前模型(可切换)，中部项目→会话导航，底部知识库/模型配置入口。
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
const switchingModel = ref(false);

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
async function onModelChange(e) {
  // 左栏直接切模型：保存后 worker 下次执行即生效（配置以库为准）
  switchingModel.value = true;
  try { await store.switchModel(e.target.value); }
  finally { switchingModel.value = false; }
}
async function onProjectCreated(projectId) {
  showNewProject.value = false;
  await store.loadProjects();
  await store.selectProject(projectId);
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
    <div class="brand">Ragent 知识库<button class="quiet collapse" aria-label="收起左栏" @click="$emit('collapse')">‹</button></div>

    <!-- 当前模型 + 切换：单 Agent 精简版，模型是最常调的运行期设置，常驻顶部 -->
    <div class="model-box">
      <div class="model-label">当前模型</div>
      <select class="model-select" :value="store.llm.model" :disabled="switchingModel || store.models.length === 0" @change="attempt(() => onModelChange($event))">
        <option v-if="!store.llm.model" value="">未配置</option>
        <option v-for="m in store.models" :key="m" :value="m">{{ m }}</option>
      </select>
      <div class="model-hint" :class="{ warn: !store.llm.key_set }">
        {{ store.llm.key_set ? '密钥已配置' : '未配置密钥，去「模型配置」填写' }}
      </div>
    </div>

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
      <RouterLink to="/chat">← 返回对话</RouterLink>
      <RouterLink to="/documents">当前项目资料</RouterLink>
      <RouterLink to="/library">知识库图书馆</RouterLink>
      <RouterLink to="/config">模型配置</RouterLink>
    </div>

    <NewProjectModal v-if="showNewProject" @created="onProjectCreated" @close="showNewProject = false" />
    <NewThreadModal v-if="showNewThread" @created="onThreadCreated" @close="showNewThread = false" />
  </aside>
</template>

<style scoped>
.sidebar {
  width: 264px;
  flex-shrink: 0;
  background: var(--panel);
  border-right: 1px solid var(--border);
  color: var(--text);
  display: flex;
  flex-direction: column;
  padding: 16px 12px;
  overflow-y: auto;
}
.brand { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-weight: 750; font-size: 17px; color: var(--ink); padding: 6px 8px 18px; letter-spacing: 0.01em; }
.model-box { padding: 10px 10px 14px; margin: 0 2px 6px; border: 1px solid var(--border); border-radius: 12px; background: var(--panel2); }
.model-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.07em; color: var(--muted); margin-bottom: 6px; }
.model-select { padding: 7px 9px; font-size: 13px; border-radius: 8px; }
.model-hint { font-size: 11px; color: var(--muted); margin-top: 6px; }
.model-hint.warn { color: #b7791f; }
.section-head {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.07em;
  color: var(--muted); padding: 14px 8px 6px;
}
.mini {
  background: transparent; color: var(--muted); border: 1px solid var(--border);
  width: 22px; height: 22px; border-radius: 7px; line-height: 1; padding: 0; font-size: 15px;
}
.mini:hover { color: var(--ink); border-color: var(--muted); background: transparent; }
.footer { margin-top: auto; padding-top: 16px; display: flex; flex-direction: column; gap: 4px; border-top: 1px solid var(--line); }
.footer a {
  color: var(--text); text-decoration: none; font-size: 14px; padding: 9px 10px; border-radius: 9px;
}
.footer a:hover { background: rgba(0,0,0,0.045); }
.footer a.router-link-active { color: var(--ink); background: var(--panel2); font-weight: 600; }

.project-tree, .thread-tree { list-style: none; margin: 0; padding: 0; }
.project-tree { padding-bottom: 20px; }
.project-node { margin-bottom: 8px; }
.project-row, .thread-row { display: flex; align-items: center; gap: 3px; border-radius: 8px; }
.project-row.active { background: var(--panel2); }
.thread-row.active { background: var(--accent-soft); }
.thread-row.active .name { color: var(--accent-d); font-weight: 600; }
.thread-tree { margin: 5px 0 10px 16px; padding-left: 10px; border-left: 1px solid var(--border); }
.name { flex: 1; min-width: 0; text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding: 9px 5px; font-size: 13px; }
.expander, .collapse { padding: 5px 8px; }
.project-tree .del { opacity: 1; padding: 5px; color: var(--muted); }
.empty { padding: 8px 6px; font-size: 12px; }
.nav-error { color: #a83232; font-size: 12px; }
</style>
