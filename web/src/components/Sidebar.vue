<script setup>
// 侧栏：顶部当前模型(可切换)，中部项目→会话导航，底部知识库/模型配置入口。
// 每个项目下挂多条会话；新建项目走弹窗(引导填名称+上传首批资料)。
import { ref } from "vue";
import { useRouter } from "vue-router";
import { store } from "../store.js";
import { api } from "../api.js";
import NewProjectModal from "./NewProjectModal.vue";
import NewThreadModal from "./NewThreadModal.vue";

const router = useRouter();
const showNewProject = ref(false);
const showNewThread = ref(false);
const switchingModel = ref(false);

async function pickProject(id) {
  await store.selectProject(id);
  router.push("/chat");
}
async function pickThread(id) {
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
async function removeThread(id, title) {
  if (!confirm('删除会话「' + title + '」？该会话的对话记录会一并删除，不可恢复。')) return;
  await store.deleteThread(id);
}
</script>

<template>
  <aside class="sidebar">
    <div class="brand">Ragent 知识库</div>

    <!-- 当前模型 + 切换：单 Agent 精简版，模型是最常调的运行期设置，常驻顶部 -->
    <div class="model-box">
      <div class="model-label">当前模型</div>
      <select class="model-select" :value="store.llm.model" :disabled="switchingModel || store.models.length === 0" @change="onModelChange">
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
    <ul class="list projects">
      <li
        v-for="p in store.projects"
        :key="p.id"
        :class="{ active: p.id === store.currentProjectId }"
        @click="pickProject(p.id)"
      >
        <span class="name">{{ p.name }}</span>
        <button class="del" title="删除项目" @click.stop="removeProject(p.id, p.name)">×</button>
      </li>
      <li v-if="store.projects.length === 0" class="empty">还没有项目，点 + 新建</li>
    </ul>

    <template v-if="store.currentProjectId">
      <div class="section-head">
        <span>会话</span>
        <button class="mini" title="新建会话" @click="showNewThread = true">+</button>
      </div>
      <ul class="list threads">
        <li
          v-for="t in store.threads"
          :key="t.id"
          :class="{ active: t.id === store.currentThreadId }"
          @click="pickThread(t.id)"
        >
          <span class="name">{{ t.title }}</span>
          <button class="del" title="删除会话" @click.stop="removeThread(t.id, t.title)">×</button>
        </li>
        <li v-if="store.threads.length === 0" class="empty">还没有会话，点 + 新建</li>
      </ul>
    </template>

    <div class="footer">
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
.brand { font-weight: 750; font-size: 17px; color: var(--ink); padding: 6px 8px 18px; letter-spacing: 0.01em; }
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
.list { list-style: none; margin: 0; padding: 0; }
.list li {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 10px; border-radius: 9px; cursor: pointer; font-size: 14px; color: var(--text);
}
.list li:hover { background: rgba(0,0,0,0.045); }
.list li.active { background: var(--panel2); color: var(--ink); font-weight: 600; }
.list .name { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tag { font-size: 11px; color: var(--muted); background: rgba(120,120,140,0.14); padding: 1px 7px; border-radius: 999px; }
.list li.active .tag { color: var(--ink); background: #fff; }
.del { background: transparent; border: none; color: #b5b2a8; font-size: 16px; padding: 0 2px; cursor: pointer; opacity: 0; transition: opacity 0.12s; box-shadow: none; }
.list li:hover .del { opacity: 1; }
.del:hover { color: var(--ink); background: transparent; box-shadow: none; }
.empty { color: var(--muted); font-size: 13px; cursor: default; }
.empty:hover { background: transparent; }
.footer { margin-top: auto; padding-top: 16px; display: flex; flex-direction: column; gap: 4px; border-top: 1px solid var(--line); }
.footer a {
  color: var(--text); text-decoration: none; font-size: 14px; padding: 9px 10px; border-radius: 9px;
}
.footer a:hover { background: rgba(0,0,0,0.045); }
.footer a.router-link-active { color: var(--ink); background: var(--panel2); font-weight: 600; }
</style>
